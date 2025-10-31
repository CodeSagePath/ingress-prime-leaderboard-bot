from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Agent, Submission


async def get_leaderboard(session: AsyncSession, limit: int, chat_id: int | None = None) -> Sequence[tuple[str, str, int]]:
    stmt = (
        select(Agent.codename, Agent.faction, func.sum(Submission.ap).label("total_ap"))
        .join(Submission, Submission.agent_id == Agent.id)
    )
    if chat_id is not None:
        stmt = stmt.where(Submission.chat_id == chat_id)
    stmt = (
        stmt.group_by(Agent.id)
        .order_by(func.sum(Submission.ap).desc(), Agent.codename)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(codename, faction, int(total_ap)) for codename, faction, total_ap in result.all()]
