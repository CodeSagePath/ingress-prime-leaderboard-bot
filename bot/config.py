from dataclasses import dataclass, field
import logging
import os
from typing import Optional
import socket
from pathlib import Path

logger = logging.getLogger(__name__)


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _get_local_ip() -> str:
    """Get the local IP address for server binding."""
    try:
        # Create a dummy socket to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@dataclass
class ServerConfig:
    """Server-specific configuration settings."""
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 1
    log_level: str = "INFO"
    max_connections: int = 1000
    keepalive_timeout: int = 65
    access_log: bool = True
    graceful_timeout: int = 30
    timeout: int = 120


@dataclass
class DatabaseConfig:
    """Database configuration with enhanced server options."""
    url: str = "sqlite+aiosqlite:///./data/bot.db"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600
    pool_pre_ping: bool = True
    echo: bool = False


@dataclass
class RedisConfig:
    """Redis configuration for server deployment."""
    url: str = "redis://localhost:6379/0"
    max_connections: int = 20
    retry_on_timeout: bool = True
    health_check_interval: int = 30
    socket_timeout: int = 5
    socket_connect_timeout: int = 5


@dataclass
class SecurityConfig:
    """Security configuration for server deployment."""
    admin_token: str = ""
    allowed_hosts: list[str] = field(default_factory=list)
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 30
    request_timeout: int = 30
    max_request_size: int = 10 * 1024 * 1024  # 10MB


@dataclass
class MonitoringConfig:
    """Monitoring and health check configuration."""
    health_check_enabled: bool = True
    health_check_path: str = "/health"
    metrics_enabled: bool = False
    metrics_path: str = "/metrics"
    log_to_file: bool = False
    log_file_path: str = "./logs/app.log"
    log_max_size: str = "100MB"
    log_backup_count: int = 5


@dataclass
class Settings:
    # Core bot settings
    telegram_token: str
    bot_name: str = "Ingress Prime Leaderboard"
    bot_description: str = "Track your Ingress Prime stats and compete with other agents!"

    # Enhanced configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)

    # Existing settings
    autodelete_delay_seconds: int = 300
    autodelete_enabled: bool = True
    leaderboard_size: int = 10
    group_message_retention_minutes: int = 60
    dashboard_enabled: bool = False
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8000
    dashboard_admin_token: str = ""
    text_only_mode: bool = False
    admin_user_ids: list[int] = field(default_factory=list)

    # Environment-specific settings
    environment: str = "production"
    debug: bool = False
    timezone: str = "UTC"

    # Backup configuration
    backup_enabled: bool = False
    backup_rclone_remote: str = ""
    backup_destination_path: str = "ingress-bot-backups"
    backup_schedule: str = "daily"
    backup_retention_count: int = 7
    backup_compress: bool = True

    # Performance settings
    cache_ttl_seconds: int = 300
    max_retries: int = 3
    retry_delay: float = 1.0


def load_settings() -> Settings:
    # Core settings
    telegram_token = os.environ.get("BOT_TOKEN", "")
    bot_name = os.environ.get("BOT_NAME", "Ingress Prime Leaderboard")
    bot_description = os.environ.get("BOT_DESCRIPTION", "Track your Ingress Prime stats and compete with other agents!")

    # Environment detection
    environment = os.environ.get("ENVIRONMENT", "production")
    debug = _bool(os.environ.get("DEBUG"), environment == "development")
    timezone = os.environ.get("TIMEZONE", "UTC")

    # Database configuration
    database_config = DatabaseConfig(
        url=os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db"),
        pool_size=int(os.environ.get("DB_POOL_SIZE", "10")),
        max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "20")),
        pool_timeout=int(os.environ.get("DB_POOL_TIMEOUT", "30")),
        pool_recycle=int(os.environ.get("DB_POOL_RECYCLE", "3600")),
        pool_pre_ping=_bool(os.environ.get("DB_POOL_PRE_PING"), True),
        echo=_bool(os.environ.get("DB_ECHO"), debug),
    )

    # Redis configuration
    redis_config = RedisConfig(
        url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        max_connections=int(os.environ.get("REDIS_MAX_CONNECTIONS", "20")),
        retry_on_timeout=_bool(os.environ.get("REDIS_RETRY_ON_TIMEOUT"), True),
        health_check_interval=int(os.environ.get("REDIS_HEALTH_CHECK_INTERVAL", "30")),
        socket_timeout=int(os.environ.get("REDIS_SOCKET_TIMEOUT", "5")),
        socket_connect_timeout=int(os.environ.get("REDIS_SOCKET_CONNECT_TIMEOUT", "5")),
    )

    # Server configuration
    server_config = ServerConfig(
        host=os.environ.get("SERVER_HOST", "0.0.0.0"),
        port=int(os.environ.get("SERVER_PORT", "8080")),
        workers=int(os.environ.get("SERVER_WORKERS", "1")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        max_connections=int(os.environ.get("MAX_CONNECTIONS", "1000")),
        keepalive_timeout=int(os.environ.get("KEEPALIVE_TIMEOUT", "65")),
        access_log=_bool(os.environ.get("ACCESS_LOG"), True),
        graceful_timeout=int(os.environ.get("GRACEFUL_TIMEOUT", "30")),
        timeout=int(os.environ.get("TIMEOUT", "120")),
    )

    # Security configuration
    security_config = SecurityConfig(
        admin_token=os.environ.get("SECURITY_ADMIN_TOKEN", ""),
        allowed_hosts=os.environ.get("ALLOWED_HOSTS", "").split(",") if os.environ.get("ALLOWED_HOSTS") else [],
        rate_limit_enabled=_bool(os.environ.get("RATE_LIMIT_ENABLED"), True),
        rate_limit_per_minute=int(os.environ.get("RATE_LIMIT_PER_MINUTE", "30")),
        request_timeout=int(os.environ.get("REQUEST_TIMEOUT", "30")),
        max_request_size=int(os.environ.get("MAX_REQUEST_SIZE", str(10 * 1024 * 1024))),
    )

    # Monitoring configuration
    monitoring_config = MonitoringConfig(
        health_check_enabled=_bool(os.environ.get("HEALTH_CHECK_ENABLED"), True),
        health_check_path=os.environ.get("HEALTH_CHECK_PATH", "/health"),
        metrics_enabled=_bool(os.environ.get("METRICS_ENABLED"), False),
        metrics_path=os.environ.get("METRICS_PATH", "/metrics"),
        log_to_file=_bool(os.environ.get("LOG_TO_FILE"), environment == "production"),
        log_file_path=os.environ.get("LOG_FILE_PATH", "./logs/app.log"),
        log_max_size=os.environ.get("LOG_MAX_SIZE", "100MB"),
        log_backup_count=int(os.environ.get("LOG_BACKUP_COUNT", "5")),
    )

    # Parse admin user IDs from environment variable
    admin_ids_str = os.environ.get("ADMIN_USER_IDS", "")
    admin_user_ids = []
    if admin_ids_str:
        try:
            admin_user_ids = [int(id_str.strip()) for id_str in admin_ids_str.split(",") if id_str.strip()]
        except ValueError:
            logger.warning("Invalid ADMIN_USER_IDS format. Using empty list.")

    # Legacy settings
    autodelete_delay_seconds = int(os.environ.get("AUTODELETE_DELAY_SECONDS", "300"))
    autodelete_enabled = _bool(os.environ.get("AUTODELETE_ENABLED"), True)
    leaderboard_size = int(os.environ.get("LEADERBOARD_SIZE", "10"))
    group_message_retention_minutes = int(os.environ.get("GROUP_MESSAGE_RETENTION_MINUTES", "60"))
    dashboard_enabled = _bool(os.environ.get("DASHBOARD_ENABLED"), False)
    dashboard_host = os.environ.get("DASHBOARD_HOST", server_config.host)
    dashboard_port = int(os.environ.get("DASHBOARD_PORT", "8000"))
    dashboard_admin_token = os.environ.get("DASHBOARD_ADMIN_TOKEN", security_config.admin_token)
    text_only_mode = _bool(os.environ.get("TEXT_ONLY_MODE"), False)

    # Backup configuration
    backup_enabled = _bool(os.environ.get("BACKUP_ENABLED"), False)
    backup_rclone_remote = os.environ.get("BACKUP_RCLONE_REMOTE", "")
    backup_destination_path = os.environ.get("BACKUP_DESTINATION_PATH", "ingress-bot-backups")
    backup_schedule = os.environ.get("BACKUP_SCHEDULE", "daily")
    backup_retention_count = int(os.environ.get("BACKUP_RETENTION_COUNT", "7"))
    backup_compress = _bool(os.environ.get("BACKUP_COMPRESS"), True)

    # Performance settings
    cache_ttl_seconds = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
    max_retries = int(os.environ.get("MAX_RETRIES", "3"))
    retry_delay = float(os.environ.get("RETRY_DELAY", "1.0"))

    # Environment-specific adjustments
    if environment == "development":
        server_config.host = "127.0.0.1"
        database_config.echo = True
        monitoring_config.log_to_file = False

    return Settings(
        telegram_token=telegram_token,
        bot_name=bot_name,
        bot_description=bot_description,
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
        cache_ttl_seconds=cache_ttl_seconds,
        max_retries=max_retries,
        retry_delay=retry_delay,
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
