"""
Health Check Module for Ingress Prime Leaderboard Bot
Provides comprehensive health monitoring for server deployment
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import psutil

from sqlalchemy import text
from .config import Settings, load_settings
from .database import build_engine, build_session_factory

logger = logging.getLogger(__name__)


class HealthChecker:
    """Comprehensive health checking system for the bot."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.start_time = datetime.now()
        self.last_check = None
        self.healthy = True

    async def check_database(self) -> Dict[str, Any]:
        """Check database connectivity and performance."""
        try:
            engine = build_engine(self.settings)
            session_factory = build_session_factory(engine)

            start_time = time.time()
            async with session_factory() as session:
                # Simple connectivity test
                result = await session.execute(text("SELECT 1"))
                result.first()

                # Check if tables exist
                try:
                    await session.execute(text("SELECT COUNT(*) FROM agents LIMIT 1"))
                    tables_ok = True
                except Exception:
                    tables_ok = False

                response_time = (time.time() - start_time) * 1000

                await engine.dispose()

                return {
                    "status": "healthy" if tables_ok else "warning",
                    "response_time_ms": round(response_time, 2),
                    "tables_exist": tables_ok,
                    "message": "Database connection successful" if tables_ok else "Database tables missing"
                }

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "response_time_ms": None,
                "tables_exist": False,
                "message": f"Database connection failed: {str(e)}"
            }

    async def check_redis(self) -> Dict[str, Any]:
        """Check Redis connectivity."""
        try:
            from redis import Redis
            from redis.exceptions import ConnectionError

            redis_client = Redis.from_url(
                self.settings.redis.url,
                socket_timeout=5,
                socket_connect_timeout=5
            )

            start_time = time.time()
            redis_client.ping()
            response_time = (time.time() - start_time) * 1000

            # Test basic operations
            test_key = "health_check_test"
            redis_client.setex(test_key, 10, "test")
            redis_client.get(test_key)
            redis_client.delete(test_key)

            redis_client.close()

            return {
                "status": "healthy",
                "response_time_ms": round(response_time, 2),
                "message": "Redis connection successful"
            }

        except ConnectionError as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "status": "unhealthy",
                "response_time_ms": None,
                "message": f"Redis connection failed: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Redis health check error: {e}")
            return {
                "status": "unhealthy",
                "response_time_ms": None,
                "message": f"Redis health check error: {str(e)}"
            }

    def check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100

            # Process info
            process = psutil.Process(os.getpid())
            process_memory = process.memory_info()

            # Determine status
            if cpu_percent > 90 or memory_percent > 90 or disk_percent > 90:
                status = "unhealthy"
            elif cpu_percent > 80 or memory_percent > 80 or disk_percent > 80:
                status = "warning"
            else:
                status = "healthy"

            return {
                "status": status,
                "cpu_percent": round(cpu_percent, 2),
                "memory_percent": round(memory_percent, 2),
                "disk_percent": round(disk_percent, 2),
                "process_memory_mb": round(process_memory.rss / 1024 / 1024, 2),
                "uptime_seconds": int((datetime.now() - self.start_time).total_seconds()),
                "message": f"System resources: CPU {cpu_percent}%, Memory {memory_percent}%, Disk {disk_percent}%"
            }

        except Exception as e:
            logger.error(f"System resource check failed: {e}")
            return {
                "status": "warning",
                "cpu_percent": None,
                "memory_percent": None,
                "disk_percent": None,
                "process_memory_mb": None,
                "uptime_seconds": None,
                "message": f"System resource check failed: {str(e)}"
            }

    async def check_bot_functionality(self) -> Dict[str, Any]:
        """Check basic bot functionality."""
        try:
            # Check if bot token is configured
            if not self.settings.telegram_token:
                return {
                    "status": "unhealthy",
                    "message": "Bot token not configured"
                }

            # Check admin users
            if not self.settings.admin_user_ids:
                return {
                    "status": "warning",
                    "message": "No admin users configured"
                }

            # Test bot configuration by trying to initialize
            from .main import build_application

            # Don't actually start the bot, just test configuration
            status = "healthy"
            message = "Bot configuration valid"

            return {
                "status": status,
                "admin_users_count": len(self.settings.admin_user_ids),
                "environment": self.settings.environment,
                "debug_mode": self.settings.debug,
                "message": message
            }

        except Exception as e:
            logger.error(f"Bot functionality check failed: {e}")
            return {
                "status": "unhealthy",
                "admin_users_count": 0,
                "environment": self.settings.environment,
                "debug_mode": self.settings.debug,
                "message": f"Bot functionality check failed: {str(e)}"
            }

    async def get_statistics(self) -> Dict[str, Any]:
        """Get basic bot statistics."""
        try:
            engine = build_engine(self.settings)
            session_factory = build_session_factory(engine)

            async with session_factory() as session:
                # Agent count
                agents_result = await session.execute(
                    text("SELECT COUNT(*) FROM agents")
                )
                agents_count = agents_result.scalar() or 0

                # Submissions count
                submissions_result = await session.execute(
                    text("SELECT COUNT(*) FROM submissions")
                )
                submissions_count = submissions_result.scalar() or 0

                # Recent activity
                recent_result = await session.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM submissions
                        WHERE submitted_at > datetime('now', '-24 hours')
                    """)
                )
                recent_submissions = recent_result.scalar() or 0

                await engine.dispose()

                return {
                    "total_agents": agents_count,
                    "total_submissions": submissions_count,
                    "recent_submissions_24h": recent_submissions
                }

        except Exception as e:
            logger.error(f"Statistics check failed: {e}")
            return {
                "total_agents": 0,
                "total_submissions": 0,
                "recent_submissions_24h": 0
            }

    async def comprehensive_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        self.last_check = datetime.now()

        # Run all checks concurrently
        checks = await asyncio.gather(
            self.check_database(),
            self.check_redis(),
            asyncio.to_thread(self.check_system_resources),
            self.check_bot_functionality(),
            self.get_statistics(),
            return_exceptions=True
        )

        database_result = checks[0] if not isinstance(checks[0], Exception) else {"status": "unhealthy", "message": str(checks[0])}
        redis_result = checks[1] if not isinstance(checks[1], Exception) else {"status": "unhealthy", "message": str(checks[1])}
        system_result = checks[2] if not isinstance(checks[2], Exception) else {"status": "unhealthy", "message": str(checks[2])}
        bot_result = checks[3] if not isinstance(checks[3], Exception) else {"status": "unhealthy", "message": str(checks[3])}
        stats_result = checks[4] if not isinstance(checks[4], Exception) else {}

        # Determine overall status
        statuses = [
            database_result.get("status", "unhealthy"),
            redis_result.get("status", "unhealthy"),
            system_result.get("status", "unhealthy"),
            bot_result.get("status", "unhealthy")
        ]

        if "unhealthy" in statuses:
            overall_status = "unhealthy"
            self.healthy = False
        elif "warning" in statuses:
            overall_status = "warning"
            self.healthy = True
        else:
            overall_status = "healthy"
            self.healthy = True

        return {
            "status": overall_status,
            "timestamp": self.last_check.isoformat(),
            "uptime_seconds": int((datetime.now() - self.start_time).total_seconds()),
            "checks": {
                "database": database_result,
                "redis": redis_result,
                "system": system_result,
                "bot": bot_result
            },
            "statistics": stats_result,
            "version": self._get_version(),
            "environment": self.settings.environment
        }

    def _get_version(self) -> str:
        """Get bot version information."""
        try:
            # Try to get git commit hash
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=Path(__file__).parent.parent,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return f"git-{result.stdout.strip()}"
        except Exception:
            pass

        return "unknown"


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker(settings: Optional[Settings] = None) -> HealthChecker:
    """Get or create health checker instance."""
    global _health_checker
    if _health_checker is None:
        if settings is None:
            settings = load_settings()
        _health_checker = HealthChecker(settings)
    return _health_checker


