from dataclasses import dataclass
import os


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    telegram_token: str
    database_url: str
    redis_url: str
    autodelete_delay_seconds: int
    autodelete_enabled: bool
    leaderboard_size: int
    group_message_retention_minutes: int
    dashboard_enabled: bool
    dashboard_host: str
    dashboard_port: int
    dashboard_admin_token: str


def load_settings() -> Settings:
    telegram_token = os.environ.get("BOT_TOKEN", "")
    database_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    autodelete_delay_seconds = int(os.environ.get("AUTODELETE_DELAY_SECONDS", "300"))
    autodelete_enabled = _bool(os.environ.get("AUTODELETE_ENABLED"), True)
    leaderboard_size = int(os.environ.get("LEADERBOARD_SIZE", "10"))
    group_message_retention_minutes = int(os.environ.get("GROUP_MESSAGE_RETENTION_MINUTES", "60"))
    dashboard_enabled = _bool(os.environ.get("DASHBOARD_ENABLED"), False)
    dashboard_host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    dashboard_port = int(os.environ.get("DASHBOARD_PORT", "8000"))
    dashboard_admin_token = os.environ.get("DASHBOARD_ADMIN_TOKEN", "")
    return Settings(
        telegram_token=telegram_token,
        database_url=database_url,
        redis_url=redis_url,
        autodelete_delay_seconds=autodelete_delay_seconds,
        autodelete_enabled=autodelete_enabled,
        leaderboard_size=leaderboard_size,
        group_message_retention_minutes=group_message_retention_minutes,
        dashboard_enabled=dashboard_enabled,
        dashboard_host=dashboard_host,
        dashboard_port=dashboard_port,
        dashboard_admin_token=dashboard_admin_token,
    )
