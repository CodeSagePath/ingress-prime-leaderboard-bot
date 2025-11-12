from collections.abc import Sequence
from typing import Any, Dict, Optional
import logging

from sqlalchemy import func, select, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Agent, Submission

logger = logging.getLogger(__name__)

# Define metric configurations for different leaderboard types
# Priority is based on stat availability and ranking value
METRIC_CONFIGS = {
    # Tier 1: Core Performance Stats (Highest Priority)
    "ap": {
        "field": "ap",
        "json_key": None,
        "default": 0,
        "priority": 1,
        "availability": 1.0,  # Always available
        "category": "core",
        "description": "Lifetime AP - Universal ranking standard"
    },
    "hacks": {
        "field": "metrics",
        "json_key": "hacks",
        "default": 0,
        "priority": 2,
        "availability": 0.98,  # Very common across agents
        "category": "core",
        "description": "Total hacks - High-frequency activity metric"
    },
    "xm_collected": {
        "field": "metrics",
        "json_key": "xm_collected",
        "default": 0,
        "priority": 3,
        "availability": 0.95,  # Most agents have this
        "category": "core",
        "description": "XM collected - Activity volume indicator"
    },

    # Tier 2: Strategic Building Stats (High Value)
    "links_created": {
        "field": "metrics",
        "json_key": "links_created",
        "default": 0,
        "priority": 4,
        "availability": 0.85,  # Common for established agents
        "category": "building",
        "description": "Links created - Network building metric"
    },
    "control_fields_created": {
        "field": "metrics",
        "json_key": "control_fields_created",
        "default": 0,
        "priority": 5,
        "availability": 0.75,  # Available for active builders
        "category": "building",
        "description": "Control fields created - Strategic contribution"
    },

    # Tier 3: Combat & Activity Stats (Medium Value)
    "portals_captured": {
        "field": "metrics",
        "json_key": "portals_captured",
        "default": 0,
        "priority": 6,
        "availability": 0.80,  # Common for active players
        "category": "combat",
        "description": "Portals captured - Territory control metric"
    },
    "resonators_deployed": {
        "field": "metrics",
        "json_key": "resonators_deployed",
        "default": 0,
        "priority": 7,
        "availability": 0.82,  # Very common activity
        "category": "building",
        "description": "Resonators deployed - Basic building activity"
    },
    "resonators_destroyed": {
        "field": "metrics",
        "json_key": "resonators_destroyed",
        "default": 0,
        "priority": 8,
        "availability": 0.70,  # Combat-focused agents
        "category": "combat",
        "description": "Resonators destroyed - Combat activity"
    },
    "portals_neutralized": {
        "field": "metrics",
        "json_key": "portals_neutralized",
        "default": 0,
        "priority": 9,
        "availability": 0.75,  # Combat and cleansing activity
        "category": "combat",
        "description": "Portals neutralized - Combat activity"
    },

    # Tier 4: Specialized Stats (Lower Priority)
    "distance_walked": {
        "field": "metrics",
        "json_key": "distance_walked",
        "default": 0,
        "priority": 10,
        "availability": 0.80,  # Physical engagement metric
        "category": "exploration",
        "description": "Distance walked - Physical activity"
    },
    "mods_deployed": {
        "field": "metrics",
        "json_key": "mods_deployed",
        "default": 0,
        "priority": 11,
        "availability": 0.85,  # Common for strategic players
        "category": "building",
        "description": "Mods deployed - Strategic enhancement"
    },
    "betatokens": {
        "field": "metrics",
        "json_key": "betatokens",
        "default": 0,
        "priority": 12,
        "availability": 0.60,  # Event-specific, less common
        "category": "events",
        "description": "Beta tokens - Event participation"
    },
}


def get_core_metrics(limit: int = 4) -> Dict[str, Dict[str, Any]]:
    """
    Get the most efficient core metrics for default leaderboards.
    Returns metrics with highest availability and ranking value.
    """
    core_metrics = {}
    for metric_key, config in METRIC_CONFIGS.items():
        if config["priority"] <= limit:
            core_metrics[metric_key] = config
    return core_metrics


def get_metrics_by_category(category: str) -> Dict[str, Dict[str, Any]]:
    """Get all metrics in a specific category."""
    return {
        metric_key: config
        for metric_key, config in METRIC_CONFIGS.items()
        if config["category"] == category
    }


def get_high_availability_metrics(min_availability: float = 0.85) -> Dict[str, Dict[str, Any]]:
    """Get metrics with high availability across agents."""
    return {
        metric_key: config
        for metric_key, config in METRIC_CONFIGS.items()
        if config["availability"] >= min_availability
    }


def get_optimal_metric_for_timeframe(timeframe_type: str) -> str:
    """
    Get the optimal metric for different timeframes.

    Args:
        timeframe_type: "daily", "weekly", "monthly", "alltime"

    Returns:
        Metric key optimal for the timeframe
    """
    timeframe_recommendations = {
        "daily": "hacks",        # High-frequency activity
        "weekly": "xm_collected", # Activity volume
        "monthly": "links_created", # Strategic building
        "alltime": "ap"          # Universal standard
    }
    return timeframe_recommendations.get(timeframe_type, "ap")


def get_metric_efficiency_score(metric_key: str) -> float:
    """
    Calculate efficiency score for a metric based on availability and priority.
    Higher score = more efficient for ranking.

    Args:
        metric_key: The metric configuration key

    Returns:
        Efficiency score (0-100)
    """
    if metric_key not in METRIC_CONFIGS:
        return 0.0

    config = METRIC_CONFIGS[metric_key]
    availability_score = config["availability"] * 50  # 50% weight
    priority_score = max(0, (13 - config["priority"]) * 4)  # 50% weight

    return availability_score + priority_score


def get_recommended_metrics_for_leaderboard(count: int = 5) -> list[str]:
    """
    Get recommended metrics sorted by efficiency for leaderboard display.

    Args:
        count: Number of metrics to return

    Returns:
        List of metric keys sorted by efficiency
    """
    sorted_metrics = sorted(
        METRIC_CONFIGS.items(),
        key=lambda x: get_metric_efficiency_score(x[0]),
        reverse=True
    )
    return [metric_key for metric_key, _ in sorted_metrics[:count]]


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
            COALESCE(CAST(json_extract(s.metrics, '$.{json_key}') AS INTEGER), 0) as metric_value,
            s.submitted_at,
            s.metrics
        FROM agents a
        JOIN submissions s ON s.agent_id = a.id
        WHERE s.submitted_at = (
                SELECT MAX(s2.submitted_at)
                FROM submissions s2
                WHERE s2.agent_id = a.id
                {f"AND s2.chat_id = {chat_id}" if chat_id else ""}
                {f"AND s2.time_span = '{time_span}'" if time_span else ""}
            )
            {f"AND s.chat_id = {chat_id}" if chat_id else ""}
            {f"AND s.time_span = '{time_span}'" if time_span else ""}
        ORDER BY COALESCE(CAST(json_extract(s.metrics, '$.{json_key}') AS INTEGER), 0) DESC, a.codename
        LIMIT {limit}
    """

    result = await session.execute(text(sql_query))
    rows = result.fetchall()

    processed_results = []
    for row in rows:
        codename, faction, ap, metric_value, submitted_at, metrics_json = row

        # Skip agents with no data at all for this metric
        if metric_value == 0 and ap == 0:
            continue

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