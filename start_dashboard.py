#!/usr/bin/env python3
"""
Standalone dashboard starter for the Ingress Prime Leaderboard Bot
"""

import asyncio
import os
import sys
import uvicorn
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def main():
    """Start the dashboard server"""
    print("🚀 Starting Ingress Leaderboard Dashboard...")

    # Load settings and database
    from bot.config import load_settings
    from bot.database import build_engine, build_session_factory, init_models

    # Load configuration
    settings = load_settings()

    if not settings.dashboard_enabled:
        print("❌ Dashboard is disabled in configuration")
        print("💡 Set DASHBOARD_ENABLED=true in your .env file")
        return

    print(f"📊 Dashboard Configuration:")
    print(f"  Host: {settings.dashboard_host}")
    print(f"  Port: {settings.dashboard_port}")
    print(f"  Admin Token: {'✅ Set' if settings.dashboard_admin_token else '❌ Not set'}")

    # Initialize database
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    await init_models(engine)

    # Create dashboard app
    from bot.dashboard import create_dashboard_app
    dashboard_app = create_dashboard_app(settings, session_factory)

    # Configure uvicorn
    config = uvicorn.Config(
        dashboard_app,
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        log_level="info",
        loop="asyncio",
    )

    server = uvicorn.Server(config)

    print(f"🌐 Dashboard starting on http://{settings.dashboard_host}:{settings.dashboard_port}")

    if settings.dashboard_admin_token:
        print(f"🔐 Admin panel: http://{settings.dashboard_host}:{settings.dashboard_port}/admin?token={settings.dashboard_admin_token}")
    else:
        print("⚠️  No admin token set - admin panel disabled")

    print("📋 Leaderboard: http://{settings.dashboard_host}:{settings.dashboard_port}")
    print("💡 Press Ctrl+C to stop the dashboard")

    try:
        await server.serve()
    except KeyboardInterrupt:
        print("\n🛑 Dashboard stopped by user")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())