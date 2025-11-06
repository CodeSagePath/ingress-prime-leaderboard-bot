import pytest
import pytest_asyncio
import importlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database import Base, session_scope

main_module = importlib.import_module("bot.main")
from bot.main import (
    leaderboard,
    parse_submission,
    set_group_privacy,
    myrank_command,
    top10_command,
    top_command,
    last_cycle_command,
    last_week_command,
    save_to_db,
    _ensure_agents_table,
)
from bot.models import Agent, Submission, GroupSetting


class DummyMessage:
    def __init__(self):
        self.sent = None
        self.kwargs = None
        self.message_id = 77

    async def reply_text(self, text, **kwargs):
        self.sent = text
        self.kwargs = kwargs
        return SimpleNamespace(message_id=88)


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


@pytest.fixture(autouse=True)
def reset_agents_db(tmp_path, monkeypatch):
    db_path = tmp_path / "agents.db"
    cycle_path = tmp_path / "cycle.txt"
    monkeypatch.setattr(main_module, "AGENTS_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "CURRENT_CYCLE_FILE", cycle_path)
    _ensure_agents_table()
    yield
    if db_path.exists():
        db_path.unlink()
    if cycle_path.exists():
        cycle_path.unlink()


def add_cycle_entry(name: str, faction: str, points: int, cycle: str, date: str | None = None, time_value: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    date_value = date or now.strftime("%Y-%m-%d")
    time_str = time_value or now.strftime("%H:%M:%S")
    save_to_db(
        {
            "time_span": "ALL TIME",
            "agent_name": name,
            "agent_faction": faction,
            "date": date_value,
            "time": time_str,
            "cycle_name": cycle,
            "cycle_points": points,
        }
    )


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
async def test_leaderboard_formats_output(session_factory, monkeypatch):
    async with session_scope(session_factory) as session:
        alpha = Agent(telegram_id=1, codename="Alpha", faction="ENL")
        beta = Agent(telegram_id=2, codename="Beta", faction="RES")
        session.add_all([alpha, beta])

    async def fake_leaderboard(session, limit, chat_id=None, time_span=None, metric="ap"):
        return [
            ("Alpha", "ENL", 1500, {}),
            ("Beta", "RES", 900, {}),
        ]

    monkeypatch.setattr(main_module, "get_leaderboard", fake_leaderboard)
    monkeypatch.setattr(main_module, "session_scope", lambda sf: session_scope(session_factory))

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

    class DummySettings:
        leaderboard_size = 10
        group_message_retention_minutes = 60
        autodelete_delay_seconds = 300
        autodelete_enabled = True
        telegram_token = "token"
        text_only_mode = False

    message = DummyMessage()
    update = SimpleNamespace(message=message, effective_chat=DummyChat())
    application = DummyApplication({"settings": DummySettings(), "session_factory": session_factory, "queue": object()})
    context = DummyContext(application)

    await leaderboard(update, context)

    assert message.sent == "🏆 *Leaderboard* 🏆\n1. Alpha [ENL]  - 1,500 AP\n2. Beta [RES]  - 900 AP"


@pytest.mark.asyncio
async def test_top10_command_returns_cycle_leaderboard(monkeypatch):
    message = DummyMessage()
    update = SimpleNamespace(message=message)
    settings = SimpleNamespace(text_only_mode=False)
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"settings": settings}))

    rows = [
        ("Alpha", "ENL", 5000),
        ("Beta", "RES", 4500),
    ]

    async def fake_fetch(limit, faction=None, cycle_name=None, since=None):
        assert limit == 10
        assert faction is None
        assert cycle_name is None
        assert since is None
        return rows

    async def fake_send(update_arg, settings_arg, rows_arg, header):
        assert rows_arg == rows
        assert header == "Top 10 agents by cycle points"
        await message.reply_text("sent")

    monkeypatch.setattr(main_module, "_fetch_cycle_leaderboard", fake_fetch)
    monkeypatch.setattr(main_module, "_send_cycle_leaderboard", fake_send)
    monkeypatch.setattr(main_module, "session_scope", lambda sf: session_scope(session_factory))

    await top10_command(update, context)

    assert message.sent == "sent"
    assert message.kwargs == {}


@pytest.mark.asyncio
async def test_top_command_filters_by_faction(monkeypatch):
    message = DummyMessage()
    update = SimpleNamespace(message=message)
    settings = SimpleNamespace(text_only_mode=False)
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"settings": settings}), args=["ENL"])

    rows = [("Alpha", "ENL", 6000)]

    async def fake_fetch(limit, faction=None, cycle_name=None, since=None):
        assert faction == "ENL"
        return rows

    async def fake_send(update_arg, settings_arg, rows_arg, header):
        assert header == "Top 10 Enlightened agents by cycle points"
        await message.reply_text("sent faction")

    monkeypatch.setattr(main_module, "_fetch_cycle_leaderboard", fake_fetch)
    monkeypatch.setattr(main_module, "_send_cycle_leaderboard", fake_send)
    monkeypatch.setattr(main_module, "session_scope", lambda sf: session_scope(session_factory))

    await top_command(update, context)

    assert message.sent == "sent faction"
    assert message.kwargs == {}


@pytest.mark.asyncio
async def test_top_command_requires_faction_arg(monkeypatch):
    message = DummyMessage()
    update = SimpleNamespace(message=message)
    settings = SimpleNamespace(text_only_mode=False)
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"settings": settings}), args=[])

    await top_command(update, context)

    assert message.sent == "Usage: /top <ENL|RES>."
    assert message.kwargs == {}


@pytest.mark.asyncio
async def test_last_cycle_command_uses_latest_cycle(monkeypatch):
    message = DummyMessage()
    update = SimpleNamespace(message=message)
    settings = SimpleNamespace(text_only_mode=False)
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"settings": settings}))

    async def fake_latest():
        return "Cycle 123"

    rows = [("Alpha", "ENL", 7000)]

    async def fake_fetch(limit, faction=None, cycle_name=None, since=None):
        assert cycle_name == "Cycle 123"
        return rows

    async def fake_send(update_arg, settings_arg, rows_arg, header):
        assert header == "Top 10 agents — Cycle 123"
        await message.reply_text("sent cycle")

    monkeypatch.setattr(main_module, "_get_latest_cycle_name_async", fake_latest)
    monkeypatch.setattr(main_module, "_fetch_cycle_leaderboard", fake_fetch)
    monkeypatch.setattr(main_module, "_send_cycle_leaderboard", fake_send)
    monkeypatch.setattr(main_module, "session_scope", lambda sf: session_scope(session_factory))

    await last_cycle_command(update, context)

    assert message.sent == "sent cycle"
    assert message.kwargs == {}


@pytest.mark.asyncio
async def test_last_cycle_command_handles_missing_cycle(monkeypatch):
    message = DummyMessage()
    update = SimpleNamespace(message=message)
    settings = SimpleNamespace(text_only_mode=False)
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"settings": settings}))

    async def fake_latest():
        return None

    monkeypatch.setattr(main_module, "_get_latest_cycle_name_async", fake_latest)

    await last_cycle_command(update, context)

    assert message.sent == "No cycle data available."
    assert message.kwargs == {}


@pytest.mark.asyncio
async def test_last_week_command_filters_by_date(monkeypatch):
    message = DummyMessage()
    update = SimpleNamespace(message=message)
    settings = SimpleNamespace(text_only_mode=False)
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"settings": settings}))

    captured_since = {}

    async def fake_fetch(limit, faction=None, cycle_name=None, since=None):
        captured_since["value"] = since
        return [("Alpha", "ENL", 3000)]

    async def fake_send(update_arg, settings_arg, rows_arg, header):
        assert header == "Top 10 agents — last 7 days"
        await message.reply_text("sent week")

    monkeypatch.setattr(main_module, "_fetch_cycle_leaderboard", fake_fetch)
    monkeypatch.setattr(main_module, "_send_cycle_leaderboard", fake_send)
    monkeypatch.setattr(main_module, "session_scope", lambda sf: session_scope(session_factory))

    await last_week_command(update, context)

    assert message.sent == "sent week"
    assert message.kwargs == {}
    assert isinstance(captured_since["value"], datetime)
    assert captured_since["value"] <= datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_last_week_command_handles_result(monkeypatch):
    message = DummyMessage()
    update = SimpleNamespace(message=message)
    settings = SimpleNamespace(text_only_mode=True)
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"settings": settings}))

    async def fake_fetch(limit, faction=None, cycle_name=None, since=None):
        return [("Alpha", "ENL", 3000)]

    async def fake_send(update_arg, settings_arg, rows_arg, header):
        assert header == "Top 10 agents — last 7 days"
        await message.reply_text("plain")

    monkeypatch.setattr(main_module, "_fetch_cycle_leaderboard", fake_fetch)
    monkeypatch.setattr(main_module, "_send_cycle_leaderboard", fake_send)
    monkeypatch.setattr(main_module, "session_scope", lambda sf: session_scope(session_factory))

    await last_week_command(update, context)

    assert message.sent == "plain"
    assert message.kwargs == {}


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

    class DummySettings:
        leaderboard_size = 10
        group_message_retention_minutes = 60
        autodelete_delay_seconds = 300
        autodelete_enabled = True
        telegram_token = "token"
        text_only_mode = False

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
            self.args = []

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
