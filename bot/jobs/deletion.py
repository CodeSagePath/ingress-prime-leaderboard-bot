import asyncio
from datetime import timedelta

from rq import Queue
from telegram import Bot


def delete_message_job(token: str, chat_id: int, message_id: int) -> None:
    asyncio.run(Bot(token=token).delete_message(chat_id=chat_id, message_id=message_id))


def schedule_message_deletion(queue: Queue, token: str, chat_id: int, message_id: int, delay_seconds: int) -> None:
    queue.enqueue_in(timedelta(seconds=delay_seconds), delete_message_job, token, chat_id, message_id)
