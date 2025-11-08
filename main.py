#!/usr/bin/env python3
"""
Unified Ingress Prime Leaderboard Bot with integrated Dashboard
Runs both the Telegram bot and web dashboard in a single process
"""

import asyncio
import logging
import os
import sys
import uvicorn
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

logger = logging.getLogger(__name__)


async def start_dashboard_server(settings, session_factory):
    """Start the dashboard server in a background task"""
    if not settings.dashboard_enabled:
        logger.info("📊 Dashboard is disabled in configuration")
        return None, None

    try:
        # Initialize database for dashboard
        from bot.database import build_engine, init_models
        engine = build_engine(settings)
        await init_models(engine)

        # Create dashboard app
        from bot.dashboard import create_dashboard_app
        dashboard_app = create_dashboard_app(settings, session_factory)

        # Configure uvicorn
        config = uvicorn.Config(
            dashboard_app,
            host=settings.dashboard_host,
            port=settings.dashboard_port,
            log_level="warning",  # Reduce log noise
            loop="asyncio",
        )

        server = uvicorn.Server(config)

        logger.info(f"🌐 Dashboard configured on http://{settings.dashboard_host}:{settings.dashboard_port}")
        if settings.dashboard_admin_token:
            logger.info(f"🔐 Admin panel: http://{settings.dashboard_host}:{settings.dashboard_port}/admin?token={settings.dashboard_admin_token}")

        return server, engine

    except Exception as e:
        logger.error(f"❌ Failed to initialize dashboard: {e}")
        return None, None


async def run_dashboard_server(server):
    """Run the dashboard server"""
    try:
        logger.info("🚀 Starting dashboard server...")
        await server.serve()
    except Exception as e:
        logger.error(f"❌ Dashboard server error: {e}")


async def main():
    """Main entry point that runs both bot and dashboard"""
    print("🤖 Starting Unified Ingress Prime Leaderboard Bot...")

    try:
        # Import bot modules
        from bot.main import build_application
        from bot.database import build_session_factory

        # Build the bot application
        application = await build_application()
        settings = application.bot_data["settings"]
        health_checker = application.bot_data["health_checker"]

        # Perform startup health check
        print("🔍 Performing startup health check...")
        health_status = await health_checker.comprehensive_health_check()

        if health_status["status"] == "unhealthy":
            print("❌ Startup health check failed:")
            for check_name, check_result in health_status["checks"].items():
                if check_result["status"] == "unhealthy":
                    print(f"  - {check_name}: {check_result.get('message', 'Unknown error')}")
            print("\nPlease resolve these issues before starting the bot.")
            sys.exit(1)
        elif health_status["status"] == "warning":
            print("⚠️  Startup health check completed with warnings:")
            for check_name, check_result in health_status["checks"].items():
                if check_result["status"] == "warning":
                    print(f"  - {check_name}: {check_result.get('message', 'Warning')}")

        print(f"✅ Health check passed - Bot starting in {settings.environment} mode")

        # Create session factory for dashboard
        session_factory = build_session_factory(application.bot_data["engine"])

        # Start dashboard server if enabled
        dashboard_server = None
        dashboard_engine = None
        dashboard_task = None

        if settings.dashboard_enabled:
            dashboard_server, dashboard_engine = await start_dashboard_server(settings, session_factory)
            if dashboard_server:
                # Run dashboard in background task
                dashboard_task = asyncio.create_task(run_dashboard_server(dashboard_server))
                print(f"📊 Dashboard enabled on port {settings.dashboard_port}")

        # Start the bot
        async with application:
            await application.start()
            await application.updater.start_polling()

            print(f"🚀 {settings.bot_name} is now running!")
            print(f"📊 Environment: {settings.environment}")
            print(f"🌐 Dashboard: {'Enabled on port ' + str(settings.dashboard_port) if settings.dashboard_enabled else 'Disabled'}")

            # Add periodic health check job
            scheduler = application.bot_data["scheduler"]
            if settings.monitoring.health_check_enabled:
                scheduler.add_job(
                    lambda: asyncio.create_task(health_checker.comprehensive_health_check()),
                    trigger="interval",
                    minutes=5,
                    max_instances=1,
                    misfire_grace_time=60,
                    coalesce=True,
                )
                print("💓 Health monitoring enabled (every 5 minutes)")

            scheduler.start()

            try:
                # Keep the bot running
                await asyncio.Event().wait()

            except KeyboardInterrupt:
                print("\n🛑 Shutting down bot and dashboard...")

                # Stop dashboard server if running
                if dashboard_task:
                    print("🔄 Stopping dashboard server...")
                    dashboard_task.cancel()
                    try:
                        await dashboard_task
                    except asyncio.CancelledError:
                        pass

                    if dashboard_engine:
                        await dashboard_engine.dispose()

                print("✅ Dashboard stopped")

            finally:
                print("🔄 Stopping bot...")
                await application.updater.stop()
                print("✅ Bot stopped successfully")

    except KeyboardInterrupt:
        print("\n🛑 Unified bot interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        logger.error(f"Fatal error during startup: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.WARNING,  # Reduce log noise for unified operation
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)