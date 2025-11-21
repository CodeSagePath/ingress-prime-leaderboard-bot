#!/usr/bin/env python3
"""
Database Connection Test Script for Ingress Leaderboard Bot

This script tests the database connection and shows sample data.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_database_connection():
    """Test database connection and show data."""
    print("🔌 Testing Database Connection")
    print("=" * 40)

    try:
        # Import after adding to path
        from bot.config import load_settings
        from bot.database import build_engine, build_session_factory, session_scope
        from bot.models import Agent, Submission
        from sqlalchemy import text, select, func

        # Load settings
        settings = load_settings()
        print(f"📊 Database URL: {settings.database.url}")

        # Build engine and session factory
        engine = await build_engine(settings)
        session_factory = build_session_factory(engine)

        # Test connection
        async with session_scope(session_factory) as db:
            print("✅ Database connection successful!")

            # Check tables exist
            try:
                result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                tables = result.fetchall()
                print(f"📋 Tables found: {[t[0] for t in tables]}")
            except:
                # For non-SQLite databases, try different approach
                print("📋 Database tables assumed to exist (non-SQLite database)")

            # Count agents
            try:
                result = await db.execute(select(func.count(Agent.id)))
                agent_count = result.scalar()
                print(f"👥 Total agents: {agent_count}")

                if agent_count > 0:
                    # Show sample agents
                    result = await db.execute(
                        select(Agent.codename, Agent.faction)
                        .limit(5)
                    )
                    agents = result.fetchall()
                    print(f"\n📝 Sample agents:")
                    for agent in agents:
                        print(f"   - {agent.codename} ({agent.faction})")

                    # Count submissions
                    result = await db.execute(select(func.count(Submission.id)))
                    submission_count = result.scalar()
                    print(f"\n📈 Total submissions: {submission_count}")

                    if submission_count > 0:
                        # Show recent submissions
                        result = await db.execute(
                            select(Submission.agent_id, Submission.ap, Submission.submitted_at)
                            .order_by(Submission.submitted_at.desc())
                            .limit(5)
                        )
                        submissions = result.fetchall()
                        print(f"\n📊 Recent submissions:")
                        for sub in submissions:
                            print(f"   - Agent {sub.agent_id}: {sub.ap} AP - {sub.submitted_at}")

                        # Show available metrics for leaderboards
                        try:
                            result = await db.execute(
                                select(Submission.agent_id, Submission.metrics)
                                .where(Submission.metrics.isnot(None))
                                .limit(1)
                            )
                            sample = result.fetchone()
                            if sample and sample.metrics:
                                metrics_keys = list(sample.metrics.keys())[:10]
                                print(f"\n🏆 Available metrics: {', '.join(metrics_keys)}")
                        except Exception as e:
                            print(f"⚠️  Could not read metrics: {e}")

                print(f"\n✅ Your bot should work with this data!")
                print(f"🚀 Try running: python main.py")

            except Exception as e:
                print(f"❌ Error querying data: {e}")
                print("⚠️  Database is connected but tables might be empty")

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\n🔧 Troubleshooting:")
        print("1. Check if DATABASE_URL in .env is correct")
        print("2. Verify database server is running")
        print("3. Ensure network connectivity to database")
        print("4. Check database credentials")
        print("5. Run: python diagnose_database.py")

async def test_bot_import():
    """Test if bot modules can be imported."""
    print(f"\n🤖 Testing Bot Module Imports")
    print("=" * 40)

    modules_to_test = [
        "bot.config",
        "bot.models",
        "bot.database",
        "bot.app"
    ]

    for module_name in modules_to_test:
        try:
            __import__(module_name)
            print(f"✅ {module_name}")
        except Exception as e:
            print(f"❌ {module_name}: {e}")

async def main():
    """Main test function."""
    print("🧪 Ingress Leaderboard Bot Connection Test")
    print("=" * 50)

    await test_bot_import()
    await test_database_connection()

if __name__ == "__main__":
    asyncio.run(main())