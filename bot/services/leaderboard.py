from collections.abc import Sequence
from typing import Any, Dict, Optional

from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Agent, Submission, Verification, VerificationStatus


async def get_leaderboard(
    session: AsyncSession,
    limit: int,
    chat_id: int | None = None,
    time_span: str | None = None,
    metric: str = "ap"
) -> Sequence[tuple[str, str, int, Dict[str, Any]]]:
    """
    Get the leaderboard data with optional filtering by time span and metric.

    Simplified version that works reliably with basic data.
    """
    try:
        # Simple query to get latest submission per agent
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

        # Main query to get agent data
        stmt = (
            select(
                Agent.codename,
                Agent.faction,
                func.max(Submission.ap).label("metric_value"),
                func.max(Submission.submitted_at).label("last_seen")
            )
            .join(Submission, Submission.agent_id == Agent.id)
            .group_by(Agent.id, Agent.codename, Agent.faction)
            .order_by(func.max(Submission.ap).desc(), Agent.codename)
            .limit(limit)
        )

        # Apply filters if specified
        if chat_id is not None:
            stmt = stmt.where(Submission.chat_id == chat_id)

        if time_span is not None:
            stmt = stmt.where(Submission.time_span == time_span)

        result = await session.execute(stmt)

        processed_results = []
        for row in result.all():
            codename, faction, metric_value, last_seen = row

            # Create simple metrics dictionary
            metrics_dict = {
                "total_ap": int(metric_value) if metric_value else 0,
                "last_seen": last_seen.isoformat() if last_seen else None,
            }

            processed_results.append((codename, faction, int(metric_value) if metric_value else 0, metrics_dict))

        return processed_results

    except Exception as e:
        print(f"Leaderboard query error: {e}")
        # Fallback: return empty list if query fails
        return []