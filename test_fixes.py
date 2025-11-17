#!/usr/bin/env python3
"""Test script for the critical fixes"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_database_and_leaderboard():
    """Test database connectivity and leaderboard data"""
    print("🔌 Testing database connectivity...")

    try:
        from bot.config import load_settings
        from bot.database import build_engine, build_session_factory, session_scope
        from bot.models import Agent, Submission
        from sqlalchemy import select, func

        settings = load_settings()

        # Test database connection
        engine = await build_engine(settings)
        print("✅ Database engine created successfully")

        session_factory = build_session_factory(engine)

        async with session_scope(session_factory) as session:
            # Check counts
            agent_count = await session.execute(select(func.count(Agent.id)))
            submission_count = await session.execute(select(func.count(Submission.id)))

            agents = agent_count.scalar()
            submissions = submission_count.scalar()

            print(f"📊 Database stats:")
            print(f"  Agents: {agents}")
            print(f"  Submissions: {submissions}")

            if agents > 0:
                # Show sample agents
                sample_agents = await session.execute(
                    select(Agent.codename, Agent.faction).limit(3)
                )
                agent_data = sample_agents.fetchall()
                print(f"Sample agents:")
                for codename, faction in agent_data:
                    print(f"  - {codename} [{faction}]")

            if submissions > 0:
                # Show sample submissions with agent names
                sample_submissions = await session.execute(
                    select(
                        Agent.codename,
                        Agent.faction,
                        Submission.ap,
                        Submission.submitted_at
                    ).join(Submission).limit(3)
                )
                submission_data = sample_submissions.fetchall()
                print(f"Sample submissions:")
                for codename, faction, ap, submitted_at in submission_data:
                    print(f"  - {codename} [{faction}]: {ap} AP")

        await engine.dispose()
        print("✅ Database test completed successfully")
        return agents > 0 and submissions > 0

    except Exception as e:
        print(f"❌ Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_health_checker():
    """Test the health checker with event loop fix"""
    print("🔍 Testing health checker...")

    try:
        from bot.config import load_settings
        from bot.health import get_health_checker

        settings = load_settings()
        health_checker = get_health_checker(settings)

        # Test comprehensive health check
        status = await health_checker.comprehensive_health_check()

        print(f"📊 Health check results:")
        print(f"  Overall status: {status['status']}")
        print(f"  Database: {status['checks']['database']['status']}")
        print(f"  Redis: {status['checks']['redis']['status']}")

        return status['status'] in ['healthy', 'warning']

    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_imports():
    """Test that all imports work correctly"""
    print("📦 Testing imports...")

    try:
        from bot.utils.data_validator import DataValidator
        from bot.utils.file_importer import FileImporter
        from bot.utils.resilient_redis import get_resilient_redis
        from bot.utils.retry_decorators import telegram_message_retry
        from bot.database import build_engine, resilient_session_scope
        print("✅ All utility imports successful")
        return True
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("🧪 Running Critical Fixes Tests")
    print("=" * 50)

    tests = [
        ("Imports", test_imports()),
        ("Database & Data", await test_database_and_leaderboard()),
        ("Health Checker", await test_health_checker())
    ]

    print("\n" + "=" * 50)
    print("📋 TEST RESULTS:")

    all_passed = True
    for test_name, passed in tests:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False

    print("=" * 50)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Your bot should work now.")
    else:
        print("⚠️  Some tests failed. Check the errors above.")

    return all_passed

if __name__ == "__main__":
    asyncio.run(main())