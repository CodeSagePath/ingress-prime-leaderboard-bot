import pytest
import pytest_asyncio
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database import Base, session_scope
from bot.main import leaderboard, parse_submission, set_group_privacy, myrank_command
from bot.models import Agent, Submission, GroupSetting


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
        group_message_retention_minutes = 60
        autodelete_delay_seconds = 300
        autodelete_enabled = True
        telegram_token = "token"

    class DummyApplication:
        def __init__(self, bot_data):
            self.bot_data = bot_data

    class DummyContext:
        def __init__(self, application):
            self.application = application
            self.args = []

    class DummyChat:
        type = "group"
        id = 222

    class DummyMessage:
        def __init__(self):
            self.sent = None
            self.message_id = 77

        async def reply_text(self, text):
            self.sent = text
            return SimpleNamespace(message_id=88)

    message = DummyMessage()
    update = SimpleNamespace(message=message, effective_chat=DummyChat())
    application = DummyApplication({"settings": DummySettings(), "session_factory": session_factory, "queue": object()})
    context = DummyContext(application)

    await leaderboard(update, context)

    assert message.sent == "1. Alpha [ENL] — 1,500 AP\n2. Beta [RES] — 900 AP"


@pytest.mark.asyncio
async def test_set_group_privacy_updates_mode(session_factory):
    async with session_scope(session_factory) as session:
        agent = Agent(telegram_id=1, codename="Alpha", faction="ENL")
        session.add(agent)
        await session.flush()
        session.add(Submission(agent_id=agent.id, chat_id=222, ap=1000, metrics={}))

    class DummySettings:
        telegram_token = "token"
        database_url = "sqlite+aiosqlite:///:memory:"
        redis_url = "redis://localhost:6379/0"
        autodelete_delay_seconds = 300
        autodelete_enabled = True
        leaderboard_size = 10
        group_message_retention_minutes = 60

    class DummyChat:
        type = "group"
        id = 222

    class DummyMessage:
        async def reply_text(self, text):
            self.text = text

    message = DummyMessage()
    update = SimpleNamespace(message=message, effective_chat=DummyChat())
    application = SimpleNamespace(bot_data={
        "settings": DummySettings(),
        "session_factory": session_factory,
        "queue": object(),
    })
    context = SimpleNamespace(application=application, args=["strict"])

    await set_group_privacy(update, context)

    async with session_scope(session_factory) as session:
        setting_result = await session.execute(select(GroupSetting).where(GroupSetting.chat_id == 222))
        setting = setting_result.scalar_one()
        assert setting.privacy_mode == "strict"


@pytest.mark.asyncio
async def test_myrank_command(session_factory):
    # Set up test data
    async with session_scope(session_factory) as session:
        alpha = Agent(telegram_id=1, codename="Alpha", faction="ENL")
        beta = Agent(telegram_id=2, codename="Beta", faction="RES")
        gamma = Agent(telegram_id=3, codename="Gamma", faction="ENL")
        session.add_all([alpha, beta, gamma])
        await session.flush()
        session.add_all([
            Submission(agent_id=alpha.id, ap=1000, metrics={}),
            Submission(agent_id=alpha.id, ap=500, metrics={}),
            Submission(agent_id=beta.id, ap=900, metrics={}),
            Submission(agent_id=gamma.id, ap=2000, metrics={}),
        ])

    class DummySettings:
        leaderboard_size = 10
        group_message_retention_minutes = 60
        autodelete_delay_seconds = 300
        autodelete_enabled = True
        telegram_token = "token"

    class DummyApplication:
        def __init__(self, bot_data):
            self.bot_data = bot_data

    class DummyContext:
        def __init__(self, application):
            self.application = application

    class DummyUser:
        id = 1  # Alpha's telegram_id

    class DummyChat:
        type = "private"

    class DummyMessage:
        def __init__(self):
            self.sent = None
            self.message_id = 77

        async def reply_text(self, text):
            self.sent = text
            return SimpleNamespace(message_id=88)

    # Test private chat (global ranking)
    message = DummyMessage()
    update = SimpleNamespace(
        message=message,
        effective_user=DummyUser(),
        effective_chat=DummyChat()
    )
    application = DummyApplication({
        "settings": DummySettings(),
        "session_factory": session_factory,
        "queue": object()
    })
    context = DummyContext(application)

    await myrank_command(update, context)

    # Alpha should be ranked #2 globally (Gamma: 2000, Alpha: 1500, Beta: 900)
    assert "Your rank globally is #2" in message.sent
    assert "Alpha [ENL] — 1,500 AP" in message.sent

    # Test group chat (group-specific ranking)
    message.sent = None
    DummyChat.type = "group"
    DummyChat.id = 222
    
    # Add a group-specific submission for Alpha
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == 1))
        alpha = result.scalar_one()
        session.add(Submission(agent_id=alpha.id, chat_id=222, ap=300, metrics={}))

    await myrank_command(update, context)

    # Alpha should be ranked #1 in the group with only 300 AP
    assert "Your rank in this group is #1" in message.sent
    assert "Alpha [ENL] — 300 AP" in message.sent
