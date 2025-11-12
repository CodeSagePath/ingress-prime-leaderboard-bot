from dataclasses import dataclass, field
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}




@dataclass
class ServerConfig:
    """Server-specific configuration settings."""
    host: str
    port: int
    log_level: str


@dataclass
class DatabaseConfig:
    """Database configuration."""
    url: str
    pool_pre_ping: bool


@dataclass
class RedisConfig:
    """Redis configuration for server deployment."""
    url: str
    max_connections: int
    retry_on_timeout: bool
    health_check_interval: int
    socket_timeout: int
    socket_connect_timeout: int


@dataclass
class SecurityConfig:
    """Security configuration for server deployment."""
    # Reserved for future security features


@dataclass
class MonitoringConfig:
    """Monitoring and health check configuration."""
    health_check_enabled: bool
    log_to_file: bool
    log_file_path: str
    log_max_size: str
    log_backup_count: int


@dataclass
class Settings:
    # Core bot settings
    telegram_token: str
    bot_name: str

    # Enhanced configurations
    database: DatabaseConfig
    redis: RedisConfig
    server: ServerConfig
    security: SecurityConfig
    monitoring: MonitoringConfig

    # Existing settings
    autodelete_delay_seconds: int
    autodelete_enabled: bool
    leaderboard_size: int
    group_message_retention_minutes: int
    dashboard_enabled: bool
    dashboard_host: str
    dashboard_port: int
    dashboard_admin_token: str
    text_only_mode: bool
    admin_user_ids: list[int]

    # Environment-specific settings
    environment: str
    debug: bool
    timezone: str

    # Backup configuration
    backup_enabled: bool
    backup_rclone_remote: str
    backup_destination_path: str
    backup_schedule: str
    backup_retention_count: int
    backup_compress: bool

    

def load_settings() -> Settings:
    # Load environment variables from .env file to ensure they're available
    from pathlib import Path
    from dotenv import load_dotenv

    # Determine project root and load .env
    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env")

    # Core settings - all required from environment
    telegram_token = os.getenv("BOT_TOKEN")
    if not telegram_token:
        raise ValueError("BOT_TOKEN is required in environment variables")

    bot_name = os.getenv("BOT_NAME", "Ingress Prime Leaderboard")

    # Environment detection
    environment = os.getenv("ENVIRONMENT", "production")
    debug = _bool(os.getenv("DEBUG"), environment == "development")
    timezone = os.getenv("TIMEZONE", "UTC")

    # Database configuration - all required from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required in environment variables")

    database_config = DatabaseConfig(
        url=database_url,
        pool_pre_ping=_bool(os.getenv("DB_POOL_PRE_PING"), True),
    )

    # Redis configuration - all required from environment
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise ValueError("REDIS_URL is required in environment variables")

    redis_config = RedisConfig(
        url=redis_url,
        max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "20")),
        retry_on_timeout=_bool(os.getenv("REDIS_RETRY_ON_TIMEOUT"), True),
        health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")),
        socket_timeout=int(os.getenv("REDIS_SOCKET_TIMEOUT", "5")),
        socket_connect_timeout=int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5")),
    )

    # Server configuration - all required from environment
    server_host = os.getenv("SERVER_HOST")
    if not server_host:
        raise ValueError("SERVER_HOST is required in environment variables")

    server_port = os.getenv("SERVER_PORT")
    if not server_port:
        raise ValueError("SERVER_PORT is required in environment variables")

    server_log_level = os.getenv("LOG_LEVEL", "INFO")

    server_config = ServerConfig(
        host=server_host,
        port=int(server_port),
        log_level=server_log_level,
    )

    # Security configuration
    security_config = SecurityConfig()

    # Monitoring configuration
    monitoring_config = MonitoringConfig(
        health_check_enabled=_bool(os.getenv("HEALTH_CHECK_ENABLED"), True),
        log_to_file=_bool(os.getenv("LOG_TO_FILE"), environment == "production"),
        log_file_path=os.getenv("LOG_FILE_PATH", "./logs/app.log"),
        log_max_size=os.getenv("LOG_MAX_SIZE", "100MB"),
        log_backup_count=int(os.getenv("LOG_BACKUP_COUNT", "5")),
    )

    # Parse admin user IDs from environment variable - required
    admin_ids_str = os.getenv("ADMIN_USER_IDS")
    if not admin_ids_str:
        raise ValueError("ADMIN_USER_IDS is required in environment variables")

    admin_user_ids = []
    try:
        admin_user_ids = [int(id_str.strip()) for id_str in admin_ids_str.split(",") if id_str.strip()]
    except ValueError:
        logger.warning("Invalid ADMIN_USER_IDS format. Using empty list.")

    # Legacy settings - get from environment
    autodelete_delay_seconds = int(os.getenv("AUTODELETE_DELAY_SECONDS", "300"))
    autodelete_enabled = _bool(os.getenv("AUTODELETE_ENABLED"), True)
    leaderboard_size = int(os.getenv("LEADERBOARD_SIZE", "10"))
    group_message_retention_minutes = int(os.getenv("GROUP_MESSAGE_RETENTION_MINUTES", "60"))
    dashboard_enabled = _bool(os.getenv("DASHBOARD_ENABLED"), False)

    # Dashboard configuration - get from environment
    dashboard_host = os.getenv("DASHBOARD_HOST", server_config.host)
    dashboard_port_str = os.getenv("DASHBOARD_PORT")
    if not dashboard_port_str:
        raise ValueError("DASHBOARD_PORT is required in environment variables")
    dashboard_port = int(dashboard_port_str)

    dashboard_admin_token = os.getenv("DASHBOARD_ADMIN_TOKEN", "")
    text_only_mode = _bool(os.getenv("TEXT_ONLY_MODE"), False)

    # Backup configuration
    backup_enabled = _bool(os.getenv("BACKUP_ENABLED"), False)
    backup_rclone_remote = os.getenv("BACKUP_RCLONE_REMOTE", "")
    backup_destination_path = os.getenv("BACKUP_DESTINATION_PATH", "ingress-bot-backups")
    backup_schedule = os.getenv("BACKUP_SCHEDULE", "daily")
    backup_retention_count = int(os.getenv("BACKUP_RETENTION_COUNT", "7"))
    backup_compress = _bool(os.getenv("BACKUP_COMPRESS"), True)

    return Settings(
        telegram_token=telegram_token,
        bot_name=bot_name,
                database=database_config,
        redis=redis_config,
        server=server_config,
        security=security_config,
        monitoring=monitoring_config,
        environment=environment,
        debug=debug,
        timezone=timezone,
        autodelete_delay_seconds=autodelete_delay_seconds,
        autodelete_enabled=autodelete_enabled,
        leaderboard_size=leaderboard_size,
        group_message_retention_minutes=group_message_retention_minutes,
        dashboard_enabled=dashboard_enabled,
        dashboard_host=dashboard_host,
        dashboard_port=dashboard_port,
        dashboard_admin_token=dashboard_admin_token,
        text_only_mode=text_only_mode,
        admin_user_ids=admin_user_ids,
        backup_enabled=backup_enabled,
        backup_rclone_remote=backup_rclone_remote,
        backup_destination_path=backup_destination_path,
        backup_schedule=backup_schedule,
        backup_retention_count=backup_retention_count,
        backup_compress=backup_compress,
            )


def validate_settings(settings: Settings) -> list[str]:
    """Validate settings and return a list of validation errors."""
    errors = []

    # Required fields
    if not settings.telegram_token:
        errors.append("BOT_TOKEN is required")

    if not settings.admin_user_ids:
        errors.append("At least one admin user ID is required in ADMIN_USER_IDS")

    # Database validation
    if not settings.database.url:
        errors.append("DATABASE_URL is required")

    # Redis validation
    if not settings.redis.url:
        errors.append("REDIS_URL is required")

    # Security validation
    if settings.dashboard_enabled and not settings.dashboard_admin_token:
        errors.append("DASHBOARD_ADMIN_TOKEN is required when dashboard is enabled")

    # Port validation
    if not (1 <= settings.server.port <= 65535):
        errors.append("SERVER_PORT must be between 1 and 65535")

    if not (1 <= settings.dashboard_port <= 65535):
        errors.append("DASHBOARD_PORT must be between 1 and 65535")

    # Logging validation
    if settings.monitoring.log_to_file:
        log_path = Path(settings.monitoring.log_file_path)
        if not log_path.parent.exists():
            errors.append(f"Log directory does not exist: {log_path.parent}")

    return errors


def print_environment_summary(settings: Settings) -> None:
    """Print a summary of the current environment configuration."""
    print(f"\n{'='*60}")
    print(f"🤖 {settings.bot_name} - Environment Summary")
    print(f"{'='*60}")
    print(f"Environment: {settings.environment}")
    print(f"Debug Mode: {settings.debug}")
    print(f"Timezone: {settings.timezone}")
    print(f"\n📊 Database:")
    print(f"  URL: {settings.database.url}")
    print(f"  Pool Size: {settings.database.pool_size}")
    print(f"  Echo: {settings.database.echo}")

    print(f"\n🔴 Redis:")
    print(f"  URL: {settings.redis.url}")
    print(f"  Max Connections: {settings.redis.max_connections}")

    print(f"\n🌐 Server:")
    print(f"  Host: {settings.server.host}")
    print(f"  Port: {settings.server.port}")
    print(f"  Workers: {settings.server.workers}")
    print(f"  Log Level: {settings.server.log_level}")

    print(f"\n🔒 Security:")
    print(f"  Rate Limiting: {settings.security.rate_limit_enabled}")
    print(f"  Allowed Hosts: {settings.security.allowed_hosts or ['All']}")

    print(f"\n📈 Monitoring:")
    print(f"  Health Check: {settings.monitoring.health_check_enabled}")
    print(f"  Log to File: {settings.monitoring.log_to_file}")

    print(f"\n🏠 Dashboard:")
    print(f"  Enabled: {settings.dashboard_enabled}")
    if settings.dashboard_enabled:
        print(f"  Port: {settings.dashboard_port}")

    print(f"\n👑 Admins: {len(settings.admin_user_ids)} configured")
    print(f"{'='*60}\n")


def get_deployment_guide(settings: Settings) -> str:
    """Generate a deployment guide based on the current settings."""
    guide = f"""
# 🚀 {settings.bot_name} Deployment Guide

## Environment: {settings.environment.upper()}

### Required Environment Variables:
```bash
# Core Configuration
export BOT_TOKEN="{settings.telegram_token}"
export ADMIN_USER_IDS="{','.join(map(str, settings.admin_user_ids))}"

# Database Configuration
export DATABASE_URL="{settings.database.url}"

# Redis Configuration
export REDIS_URL="{settings.redis.url}"

# Server Configuration
export SERVER_HOST="{settings.server.host}"
export SERVER_PORT="{settings.server.port}"
export LOG_LEVEL="{settings.server.log_level}"

# Security Configuration
export SECURITY_ADMIN_TOKEN="{settings.security.admin_token}"
```

### Optional Environment Variables:
```bash
# Performance Tuning
export DB_POOL_SIZE="{settings.database.pool_size}"
export REDIS_MAX_CONNECTIONS="{settings.redis.max_connections}"

# Monitoring
export HEALTH_CHECK_ENABLED="{settings.monitoring.health_check_enabled}"
export LOG_TO_FILE="{settings.monitoring.log_to_file}"

# Dashboard
export DASHBOARD_ENABLED="{settings.dashboard_enabled}"
export DASHBOARD_PORT="{settings.dashboard_port}"
```

### Docker Deployment:
```bash
docker build -t ingress-bot .
docker run -d \\
  --name ingress-bot \\
  --restart unless-stopped \\
  -e BOT_TOKEN="$BOT_TOKEN" \\
  -e ADMIN_USER_IDS="$ADMIN_USER_IDS" \\
  -e DATABASE_URL="$DATABASE_URL" \\
  -e REDIS_URL="$REDIS_URL" \\
  -p {settings.server.port}:{settings.server.port} \\
  ingress-bot
```

### Docker Compose Deployment:
```bash
docker-compose up -d
```

### Health Check:
curl http://{settings.server.host}:{settings.server.port}{settings.monitoring.health_check_path}

### Dashboard:
http://{settings.server.host}:{settings.dashboard_port if settings.dashboard_enabled else 'N/A'}
"""
    return guide
