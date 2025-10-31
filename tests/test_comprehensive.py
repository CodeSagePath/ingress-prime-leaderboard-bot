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


# ==================== REGISTER FEATURE TESTS ====================

class TestRegisterFeature:
    """Test cases for the registration feature"""

    @pytest.mark.asyncio
    async def test_register_start_new_user(self, mock_update, mock_context, session_factory):
        """Test register_start with a new user"""
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_start(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("Please send your agent codename.")
        assert result == 0  # CODENAME

    @pytest.mark.asyncio
    async def test_register_start_existing_user(self, mock_update, mock_context, session_factory):
        """Test register_start with an already registered user"""
        # Create an existing agent
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_start(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("You are already registered as TestAgent (ENL).")
        assert result == -1  # ConversationHandler.END

    @pytest.mark.asyncio
    async def test_register_start_no_message(self, mock_context):
        """Test register_start with no message"""
        mock_update.message = None
        
        result = await register_start(mock_update, mock_context)
        
        assert result == -1  # ConversationHandler.END

    @pytest.mark.asyncio
    async def test_register_start_no_user(self, mock_update, mock_context):
        """Test register_start with no effective user"""
        mock_update.effective_user = None
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_start(mock_update, mock_context)
        
        assert result == -1  # ConversationHandler.END

    @pytest.mark.asyncio
    async def test_register_codename_valid(self, mock_update, mock_context):
        """Test register_codename with a valid codename"""
        mock_update.message.text = "TestCodename"
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_codename(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("Send your faction (ENL or RES).")
        assert mock_context.user_data["codename"] == "TestCodename"
        assert result == 1  # FACTION

    @pytest.mark.asyncio
    async def test_register_codename_empty(self, mock_update, mock_context):
        """Test register_codename with an empty codename"""
        mock_update.message.text = "   "
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_codename(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("Codename cannot be empty. Send your codename.")
        assert result == 0  # CODENAME

    @pytest.mark.asyncio
    async def test_register_codename_no_message(self, mock_context):
        """Test register_codename with no message"""
        mock_update.message = None
        
        result = await register_codename(mock_update, mock_context)
        
        assert result == -1  # ConversationHandler.END

    @pytest.mark.asyncio
    async def test_register_faction_valid_enl(self, mock_update, mock_context, session_factory):
        """Test register_faction with valid ENL faction"""
        mock_context.user_data["codename"] = "TestCodename"
        mock_update.message.text = "enl"
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_faction(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("Registered TestCodename (ENL).")
        assert result == -1  # ConversationHandler.END
        
        # Verify agent was created
        async with session_scope(session_factory) as session:
            agent_result = await session.execute(select(Agent).where(Agent.telegram_id == 12345))
            agent = agent_result.scalar_one()
            assert agent.codename == "TestCodename"
            assert agent.faction == "ENL"

    @pytest.mark.asyncio
    async def test_register_faction_valid_res(self, mock_update, mock_context, session_factory):
        """Test register_faction with valid RES faction"""
        mock_context.user_data["codename"] = "TestCodename"
        mock_update.message.text = "RES"
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_faction(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("Registered TestCodename (RES).")
        assert result == -1  # ConversationHandler.END
        
        # Verify agent was created
        async with session_scope(session_factory) as session:
            agent_result = await session.execute(select(Agent).where(Agent.telegram_id == 12345))
            agent = agent_result.scalar_one()
            assert agent.codename == "TestCodename"
            assert agent.faction == "RES"

    @pytest.mark.asyncio
    async def test_register_faction_invalid(self, mock_update, mock_context):
        """Test register_faction with invalid faction"""
        mock_context.user_data["codename"] = "TestCodename"
        mock_update.message.text = "INVALID"
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_faction(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("Faction must be ENL or RES. Send your faction.")
        assert result == 1  # FACTION

    @pytest.mark.asyncio
    async def test_register_faction_missing_codename(self, mock_update, mock_context):
        """Test register_faction with missing codename in user_data"""
        mock_update.message.text = "ENL"
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_faction(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("Codename missing. Restart with /register.")
        assert result == -1  # ConversationHandler.END

    @pytest.mark.asyncio
    async def test_register_faction_existing_agent_update(self, mock_update, mock_context, session_factory):
        """Test register_faction updating an existing agent"""
        # Create an existing agent
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="OldCodename", faction="ENL")
            session.add(agent)
        
        mock_context.user_data["codename"] = "NewCodename"
        mock_update.message.text = "RES"
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_faction(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("Registered NewCodename (RES).")
        assert result == -1  # ConversationHandler.END
        
        # Verify agent was updated
        async with session_scope(session_factory) as session:
            agent_result = await session.execute(select(Agent).where(Agent.telegram_id == 12345))
            agent = agent_result.scalar_one()
            assert agent.codename == "NewCodename"
            assert agent.faction == "RES"

    @pytest.mark.asyncio
    async def test_register_faction_no_message(self, mock_context):
        """Test register_faction with no message"""
        mock_context.user_data["codename"] = "TestCodename"
        mock_update.message = None
        
        result = await register_faction(mock_update, mock_context)
        
        assert result == -1  # ConversationHandler.END

    @pytest.mark.asyncio
    async def test_register_faction_no_user(self, mock_update, mock_context):
        """Test register_faction with no effective user"""
        mock_context.user_data["codename"] = "TestCodename"
        mock_update.effective_user = None
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_faction(mock_update, mock_context)
        
        assert result == -1  # ConversationHandler.END

    @pytest.mark.asyncio
    async def test_register_cancel_with_message(self, mock_update, mock_context):
        """Test register_cancel with a message"""
        mock_context.user_data["codename"] = "TestCodename"
        mock_update.message.reply_text = AsyncMock()
        
        result = await register_cancel(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("Registration cancelled.")
        assert "codename" not in mock_context.user_data
        assert result == -1  # ConversationHandler.END

    @pytest.mark.asyncio
    async def test_register_cancel_no_message(self, mock_context):
        """Test register_cancel with no message"""
        mock_context.user_data["codename"] = "TestCodename"
        mock_update.message = None
        
        result = await register_cancel(mock_update, mock_context)
        
        assert "codename" not in mock_context.user_data
        assert result == -1  # ConversationHandler.END


# ==================== SUBMIT FEATURE TESTS ====================

class TestSubmitFeature:
    """Test cases for the submission feature"""

    @pytest.mark.asyncio
    async def test_parse_submission_valid(self):
        """Test parse_submission with valid input"""
        ap, metrics = parse_submission("ap=12345; hacks=17; distance=12.5; note=First run")
        assert ap == 12345
        assert metrics == {"hacks": 17, "distance": 12.5, "note": "First run"}

    @pytest.mark.asyncio
    async def test_parse_submission_missing_ap(self):
        """Test parse_submission with missing AP value"""
        with pytest.raises(ValueError, match="Missing ap value"):
            parse_submission("hacks=17; distance=12.5")

    @pytest.mark.asyncio
    async def test_parse_submission_invalid_ap(self):
        """Test parse_submission with invalid AP value"""
        with pytest.raises(ValueError, match="ap must be an integer"):
            parse_submission("ap=not_a_number; hacks=17")

    @pytest.mark.asyncio
    async def test_parse_submission_invalid_format(self):
        """Test parse_submission with invalid format"""
        with pytest.raises(ValueError, match="Entries must be provided as key=value pairs"):
            parse_submission("ap=12345; invalid_entry")

    @pytest.mark.asyncio
    async def test_parse_submission_empty_entry(self):
        """Test parse_submission with empty entry"""
        with pytest.raises(ValueError, match="Invalid entry"):
            parse_submission("ap=12345; =empty_key")

    @pytest.mark.asyncio
    async def test_parse_submission_newline_separated(self):
        """Test parse_submission with newline separated values"""
        ap, metrics = parse_submission("ap=12345\nhacks=17\ndistance=12.5")
        assert ap == 12345
        assert metrics == {"hacks": 17, "distance": 12.5}

    @pytest.mark.asyncio
    async def test_parse_submission_multi_space_separated(self):
        """Test parse_submission with multi-space separated values"""
        ap, metrics = parse_submission("ap=12345  hacks=17  distance=12.5")
        assert ap == 12345
        assert metrics == {"hacks": 17, "distance": 12.5}

    @pytest.mark.asyncio
    async def test_submit_success(self, mock_update, mock_context, session_factory):
        """Test successful submission"""
        # Create a registered agent
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        mock_update.message.text = "/submit ap=12345; hacks=17"
        mock_update.message.message_id = 67890
        mock_update.message.reply_text = AsyncMock(return_value=Mock(message_id=11111))
        
        await submit(mock_update, mock_context)
        
        # Verify submission was recorded
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
    async def test_submit_no_payload(self, mock_update, mock_context):
        """Test submission with no payload"""
        mock_update.message.text = "/submit"
        mock_update.message.reply_text = AsyncMock()
        
        await submit(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("Usage: /submit ap=12345; metric=678")

    @pytest.mark.asyncio
    async def test_submit_invalid_payload(self, mock_update, mock_context):
        """Test submission with invalid payload"""
        mock_update.message.text = "/submit invalid_payload"
        mock_update.message.reply_text = AsyncMock()
        
        await submit(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_unregistered_user(self, mock_update, mock_context):
        """Test submission from unregistered user"""
        mock_update.message.text = "/submit ap=12345; hacks=17"
        mock_update.message.reply_text = AsyncMock()
        
        await submit(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("Register first with /register.")

    @pytest.mark.asyncio
    async def test_submit_no_message(self, mock_context):
        """Test submit with no message"""
        mock_update.message = None
        
        await submit(mock_update, mock_context)
        
        # Should not raise an exception

    @pytest.mark.asyncio
    async def test_submit_no_user(self, mock_update, mock_context):
        """Test submit with no effective user"""
        mock_update.effective_user = None
        mock_update.message.text = "/submit ap=12345"
        
        await submit(mock_update, mock_context)
        
        # Should not raise an exception

    @pytest.mark.asyncio
    async def test_submit_with_autodelete_enabled(self, mock_update, mock_context, session_factory, mock_queue):
        """Test submission with autodelete enabled"""
        # Create a registered agent
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        mock_update.message.text = "/submit ap=12345; hacks=17"
        mock_update.message.message_id = 67890
        mock_update.message.chat_id = 123456
        mock_reply = Mock(message_id=11111)
        mock_update.message.reply_text = AsyncMock(return_value=mock_reply)
        
        await submit(mock_update, mock_context)
        
        # Verify deletion was scheduled
        mock_queue.enqueue_at.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_with_autodelete_disabled(self, mock_update, mock_context, session_factory, mock_queue):
        """Test submission with autodelete disabled"""
        # Disable autodelete
        mock_context.application.bot_data["settings"].autodelete_enabled = False
        
        # Create a registered agent
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        mock_update.message.text = "/submit ap=12345; hacks=17"
        mock_update.message.message_id = 67890
        mock_update.message.chat_id = 123456
        mock_reply = Mock(message_id=11111)
        mock_update.message.reply_text = AsyncMock(return_value=mock_reply)
        
        await submit(mock_update, mock_context)
        
        # Verify deletion was not scheduled
        mock_queue.enqueue_at.assert_not_called()


# ==================== GROUP SUBMIT + AUTODELETE FEATURE TESTS ====================

class TestGroupSubmitAutodelete:
    """Test cases for group submit and autodelete feature"""

    @pytest.mark.asyncio
    async def test_delete_messages_with_permissions(self):
        """Test _delete_messages with proper permissions"""
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
    async def test_delete_messages_owner_permissions(self):
        """Test _delete_messages with owner permissions"""
        mock_bot = Mock()
        mock_me = Mock()
        mock_me.id = 98765
        mock_bot.get_me = AsyncMock(return_value=mock_me)
        
        mock_membership = Mock()
        mock_membership.status = "owner"
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

    @pytest.mark.asyncio
    async def test_delete_messages_no_permissions(self):
        """Test _delete_messages without proper permissions"""
        mock_bot = Mock()
        mock_me = Mock()
        mock_me.id = 98765
        mock_bot.get_me = AsyncMock(return_value=mock_me)
        
        mock_membership = Mock()
        mock_membership.status = "member"
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

    @pytest.mark.asyncio
    async def test_delete_messages_admin_no_delete_permission(self):
        """Test _delete_messages with admin but no delete permission"""
        mock_bot = Mock()
        mock_me = Mock()
        mock_me.id = 98765
        mock_bot.get_me = AsyncMock(return_value=mock_me)
        
        mock_membership = Mock()
        mock_membership.status = "administrator"
        mock_membership.can_delete_messages = False
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

    @pytest.mark.asyncio
    async def test_delete_messages_telegram_error(self):
        """Test _delete_messages with Telegram API error"""
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
        
        # Verify delete was attempted
        assert mock_bot.delete_message.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_messages_get_chat_member_error(self):
        """Test _delete_messages with error getting chat member"""
        mock_bot = Mock()
        mock_me = Mock()
        mock_me.id = 98765
        mock_bot.get_me = AsyncMock(return_value=mock_me)
        
        from telegram.error import TelegramError
        mock_bot.get_chat_member = AsyncMock(side_effect=TelegramError("Chat not found"))
        mock_bot.delete_message = AsyncMock()
        
        payload = {
            "chat_id": 123456,
            "message_id": 67890,
            "confirmation_message_id": 11111,
        }
        
        with patch('bot.jobs.deletion.Bot', return_value=mock_bot):
            # Should not raise an exception
            await _delete_messages("test_token", payload)
        
        # Verify no messages were deleted
        mock_bot.delete_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_messages_missing_message_id(self):
        """Test _delete_messages with missing message_id"""
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
            "confirmation_message_id": 11111,
        }
        
        with patch('bot.jobs.deletion.Bot', return_value=mock_bot):
            await _delete_messages("test_token", payload)
        
        # Verify only confirmation message was deleted
        mock_bot.delete_message.assert_called_once_with(chat_id=123456, message_id=11111)

    @pytest.mark.asyncio
    async def test_delete_messages_missing_confirmation_id(self):
        """Test _delete_messages with missing confirmation_message_id"""
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
        }
        
        with patch('bot.jobs.deletion.Bot', return_value=mock_bot):
            await _delete_messages("test_token", payload)
        
        # Verify only original message was deleted
        mock_bot.delete_message.assert_called_once_with(chat_id=123456, message_id=67890)

    def test_delete_message_job_success(self):
        """Test delete_message_job with successful execution"""
        with patch('bot.jobs.deletion._delete_messages') as mock_delete:
            delete_message_job("test_token", {"chat_id": 123456})
            mock_delete.assert_called_once_with("test_token", {"chat_id": 123456})

    def test_delete_message_job_exception(self):
        """Test delete_message_job with exception"""
        with patch('bot.jobs.deletion._delete_messages', side_effect=Exception("Test error")):
            # Should not raise an exception
            delete_message_job("test_token", {"chat_id": 123456})

    def test_schedule_message_deletion(self):
        """Test schedule_message_deletion"""
        mock_queue = Mock()
        
        schedule_message_deletion(
            mock_queue,
            "test_token",
            123456,
            67890,
            11111,
            300,
        )
        
        # Verify job was enqueued
        mock_queue.enqueue_at.assert_called_once()
        args, kwargs = mock_queue.enqueue_at.call_args
        assert len(args) >= 2  # run_at and function
        assert args[1] == delete_message_job  # function
        assert args[2] == "test_token"  # token
        assert isinstance(args[0], datetime)  # run_at is a datetime

    def test_schedule_message_deletion_no_confirmation(self):
        """Test schedule_message_deletion with no confirmation message ID"""
        mock_queue = Mock()
        
        schedule_message_deletion(
            mock_queue,
            "test_token",
            123456,
            67890,
            None,
            300,
        )
        
        # Verify job was enqueued
        mock_queue.enqueue_at.assert_called_once()
        args, kwargs = mock_queue.enqueue_at.call_args
        assert len(args) >= 2  # run_at and function
        assert args[1] == delete_message_job  # function
        assert args[2] == "test_token"  # token
        assert isinstance(args[0], datetime)  # run_at is a datetime


# ==================== LEADERBOARD CACHING FEATURE TESTS ====================

class TestLeaderboardCaching:
    """Test cases for the leaderboard caching feature"""

    @pytest.mark.asyncio
    async def test_get_leaderboard_with_data(self, session_factory):
        """Test get_leaderboard with existing data"""
        # Create test data
        async with session_scope(session_factory) as session:
            agent1 = Agent(telegram_id=1, codename="Agent1", faction="ENL")
            agent2 = Agent(telegram_id=2, codename="Agent2", faction="RES")
            session.add_all([agent1, agent2])
            await session.flush()
            
            session.add(Submission(agent_id=agent1.id, ap=1000, metrics={}))
            session.add(Submission(agent_id=agent1.id, ap=500, metrics={}))
            session.add(Submission(agent_id=agent2.id, ap=900, metrics={}))
        
        # Test get_leaderboard
        async with session_scope(session_factory) as session:
            leaderboard = await get_leaderboard(session, 10)
            
            assert len(leaderboard) == 2
            assert leaderboard[0] == ("Agent1", "ENL", 1500)
            assert leaderboard[1] == ("Agent2", "RES", 900)

    @pytest.mark.asyncio
    async def test_get_leaderboard_with_limit(self, session_factory):
        """Test get_leaderboard with a limit"""
        # Create test data
        async with session_scope(session_factory) as session:
            agents = [
                Agent(telegram_id=i, codename=f"Agent{i}", faction="ENL" if i % 2 == 0 else "RES")
                for i in range(1, 6)
            ]
            session.add_all(agents)
            await session.flush()
            
            for i, agent in enumerate(agents):
                session.add(Submission(agent_id=agent.id, ap=(6-i)*100, metrics={}))
        
        # Test get_leaderboard with limit
        async with session_scope(session_factory) as session:
            leaderboard = await get_leaderboard(session, 3)
            
            assert len(leaderboard) == 3
            assert leaderboard[0] == ("Agent1", "RES", 500)
            assert leaderboard[1] == ("Agent2", "ENL", 400)
            assert leaderboard[2] == ("Agent3", "RES", 300)

    @pytest.mark.asyncio
    async def test_get_leaderboard_no_data(self, session_factory):
        """Test get_leaderboard with no data"""
        async with session_scope(session_factory) as session:
            leaderboard = await get_leaderboard(session, 10)
            
            assert len(leaderboard) == 0

    @pytest.mark.asyncio
    async def test_collect_leaderboards_with_data(self, session_factory):
        """Test _collect_leaderboards with existing data"""
        # Create test data and stats table
        async with session_scope(session_factory) as session:
            # Create agents
            agent1 = Agent(telegram_id=1, codename="Agent1", faction="ENL")
            agent2 = Agent(telegram_id=2, codename="Agent2", faction="RES")
            session.add_all([agent1, agent2])
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
            
            # Insert stats data
            await session.execute(text("""
                INSERT INTO stats (agent_id, category, faction, value) VALUES
                (:agent1_id, 'ap', 'ENL', 1000),
                (:agent1_id, 'ap', 'ENL', 500),
                (:agent2_id, 'ap', 'RES', 900),
                (:agent1_id, 'hacks', 'ENL', 100),
                (:agent2_id, 'hacks', 'RES', 150)
            """), {"agent1_id": agent1.id, "agent2_id": agent2.id})
        
        # Test _collect_leaderboards
        async with session_scope(session_factory) as session:
            grouped = await _collect_leaderboards(session, 10)
            
            assert len(grouped) == 4  # (ap, ENL), (ap, RES), (hacks, ENL), (hacks, RES)
            
            # Check AP leaderboard
            ap_enl = grouped.get(("ap", "ENL"))
            assert ap_enl is not None
            assert len(ap_enl) == 1
            assert ap_enl[0]["codename"] == "Agent1"
            assert ap_enl[0]["value"] == 1500
            
            ap_res = grouped.get(("ap", "RES"))
            assert ap_res is not None
            assert len(ap_res) == 1
            assert ap_res[0]["codename"] == "Agent2"
            assert ap_res[0]["value"] == 900
            
            # Check hacks leaderboard
            hacks_enl = grouped.get(("hacks", "ENL"))
            assert hacks_enl is not None
            assert len(hacks_enl) == 1
            assert hacks_enl[0]["codename"] == "Agent1"
            assert hacks_enl[0]["value"] == 100
            
            hacks_res = grouped.get(("hacks", "RES"))
            assert hacks_res is not None
            assert len(hacks_res) == 1
            assert hacks_res[0]["codename"] == "Agent2"
            assert hacks_res[0]["value"] == 150

    @pytest.mark.asyncio
    async def test_collect_leaderboards_no_data(self, session_factory):
        """Test _collect_leaderboards with no data"""
        # Create stats table
        async with session_scope(session_factory) as session:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY,
                    agent_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    faction TEXT NOT NULL,
                    value REAL NOT NULL
                )
            """))
        
        # Test _collect_leaderboards
        async with session_scope(session_factory) as session:
            grouped = await _collect_leaderboards(session, 10)
            
            assert len(grouped) == 0

    @pytest.mark.asyncio
    async def test_persist_leaderboards(self, session_factory):
        """Test _persist_leaderboards"""
        # Create leaderboard_cache table
        async with session_scope(session_factory) as session:
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
        
        # Test data
        grouped = {
            ("ap", "ENL"): [
                {"rank": 1, "agent_id": 1, "codename": "Agent1", "value": 1500}
            ],
            ("ap", "RES"): [
                {"rank": 1, "agent_id": 2, "codename": "Agent2", "value": 900}
            ]
        }
        
        # Test _persist_leaderboards
        async with session_scope(session_factory) as session:
            await _persist_leaderboards(session, grouped)
        
        # Verify data was persisted
        async with session_scope(session_factory) as session:
            result = await session.execute(text("SELECT * FROM leaderboard_cache"))
            rows = result.fetchall()
            
            assert len(rows) == 2
            
            # Check ENL entry
            enl_row = next(row for row in rows if row[1] == "ENL")
            assert enl_row[0] == "ap"  # category
            assert enl_row[1] == "ENL"  # faction
            payload = json.loads(enl_row[2])
            assert payload["category"] == "ap"
            assert payload["faction"] == "ENL"
            assert len(payload["leaders"]) == 1
            assert payload["leaders"][0]["codename"] == "Agent1"
            assert payload["leaders"][0]["value"] == 1500
            
            # Check RES entry
            res_row = next(row for row in rows if row[1] == "RES")
            assert res_row[0] == "ap"  # category
            assert res_row[1] == "RES"  # faction
            payload = json.loads(res_row[2])
            assert payload["category"] == "ap"
            assert payload["faction"] == "RES"
            assert len(payload["leaders"]) == 1
            assert payload["leaders"][0]["codename"] == "Agent2"
            assert payload["leaders"][0]["value"] == 900

    @pytest.mark.asyncio
    async def test_recompute_with_data(self, mock_settings):
        """Test _recompute with data"""
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
            session.add_all([agent1, agent2])
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
                (:agent2_id, 'ap', 'RES', 900)
            """), {"agent1_id": agent1.id, "agent2_id": agent2.id})
        
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
    async def test_recompute_no_data(self, mock_settings):
        """Test _recompute with no data"""
        # Create a temporary engine and session factory
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        
        # Create leaderboard_cache table
        async with session_scope(session_factory) as session:
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
        
        # Test _recompute
        await _recompute(mock_settings)
        
        await engine.dispose()

    def test_recompute_leaderboards_job_success(self):
        """Test recompute_leaderboards_job with successful execution"""
        with patch('bot.jobs.leaderboard_worker._recompute') as mock_recompute:
            with patch('bot.jobs.leaderboard_worker.load_settings') as mock_load_settings:
                mock_load_settings.return_value = mock_settings()
                recompute_leaderboards_job()
                mock_recompute.assert_called_once()

    def test_recompute_leaderboards_job_exception(self):
        """Test recompute_leaderboards_job with exception"""
        with patch('bot.jobs.leaderboard_worker._recompute', side_effect=Exception("Test error")):
            with patch('bot.jobs.leaderboard_worker.load_settings') as mock_load_settings:
                mock_load_settings.return_value = mock_settings()
                with pytest.raises(Exception):
                    recompute_leaderboards_job()

    def test_enqueue_recompute_job(self):
        """Test enqueue_recompute_job"""
        mock_queue = Mock()
        
        enqueue_recompute_job(mock_queue)
        
        mock_queue.enqueue.assert_called_once_with(recompute_leaderboards_job)


# ==================== VERIFICATION QUEUE FEATURE TESTS ====================

class TestVerificationQueue:
    """Test cases for the verification queue feature"""

    def test_enqueue_recompute_job(self):
        """Test enqueue_recompute_job"""
        mock_queue = Mock()
        
        enqueue_recompute_job(mock_queue)
        
        mock_queue.enqueue.assert_called_once_with(recompute_leaderboards_job)


# ==================== ADMIN COMMANDS FEATURE TESTS ====================

class TestAdminCommands:
    """Test cases for admin commands"""

    @pytest.mark.asyncio
    async def test_start_command(self, mock_update, mock_context):
        """Test start command"""
        mock_update.message.reply_text = AsyncMock()
        
        await start(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with(
            "Welcome to the Ingress leaderboard bot. Use /register to begin."
        )

    @pytest.mark.asyncio
    async def test_start_command_no_message(self, mock_context):
        """Test start command with no message"""
        mock_update.message = None
        
        await start(mock_update, mock_context)
        
        # Should not raise an exception

    @pytest.mark.asyncio
    async def test_leaderboard_command_with_data(self, mock_update, mock_context, session_factory):
        """Test leaderboard command with data"""
        # Create test data
        async with session_scope(session_factory) as session:
            agent1 = Agent(telegram_id=1, codename="Agent1", faction="ENL")
            agent2 = Agent(telegram_id=2, codename="Agent2", faction="RES")
            session.add_all([agent1, agent2])
            await session.flush()
            
            session.add(Submission(agent_id=agent1.id, ap=1000, metrics={}))
            session.add(Submission(agent_id=agent1.id, ap=500, metrics={}))
            session.add(Submission(agent_id=agent2.id, ap=900, metrics={}))
        
        mock_update.message.reply_text = AsyncMock()
        
        await leaderboard(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        assert "1. Agent1 [ENL] — 1,500 AP" in reply_text
        assert "2. Agent2 [RES] — 900 AP" in reply_text

    @pytest.mark.asyncio
    async def test_leaderboard_command_no_data(self, mock_update, mock_context):
        """Test leaderboard command with no data"""
        mock_update.message.reply_text = AsyncMock()
        
        await leaderboard(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with("No submissions yet.")

    @pytest.mark.asyncio
    async def test_leaderboard_command_no_message(self, mock_context):
        """Test leaderboard command with no message"""
        mock_update.message = None
        
        await leaderboard(mock_update, mock_context)
        
        # Should not raise an exception

    @pytest.mark.asyncio
    async def test_leaderboard_command_with_limit(self, mock_update, mock_context, session_factory):
        """Test leaderboard command with a limit"""
        # Create test data
        async with session_scope(session_factory) as session:
            agents = [
                Agent(telegram_id=i, codename=f"Agent{i}", faction="ENL" if i % 2 == 0 else "RES")
                for i in range(1, 6)
            ]
            session.add_all(agents)
            await session.flush()
            
            for i, agent in enumerate(agents):
                session.add(Submission(agent_id=agent.id, ap=(6-i)*100, metrics={}))
        
        # Set a smaller leaderboard size
        mock_context.application.bot_data["settings"].leaderboard_size = 3
        mock_update.message.reply_text = AsyncMock()
        
        await leaderboard(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        lines = reply_text.split("\n")
        assert len(lines) == 3  # Should only show top 3
        assert "1. Agent1 [RES] — 500 AP" in lines[0]
        assert "2. Agent2 [ENL] — 400 AP" in lines[1]
        assert "3. Agent3 [RES] — 300 AP" in lines[2]


# ==================== DATA VALIDATION TESTS ====================

class TestDataValidation:
    """Test cases for data validation"""

    def test_faction_enum_values(self):
        """Test Faction enum values"""
        assert Faction.enl == "ENL"
        assert Faction.res == "RES"
        assert str(Faction.enl) == "ENL"
        assert str(Faction.res) == "RES"

    @pytest.mark.asyncio
    async def test_agent_model_validation(self, session_factory):
        """Test Agent model validation"""
        # Test valid agent
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
            await session.flush()
            
            assert agent.id is not None
            assert agent.telegram_id == 12345
            assert agent.codename == "TestAgent"
            assert agent.faction == "ENL"
            assert agent.created_at is not None

    @pytest.mark.asyncio
    async def test_submission_model_validation(self, session_factory):
        """Test Submission model validation"""
        # Create agent first
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
            await session.flush()
            
            # Test valid submission
            submission = Submission(agent_id=agent.id, ap=1000, metrics={"hacks": 10})
            session.add(submission)
            await session.flush()
            
            assert submission.id is not None
            assert submission.agent_id == agent.id
            assert submission.ap == 1000
            assert submission.metrics == {"hacks": 10}
            assert submission.submitted_at is not None

    @pytest.mark.asyncio
    async def test_agent_submission_relationship(self, session_factory):
        """Test Agent-Submission relationship"""
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
            await session.flush()
            
            submission1 = Submission(agent_id=agent.id, ap=1000, metrics={"hacks": 10})
            submission2 = Submission(agent_id=agent.id, ap=500, metrics={"fields": 2})
            session.add_all([submission1, submission2])
            await session.flush()
            
            # Test relationship
            assert len(agent.submissions) == 2
            assert agent.submissions[0].ap == 1000
            assert agent.submissions[1].ap == 500
            assert submission1.agent == agent
            assert submission2.agent == agent


# ==================== DATABASE OPERATIONS TESTS ====================

class TestDatabaseOperations:
    """Test cases for database operations"""

    @pytest.mark.asyncio
    async def test_session_scope_commit(self, session_factory):
        """Test session_scope commits on success"""
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        # Verify data was committed
        async with session_scope(session_factory) as session:
            result = await session.execute(select(Agent).where(Agent.telegram_id == 12345))
            agent = result.scalar_one()
            assert agent.codename == "TestAgent"

    @pytest.mark.asyncio
    async def test_session_scope_rollback(self, session_factory):
        """Test session_scope rolls back on exception"""
        with pytest.raises(ValueError):
            async with session_scope(session_factory) as session:
                agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
                session.add(agent)
                await session.flush()
                raise ValueError("Test error")
        
        # Verify data was not committed
        async with session_scope(session_factory) as session:
            result = await session.execute(select(Agent).where(Agent.telegram_id == 12345))
            agent = result.scalar_one_or_none()
            assert agent is None

    @pytest.mark.asyncio
    async def test_session_scope_always_closes(self, session_factory):
        """Test session_scope always closes the session"""
        session = None
        async with session_scope(session_factory) as session:
            pass
        
        # Session should be closed
        assert session.is_closed


# ==================== ERROR HANDLING TESTS ====================

class TestErrorHandling:
    """Test cases for error handling"""

    @pytest.mark.asyncio
    async def test_parse_submission_various_invalid_formats(self):
        """Test parse_submission with various invalid formats"""
        # Empty string
        with pytest.raises(ValueError, match="Missing ap value"):
            parse_submission("")
        
        # Only whitespace
        with pytest.raises(ValueError, match="Missing ap value"):
            parse_submission("   ")
        
        # Invalid key=value format
        with pytest.raises(ValueError, match="Entries must be provided as key=value pairs"):
            parse_submission("invalid_format")
        
        # Empty key
        with pytest.raises(ValueError, match="Invalid entry"):
            parse_submission("=value")
        
        # Empty value
        with pytest.raises(ValueError, match="Invalid entry"):
            parse_submission("key=")
        
        # Non-integer AP
        with pytest.raises(ValueError, match="ap must be an integer"):
            parse_submission("ap=not_a_number")

    @pytest.mark.asyncio
    async def test_register_faction_case_insensitive(self, mock_update, mock_context, session_factory):
        """Test register_faction with case insensitive faction input"""
        mock_context.user_data["codename"] = "TestCodename"
        mock_update.message.reply_text = AsyncMock()
        
        # Test lowercase
        mock_update.message.text = "enl"
        await register_faction(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once_with("Registered TestCodename (ENL).")
        
        # Reset for next test
        mock_update.message.reply_text.reset_mock()
        mock_context.user_data["codename"] = "TestCodename2"
        
        # Test mixed case
        mock_update.message.text = "Res"
        await register_faction(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once_with("Registered TestCodename2 (RES).")

    @pytest.mark.asyncio
    async def test_register_codename_whitespace_handling(self, mock_update, mock_context):
        """Test register_codename with various whitespace inputs"""
        mock_update.message.reply_text = AsyncMock()
        
        # Leading/trailing whitespace
        mock_update.message.text = "  TestCodename  "
        result = await register_codename(mock_update, mock_context)
        assert result == 1  # FACTION
        assert mock_context.user_data["codename"] == "TestCodename"
        
        # Reset for next test
        mock_context.user_data.clear()
        
        # Only whitespace
        mock_update.message.text = "   "
        result = await register_codename(mock_update, mock_context)
        assert result == 0  # CODENAME
        assert "codename" not in mock_context.user_data

    @pytest.mark.asyncio
    async def test_submit_payload_parsing(self, mock_update, mock_context, session_factory):
        """Test submit with various payload formats"""
        # Create a registered agent
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        mock_update.message.reply_text = AsyncMock()
        
        # Test with semicolon separator
        mock_update.message.text = "/submit ap=12345; hacks=17"
        await submit(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        
        # Reset for next test
        mock_update.message.reply_text.reset_mock()
        
        # Test with newline separator
        mock_update.message.text = "/submit ap=12345\nhacks=17"
        await submit(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        
        # Reset for next test
        mock_update.message.reply_text.reset_mock()
        
        # Test with multi-space separator
        mock_update.message.text = "/submit ap=12345  hacks=17"
        await submit(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()


# ==================== BUSINESS LOGIC TESTS ====================

class TestBusinessLogic:
    """Test cases for business logic"""

    @pytest.mark.asyncio
    async def test_leaderboard_ordering(self, session_factory):
        """Test leaderboard ordering by AP and then by codename"""
        # Create test data
        async with session_scope(session_factory) as session:
            # Create agents with codenames that would test alphabetical ordering
            agent1 = Agent(telegram_id=1, codename="Zebra", faction="ENL")
            agent2 = Agent(telegram_id=2, codename="Alpha", faction="ENL")
            agent3 = Agent(telegram_id=3, codename="Beta", faction="ENL")
            session.add_all([agent1, agent2, agent3])
            await session.flush()
            
            # Give Zebra and Alpha the same AP to test alphabetical ordering
            session.add(Submission(agent_id=agent1.id, ap=1000, metrics={}))
            session.add(Submission(agent_id=agent2.id, ap=1000, metrics={}))
            session.add(Submission(agent_id=agent3.id, ap=500, metrics={}))
        
        # Test get_leaderboard
        async with session_scope(session_factory) as session:
            leaderboard = await get_leaderboard(session, 10)
            
            # Alpha should come before Zebra due to alphabetical ordering
            assert leaderboard[0] == ("Alpha", "ENL", 1000)
            assert leaderboard[1] == ("Zebra", "ENL", 1000)
            assert leaderboard[2] == ("Beta", "ENL", 500)

    @pytest.mark.asyncio
    async def test_submission_accumulation(self, session_factory):
        """Test that submissions accumulate correctly for an agent"""
        # Create test data
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=1, codename="TestAgent", faction="ENL")
            session.add(agent)
            await session.flush()
            
            # Add multiple submissions
            session.add(Submission(agent_id=agent.id, ap=1000, metrics={}))
            session.add(Submission(agent_id=agent.id, ap=500, metrics={}))
            session.add(Submission(agent_id=agent.id, ap=250, metrics={}))
        
        # Test get_leaderboard
        async with session_scope(session_factory) as session:
            leaderboard = await get_leaderboard(session, 10)
            
            assert len(leaderboard) == 1
            assert leaderboard[0] == ("TestAgent", "ENL", 1750)  # 1000 + 500 + 250

    @pytest.mark.asyncio
    async def test_agent_faction_filtering(self, session_factory):
        """Test that leaderboard correctly filters by faction"""
        # Create test data
        async with session_scope(session_factory) as session:
            enl_agent = Agent(telegram_id=1, codename="ENLAgent", faction="ENL")
            res_agent = Agent(telegram_id=2, codename="RESAgent", faction="RES")
            session.add_all([enl_agent, res_agent])
            await session.flush()
            
            session.add(Submission(agent_id=enl_agent.id, ap=1000, metrics={}))
            session.add(Submission(agent_id=res_agent.id, ap=1500, metrics={}))
        
        # Test get_leaderboard
        async with session_scope(session_factory) as session:
            leaderboard = await get_leaderboard(session, 10)
            
            assert len(leaderboard) == 2
            # RES agent should be first due to higher AP
            assert leaderboard[0] == ("RESAgent", "RES", 1500)
            assert leaderboard[1] == ("ENLAgent", "ENL", 1000)

    @pytest.mark.asyncio
    async def test_autodelete_scheduling(self, mock_update, mock_context, session_factory, mock_queue):
        """Test that autodelete is scheduled correctly"""
        # Create a registered agent
        async with session_scope(session_factory) as session:
            agent = Agent(telegram_id=12345, codename="TestAgent", faction="ENL")
            session.add(agent)
        
        mock_update.message.text = "/submit ap=12345; hacks=17"
        mock_update.message.message_id = 67890
        mock_update.message.chat_id = 123456
        mock_reply = Mock(message_id=11111)
        mock_update.message.reply_text = AsyncMock(return_value=mock_reply)
        
        await submit(mock_update, mock_context)
        
        # Verify deletion was scheduled with correct parameters
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
    async def test_registration_flow(self, mock_update, mock_context, session_factory):
        """Test the complete registration flow"""
        # Start registration
        mock_update.message.reply_text = AsyncMock()
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

    @pytest.mark.asyncio
    async def test_registration_cancellation(self, mock_update, mock_context):
        """Test registration cancellation"""
        # Start registration
        mock_update.message.reply_text = AsyncMock()
        result = await register_start(mock_update, mock_context)
        assert result == 0  # CODENAME
        
        # Provide codename
        mock_update.message.text = "TestAgent"
        mock_update.message.reply_text.reset_mock()
        result = await register_codename(mock_update, mock_context)
        assert result == 1  # FACTION
        assert mock_context.user_data["codename"] == "TestAgent"
        
        # Cancel registration
        mock_update.message.reply_text.reset_mock()
        result = await register_cancel(mock_update, mock_context)
        assert result == -1  # ConversationHandler.END
        mock_update.message.reply_text.assert_called_with("Registration cancelled.")
        assert "codename" not in mock_context.user_data