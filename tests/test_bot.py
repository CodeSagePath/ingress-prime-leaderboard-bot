import pytest
import pytest_asyncio
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database import Base, session_scope
from bot.main import leaderboard, parse_submission
from bot.models import Agent, Submission


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


def test_parse_submission_parses_values():
    ap, metrics = parse_submission("ap=12345; hacks=17; distance=12.5; note=First run")
    assert ap == 12345
    assert metrics == {"hacks": 17, "distance": 12.5, "note": "First run"}


def test_parse_submission_requires_ap():
    with pytest.raises(ValueError, match="Missing ap value"):
        parse_submission("hacks=1")


@pytest.mark.asyncio
async def test_submission_persists(session_factory):
    async with session_scope(session_factory) as session:
        agent = Agent(telegram_id=1, codename="Alpha", faction="ENL")
        session.add(agent)
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == 1))
        agent = result.scalar_one()
        submission = Submission(agent_id=agent.id, ap=1500, metrics={"fields": 3})
        session.add(submission)
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Submission).join(Agent).where(Agent.telegram_id == 1))
        saved = result.scalar_one()
        assert saved.ap == 1500
        assert saved.metrics == {"fields": 3}


@pytest.mark.asyncio
async def test_leaderboard_formats_output(session_factory):
    async with session_scope(session_factory) as session:
        alpha = Agent(telegram_id=1, codename="Alpha", faction="ENL")
        beta = Agent(telegram_id=2, codename="Beta", faction="RES")
        session.add_all([alpha, beta])
        await session.flush()
        session.add_all([
            Submission(agent_id=alpha.id, ap=1000, metrics={}),
            Submission(agent_id=alpha.id, ap=500, metrics={}),
            Submission(agent_id=beta.id, ap=900, metrics={}),
        ])

    class DummySettings:
        leaderboard_size = 10

    class DummyApplication:
        def __init__(self, bot_data):
            self.bot_data = bot_data

    class DummyContext:
        def __init__(self, application):
            self.application = application

    class DummyMessage:
        def __init__(self):
            self.sent = None

        async def reply_text(self, text):
            self.sent = text
            return text

    message = DummyMessage()
    update = SimpleNamespace(message=message)
    application = DummyApplication({"settings": DummySettings(), "session_factory": session_factory})
    context = DummyContext(application)

    await leaderboard(update, context)

    assert message.sent == "1. Alpha [ENL] — 1,500 AP\n2. Beta [RES] — 900 AP"
