from collections.abc import Sequence

from sqlalchemy import func, select, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Agent, Submission, Verification, VerificationStatus


async def get_leaderboard(session: AsyncSession, limit: int, chat_id: int | None = None) -> Sequence[tuple[str, str, int]]:
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
    
    # Main query to get the leaderboard with verification status
    stmt = (
        select(
            Agent.codename,
            Agent.faction,
            func.sum(Submission.ap).label("total_ap"),
            func.coalesce(verified_subquery.c.verified_ap, 0).label("verified_ap"),
            func.coalesce(verified_subquery.c.pending_ap, 0).label("pending_ap"),
            func.coalesce(verified_subquery.c.rejected_ap, 0).label("rejected_ap"),
            func.coalesce(verified_subquery.c.unverified_ap, 0).label("unverified_ap")
        )
        .join(Submission, Submission.agent_id == Agent.id)
        .join(verified_subquery, verified_subquery.c.agent_id == Agent.id, isouter=True)
    )
    
    if chat_id is not None:
        stmt = stmt.where(Submission.chat_id == chat_id)
    
    stmt = (
        stmt.group_by(Agent.id)
        .order_by(
            # Prioritize agents with more verified AP
            func.coalesce(verified_subquery.c.verified_ap, 0).desc(),
            # Then by total AP
            func.sum(Submission.ap).desc(),
            # Then by codename
            Agent.codename
        )
        .limit(limit)
    )
    
    result = await session.execute(stmt)
    return [(codename, faction, int(total_ap)) for codename, faction, total_ap, _, _, _, _ in result.all()]
