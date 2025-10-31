import asyncio
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from redis import Redis
from rq import Queue
import uvicorn
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import Update
from telegram.error import RetryAfter, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings, load_settings
from .dashboard import create_dashboard_app
from .database import build_engine, build_session_factory, init_models, session_scope
from .jobs.deletion import cleanup_expired_group_messages
from .models import Agent, GroupMessage, GroupPrivacyMode, GroupSetting, PendingAction, Submission, WeeklyStat
from .services.leaderboard import get_leaderboard

logger = logging.getLogger(__name__)

CODENAME, FACTION = range(2)


def parse_submission(payload: str) -> tuple[int, dict[str, Any]]:
    parts = [segment.strip() for segment in re.split(r"[;\n]+|\s{2,}", payload) if segment.strip()]
    data: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            raise ValueError("Entries must be provided as key=value pairs")
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key or not value:
            raise ValueError("Invalid entry")
        data[key] = value
    if "ap" not in data:
        raise ValueError("Missing ap value")
    try:
        ap = int(data.pop("ap"))
    except ValueError as exc:
        raise ValueError("ap must be an integer") from exc
    metrics: dict[str, Any] = {}
    for key, value in data.items():
        try:
            metrics[key] = int(value)
            continue
        except ValueError:
            pass
        try:
            metrics[key] = float(value)
            continue
        except ValueError:
            pass
        metrics[key] = value
    return ap, metrics


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text("Welcome to the Ingress leaderboard bot. Use /register to begin.")


async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
    if agent:
        await update.message.reply_text(f"You are already registered as {agent.codename} ({agent.faction}).")
        return ConversationHandler.END
    await update.message.reply_text("Please send your agent codename.")
    return CODENAME


async def register_codename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return ConversationHandler.END
    codename = update.message.text.strip()
    if not codename:
        await update.message.reply_text("Codename cannot be empty. Send your codename.")
        return CODENAME
    context.user_data["codename"] = codename
    await update.message.reply_text("Send your faction (ENL or RES).")
    return FACTION


async def register_faction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    faction = update.message.text.strip().upper()
    if faction not in {"ENL", "RES"}:
        await update.message.reply_text("Faction must be ENL or RES. Send your faction.")
        return FACTION
    codename = context.user_data.get("codename")
    if not codename:
        await update.message.reply_text("Codename missing. Restart with /register.")
        return ConversationHandler.END
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
        if agent:
            agent.codename = codename
            agent.faction = faction
        else:
            session.add(Agent(telegram_id=update.effective_user.id, codename=codename, faction=faction))
    await update.message.reply_text(f"Registered {codename} ({faction}).")
    context.user_data.clear()
    return ConversationHandler.END


async def register_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("Registration cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


async def _get_or_create_group_setting(
    session: AsyncSession,
    chat_id: int,
    default_retention_minutes: int,
) -> GroupSetting:
    result = await session.execute(select(GroupSetting).where(GroupSetting.chat_id == chat_id))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = GroupSetting(
            chat_id=chat_id,
            privacy_mode=GroupPrivacyMode.public.value,
            retention_minutes=max(default_retention_minutes, 0),
        )
        session.add(setting)
        await session.flush()
    return setting


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings: Settings = context.application.bot_data["settings"]
    text = update.message.text or ""
    _, _, payload = text.partition(" ")
    payload = payload.strip()
    if not payload:
        await update.message.reply_text("Usage: /submit ap=12345; metric=678")
        return
    try:
        ap, metrics = parse_submission(payload)
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return
    chat = getattr(update, "effective_chat", None)
    is_group_chat = bool(chat and getattr(chat, "type", None) in {"group", "supergroup"})
    chat_id_value = chat.id if is_group_chat else None
    session_factory = context.application.bot_data["session_factory"]
    agent = None
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
        if not agent:
            await update.message.reply_text("Register first with /register.")
            return
        
        # Check if the user already has a submission for this chat
        result = await session.execute(
            select(Submission)
            .where(Submission.agent_id == agent.id)
            .where(Submission.chat_id == chat_id_value)
            .order_by(Submission.submitted_at.desc())
            .limit(1)
        )
        existing_submission = result.scalar_one_or_none()
        
        if existing_submission:
            # Update the existing submission
            existing_submission.ap = ap
            existing_submission.metrics = metrics
            existing_submission.submitted_at = datetime.utcnow()
            submission = existing_submission
        else:
            # Create a new submission
            submission = Submission(agent_id=agent.id, chat_id=chat_id_value, ap=ap, metrics=metrics)
            session.add(submission)
        if is_group_chat:
            setting = await _get_or_create_group_setting(
                session,
                chat.id,
                settings.group_message_retention_minutes,
            )
            # Store the messages for later deletion by the scheduled job
            if setting.privacy_mode != GroupPrivacyMode.public.value:
                reply = await update.message.reply_text(f"Recorded {ap} AP for {agent.codename}.")
                original_message_id = getattr(update.message, "message_id", None)
                confirmation_message_id = getattr(reply, "message_id", None)
                
                if original_message_id is not None:
                    session.add(
                        GroupMessage(
                            chat_id=chat.id,
                            message_id=original_message_id,
                            received_at=update.message.date or datetime.now(timezone.utc),
                        )
                    )
                
                if confirmation_message_id is not None and setting.privacy_mode == GroupPrivacyMode.soft.value:
                    session.add(
                        GroupMessage(
                            chat_id=chat.id,
                            message_id=confirmation_message_id,
                            received_at=datetime.now(timezone.utc),
                        )
                    )
            else:
                await update.message.reply_text(f"Recorded {ap} AP for {agent.codename}.")
        else:
            await update.message.reply_text(f"Recorded {ap} AP for {agent.codename}.")


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    settings: Settings = context.application.bot_data["settings"]
    session_factory = context.application.bot_data["session_factory"]
    chat = getattr(update, "effective_chat", None)
    is_group_chat = bool(chat and getattr(chat, "type", None) in {"group", "supergroup"})
    chat_id_value = chat.id if is_group_chat else None
    privacy_mode = GroupPrivacyMode.public
    async with session_scope(session_factory) as session:
        if is_group_chat:
            setting = await _get_or_create_group_setting(
                session,
                chat.id,
                settings.group_message_retention_minutes,
            )
            privacy_mode = GroupPrivacyMode(setting.privacy_mode)
        rows = await get_leaderboard(session, settings.leaderboard_size, chat_id_value)
    if not rows:
        await update.message.reply_text("No submissions yet.")
        return
    lines = [f"{index}. {codename} [{faction}] — {total_ap:,} AP" for index, (codename, faction, total_ap) in enumerate(rows, start=1)]
    reply = await update.message.reply_text("\n".join(lines))
    
    # In strict mode, store messages for immediate deletion and clear submissions
    if is_group_chat and privacy_mode is GroupPrivacyMode.strict:
        confirmation_message_id = getattr(reply, "message_id", None)
        original_message_id = getattr(update.message, "message_id", None)
        
        async with session_scope(session_factory) as session:
            # Store messages for deletion
            if original_message_id is not None:
                session.add(
                    GroupMessage(
                        chat_id=chat.id,
                        message_id=original_message_id,
                        received_at=update.message.date or datetime.now(timezone.utc),
                    )
                )
            
            if confirmation_message_id is not None:
                session.add(
                    GroupMessage(
                        chat_id=chat.id,
                        message_id=confirmation_message_id,
                        received_at=datetime.now(timezone.utc),
                    )
                )
            
            # Clear submissions and other data for this group
            await session.execute(delete(Submission).where(Submission.chat_id == chat_id_value))
            await session.execute(delete(GroupMessage).where(GroupMessage.chat_id == chat_id_value))
            await session.execute(delete(PendingAction).where(PendingAction.chat_id == chat_id_value))


async def myrank_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    session_factory = context.application.bot_data["session_factory"]
    chat = getattr(update, "effective_chat", None)
    is_group_chat = bool(chat and getattr(chat, "type", None) in {"group", "supergroup"})
    chat_id_value = chat.id if is_group_chat else None
    
    # Get the agent
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
        
        if not agent:
            await update.message.reply_text("Register first with /register.")
            return
        
        # Get the agent's total AP
        agent_ap_result = await session.execute(
            select(func.sum(Submission.ap))
            .where(Submission.agent_id == agent.id)
            .where(Submission.chat_id == chat_id_value if is_group_chat else True)
        )
        agent_ap = agent_ap_result.scalar() or 0
        
        # Get all agents ranked by AP (for the same chat_id if in group)
        stmt = (
            select(Agent.id, Agent.codename, Agent.faction, func.sum(Submission.ap).label("total_ap"))
            .join(Submission, Submission.agent_id == Agent.id)
        )
        if is_group_chat:
            stmt = stmt.where(Submission.chat_id == chat_id_value)
        stmt = stmt.group_by(Agent.id).order_by(func.sum(Submission.ap).desc())
        
        result = await session.execute(stmt)
        all_agents = result.all()
        
        # Find the user's rank
        rank = None
        for i, (agent_id, codename, faction, total_ap) in enumerate(all_agents, start=1):
            if agent_id == agent.id:
                rank = i
                break
        
        if rank is None:
            await update.message.reply_text("You don't have any submissions yet.")
            return
        
        # Format the response
        context_text = "in this group" if is_group_chat else "globally"
        response = f"Your rank {context_text} is #{rank}\n"
        response += f"{agent.codename} [{agent.faction}] — {int(agent_ap):,} AP"
        
        await update.message.reply_text(response)


async def store_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or message.chat_id is None:
        return
    timestamp = message.date or datetime.now(timezone.utc)
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        setting = await _get_or_create_group_setting(session, message.chat_id)
        mode = GroupPrivacyMode(setting.privacy_mode)
        if mode is GroupPrivacyMode.public:
            return
        exists = await session.execute(
            select(GroupMessage.id).where(
                GroupMessage.chat_id == message.chat_id,
                GroupMessage.message_id == message.message_id,
            )
        )
        if exists.scalar_one_or_none() is not None:
            return
        session.add(
            GroupMessage(
                chat_id=message.chat_id,
                message_id=message.message_id,
                received_at=timestamp,
            )
        )


async def set_group_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    chat = getattr(update, "effective_chat", None)
    if not chat or getattr(chat, "type", None) not in {"group", "supergroup"}:
        await update.message.reply_text("This command can only be used in groups.")
        return
    args = getattr(context, "args", [])
    if not args:
        await update.message.reply_text("Usage: /privacy <public|soft|strict>.")
        return
    value = args[0].lower()
    try:
        mode = GroupPrivacyMode(value)
    except ValueError:
        options = ", ".join(sorted(mode_option.value for mode_option in GroupPrivacyMode))
        await update.message.reply_text(f"Invalid mode. Choose from {options}.")
        return
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        setting = await _get_or_create_group_setting(session, chat.id)
        setting.privacy_mode = mode.value
    await update.message.reply_text(f"Privacy mode set to {mode.value}.")




async def announce_weekly_winners(application: Application, session_factory: async_sessionmaker, week_start: datetime, week_end: datetime) -> None:
    """Announce the weekly winners in all active group chats."""
    logger.info(f"Starting weekly winners announcement for week {week_start} to {week_end}")
    
    try:
        # Enhanced database connection error handling
        try:
            async with session_scope(session_factory) as session:
                logger.debug("Database connection established for weekly winners announcement")
                
                # Get top performers for each faction from WeeklyStat
                try:
                    result = await session.execute(
                        select(
                            WeeklyStat.agent_id,
                            WeeklyStat.value,
                            WeeklyStat.faction,
                            Agent.codename,
                        )
                        .join(Agent, Agent.id == WeeklyStat.agent_id)
                        .where(WeeklyStat.week_start == week_start)
                        .where(WeeklyStat.week_end == week_end)
                        .where(WeeklyStat.category == "ap")
                        .order_by(WeeklyStat.value.desc())
                    )
                    logger.debug("Successfully retrieved weekly stats from database")
                except Exception as db_error:
                    logger.error(f"Database error while fetching weekly stats: {db_error}")
                    raise
                
                # Separate by faction with validation
                enl_agents = []
                res_agents = []
                
                for agent_id, value, faction, codename in result.all():
                    # Validate WeeklyStat data
                    if not agent_id or not faction or not codename:
                        logger.warning(f"Invalid WeeklyStat data: agent_id={agent_id}, faction={faction}, codename={codename}")
                        continue
                    
                    if value is None or value <= 0:
                        logger.warning(f"Invalid AP value for agent {codename}: {value}")
                        continue
                    
                    if faction == "ENL":
                        enl_agents.append((codename, value))
                        logger.debug(f"Added ENL agent: {codename} with {value} AP")
                    elif faction == "RES":
                        res_agents.append((codename, value))
                        logger.debug(f"Added RES agent: {codename} with {value} AP")
                    else:
                        logger.warning(f"Unknown faction {faction} for agent {codename}")
                
                logger.info(f"Found {len(enl_agents)} ENL agents and {len(res_agents)} RES agents")
                
                # Get all active group chats
                try:
                    group_settings_result = await session.execute(select(GroupSetting))
                    group_settings = group_settings_result.scalars().all()
                    logger.debug(f"Retrieved {len(group_settings)} group settings")
                except Exception as db_error:
                    logger.error(f"Database error while fetching group settings: {db_error}")
                    raise
                
                if not group_settings:
                    logger.info("No group chats found for announcing weekly winners")
                    return
                
                # Format the announcement message
                announcement = "🏆 *Weekly Competition Results* 🏆\n\n"
                
                # Add ENL winners
                if enl_agents:
                    announcement += "*🟢 Enlightened (ENL) Top Performers:*\n"
                    for i, (codename, ap) in enumerate(enl_agents[:3], start=1):
                        announcement += f"{i}. {codename} - {ap:,} AP\n"
                    announcement += "\n"
                else:
                    announcement += "*🟢 Enlightened (ENL):* No submissions this week\n\n"
                
                # Add RES winners
                if res_agents:
                    announcement += "*🔵 Resistance (RES) Top Performers:*\n"
                    for i, (codename, ap) in enumerate(res_agents[:3], start=1):
                        announcement += f"{i}. {codename} - {ap:,} AP\n"
                    announcement += "\n"
                else:
                    announcement += "*🔵 Resistance (RES):* No submissions this week\n\n"
                
                # Add footer
                announcement += "Scores have been reset for the new week. Good luck! 🍀"
                
                # Send announcement to all group chats with enhanced error handling
                successful_sends = 0
                failed_sends = 0
                
                for setting in group_settings:
                    try:
                        # Verify if the group chat is active before sending
                        try:
                            chat = await application.bot.get_chat(setting.chat_id)
                            if chat.type not in ["group", "supergroup"]:
                                logger.warning(f"Chat {setting.chat_id} is not a group/supergroup, skipping")
                                continue
                            
                            logger.debug(f"Sending announcement to group {setting.chat_id}")
                            await application.bot.send_message(
                                chat_id=setting.chat_id,
                                text=announcement,
                                parse_mode="Markdown"
                            )
                            successful_sends += 1
                            logger.info(f"Sent weekly winners announcement to group {setting.chat_id}")
                        except RetryAfter as e:
                            logger.warning(f"Rate limit hit for group {setting.chat_id}, retry after {e.retry_after} seconds")
                            await asyncio.sleep(e.retry_after)
                            # Retry once after waiting
                            try:
                                await application.bot.send_message(
                                    chat_id=setting.chat_id,
                                    text=announcement,
                                    parse_mode="Markdown"
                                )
                                successful_sends += 1
                                logger.info(f"Successfully sent weekly winners announcement to group {setting.chat_id} after retry")
                            except TelegramError as retry_error:
                                failed_sends += 1
                                logger.error(f"Failed to send weekly winners announcement to group {setting.chat_id} after retry: {retry_error}")
                        except Forbidden as e:
                            failed_sends += 1
                            logger.error(f"Forbidden error for group {setting.chat_id}: {e}. Bot may have been blocked or removed from the group.")
                        except TelegramError as e:
                            failed_sends += 1
                            logger.error(f"Failed to send weekly winners announcement to group {setting.chat_id}: {e}")
                    except Exception as e:
                        failed_sends += 1
                        logger.error(f"Unexpected error sending to group {setting.chat_id}: {e}")
                
                logger.info(f"Weekly winners announcement completed: {successful_sends} successful, {failed_sends} failed")
        except Exception as db_error:
            logger.error(f"Database connection error in announce_weekly_winners: {db_error}")
            raise
                    
    except Exception as e:
        logger.error(f"Error in announce_weekly_winners: {e}", exc_info=True)


async def reset_weekly_scores(application: Application, session_factory: async_sessionmaker) -> None:
    """Reset weekly scores and store them in WeeklyStat table."""
    logger.info("Starting weekly score reset process")
    
    # Improved timezone handling - ensure we're using UTC consistently
    now = datetime.now(timezone.utc)
    week_end = now
    week_start = week_end - timedelta(days=7)
    
    logger.info(f"Processing weekly stats for period {week_start} to {week_end}")
    
    try:
        # Use a transaction to prevent race conditions during score reset
        async with session_scope(session_factory) as session:
            logger.debug("Database connection established for weekly score reset")
            
            try:
                # Get all submissions grouped by agent and faction
                result = await session.execute(
                    select(Submission.agent_id, func.sum(Submission.ap), Agent.faction)
                    .join(Agent, Agent.id == Submission.agent_id)
                    .group_by(Submission.agent_id, Agent.faction)
                )
                logger.debug("Successfully retrieved submission data for weekly stats")
                
                # Process each agent's weekly stats
                stats_created = 0
                for agent_id, total_ap, faction in result.all():
                    # Validate data before processing
                    if not agent_id or not faction:
                        logger.warning(f"Invalid data: agent_id={agent_id}, faction={faction}")
                        continue
                    
                    total_value = int(total_ap or 0)
                    if total_value <= 0:
                        logger.debug(f"Skipping agent {agent_id} with non-positive AP: {total_value}")
                        continue
                    
                    # Create WeeklyStat record
                    try:
                        session.add(
                            WeeklyStat(
                                agent_id=agent_id,
                                category="ap",
                                faction=faction,
                                value=total_value,
                                week_start=week_start,
                                week_end=week_end,
                            )
                        )
                        stats_created += 1
                        logger.debug(f"Created weekly stat for agent {agent_id}: {total_value} AP")
                    except Exception as e:
                        logger.error(f"Error creating weekly stat for agent {agent_id}: {e}")
                
                logger.info(f"Created {stats_created} weekly stat records")
                
                # Delete all submissions - this is done after creating stats to prevent data loss
                try:
                    delete_result = await session.execute(delete(Submission))
                    deleted_count = delete_result.rowcount
                    logger.info(f"Deleted {deleted_count} submission records")
                except Exception as e:
                    logger.error(f"Error deleting submissions: {e}")
                    raise
                
                # Commit the transaction
                await session.commit()
                logger.info("Weekly score reset transaction completed successfully")
                
            except Exception as db_error:
                logger.error(f"Database error during weekly score reset: {db_error}")
                await session.rollback()
                raise
        
        # Announce weekly winners after reset is complete and transaction is committed
        logger.info("Starting weekly winners announcement")
        await announce_weekly_winners(application, session_factory, week_start, week_end)
        logger.info("Weekly score reset process completed successfully")
        
    except Exception as e:
        logger.error(f"Error in reset_weekly_scores: {e}", exc_info=True)
        raise


def configure_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    register_handler = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            CODENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_codename)],
            FACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_faction)],
        },
        fallbacks=[CommandHandler("cancel", register_cancel)],
    )
    application.add_handler(register_handler)
    application.add_handler(CommandHandler("submit", submit))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("myrank", myrank_command))
    application.add_handler(CommandHandler("privacy", set_group_privacy))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, store_group_message))


async def run() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    await init_models(engine)
    redis_conn = Redis.from_url(settings.redis_url)
    queue = Queue(connection=redis_conn)
    dashboard_server: uvicorn.Server | None = None
    dashboard_task: asyncio.Task | None = None
    if settings.dashboard_enabled:
        dashboard_app = create_dashboard_app(settings, session_factory)
        config = uvicorn.Config(
            dashboard_app,
            host=settings.dashboard_host,
            port=settings.dashboard_port,
            log_level="info",
            loop="asyncio",
        )
        dashboard_server = uvicorn.Server(config)
        dashboard_task = asyncio.create_task(dashboard_server.serve())
    application = ApplicationBuilder().token(settings.telegram_token).build()
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    application.bot_data["settings"] = settings
    application.bot_data["engine"] = engine
    application.bot_data["session_factory"] = session_factory
    application.bot_data["queue"] = queue
    application.bot_data["redis_connection"] = redis_conn
    application.bot_data["scheduler"] = scheduler
    configure_handlers(application)
    scheduler.add_job(
        cleanup_expired_group_messages,
        trigger="interval",
        minutes=10,
        args=(application, session_factory),
        max_instances=1,
        misfire_grace_time=60,
        coalesce=True,
    )
    scheduler.add_job(
        reset_weekly_scores,
        trigger="cron",
        day_of_week="sat",
        hour=0,
        minute=0,
        args=(application, session_factory),
        max_instances=1,
        misfire_grace_time=300,
        coalesce=True,
    )
    scheduler.start()
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    try:
        await application.updater.idle()
    finally:
        if dashboard_server is not None:
            dashboard_server.should_exit = True
        scheduler.shutdown(wait=False)
        await application.stop()
        await application.shutdown()
        if dashboard_task is not None:
            await dashboard_task
        await engine.dispose()
        redis_conn.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
