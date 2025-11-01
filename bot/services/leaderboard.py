from collections.abc import Sequence
from typing import Any, Dict, Optional

from sqlalchemy import func, select, case, literal_column
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
    
    Args:
        session: Database session
        limit: Maximum number of results to return
        chat_id: Optional chat ID to filter submissions by
        time_span: Optional time span to filter submissions by (e.g., "ALL TIME", "WEEKLY")
        metric: The metric to rank by (default: "ap")
    
    Returns:
        Sequence of tuples containing (codename, faction, metric_value, metrics_dict)
    """
    # Create a subquery to count verified submissions for each agent
    verified_subquery = (
        select(
            Submission.agent_id,
            func.sum(case(
                (Verification.status == VerificationStatus.approved.value, Submission.ap),
                else_=0
            )).label("verified_ap"),
            func.sum(case(
                (Verification.status == VerificationStatus.pending.value, Submission.ap),
                else_=0
            )).label("pending_ap"),
            func.sum(case(
                (Verification.status == VerificationStatus.rejected.value, Submission.ap),
                else_=0
            )).label("rejected_ap"),
            func.sum(case(
                (Verification.status.is_(None), Submission.ap),
                else_=0
            )).label("unverified_ap")
        )
        .join(Verification, Verification.submission_id == Submission.id, isouter=True)
        .group_by(Submission.agent_id)
    ).subquery()
    
    # Determine which metric field to use for ranking
    if metric == "ap":
        metric_field = Submission.ap
    else:
        # For custom metrics, we need to extract them from the JSON metrics field
        metric_field = func.coalesce(Submission.metrics[metric].astext.cast(Integer), 0)
    
    # Main query to get the leaderboard with verification status
    stmt = (
        select(
            Agent.codename,
            Agent.faction,
            func.sum(metric_field).label("metric_value"),
            func.sum(Submission.ap).label("total_ap"),
            func.coalesce(verified_subquery.c.verified_ap, 0).label("verified_ap"),
            func.coalesce(verified_subquery.c.pending_ap, 0).label("pending_ap"),
            func.coalesce(verified_subquery.c.rejected_ap, 0).label("rejected_ap"),
            func.coalesce(verified_subquery.c.unverified_ap, 0).label("unverified_ap"),
            # Include all metrics as JSON for display
            func.json_object_agg(
                func.distinct(func.jsonb_each_text(Submission.metrics).key),
                func.sum(func.cast(func.jsonb_each_text(Submission.metrics).value, Integer))
            ).label("all_metrics")
        )
        .join(Submission, Submission.agent_id == Agent.id)
        .join(verified_subquery, verified_subquery.c.agent_id == Agent.id, isouter=True)
    )
    
    # Apply filters
    if chat_id is not None:
        stmt = stmt.where(Submission.chat_id == chat_id)
    
    if time_span is not None:
        stmt = stmt.where(Submission.time_span == time_span)
    
    stmt = (
        stmt.group_by(Agent.id)
        .order_by(
            # Prioritize agents with more verified AP
            func.coalesce(verified_subquery.c.verified_ap, 0).desc(),
            # Then by the selected metric
            func.sum(metric_field).desc(),
            # Then by codename
            Agent.codename
        )
        .limit(limit)
    )
    
    result = await session.execute(stmt)
    
    # Process results and return with metrics dictionary
    processed_results = []
    for row in result.all():
        codename, faction, metric_value, total_ap, verified_ap, pending_ap, rejected_ap, unverified_ap, all_metrics = row
        
        # Create metrics dictionary with verification status
        metrics_dict = {
            "total_ap": int(total_ap),
            "verified_ap": int(verified_ap),
            "pending_ap": int(pending_ap),
            "rejected_ap": int(rejected_ap),
            "unverified_ap": int(unverified_ap),
        }
        
        # Add all other metrics if available
        if all_metrics:
            for key, value in all_metrics.items():
                if key not in metrics_dict:  # Don't overwrite verification metrics
                    metrics_dict[key] = int(value) if value is not None else 0
        
        processed_results.append((codename, faction, int(metric_value), metrics_dict))
    
    return processed_results
