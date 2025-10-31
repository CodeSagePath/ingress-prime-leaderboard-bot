import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from rq import Queue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from telegram import Bot
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

from ..config import load_settings
from ..database import build_engine, build_session_factory, init_models, session_scope
from ..models import PendingAction

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


def schedule_message_deletion(queue: Queue, token: str, chat_id: int, message_id: int, confirmation_message_id: int | None, delay_seconds: int) -> None:
    run_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "confirmation_message_id": confirmation_message_id,
        "run_at": run_at,
    }
    queue.enqueue_at(run_at, delete_message_job, token, payload)
