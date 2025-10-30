import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from rq import Queue
from telegram import Bot
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError


logger = logging.getLogger(__name__)


async def _delete_messages(token: str, payload: dict[str, Any]) -> None:
    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        membership = await bot.get_chat_member(payload["chat_id"], me.id)
    except TelegramError as exc:
        logger.warning("Unable to verify permissions in chat %s: %s", payload.get("chat_id"), exc)
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
