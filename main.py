#!/usr/bin/env python3
"""
Unified Ingress Prime Leaderboard Bot with integrated Dashboard
Runs both the Telegram bot and web dashboard in a single process
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timezone 
from bot.config import load_settings

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(project_root / "config" / ".env")

# Dictionary to track bot messages for auto-deletion
bot_messages = {}  # {message_id: (timestamp, chat_id)}

# Global variable for bot message cleanup timing
bot_message_cleanup_minutes = 5

logger = logging.getLogger(__name__)


def start_dashboard_process():
    """Dashboard process function"""
    try:
        # Load environment variables from .env file
        from dotenv import load_dotenv
        project_root = Path(__file__).parent
        load_dotenv(project_root / "config" / ".env")

        from bot.config import load_settings
        settings = load_settings()
        if not settings.dashboard_enabled:
            print("❌ Dashboard is disabled in configuration")
            return

        print("🌐 Starting Dashboard Server...")
        import asyncio

        def run_dashboard():
            from bot.dashboard import start_dashboard_server, run_dashboard_server_sync
            dashboard_app, _ = start_dashboard_server(settings)
            if dashboard_app:
                run_dashboard_server_sync(dashboard_app, settings)
            else:
                print("❌ Failed to initialize dashboard")

        run_dashboard()
    except Exception as e:
        print(f"❌ Dashboard error: {e}")


def start_bot_process(bot_settings):
    """Bot process function"""
    try:
        print("🤖 Starting Telegram Bot...")

        # Store cleanup settings globally for the bot process
        global bot_message_cleanup_minutes
        bot_message_cleanup_minutes = bot_settings['bot_message_cleanup_minutes']

        from bot.app import main
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Bot error: {e}")


async def schedule_bot_message_deletion(context, message_id: int, chat_id: int, delete_after_minutes: int):
    """Schedule deletion of bot message after specified minutes"""
    try:
        await asyncio.sleep(delete_after_minutes * 60)

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.info(f"Auto-deleted bot message {message_id} from chat {chat_id}")
        except Exception as e:
            logger.warning(f"Failed to delete bot message {message_id} from chat {chat_id}: {e}")
        finally:
            # Remove from tracking
            if message_id in bot_messages:
                del bot_messages[message_id]

    except asyncio.CancelledError:
        # Task was cancelled, likely due to shutdown
        if message_id in bot_messages:
            del bot_messages[message_id]
    except Exception as e:
        logger.error(f"Error in bot message deletion task for message {message_id}: {e}")


async def track_and_schedule_deletion(context, message, delete_after_minutes: int = 5):
    """Track bot message and schedule its deletion"""
    if message and delete_after_minutes > 0:
        message_id = message.message_id
        chat_id = message.chat.id
        current_time = datetime.now(timezone.utc)

        # Track the message
        bot_messages[message_id] = (current_time, chat_id)

        # Schedule deletion
        asyncio.create_task(schedule_bot_message_deletion(context, message_id, chat_id, delete_after_minutes))


async def send_with_auto_delete(context, text: str, delete_after_minutes: int = 5, reply_to_message_id: int = None, parse_mode: str = None):
    """Send a message and schedule its auto-deletion"""
    try:
        message = await context.bot.send_message(
            chat_id=context.effective_chat.id,
            text=text,
            reply_to_message_id=reply_to_message_id,
            parse_mode=parse_mode
        )

        # Schedule deletion of this bot message
        await track_and_schedule_deletion(context, message, delete_after_minutes)
        return message

    except Exception as e:
        logger.error(f"Failed to send message with auto-deletion: {e}")
        return None


async def start_dashboard_server(settings):
    """Initialize dashboard server configuration without starting it"""
    if not settings.dashboard_enabled:
        logger.info("📊 Dashboard is disabled in configuration")
        return None, None

    try:
        # Create dashboard app configuration (but don't start server yet)
        from bot.dashboard import create_dashboard_app
        from bot.database import build_engine, build_session_factory, init_models

        engine = build_engine(settings)
        await init_models(engine)
        session_factory = build_session_factory(engine)
        dashboard_app = create_dashboard_app(settings, session_factory)

        logger.info(f"🌐 Dashboard configured on http://{settings.dashboard_host}:{settings.dashboard_port}")
        if settings.dashboard_admin_token:
            logger.info(f"🔐 Admin panel: http://{settings.dashboard_host}:{settings.dashboard_port}/admin?token={settings.dashboard_admin_token}")

        return dashboard_app, engine

    except Exception as e:
        logger.error(f"❌ Failed to initialize dashboard: {e}")
        return None, None


def run_dashboard_server_sync(dashboard_app, settings):
    """Run dashboard server in a separate process (blocking)"""
    import uvicorn
    import os

    # Get configuration from environment variables as fallback
    host = getattr(settings, 'dashboard_host', None) or os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = getattr(settings, 'dashboard_port', None) or int(os.getenv("DASHBOARD_PORT", "8000"))

    try:
        uvicorn.run(
            dashboard_app,
            host=host,
            port=port,
            log_level="warning"
        )
    except Exception as e:
        logger.error(f"❌ Dashboard server error: {e}")


async def main():
    """Main entry point that runs both bot and dashboard"""
    print("🤖 Starting Unified Ingress Prime Leaderboard Bot...")

    try:
        # Import bot modules
        from bot.app import build_application
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
            dashboard_app, dashboard_engine = await start_dashboard_server(settings)
            if dashboard_app:
                print(f"📊 Dashboard configured on port {settings.dashboard_port} (use --dashboard to start)")

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
                health_check_interval = int(os.environ.get("HEALTH_CHECK_INTERVAL_MINUTES", "5"))
                print(f"💓 Health monitoring enabled (every {health_check_interval} minutes)")

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
    import argparse
    import logging
    import multiprocessing
    from pathlib import Path

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Ingress Prime Leaderboard Bot')
    parser.add_argument('--no-dashboard', action='store_true',
                       help='Start bot only (no dashboard)')
    args = parser.parse_args()

    # Configure logging
    settings = load_settings()
    log_level = getattr(logging, settings.server.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Add file logging if enabled
    if settings.monitoring.log_to_file:
        try:
            from logging.handlers import RotatingFileHandler
            import os

            log_file = Path(settings.monitoring.log_file_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=int(settings.monitoring.log_max_size.replace('MB', '')) * 1024 * 1024,
                backupCount=settings.monitoring.log_backup_count
            )
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            )

            root_logger = logging.getLogger()
            root_logger.addHandler(file_handler)

            print(f"📝 Logging to file: {log_file}")

        except Exception as e:
            print(f"⚠️ Failed to set up file logging: {e}")

    # Bot message auto-deletion configuration
    bot_message_cleanup_minutes = int(os.getenv('BOT_MESSAGE_CLEANUP_MINUTES', '5'))

    # Pass settings to bot process
    bot_settings = {
        'settings': settings,
        'bot_message_cleanup_minutes': bot_message_cleanup_minutes
    }

    # Start processes
    processes = []

    if not args.no_dashboard:
        if settings.dashboard_enabled:
            # Start dashboard in background process
            dashboard_proc = multiprocessing.Process(target=start_dashboard_process)
            dashboard_proc.start()
            processes.append(dashboard_proc)
            print(f"📊 Dashboard process started (PID: {dashboard_proc.pid})")

    # Start bot process (always runs)
    bot_proc = multiprocessing.Process(target=start_bot_process, args=(bot_settings,))
    bot_proc.start()
    processes.append(bot_proc)
    print(f"🤖 Bot process started (PID: {bot_proc.pid})")

    print(f"🚀 Ingress Prime Leaderboard is running!")
    print(f"   • Bot: Active")
    print(f"   • Bot message cleanup: {bot_message_cleanup_minutes} minutes")
    if not args.no_dashboard:
        if settings.dashboard_enabled:
            print(f"   • Dashboard: http://{settings.dashboard_host}:{settings.dashboard_port}")
        else:
            print(f"   • Dashboard: Disabled (set DASHBOARD_ENABLED=true)")
    print(f"   • Press Ctrl+C to stop both services")

    # Setup signal handlers for graceful shutdown
    import signal

    def signal_handler(signum, frame):
        print(f"\n🛑 Received signal {signum}, shutting down...")
        for proc in processes:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
                if proc.is_alive():
                    print(f"Force killing process {proc.pid}")
                    proc.kill()
        print("✅ All services stopped!")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Wait for processes to complete
        for proc in processes:
            proc.join()
    except KeyboardInterrupt:
        print("\n🛑 Keyboard interrupt, shutting down...")
        for proc in processes:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
                if proc.is_alive():
                    print(f"Force killing process {proc.pid}")
                    proc.kill()
        print("✅ All services stopped!")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Error: {e}")
        for proc in processes:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
                if proc.is_alive():
                    proc.kill()
        sys.exit(1)