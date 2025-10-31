import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from redis import Redis
from rq import Queue
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
from .database import build_engine, build_session_factory, init_models, session_scope
from .jobs import schedule_message_deletion
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


async def _get_or_create_group_setting(session: AsyncSession, chat_id: int) -> GroupSetting:
    result = await session.execute(select(GroupSetting).where(GroupSetting.chat_id == chat_id))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = GroupSetting(chat_id=chat_id, privacy_mode=GroupPrivacyMode.public.value)
        session.add(setting)
        await session.flush()
    return setting


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings: Settings = context.application.bot_data["settings"]
    queue: Queue | None = context.application.bot_data.get("queue")
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
    privacy_mode = GroupPrivacyMode.public
    agent = None
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
        if not agent:
            await update.message.reply_text("Register first with /register.")
            return
        submission = Submission(agent_id=agent.id, chat_id=chat_id_value, ap=ap, metrics=metrics)
        session.add(submission)
        if is_group_chat:
            setting = await _get_or_create_group_setting(session, chat.id)
            privacy_mode = GroupPrivacyMode(setting.privacy_mode)
    reply = await update.message.reply_text(f"Recorded {ap} AP for {agent.codename}.")
    confirmation_message_id = getattr(reply, "message_id", None)
    original_message_id = getattr(update.message, "message_id", None)
    if is_group_chat and queue and chat_id_value is not None and original_message_id is not None:
        if privacy_mode is GroupPrivacyMode.public:
            schedule_message_deletion(
                queue,
                settings.telegram_token,
                chat_id_value,
                original_message_id,
                confirmation_message_id,
                settings.autodelete_delay_seconds,
            )
        elif privacy_mode is GroupPrivacyMode.soft:
            schedule_message_deletion(
                queue,
                settings.telegram_token,
                chat_id_value,
                original_message_id,
                confirmation_message_id,
                settings.autodelete_delay_seconds,
            )
            schedule_message_deletion(
                queue,
                settings.telegram_token,
                chat_id_value,
                confirmation_message_id,
                None,
                settings.autodelete_delay_seconds,
            )
        elif privacy_mode is GroupPrivacyMode.strict:
            schedule_message_deletion(
                queue,
                settings.telegram_token,
                chat_id_value,
                original_message_id,
                confirmation_message_id,
                0,
            )
    elif not is_group_chat and queue and settings.autodelete_enabled and original_message_id is not None:
        direct_chat_id = getattr(chat, "id", None) or getattr(update.message, "chat_id", None)
        if direct_chat_id is not None:
            schedule_message_deletion(
                queue,
                settings.telegram_token,
                direct_chat_id,
                original_message_id,
                confirmation_message_id,
                settings.autodelete_delay_seconds,
            )


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    settings: Settings = context.application.bot_data["settings"]
    queue: Queue | None = context.application.bot_data.get("queue")
    session_factory = context.application.bot_data["session_factory"]
    chat = getattr(update, "effective_chat", None)
    is_group_chat = bool(chat and getattr(chat, "type", None) in {"group", "supergroup"})
    chat_id_value = chat.id if is_group_chat else None
    privacy_mode = GroupPrivacyMode.public
    async with session_scope(session_factory) as session:
        if is_group_chat:
            setting = await _get_or_create_group_setting(session, chat.id)
            privacy_mode = GroupPrivacyMode(setting.privacy_mode)
        rows = await get_leaderboard(session, settings.leaderboard_size, chat_id_value)
    if not rows:
        await update.message.reply_text("No submissions yet.")
        return
    lines = [f"{index}. {codename} [{faction}] — {total_ap:,} AP" for index, (codename, faction, total_ap) in enumerate(rows, start=1)]
    reply = await update.message.reply_text("\n".join(lines))
    if is_group_chat and privacy_mode is GroupPrivacyMode.strict:
        confirmation_message_id = getattr(reply, "message_id", None)
        original_message_id = getattr(update.message, "message_id", None)
        if queue and chat_id_value is not None and original_message_id is not None:
            schedule_message_deletion(
                queue,
                settings.telegram_token,
                chat_id_value,
                original_message_id,
                confirmation_message_id,
                0,
            )
        async with session_scope(session_factory) as session:
            await session.execute(delete(Submission).where(Submission.chat_id == chat_id_value))
            await session.execute(delete(GroupMessage).where(GroupMessage.chat_id == chat_id_value))
            await session.execute(delete(PendingAction).where(PendingAction.chat_id == chat_id_value))


async def store_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or message.chat_id is None:
        return
    timestamp = message.date or datetime.now(timezone.utc)
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        setting = await _get_or_create_group_setting(session, message.chat_id)
        mode = GroupPrivacyMode(setting.privacy_mode)
        if mode in {GroupPrivacyMode.public, GroupPrivacyMode.soft}:
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


async def _execute_pending_deletions(application: Application, session_factory: async_sessionmaker) -> None:
    async with session_scope(session_factory) as session:
        result = await session.execute(select(PendingAction).where(PendingAction.executed.is_(False)))
        pending = result.scalars().all()
        if not pending:
            return
        for action in pending:
            if action.action != "delete_message" or action.message_id is None:
                continue
            try:
                await application.bot.delete_message(chat_id=action.chat_id, message_id=action.message_id)
            except RetryAfter as exc:
                delay = max(int(exc.retry_after), 1)
                await asyncio.sleep(delay)
                await application.bot.delete_message(chat_id=action.chat_id, message_id=action.message_id)
            except TelegramError:
                continue
            action.executed = True
        await session.flush()


async def cleanup_expired_group_messages(
    application: Application,
    session_factory: async_sessionmaker,
    retention_minutes: int,
) -> None:
    await _execute_pending_deletions(application, session_factory)
    threshold = datetime.now(timezone.utc) - timedelta(minutes=retention_minutes)
    async with session_scope(session_factory) as session:
        settings_rows = await session.execute(select(GroupSetting))
        group_settings = {row.chat_id: GroupPrivacyMode(row.privacy_mode) for row in settings_rows.scalars()}
        while True:
            result = await session.execute(
                select(GroupMessage)
                .where(GroupMessage.received_at < threshold)
                .order_by(GroupMessage.received_at)
                .limit(200)
            )
            rows = result.scalars().all()
            if not rows:
                break
            ids = []
            for record in rows:
                mode = group_settings.get(record.chat_id, GroupPrivacyMode.public)
                if mode is GroupPrivacyMode.public:
                    continue
                try:
                    await application.bot.delete_message(chat_id=record.chat_id, message_id=record.message_id)
                except RetryAfter as exc:
                    delay = max(int(exc.retry_after), 1)
                    await asyncio.sleep(delay)
                    try:
                        await application.bot.delete_message(chat_id=record.chat_id, message_id=record.message_id)
                    except TelegramError:
                        continue
                except TelegramError:
                    continue
                ids.append(record.id)
            if ids:
                await session.execute(delete(GroupMessage).where(GroupMessage.id.in_(ids)))
        await session.commit()


async def reset_weekly_scores(session_factory: async_sessionmaker) -> None:
    now = datetime.now(timezone.utc)
    week_end = now
    week_start = week_end - timedelta(days=7)
    async with session_scope(session_factory) as session:
        result = await session.execute(
            select(Submission.agent_id, func.sum(Submission.ap), Agent.faction)
            .join(Agent, Agent.id == Submission.agent_id)
            .group_by(Submission.agent_id, Agent.faction)
        )
        for agent_id, total_ap, faction in result.all():
            total_value = int(total_ap or 0)
            if total_value <= 0:
                continue
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
        await session.execute(delete(Submission))


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
        args=(application, session_factory, settings.group_message_retention_minutes),
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
        args=(session_factory,),
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
        scheduler.shutdown(wait=False)
        await application.stop()
        await application.shutdown()
        await engine.dispose()
        redis_conn.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
