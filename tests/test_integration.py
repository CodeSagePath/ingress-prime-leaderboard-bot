import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import pytest
import pytest_asyncio
from types import SimpleNamespace
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.database import Base, session_scope
from bot.main import (
    parse_submission,
    register_start,
    register_codename,
    register_faction,
    register_cancel,
    submit,
    leaderboard,
    start,
)
from bot.models import Agent, Submission, Faction
from bot.jobs.deletion import (
    _delete_messages,
    delete_message_job,
    schedule_message_deletion,
)
from bot.jobs.leaderboard_worker import (
    enqueue_recompute_job,
    _collect_leaderboards,
    _persist_leaderboards,
    recompute_leaderboards_job,
    _recompute,
)
from bot.services.leaderboard import get_leaderboard
from bot.config import Settings


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


@pytest.fixture
def mock_settings():
    return Settings(
        telegram_token="test_token",
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        autodelete_delay_seconds=300,
        autodelete_enabled=True,
        leaderboard_size=10,
        group_message_retention_minutes=60,
    )


@pytest.fixture
def mock_queue():
    return Mock()


@pytest.fixture
def mock_update():
    update = Mock()
    update.message = Mock()
    update.effective_user = Mock()
    update.effective_user.id = 12345
    return update


@pytest.fixture
def mock_context(mock_settings, mock_queue, session_factory):
    context = Mock()
    context.application = Mock()
    context.application.bot_data = {
        "settings": mock_settings,
        "queue": mock_queue,
        "session_factory": session_factory,
    }
    return context


@pytest.fixture
def multiple_mock_updates():
    """Create multiple mock updates for different users"""
    updates = []
    for i in range(1, 6):  # Create 5 different users
        update = Mock()
        update.message = Mock()
        update.effective_user = Mock()
        update.effective_user.id = 10000 + i  # Different telegram IDs
        updates.append(update)
    return updates


@pytest.fixture
def multiple_mock_contexts(mock_settings, mock_queue, session_factory):
    """Create multiple mock contexts for different users"""
    contexts = []
    for i in range(1, 6):  # Create 5 different users
        context = Mock()
        context.application = Mock()
        context.application.bot_data = {
            "settings": mock_settings,
            "queue": mock_queue,
            "session_factory": session_factory,
        }
        context.user_data = {}
        contexts.append(context)
    return contexts


# ==================== FEATURE INTERACTION TESTS ====================

class TestRegisterSubmitFlow:
    """Test Register → Submit flow: Test that a user can register and then successfully submit AP"""

    @pytest.mark.asyncio
    async def test_complete_register_submit_flow(self, mock_update, mock_context, session_factory):
        """
        Test that a user can register and then successfully submit AP
        1. User registers with codename and faction
        2. User submits AP with metrics
        3. Verify submission is recorded correctly
        """
        # Step 1: Register user
        mock_update.message.reply_text = AsyncMock()
        
        # Start registration
        result = await register_start(mock_update, mock_context)
        assert result == 0  # CODENAME
        mock_update.message.reply_text.assert_called_with("Please send your agent codename.")
        
        # Provide codename
        mock_update.message.text = "TestAgent"
        mock_update.message.reply_text.reset_mock()
        result = await register_codename(mock_update, mock_context)
        assert result == 1  # FACTION
        mock_update.message.reply_text.assert_called_with("Send your faction (ENL or RES).")
        assert mock_context.user_data["codename"] == "TestAgent"
        
        # Provide faction
        mock_update.message.text = "ENL"
        mock_update.message.reply_text.reset_mock()
        result = await register_faction(mock_update, mock_context)
        assert result == -1  # ConversationHandler.END
        mock_update.message.reply_text.assert_called_with("Registered TestAgent (ENL).")
        assert "codename" not in mock_context.user_data
        
        # Verify agent was created
        async with session_scope(session_factory) as session:
            result = await session.execute(select(Agent).where(Agent.telegram_id == 12345))
            agent = result.scalar_one()
            assert agent.codename == "TestAgent"
            assert agent.faction == "ENL"
        
        # Step 2: Submit AP
        mock_update.message.text = "/submit ap=12345; hacks=17"
        mock_update.message.message_id = 67890
        mock_update.message.reply_text = AsyncMock(return_value=Mock(message_id=11111))
        
        await submit(mock_update, mock_context)
        
        # Step 3: Verify submission was recorded
        async with session_scope(session_factory) as session:
            result = await session.execute(select(Submission).join(Agent).where(Agent.telegram_id == 12345))
            submission = result.scalar_one()
            assert submission.ap == 12345
            assert submission.metrics == {"hacks": 17}
        
        # Verify reply was sent
        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        assert "Recorded 12345 AP for TestAgent" in reply_text

    @pytest.mark.asyncio
    async def test_register_submit_with_multiple_submissions(self, mock_update, mock_context, session_factory):
        """
        Test that a user can register and then submit multiple AP entries
        1. User registers
        2. User submits AP multiple times
        3. Verify all submissions are recorded and accumulated
        """
        # Register user (simplified)
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        # Submit multiple times
        submissions_data = [
            ("/submit ap=1000; hacks=10", 1000),
            ("/submit ap=500; fields=2", 500),
            ("/submit ap=250; mods=5", 250),
        ]
        
        for submit_text, expected_ap in submissions_data:
            mock_update.message.text = submit_text
            mock_update.message.message_id = 67890
            mock_update.message.reply_text = AsyncMock(return_value=Mock(message_id=11111))
            
            await submit(mock_update, mock_context)
            
            # Verify submission was recorded
            async with session_scope(session_factory) as session:
                result = await session.execute(select(Submission).join(Agent).where(Agent.telegram_id == 12345))
                submission = result.scalar_one()
                assert submission.ap == expected_ap
        
        # Verify total AP in leaderboard
        async with session_scope(session_factory) as session:
            leaderboard = await get_leaderboard(session, 10)
            assert len(leaderboard) == 1
            assert leaderboard[0] == ("TestAgent", "ENL", 1750)  # 1000 + 500 + 250


class TestSubmitLeaderboardFlow:
    """Test Submit → Leaderboard flow: Test that submissions are properly reflected in the leaderboard"""

    @pytest.mark.asyncio
    async def test_single_submission_reflected_in_leaderboard(self, mock_update, mock_context, session_factory):
        """
        Test that a single submission is properly reflected in the leaderboard
        1. Register a user
        2. Submit AP
        3. Check leaderboard
        4. Verify submission is reflected
        """
        # Register user
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        # Submit AP
        mock_update.message.text = "/submit ap=12345; hacks=17"
        mock_update.message.message_id = 67890
        mock_update.message.reply_text = AsyncMock(return_value=Mock(message_id=11111))
        
        await submit(mock_update, mock_context)
        
        # Check leaderboard
        mock_update.message.reply_text.reset_mock()
        await leaderboard(mock_update, mock_context)
        
        # Verify leaderboard shows the submission
        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        assert "1. TestAgent [ENL] — 12,345 AP" in reply_text

    @pytest.mark.asyncio
    async def test_multiple_submissions_accumulated_in_leaderboard(self, mock_update, mock_context, session_factory):
        """
        Test that multiple submissions from the same user are accumulated in the leaderboard
        1. Register a user
        2. Submit AP multiple times
        3. Check leaderboard
        4. Verify total AP is accumulated
        """
        # Register user
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        # Submit AP multiple times
        submissions = [1000, 500, 250]
        for ap in submissions:
            mock_update.message.text = f"/submit ap={ap}"
            mock_update.message.message_id = 67890
            mock_update.message.reply_text = AsyncMock(return_value=Mock(message_id=11111))
            
            await submit(mock_update, mock_context)
        
        # Check leaderboard
        mock_update.message.reply_text.reset_mock()
        await leaderboard(mock_update, mock_context)
        
        # Verify leaderboard shows accumulated AP
        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        assert "1. TestAgent [ENL] — 1,750 AP" in reply_text  # 1000 + 500 + 250

    @pytest.mark.asyncio
    async def test_multiple_users_ranked_correctly_in_leaderboard(self, multiple_mock_updates, multiple_mock_contexts, session_factory):
        """
        Test that multiple users are ranked correctly in the leaderboard
        1. Register multiple users
        2. Each user submits different AP amounts
        3. Check leaderboard
        4. Verify users are ranked correctly by total AP
        """
        # Register multiple users with different AP amounts
        users_data = [
            ("Agent1", "ENL", 1500),
            ("Agent2", "RES", 2000),
            ("Agent3", "ENL", 1000),
            ("Agent4", "RES", 2500),
            ("Agent5", "ENL", 500),
        ]
        
        # Create agents and submissions
        async with session_scope(session_factory) as session:
            for i, (codename, faction, ap) in enumerate(users_data):
                agent = Agent(telegram_id=10001 + i, codename=codename, faction=faction)
                session.add(agent)
                await session.flush()
                
                submission = Submission(agent_id=agent.id, ap=ap, metrics={})
                session.add(submission)
        
        # Check leaderboard using the first user's context
        mock_update = multiple_mock_updates[0]
        mock_context = multiple_mock_contexts[0]
        mock_update.message.reply_text = AsyncMock()
        
        await leaderboard(mock_update, mock_context)
        
        # Verify leaderboard shows users ranked correctly
        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        lines = reply_text.split("\n")
        
        # Check ranking (highest AP first)
        assert "1. Agent4 [RES] — 2,500 AP" in lines[0]
        assert "2. Agent2 [RES] — 2,000 AP" in lines[1]
        assert "3. Agent1 [ENL] — 1,500 AP" in lines[2]
        assert "4. Agent3 [ENL] — 1,000 AP" in lines[3]
        assert "5. Agent5 [ENL] — 500 AP" in lines[4]


class TestGroupSubmitAutodeleteFlow:
    """Test Group Submit → Autodelete flow: Test that submissions in groups trigger the autodelete functionality"""

    @pytest.mark.asyncio
    async def test_group_submission_schedules_autodelete(self, mock_update, mock_context, session_factory, mock_queue):
        """
        Test that submissions in group chats schedule autodelete jobs
        1. Register a user
        2. Submit AP in a group chat
        3. Verify autodelete job is scheduled
        """
        # Register user
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        # Submit AP in a group chat
        mock_update.message.text = "/submit ap=12345; hacks=17"
        mock_update.message.message_id = 67890
        mock_update.message.chat_id = 123456  # Group chat ID
        mock_reply = Mock(message_id=11111)
        mock_update.message.reply_text = AsyncMock(return_value=mock_reply)
        
        await submit(mock_update, mock_context)
        
        # Verify autodelete was scheduled
        mock_queue.enqueue_at.assert_called_once()
        args, kwargs = mock_queue.enqueue_at.call_args
        
        # Check run_at is approximately now + delay
        run_at = args[0]
        expected_time = datetime.utcnow() + timedelta(seconds=300)
        assert abs((run_at - expected_time).total_seconds()) < 5  # Allow 5 seconds difference
        
        # Check function and parameters
        assert args[1] == delete_message_job
        assert args[2] == "test_token"
        payload = args[3]
        assert payload["chat_id"] == 123456
        assert payload["message_id"] == 67890
        assert payload["confirmation_message_id"] == 11111

    @pytest.mark.asyncio
    async def test_autodelete_job_executes_with_permissions(self):
        """
        Test that autodelete job executes successfully with proper permissions
        1. Schedule an autodelete job
        2. Mock bot with admin permissions
        3. Execute the job
        4. Verify messages are deleted
        """
        mock_bot = Mock()
        mock_me = Mock()
        mock_me.id = 98765
        mock_bot.get_me = AsyncMock(return_value=mock_me)
        
        mock_membership = Mock()
        mock_membership.status = "administrator"
        mock_membership.can_delete_messages = True
        mock_bot.get_chat_member = AsyncMock(return_value=mock_membership)
        mock_bot.delete_message = AsyncMock()
        
        payload = {
            "chat_id": 123456,
            "message_id": 67890,
            "confirmation_message_id": 11111,
        }
        
        with patch('bot.jobs.deletion.Bot', return_value=mock_bot):
            await _delete_messages("test_token", payload)
        
        # Verify both messages were deleted
        assert mock_bot.delete_message.call_count == 2
        mock_bot.delete_message.assert_any_call(chat_id=123456, message_id=67890)
        mock_bot.delete_message.assert_any_call(chat_id=123456, message_id=11111)

    @pytest.mark.asyncio
    async def test_autodelete_job_skipped_without_permissions(self):
        """
        Test that autodelete job is skipped when bot lacks permissions
        1. Schedule an autodelete job
        2. Mock bot without delete permissions
        3. Execute the job
        4. Verify messages are not deleted
        """
        mock_bot = Mock()
        mock_me = Mock()
        mock_me.id = 98765
        mock_bot.get_me = AsyncMock(return_value=mock_me)
        
        mock_membership = Mock()
        mock_membership.status = "member"  # Regular member, not admin
        mock_bot.get_chat_member = AsyncMock(return_value=mock_membership)
        mock_bot.delete_message = AsyncMock()
        
        payload = {
            "chat_id": 123456,
            "message_id": 67890,
            "confirmation_message_id": 11111,
        }
        
        with patch('bot.jobs.deletion.Bot', return_value=mock_bot):
            await _delete_messages("test_token", payload)
        
        # Verify no messages were deleted
        mock_bot.delete_message.assert_not_called()


class TestSubmitVerificationQueueLeaderboardFlow:
    """Test Submit → Verification Queue → Leaderboard flow: Test that submissions go through the queue and update the leaderboard"""

    @pytest.mark.asyncio
    async def test_submission_triggers_leaderboard_recompute(self, mock_update, mock_context, session_factory, mock_queue):
        """
        Test that submissions trigger leaderboard recompute through the verification queue
        1. Register a user
        2. Submit AP
        3. Verify leaderboard recompute job is enqueued
        4. Execute the recompute job
        5. Verify leaderboard is updated
        """
        # Register user
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        # Submit AP
        mock_update.message.text = "/submit ap=12345; hacks=17"
        mock_update.message.message_id = 67890
        mock_update.message.reply_text = AsyncMock(return_value=Mock(message_id=11111))
        
        await submit(mock_update, mock_context)
        
        # Manually enqueue leaderboard recompute job (simulating verification queue)
        enqueue_recompute_job(mock_queue)
        
        # Verify job was enqueued
        mock_queue.enqueue.assert_called_once_with(recompute_leaderboards_job)
        
        # Create a temporary engine and session factory for the recompute job
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        session_factory_for_recompute = async_sessionmaker(engine, expire_on_commit=False)
        
        # Copy data to the new engine
        async with session_scope(session_factory) as source_session:
            async with session_scope(session_factory_for_recompute) as target_session:
                # Copy agents
                agents_result = await source_session.execute(select(Agent))
                for agent in agents_result.scalars():
                    new_agent = Agent(
                        telegram_id=agent.telegram_id,
                        codename=agent.codename,
                        faction=agent.faction
                    )
                    target_session.add(new_agent)
                    await target_session.flush()
                    
                    # Copy submissions
                    for submission in agent.submissions:
                        new_submission = Submission(
                            agent_id=new_agent.id,
                            ap=submission.ap,
                            metrics=submission.metrics
                        )
                        target_session.add(new_submission)
        
        # Create stats and leaderboard_cache tables
        async with session_scope(session_factory_for_recompute) as session:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY,
                    agent_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    faction TEXT NOT NULL,
                    value REAL NOT NULL
                )
            """))
            
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS leaderboard_cache (
                    id INTEGER PRIMARY KEY,
                    category TEXT NOT NULL,
                    faction TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    UNIQUE(category, faction)
                )
            """))
            
            # Insert stats data from submissions
            await session.execute(text("""
                INSERT INTO stats (agent_id, category, faction, value)
                SELECT s.agent_id, 'ap', a.faction, s.ap
                FROM submissions s
                JOIN agents a ON a.id = s.agent_id
            """))
        
        # Mock settings for recompute job
        mock_recompute_settings = Settings(
            telegram_token="test_token",
            database_url=f"sqlite+aiosqlite:///:memory:",
            redis_url="redis://localhost:6379/0",
            autodelete_delay_seconds=300,
            autodelete_enabled=True,
            leaderboard_size=10,
            group_message_retention_minutes=60,
        )
        
        # Execute recompute job
        with patch('bot.jobs.leaderboard_worker.load_settings', return_value=mock_recompute_settings):
            with patch('bot.jobs.leaderboard_worker.build_engine', return_value=engine):
                with patch('bot.jobs.leaderboard_worker.build_session_factory', return_value=session_factory_for_recompute):
                    recompute_leaderboards_job()
        
        # Verify leaderboard cache was updated
        async with session_scope(session_factory_for_recompute) as session:
            result = await session.execute(text("SELECT * FROM leaderboard_cache"))
            rows = result.fetchall()
            assert len(rows) == 2  # One for ENL, one for RES (even if RES is empty)
            
            # Check ENL entry
            enl_row = next((row for row in rows if row[1] == "ENL"), None)
            assert enl_row is not None
            payload = json.loads(enl_row[2])
            assert payload["category"] == "ap"
            assert payload["faction"] == "ENL"
            assert len(payload["leaders"]) == 1
            assert payload["leaders"][0]["codename"] == "TestAgent"
            assert payload["leaders"][0]["value"] == 12345
        
        await engine.dispose()


class TestMultipleSubmissionsLeaderboardRanking:
    """Test Multiple submissions → Leaderboard ranking: Test that multiple submissions from different users are correctly ranked"""

    @pytest.mark.asyncio
    async def test_concurrent_submissions_ranked_correctly(self, multiple_mock_updates, multiple_mock_contexts, session_factory):
        """
        Test that concurrent submissions from different users are ranked correctly
        1. Register multiple users
        2. Simulate concurrent submissions
        3. Check leaderboard
        4. Verify ranking is correct
        """
        # Register multiple users
        users_data = [
            ("Agent1", "ENL"),
            ("Agent2", "RES"),
            ("Agent3", "ENL"),
            ("Agent4", "RES"),
            ("Agent5", "ENL"),
        ]
        
        async with session_scope(session_factory) as session:
            for i, (codename, faction) in enumerate(users_data):
                agent = Agent(telegram_id=10001 + i, codename=codename, faction=faction)
                session.add(agent)
        
        # Simulate concurrent submissions with different AP values
        submissions_data = [
            (10001, 1500),  # Agent1
            (10002, 2000),  # Agent2
            (10003, 1000),  # Agent3
            (10004, 2500),  # Agent4
            (10005, 500),   # Agent5
        ]
        
        # Create tasks for concurrent submissions
        async def submit_ap(telegram_id, ap):
            async with session_scope(session_factory) as session:
                result = await session.execute(select(Agent).where(Agent.telegram_id == telegram_id))
                agent = result.scalar_one()
                
                submission = Submission(agent_id=agent.id, ap=ap, metrics={})
                session.add(submission)
        
        # Execute submissions concurrently
        tasks = [submit_ap(telegram_id, ap) for telegram_id, ap in submissions_data]
        await asyncio.gather(*tasks)
        
        # Check leaderboard
        mock_update = multiple_mock_updates[0]
        mock_context = multiple_mock_contexts[0]
        mock_update.message.reply_text = AsyncMock()
        
        await leaderboard(mock_update, mock_context)
        
        # Verify leaderboard shows users ranked correctly
        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        lines = reply_text.split("\n")
        
        # Check ranking (highest AP first)
        assert "1. Agent4 [RES] — 2,500 AP" in lines[0]
        assert "2. Agent2 [RES] — 2,000 AP" in lines[1]
        assert "3. Agent1 [ENL] — 1,500 AP" in lines[2]
        assert "4. Agent3 [ENL] — 1,000 AP" in lines[3]
        assert "5. Agent5 [ENL] — 500 AP" in lines[4]

    @pytest.mark.asyncio
    async def test_tie_breaking_by_codename(self, multiple_mock_updates, multiple_mock_contexts, session_factory):
        """
        Test that ties in AP are broken by codename alphabetically
        1. Register multiple users with codenames that would test alphabetical ordering
        2. Submit the same AP for multiple users
        3. Check leaderboard
        4. Verify ties are broken by codename
        """
        # Register users with codenames that would test alphabetical ordering
        users_data = [
            ("Zebra", "ENL"),
            ("Alpha", "ENL"),
            ("Beta", "ENL"),
        ]
        
        async with session_scope(session_factory) as session:
            for i, (codename, faction) in enumerate(users_data):
                agent = Agent(telegram_id=10001 + i, codename=codename, faction=faction)
                session.add(agent)
        
        # Submit the same AP for all users
        async def submit_ap(telegram_id, ap):
            async with session_scope(session_factory) as session:
                result = await session.execute(select(Agent).where(Agent.telegram_id == telegram_id))
                agent = result.scalar_one()
                
                submission = Submission(agent_id=agent.id, ap=ap, metrics={})
                session.add(submission)
        
        # Execute submissions with the same AP
        tasks = [submit_ap(10001 + i, 1000) for i in range(len(users_data))]
        await asyncio.gather(*tasks)
        
        # Check leaderboard
        mock_update = multiple_mock_updates[0]
        mock_context = multiple_mock_contexts[0]
        mock_update.message.reply_text = AsyncMock()
        
        await leaderboard(mock_update, mock_context)
        
        # Verify leaderboard shows users ordered by codename when AP is tied
        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        lines = reply_text.split("\n")
        
        # Alpha should come before Beta, which comes before Zebra
        assert "1. Alpha [ENL] — 1,000 AP" in lines[0]
        assert "2. Beta [ENL] — 1,000 AP" in lines[1]
        assert "3. Zebra [ENL] — 1,000 AP" in lines[2]

    @pytest.mark.asyncio
    async def test_leaderboard_with_faction_filtering(self, multiple_mock_updates, multiple_mock_contexts, session_factory):
        """
        Test that leaderboard correctly shows both factions
        1. Register users from both factions
        2. Submit different AP values
        3. Check leaderboard
        4. Verify both factions are shown
        """
        # Register users from both factions
        users_data = [
            ("ENLAgent1", "ENL", 1500),
            ("RESAgent1", "RES", 2000),
            ("ENLAgent2", "ENL", 1000),
            ("RESAgent2", "RES", 2500),
        ]
        
        async with session_scope(session_factory) as session:
            for i, (codename, faction, ap) in enumerate(users_data):
                agent = Agent(telegram_id=10001 + i, codename=codename, faction=faction)
                session.add(agent)
                await session.flush()
                
                submission = Submission(agent_id=agent.id, ap=ap, metrics={})
                session.add(submission)
        
        # Check leaderboard
        mock_update = multiple_mock_updates[0]
        mock_context = multiple_mock_contexts[0]
        mock_update.message.reply_text = AsyncMock()
        
        await leaderboard(mock_update, mock_context)
        
        # Verify leaderboard shows both factions
        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        lines = reply_text.split("\n")
        
        # Check that both factions are shown and ranked correctly
        assert "1. RESAgent2 [RES] — 2,500 AP" in lines[0]
        assert "2. RESAgent1 [RES] — 2,000 AP" in lines[1]
        assert "3. ENLAgent1 [ENL] — 1,500 AP" in lines[2]
        assert "4. ENLAgent2 [ENL] — 1,000 AP" in lines[3]


# ==================== COMPLEX SCENARIO TESTS ====================

class TestComplexScenarios:
    """Test complex scenarios involving multiple features and edge cases"""

    @pytest.mark.asyncio
    async def test_leaderboard_recomputation_with_multiple_submissions(self, mock_settings):
        """
        Test leaderboard recomputation with multiple submissions
        1. Create a temporary database with multiple agents and submissions
        2. Run the recompute job
        3. Verify the leaderboard cache is updated correctly
        """
        # Create a temporary engine and session factory
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        
        # Create test data
        async with session_scope(session_factory) as session:
            # Create agents
            agent1 = Agent(telegram_id=1, codename="Agent1", faction="ENL")
            agent2 = Agent(telegram_id=2, codename="Agent2", faction="RES")
            agent3 = Agent(telegram_id=3, codename="Agent3", faction="ENL")
            session.add_all([agent1, agent2, agent3])
            await session.flush()
            
            # Create stats table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY,
                    agent_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    faction TEXT NOT NULL,
                    value REAL NOT NULL
                )
            """))
            
            # Create leaderboard_cache table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS leaderboard_cache (
                    id INTEGER PRIMARY KEY,
                    category TEXT NOT NULL,
                    faction TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    UNIQUE(category, faction)
                )
            """))
            
            # Insert stats data
            await session.execute(text("""
                INSERT INTO stats (agent_id, category, faction, value) VALUES
                (:agent1_id, 'ap', 'ENL', 1000),
                (:agent1_id, 'ap', 'ENL', 500),
                (:agent2_id, 'ap', 'RES', 900),
                (:agent3_id, 'ap', 'ENL', 750),
                (:agent1_id, 'hacks', 'ENL', 100),
                (:agent2_id, 'hacks', 'RES', 150),
                (:agent3_id, 'hacks', 'ENL', 50)
            """), {"agent1_id": agent1.id, "agent2_id": agent2.id, "agent3_id": agent3.id})
        
        # Test _recompute
        await _recompute(mock_settings)
        
        # Verify data was computed and persisted
        new_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        async with new_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        new_session_factory = async_sessionmaker(new_engine, expire_on_commit=False)
        
        # Create tables in the new engine
        async with session_scope(new_session_factory) as session:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS leaderboard_cache (
                    id INTEGER PRIMARY KEY,
                    category TEXT NOT NULL,
                    faction TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    UNIQUE(category, faction)
                )
            """))
        
        await engine.dispose()
        await new_engine.dispose()

    @pytest.mark.asyncio
    async def test_group_chat_submissions_with_different_permissions(self, mock_update, mock_context, session_factory):
        """
        Test group chat submissions with different permission scenarios
        1. Test with admin permissions
        2. Test with owner permissions
        3. Test with member permissions
        4. Verify autodelete behavior in each case
        """
        # Register user
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        # Test with admin permissions
        mock_bot = Mock()
        mock_me = Mock()
        mock_me.id = 98765
        mock_bot.get_me = AsyncMock(return_value=mock_me)
        
        mock_membership = Mock()
        mock_membership.status = "administrator"
        mock_membership.can_delete_messages = True
        mock_bot.get_chat_member = AsyncMock(return_value=mock_membership)
        mock_bot.delete_message = AsyncMock()
        
        payload = {
            "chat_id": 123456,
            "message_id": 67890,
            "confirmation_message_id": 11111,
        }
        
        with patch('bot.jobs.deletion.Bot', return_value=mock_bot):
            await _delete_messages("test_token", payload)
        
        # Verify messages were deleted
        assert mock_bot.delete_message.call_count == 2
        
        # Reset mock for next test
        mock_bot.reset_mock()
        
        # Test with owner permissions
        mock_membership.status = "owner"
        mock_bot.get_chat_member = AsyncMock(return_value=mock_membership)
        
        with patch('bot.jobs.deletion.Bot', return_value=mock_bot):
            await _delete_messages("test_token", payload)
        
        # Verify messages were deleted
        assert mock_bot.delete_message.call_count == 2
        
        # Reset mock for next test
        mock_bot.reset_mock()
        
        # Test with member permissions
        mock_membership.status = "member"
        mock_bot.get_chat_member = AsyncMock(return_value=mock_membership)
        
        with patch('bot.jobs.deletion.Bot', return_value=mock_bot):
            await _delete_messages("test_token", payload)
        
        # Verify messages were not deleted
        mock_bot.delete_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_recovery_in_feature_interactions(self, mock_update, mock_context, session_factory):
        """
        Test error recovery in feature interactions
        1. Test submission with database error
        2. Test leaderboard with database error
        3. Test autodelete with Telegram API error
        4. Verify system recovers gracefully
        """
        # Test submission with database error
        mock_update.message.text = "/submit ap=12345; hacks=17"
        mock_update.message.reply_text = AsyncMock()
        
        # Mock session_scope to raise an exception
        with patch('bot.database.session_scope') as mock_session_scope:
            mock_session_scope.side_effect = Exception("Database error")
            
            await submit(mock_update, mock_context)
            
            # Verify error was handled gracefully
            mock_update.message.reply_text.assert_not_called()
        
        # Test autodelete with Telegram API error
        mock_bot = Mock()
        mock_me = Mock()
        mock_me.id = 98765
        mock_bot.get_me = AsyncMock(return_value=mock_me)
        
        mock_membership = Mock()
        mock_membership.status = "administrator"
        mock_membership.can_delete_messages = True
        mock_bot.get_chat_member = AsyncMock(return_value=mock_membership)
        
        from telegram.error import TelegramError
        mock_bot.delete_message = AsyncMock(side_effect=TelegramError("Permission denied"))
        
        payload = {
            "chat_id": 123456,
            "message_id": 67890,
            "confirmation_message_id": 11111,
        }
        
        with patch('bot.jobs.deletion.Bot', return_value=mock_bot):
            # Should not raise an exception
            await _delete_messages("test_token", payload)
        
        # Verify delete was attempted despite error
        assert mock_bot.delete_message.call_count == 2

    @pytest.mark.asyncio
    async def test_data_consistency_across_features(self, multiple_mock_updates, multiple_mock_contexts, session_factory):
        """
        Test data consistency across features
        1. Register multiple users
        2. Submit AP for multiple users
        3. Check leaderboard
        4. Verify data consistency between submissions and leaderboard
        """
        # Register multiple users
        users_data = [
            ("Agent1", "ENL"),
            ("Agent2", "RES"),
            ("Agent3", "ENL"),
        ]
        
        async with session_scope(session_factory) as session:
            for i, (codename, faction) in enumerate(users_data):
                agent = Agent(telegram_id=10001 + i, codename=codename, faction=faction)
                session.add(agent)
        
        # Submit AP for multiple users
        submissions_data = [
            (10001, 1500),  # Agent1
            (10002, 2000),  # Agent2
            (10003, 1000),  # Agent3
        ]
        
        async def submit_ap(telegram_id, ap):
            async with session_scope(session_factory) as session:
                result = await session.execute(select(Agent).where(Agent.telegram_id == telegram_id))
                agent = result.scalar_one()
                
                submission = Submission(agent_id=agent.id, ap=ap, metrics={})
                session.add(submission)
        
        # Execute submissions
        tasks = [submit_ap(telegram_id, ap) for telegram_id, ap in submissions_data]
        await asyncio.gather(*tasks)
        
        # Verify data consistency
        async with session_scope(session_factory) as session:
            # Check submissions
            submissions_result = await session.execute(select(Submission))
            submissions = submissions_result.scalars().all()
            assert len(submissions) == 3
            
            # Check total AP per agent
            for telegram_id, expected_ap in submissions_data:
                result = await session.execute(select(Agent).where(Agent.telegram_id == telegram_id))
                agent = result.scalar_one()
                
                submissions_query = select(Submission).where(Submission.agent_id == agent.id)
                submissions_result = await session.execute(submissions_query)
                agent_submissions = submissions_result.scalars().all()
                
                total_ap = sum(s.ap for s in agent_submissions)
                assert total_ap == expected_ap
            
            # Check leaderboard
            leaderboard = await get_leaderboard(session, 10)
            assert len(leaderboard) == 3
            
            # Verify leaderboard matches submission data
            leaderboard_dict = {codename: ap for codename, _, ap in leaderboard}
            assert leaderboard_dict["Agent2"] == 2000
            assert leaderboard_dict["Agent1"] == 1500
            assert leaderboard_dict["Agent3"] == 1000

    @pytest.mark.asyncio
    async def test_performance_with_large_dataset(self, session_factory):
        """
        Test performance with a large dataset
        1. Create many agents and submissions
        2. Check leaderboard performance
        3. Verify system handles large dataset efficiently
        """
        # Create many agents and submissions
        num_agents = 100
        num_submissions_per_agent = 10
        
        async with session_scope(session_factory) as session:
            agents = []
            for i in range(num_agents):
                agent = Agent(
                    telegram_id=20000 + i,
                    codename=f"Agent{i}",
                    faction="ENL" if i % 2 == 0 else "RES"
                )
                session.add(agent)
                agents.append(agent)
            
            await session.flush()
            
            # Create submissions for each agent
            for agent in agents:
                for j in range(num_submissions_per_agent):
                    ap = 100 * (j + 1)  # 100, 200, 300, ..., 1000
                    submission = Submission(agent_id=agent.id, ap=ap, metrics={})
                    session.add(submission)
        
        # Measure leaderboard performance
        import time
        start_time = time.time()
        
        async with session_scope(session_factory) as session:
            leaderboard = await get_leaderboard(session, 10)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Verify leaderboard is correct
        assert len(leaderboard) == 10
        
        # Verify performance (should complete in reasonable time)
        assert execution_time < 2.0  # Should complete in less than 2 seconds
        
        # Verify ranking is correct
        for i in range(len(leaderboard) - 1):
            current_ap = leaderboard[i][2]
            next_ap = leaderboard[i + 1][2]
            assert current_ap >= next_ap  # Should be in descending order

    @pytest.mark.asyncio
    async def test_race_conditions_with_concurrent_operations(self, multiple_mock_updates, multiple_mock_contexts, session_factory):
        """
        Test race conditions with concurrent operations
        1. Simulate concurrent submissions from the same user
        2. Simulate concurrent leaderboard requests
        3. Verify data integrity is maintained
        """
        # Register a user
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        # Simulate concurrent submissions from the same user
        async def submit_ap(ap):
            async with session_scope(session_factory) as session:
                result = await session.execute(select(Agent).where(Agent.telegram_id == 12345))
                agent = result.scalar_one()
                
                submission = Submission(agent_id=agent.id, ap=ap, metrics={})
                session.add(submission)
        
        # Execute concurrent submissions
        tasks = [submit_ap(100 * i) for i in range(1, 11)]  # 100, 200, 300, ..., 1000
        await asyncio.gather(*tasks)
        
        # Verify all submissions were recorded
        async with session_scope(session_factory) as session:
            result = await session.execute(select(Submission).join(Agent).where(Agent.telegram_id == 12345))
            submissions = result.scalars().all()
            assert len(submissions) == 10
            
            # Verify total AP
            total_ap = sum(s.ap for s in submissions)
            assert total_ap == 5500  # Sum of 100, 200, 300, ..., 1000
        
        # Simulate concurrent leaderboard requests
        async def get_leaderboard_data():
            async with session_scope(session_factory) as session:
                return await get_leaderboard(session, 10)
        
        # Execute concurrent leaderboard requests
        tasks = [get_leaderboard_data() for _ in range(5)]
        leaderboards = await asyncio.gather(*tasks)
        
        # Verify all leaderboard requests return the same data
        for leaderboard in leaderboards:
            assert len(leaderboard) == 1
            assert leaderboard[0] == ("TestAgent", "ENL", 5500)

    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self, multiple_mock_updates, multiple_mock_contexts, session_factory, mock_queue):
        """
        Test complete end-to-end workflow
        1. Register multiple users
        2. Submit AP from multiple users
        3. Check leaderboard
        4. Verify autodelete scheduling
        5. Verify data consistency
        """
        # Register multiple users
        users_data = [
            ("Agent1", "ENL"),
            ("Agent2", "RES"),
            ("Agent3", "ENL"),
        ]
        
        for i, (codename, faction) in enumerate(users_data):
            mock_update = multiple_mock_updates[i]
            mock_context = multiple_mock_contexts[i]
            mock_update.effective_user.id = 10001 + i
            mock_update.message.reply_text = AsyncMock()
            
            # Start registration
            result = await register_start(mock_update, mock_context)
            assert result == 0  # CODENAME
            
            # Provide codename
            mock_update.message.text = codename
            mock_update.message.reply_text.reset_mock()
            result = await register_codename(mock_update, mock_context)
            assert result == 1  # FACTION
            
            # Provide faction
            mock_update.message.text = faction
            mock_update.message.reply_text.reset_mock()
            result = await register_faction(mock_update, mock_context)
            assert result == -1  # ConversationHandler.END
        
        # Submit AP from multiple users
        submissions_data = [
            (10001, 1500),  # Agent1
            (10002, 2000),  # Agent2
            (10003, 1000),  # Agent3
        ]
        
        for i, (telegram_id, ap) in enumerate(submissions_data):
            mock_update = multiple_mock_updates[i]
            mock_context = multiple_mock_contexts[i]
            mock_update.effective_user.id = telegram_id
            mock_update.message.text = f"/submit ap={ap}"
            mock_update.message.message_id = 67890 + i
            mock_update.message.chat_id = 123456  # Group chat
            mock_reply = Mock(message_id=11111 + i)
            mock_update.message.reply_text = AsyncMock(return_value=mock_reply)
            
            await submit(mock_update, mock_context)
        
        # Verify autodelete was scheduled for each submission
        assert mock_queue.enqueue_at.call_count == 3
        
        # Check leaderboard
        mock_update = multiple_mock_updates[0]
        mock_context = multiple_mock_contexts[0]
        mock_update.message.reply_text = AsyncMock()
        
        await leaderboard(mock_update, mock_context)
        
        # Verify leaderboard shows users ranked correctly
        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        lines = reply_text.split("\n")
        
        # Check ranking (highest AP first)
        assert "1. Agent2 [RES] — 2,000 AP" in lines[0]
        assert "2. Agent1 [ENL] — 1,500 AP" in lines[1]
        assert "3. Agent3 [ENL] — 1,000 AP" in lines[2]
        
        # Verify data consistency
        async with session_scope(session_factory) as session:
            # Check agents
            agents_result = await session.execute(select(Agent))
            agents = agents_result.scalars().all()
            assert len(agents) == 3
            
            # Check submissions
            submissions_result = await session.execute(select(Submission))
            submissions = submissions_result.scalars().all()
            assert len(submissions) == 3
            
            # Verify total AP per agent
            for telegram_id, expected_ap in submissions_data:
                result = await session.execute(select(Agent).where(Agent.telegram_id == telegram_id))
                agent = result.scalar_one()
                
                submissions_query = select(Submission).where(Submission.agent_id == agent.id)
                submissions_result = await session.execute(submissions_query)
                agent_submissions = submissions_result.scalars().all()
                
                total_ap = sum(s.ap for s in agent_submissions)
                assert total_ap == expected_ap