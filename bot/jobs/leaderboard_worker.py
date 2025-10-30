import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from redis import Redis
from rq import Connection, Queue, Worker
from sqlalchemy import text

from bot.config import load_settings
from bot.database import build_engine, build_session_factory, session_scope

logger = logging.getLogger("leaderboard_worker")


def enqueue_recompute_job(queue: Queue) -> None:
    queue.enqueue(recompute_leaderboards_job)


async def _collect_leaderboards(session, limit: int) -> dict[tuple[str, str], list[dict[str, object]]]:
    query = text(
        """
        WITH ranked AS (
            SELECT
                s.category,
                s.faction,
                s.agent_id,
                a.codename,
                SUM(s.value) AS total_value,
                ROW_NUMBER() OVER (
                    PARTITION BY s.category, s.faction
                    ORDER BY SUM(s.value) DESC, a.codename
                ) AS row_number
            FROM stats s
            JOIN agents a ON a.id = s.agent_id
            GROUP BY s.category, s.faction, s.agent_id, a.codename
        )
        SELECT
            category,
            faction,
            agent_id,
            codename,
            total_value,
            row_number
        FROM ranked
        WHERE row_number <= :limit
        ORDER BY category, faction, row_number
        """
    )
    result = await session.execute(query, {"limit": limit})
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in result.mappings():
        key = (row["category"], row["faction"])
        grouped[key].append(
            {
                "rank": int(row["row_number"]),
                "agent_id": int(row["agent_id"]),
                "codename": row["codename"],
                "value": float(row["total_value"]) if row["total_value"] is not None else 0.0,
            }
        )
    return grouped


async def _persist_leaderboards(session, grouped: dict[tuple[str, str], list[dict[str, object]]]) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    for (category, faction), leaders in grouped.items():
        payload = {
            "category": category,
            "faction": faction,
            "generated_at": generated_at,
            "leaders": leaders,
        }
        await session.execute(
            text("DELETE FROM leaderboard_cache WHERE category = :category AND faction = :faction"),
            {"category": category, "faction": faction},
        )
        await session.execute(
            text(
                "INSERT INTO leaderboard_cache (category, faction, payload, generated_at) "
                "VALUES (:category, :faction, :payload, :generated_at)"
            ),
            {
                "category": category,
                "faction": faction,
                "payload": json.dumps(payload, separators=(",", ":")),
                "generated_at": generated_at,
            },
        )


async def _recompute(settings) -> None:
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    try:
        async with session_scope(session_factory) as session:
            async with session.begin():
                grouped = await _collect_leaderboards(session, settings.leaderboard_size)
                if not grouped:
                    await session.execute(text("DELETE FROM leaderboard_cache"))
                else:
                    await _persist_leaderboards(session, grouped)
        logger.info("leaderboard cache updated", extra={"partitions": len(grouped)})
    finally:
        await engine.dispose()


def recompute_leaderboards_job() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    try:
        asyncio.run(_recompute(settings))
    except Exception:
        logger.exception("failed to recompute leaderboards")
        raise


def _create_scheduler(queue: Queue) -> BackgroundScheduler:
    cron_expression = os.environ.get("LEADERBOARD_RECOMPUTE_CRON", "0 */1 * * *")
    timezone_name = os.environ.get("LEADERBOARD_TIMEZONE", "UTC")
    scheduler = BackgroundScheduler(timezone=timezone_name)
    trigger = CronTrigger.from_crontab(cron_expression)
    scheduler.add_job(
        enqueue_recompute_job,
        trigger=trigger,
        args=[queue],
        id="recompute-leaderboards",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    return scheduler


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    redis_conn = Redis.from_url(settings.redis_url)
    queue_name = os.environ.get("LEADERBOARD_QUEUE_NAME", "leaderboard")
    queue = Queue(name=queue_name, connection=redis_conn)
    scheduler = _create_scheduler(queue)
    try:
        scheduler.start()
        enqueue_recompute_job(queue)
        with Connection(redis_conn):
            worker = Worker([queue])
            worker.work(with_scheduler=True)
    except KeyboardInterrupt:
        logger.info("shutdown requested")
    finally:
        scheduler.shutdown(wait=False)
        redis_conn.close()


if __name__ == "__main__":
    main()
