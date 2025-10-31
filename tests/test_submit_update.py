import pytest
import pytest_asyncio
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from datetime import datetime, timezone

from bot.database import Base, session_scope
from bot.main import submit, parse_submission
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


@pytest.mark.asyncio
async def test_submit_updates_existing_submission(session_factory):
    """Test that submit updates an existing submission instead of creating a new one"""
    # Set up test data
    async with session_scope(session_factory) as session:
        agent = Agent(telegram_id=1, codename="Alpha", faction="ENL")
        session.add(agent)
        await session.flush()
        # Create initial submission
        submission = Submission(agent_id=agent.id, chat_id=None, ap=1000, metrics={"fields": 3})
        session.add(submission)
    
    # Set up dummy objects for the submit function
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

    class DummyMessage:
        def __init__(self):
            self.sent = None
            self.message_id = 77
            self.text = "/submit ap=2000; fields=5"

        async def reply_text(self, text):
            self.sent = text
            return SimpleNamespace(message_id=88)

    # Create update and context objects
    message = DummyMessage()
    update = SimpleNamespace(
        message=message,
        effective_user=DummyUser(),
        effective_chat=None  # Private chat
    )
    application = DummyApplication({
        "settings": DummySettings(),
        "session_factory": session_factory,
        "queue": object()
    })
    context = DummyContext(application)

    # Call the submit function
    await submit(update, context)

    # Verify that the existing submission was updated, not a new one created
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Submission).where(Submission.agent_id == 1))
        submissions = result.scalars().all()
        
        # There should still be only one submission
        assert len(submissions) == 1
        
        # The submission should have the updated values
        updated_submission = submissions[0]
        assert updated_submission.ap == 2000
        assert updated_submission.metrics == {"fields": 5}
        assert updated_submission.submitted_at > submission.submitted_at


@pytest.mark.asyncio
async def test_submit_creates_new_submission_if_none_exists(session_factory):
    """Test that submit creates a new submission if none exists for the user"""
    # Set up test data - only create an agent, no submission
    async with session_scope(session_factory) as session:
        agent = Agent(telegram_id=1, codename="Alpha", faction="ENL")
        session.add(agent)
    
    # Set up dummy objects for the submit function
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

    class DummyMessage:
        def __init__(self):
            self.sent = None
            self.message_id = 77
            self.text = "/submit ap=2000; fields=5"

        async def reply_text(self, text):
            self.sent = text
            return SimpleNamespace(message_id=88)

    # Create update and context objects
    message = DummyMessage()
    update = SimpleNamespace(
        message=message,
        effective_user=DummyUser(),
        effective_chat=None  # Private chat
    )
    application = DummyApplication({
        "settings": DummySettings(),
        "session_factory": session_factory,
        "queue": object()
    })
    context = DummyContext(application)

    # Call the submit function
    await submit(update, context)

    # Verify that a new submission was created
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Submission).where(Submission.agent_id == 1))
        submissions = result.scalars().all()
        
        # There should be one submission
        assert len(submissions) == 1
        
        # The submission should have the correct values
        new_submission = submissions[0]
        assert new_submission.ap == 2000
        assert new_submission.metrics == {"fields": 5}
        assert new_submission.agent_id == 1


@pytest.mark.asyncio
async def test_submit_updates_correct_submission_for_group_chat(session_factory):
    """Test that submit updates the correct submission for a group chat"""
    # Set up test data
    async with session_scope(session_factory) as session:
        agent = Agent(telegram_id=1, codename="Alpha", faction="ENL")
        session.add(agent)
        await session.flush()
        # Create submissions for different contexts
        private_submission = Submission(agent_id=agent.id, chat_id=None, ap=1000, metrics={"fields": 3})
        group_submission = Submission(agent_id=agent.id, chat_id=222, ap=500, metrics={"fields": 1})
        session.add_all([private_submission, group_submission])
    
    # Set up dummy objects for the submit function
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
        type = "group"
        id = 222

    class DummyMessage:
        def __init__(self):
            self.sent = None
            self.message_id = 77
            self.text = "/submit ap=1500; fields=4"

        async def reply_text(self, text):
            self.sent = text
            return SimpleNamespace(message_id=88)

    # Create update and context objects
    message = DummyMessage()
    update = SimpleNamespace(
        message=message,
        effective_user=DummyUser(),
        effective_chat=DummyChat()  # Group chat
    )
    application = DummyApplication({
        "settings": DummySettings(),
        "session_factory": session_factory,
        "queue": object()
    })
    context = DummyContext(application)

    # Call the submit function
    await submit(update, context)

    # Verify that the group submission was updated, not the private one
    async with session_scope(session_factory) as session:
        # Check private submission (should be unchanged)
        result = await session.execute(
            select(Submission).where(
                Submission.agent_id == 1,
                Submission.chat_id == None
            )
        )
        private_sub = result.scalar_one()
        assert private_sub.ap == 1000
        assert private_sub.metrics == {"fields": 3}
        
        # Check group submission (should be updated)
        result = await session.execute(
            select(Submission).where(
                Submission.agent_id == 1,
                Submission.chat_id == 222
            )
        )
        group_sub = result.scalar_one()
        assert group_sub.ap == 1500
        assert group_sub.metrics == {"fields": 4}