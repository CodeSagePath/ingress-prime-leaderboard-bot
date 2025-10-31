import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from telegram import Bot
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError, RetryAfter

from ..config import load_settings
from ..database import build_engine, build_session_factory, init_models, session_scope
from ..models import GroupMessage, GroupSetting, PendingAction

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        settings = load_settings()
        _engine = build_engine(settings)
        await init_models(_engine)
        _session_factory = build_session_factory(_engine)
    return _session_factory


async def _persist_pending_actions(chat_id: int | None, message_ids: list[int | None]) -> None:
    if chat_id is None:
        return
    ids = [value for value in message_ids if value is not None]
    if not ids:
        return
    session_factory = await _get_session_factory()
    async with session_scope(session_factory) as session:
        for message_id in ids:
            exists = await session.execute(
                select(PendingAction.id).where(
                    PendingAction.action == "delete_message",
                    PendingAction.chat_id == chat_id,
                    PendingAction.message_id == message_id,
                    PendingAction.executed.is_(False),
                )
            )
            if exists.scalar_one_or_none() is not None:
                continue
            session.add(
                PendingAction(
                    action="delete_message",
                    chat_id=chat_id,
                    message_id=message_id,
                )
            )


async def _delete_messages(token: str, payload: dict[str, Any]) -> None:
    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        membership = await bot.get_chat_member(payload["chat_id"], me.id)
    except TelegramError as exc:
        logger.warning("Unable to verify permissions in chat %s: %s", payload.get("chat_id"), exc)
        await _persist_pending_actions(
            payload.get("chat_id"),
            [payload.get("message_id"), payload.get("confirmation_message_id")],
        )
        return
    allowed = False
    if membership.status == ChatMemberStatus.OWNER:
        allowed = True
    elif membership.status == ChatMemberStatus.ADMINISTRATOR:
        allowed = bool(getattr(membership, "can_delete_messages", False))
    if not allowed:
        logger.info("Skipping deletion because bot lacks permission in chat %s", payload.get("chat_id"))
        return
    for key in ("message_id", "confirmation_message_id"):
        message_id = payload.get(key)
        if message_id is None:
            continue
        try:
            await bot.delete_message(chat_id=payload["chat_id"], message_id=message_id)
        except TelegramError as exc:
            logger.warning("Failed to delete message %s in chat %s: %s", message_id, payload["chat_id"], exc)
            await _persist_pending_actions(payload.get("chat_id"), [message_id])


def delete_message_job(token: str, payload: dict[str, Any]) -> None:
    try:
        asyncio.run(_delete_messages(token, payload))
    except Exception as exc:
        logger.exception("Deletion job failed for chat %s: %s", payload.get("chat_id"), exc)


async def execute_pending_deletions(application, session_factory: async_sessionmaker) -> None:
    """Execute any pending deletions that failed previously"""
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
                action.executed = True
            except RetryAfter as exc:
                delay = max(int(exc.retry_after), 1)
                await asyncio.sleep(delay)
                try:
                    await application.bot.delete_message(chat_id=action.chat_id, message_id=action.message_id)
                    action.executed = True
                except TelegramError as exc:
                    logger.error("Failed to delete pending message %s in chat %s after retry: %s",
                                action.message_id, action.chat_id, exc)
            except TelegramError as exc:
                logger.error("Failed to delete pending message %s in chat %s: %s",
                              action.message_id, action.chat_id, exc)
        await session.flush()


async def cleanup_expired_group_messages(
    application,
    session_factory: async_sessionmaker,
) -> None:
    """
    Delete messages older than the group-configured retention interval.
    This function is designed to be called by APScheduler every 10 minutes.
    """
    # First, execute any pending deletions that failed previously
    await execute_pending_deletions(application, session_factory)
    
    # Get all group settings with their retention intervals
    async with session_scope(session_factory) as session:
        settings_result = await session.execute(select(GroupSetting))
        group_settings = settings_result.scalars().all()
        
        for setting in group_settings:
            # Calculate threshold based on group-specific retention interval
            threshold = datetime.now(timezone.utc) - timedelta(minutes=setting.retention_minutes)
            
            # Find messages older than the threshold for this group
            while True:
                result = await session.execute(
                    select(GroupMessage)
                    .where(
                        GroupMessage.chat_id == setting.chat_id,
                        GroupMessage.received_at < threshold
                    )
                    .order_by(GroupMessage.received_at)
                    .limit(200)  # Process in batches to avoid memory issues
                )
                rows = result.scalars().all()
                if not rows:
                    break
                
                deleted_ids = []
                for record in rows:
                    try:
                        await application.bot.delete_message(chat_id=record.chat_id, message_id=record.message_id)
                        deleted_ids.append(record.id)
                    except RetryAfter as exc:
                        delay = max(int(exc.retry_after), 1)
                        await asyncio.sleep(delay)
                        try:
                            await application.bot.delete_message(chat_id=record.chat_id, message_id=record.message_id)
                            deleted_ids.append(record.id)
                        except TelegramError as exc:
                            logger.error("Failed to delete message %s in chat %s after retry: %s",
                                        record.message_id, record.chat_id, exc)
                            # Add to pending actions for later retry
                            await _persist_pending_actions(record.chat_id, [record.message_id])
                    except TelegramError as exc:
                        logger.error("Failed to delete message %s in chat %s: %s",
                                      record.message_id, record.chat_id, exc)
                        # Add to pending actions for later retry
                        await _persist_pending_actions(record.chat_id, [record.message_id])
                
                # Delete processed records from database
                if deleted_ids:
                    await session.execute(delete(GroupMessage).where(GroupMessage.id.in_(deleted_ids)))
                    await session.flush()
        
        await session.commit()
