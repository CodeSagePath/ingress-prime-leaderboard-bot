from collections.abc import Sequence
from typing import Any, Dict, Optional
import logging

from sqlalchemy import func, select, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Agent, Submission, Verification, VerificationStatus

logger = logging.getLogger(__name__)

# Define metric configurations for different leaderboard types
METRIC_CONFIGS = {
    "ap": {"field": "ap", "json_key": None, "default": 0},
    "hacks": {"field": "metrics", "json_key": "hacks", "default": 0},
    "xm_collected": {"field": "metrics", "json_key": "xm_collected", "default": 0},
    "portals_captured": {"field": "metrics", "json_key": "portals_captured", "default": 0},
    "resonators_deployed": {"field": "metrics", "json_key": "resonators_deployed", "default": 0},
    "links_created": {"field": "metrics", "json_key": "links_created", "default": 0},
    "fields_created": {"field": "metrics", "json_key": "fields_created", "default": 0},
    "mods_deployed": {"field": "metrics", "json_key": "mods_deployed", "default": 0},
    "resonators_destroyed": {"field": "metrics", "json_key": "resonators_destroyed", "default": 0},
    "portals_neutralized": {"field": "metrics", "json_key": "portals_neutralized", "default": 0},
    "distance_walked": {"field": "metrics", "json_key": "distance_walked", "default": 0},
}


async def get_leaderboard(
    session: AsyncSession,
    limit: int,
    chat_id: int | None = None,
    time_span: str | None = None,
    metric: str = "ap"
) -> Sequence[tuple[str, str, int, Dict[str, Any]]]:
    """
    Get the leaderboard data with support for all metrics while maintaining existing workflow.

    This function:
    1. Uses the same submission format users already use
    2. Automatically handles missing stats (excludes agents without required data)
    3. Works with existing database structure
    4. Returns data in the same format as before

    If an agent is missing the required stat for a specific leaderboard,
    they will be excluded from that leaderboard (shown as blank).
    """
    try:
        # Validate metric and get configuration
        if metric not in METRIC_CONFIGS:
            logger.warning(f"Unknown metric '{metric}', falling back to AP")
            metric = "ap"

        config = METRIC_CONFIGS[metric]

        # For AP metric, use the original query
        if config["field"] == "ap":
            return await _get_ap_leaderboard(session, limit, chat_id, time_span)
        else:
            # For JSON metrics, use enhanced query
            return await _get_metric_leaderboard(session, limit, chat_id, time_span, config)

    except Exception as e:
        logger.error(f"Leaderboard query error for metric '{metric}': {e}")
        # Fallback: return empty list if query fails
        return []


async def _get_ap_leaderboard(
    session: AsyncSession,
    limit: int,
    chat_id: int | None,
    time_span: str | None
) -> Sequence[tuple[str, str, int, Dict[str, Any]]]:
    """Get AP-based leaderboard (original logic)."""

    # Get latest submission per agent
    latest_submissions = (
        select(
            Agent.codename,
            Agent.faction,
            func.max(Submission.submitted_at).label("latest_submission")
        )
        .join(Submission, Submission.agent_id == Agent.id)
        .group_by(Agent.id, Agent.codename, Agent.faction)
        .subquery()
    )

    # Main query
    stmt = (
        select(
            Agent.codename,
            Agent.faction,
            func.max(Submission.ap).label("metric_value"),
            func.max(Submission.submitted_at).label("last_seen"),
            func.max(Submission.metrics).label("all_metrics")
        )
        .join(Submission, Submission.agent_id == Agent.id)
        .join(latest_submissions, latest_submissions.c.latest_submission == Submission.submitted_at)
        .group_by(Agent.id, Agent.codename, Agent.faction)
        .order_by(func.max(Submission.ap).desc(), Agent.codename)
        .limit(limit)
    )

    # Apply filters
    if chat_id is not None:
        stmt = stmt.where(Submission.chat_id == chat_id)
    if time_span is not None:
        stmt = stmt.where(Submission.time_span == time_span)

    result = await session.execute(stmt)

    processed_results = []
    for row in result.all():
        codename, faction, metric_value, last_seen, all_metrics = row

        # Build metrics dictionary
        metrics_dict = {
            "ap": int(metric_value) if metric_value else 0,
            "last_seen": last_seen.isoformat() if last_seen else None,
        }

        # Add any available JSON metrics
        if all_metrics:
            for key, value in all_metrics.items():
                if isinstance(value, (int, float)):
                    metrics_dict[key] = int(value)

        processed_results.append((codename, faction, int(metric_value) if metric_value else 0, metrics_dict))

    return processed_results


async def _get_metric_leaderboard(
    session: AsyncSession,
    limit: int,
    chat_id: int | None,
    time_span: str | None,
    config: Dict[str, Any]
) -> Sequence[tuple[str, str, int, Dict[str, Any]]]:
    """Get leaderboard for specific JSON metric."""

    json_key = config["json_key"]

    # Build raw SQL query for JSON extraction (more reliable for SQLite)
    sql_query = f"""
        SELECT
            a.codename,
            a.faction,
            CAST(s.ap AS INTEGER) as ap,
            CAST(json_extract(s.metrics, '$.{json_key}') AS INTEGER) as metric_value,
            s.submitted_at,
            s.metrics
        FROM agents a
        JOIN submissions s ON s.agent_id = a.id
        WHERE json_extract(s.metrics, '$.{json_key}') IS NOT NULL
            AND json_extract(s.metrics, '$.{json_key}') != ''
            AND s.submitted_at = (
                SELECT MAX(s2.submitted_at)
                FROM submissions s2
                WHERE s2.agent_id = a.id
                {f"AND s2.chat_id = {chat_id}" if chat_id else ""}
                {f"AND s2.time_span = '{time_span}'" if time_span else ""}
            )
            {f"AND s.chat_id = {chat_id}" if chat_id else ""}
            {f"AND s.time_span = '{time_span}'" if time_span else ""}
        ORDER BY CAST(json_extract(s.metrics, '$.{json_key}') AS INTEGER) DESC, a.codename
        LIMIT {limit}
    """

    result = await session.execute(text(sql_query))
    rows = result.fetchall()

    processed_results = []
    for row in rows:
        codename, faction, ap, metric_value, submitted_at, metrics_json = row

        # Build complete metrics dictionary
        metrics_dict = {
            "ap": int(ap) if ap else 0,
            "last_seen": submitted_at.isoformat() if submitted_at else None,
        }

        # Add all available JSON metrics
        if metrics_json:
            for key, value in metrics_json.items():
                if isinstance(value, (int, float)):
                    metrics_dict[key] = int(value)

        processed_results.append((codename, faction, int(metric_value) if metric_value else 0, metrics_dict))

    return processed_results