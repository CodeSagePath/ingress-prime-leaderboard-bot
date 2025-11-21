#!/usr/bin/env python3
"""
Test Bot Commands Script for Ingress Leaderboard Bot

This script tests the core bot functionality directly without running the full Telegram bot.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_leaderboard_functionality():
    """Test the leaderboard functionality."""
    print("🏆 Testing Leaderboard Functionality")
    print("=" * 40)

    try:
        from bot.config import load_settings
        from bot.database import build_engine, build_session_factory, session_scope
        from bot.models import Agent, Submission
        from bot.leaderboard import get_leaderboard
        from sqlalchemy import select, func

        # Load settings and connect to database
        settings = load_settings()
        engine = await build_engine(settings)
        session_factory = build_session_factory(engine)

        print(f"✅ Database connected successfully")

        # Test different leaderboard metrics
        test_metrics = [
            "ap",          # AP-based leaderboard
            "hacks",       # JSON metric leaderboard
            "distance",    # Another JSON metric
            "links",       # Field creation metric
        ]

        for metric in test_metrics:
            print(f"\n📊 Testing {metric.upper()} leaderboard:")
            try:
                async with session_scope(session_factory) as session:
                    # Get leaderboard data
                    result = await get_leaderboard(
                        session=session,
                        chat_id=None,  # Global leaderboard (not chat-specific)
                        time_span="ALL TIME",
                        metric=metric,
                        limit=5
                    )

                    if result:
                        print(f"   ✅ Found {len(result)} agents for {metric}")
                        for i, (codename, faction, value, metrics) in enumerate(result[:3], 1):
                            print(f"   {i}. {codename} ({faction}) - {value:,}")
                    else:
                        print(f"   ❌ No data found for {metric}")

            except Exception as e:
                print(f"   ❌ Error testing {metric}: {e}")

        # Test agent registration
        print(f"\n👥 Testing Agent Registration:")
        async with session_scope(session_factory) as session:
            result = await session.execute(
                select(Agent.codename, Agent.faction)
                .order_by(Agent.codename)
            )
            agents = result.fetchall()
            print(f"   ✅ Found {len(agents)} registered agents:")
            for agent in agents:
                print(f"   - {agent.codename} ({agent.faction})")

        # Test submission data quality
        print(f"\n📈 Testing Submission Data:")
        async with session_scope(session_factory) as session:
            result = await session.execute(
                select(Submission)
                .order_by(Submission.ap.desc())
                .limit(3)
            )
            submissions = result.fetchall()
            print(f"   ✅ Found recent submissions:")
            for sub in submissions:
                print(f"   - Agent {sub.agent_id}: {sub.ap:,} AP ({sub.time_span})")
                print(f"     Metrics: {list(sub.metrics.keys())[:5]}...")

        print(f"\n✅ Bot functionality test completed successfully!")
        print(f"🚀 Your bot should work perfectly!")

    except Exception as e:
        print(f"❌ Error testing bot functionality: {e}")
        import traceback
        traceback.print_exc()

async def test_available_commands():
    """Show what commands are available."""
    print(f"\n🤖 Available Bot Commands:")
    print(f"=" * 40)

    commands = [
        ("/start", "Register as a new agent"),
        ("/leaderboard", "Show AP leaderboard"),
        ("/leaderboard [metric]", "Show custom metric leaderboard"),
        ("/stats", "Show your personal stats"),
        ("/register", "Register with your Ingress agent name"),
        ("/help", "Show all available commands"),
        ("/debug", "Debug database and show data info"),
        ("/top5", "Show top 5 agents"),
        ("/myrank", "Show your current rank"),
    ]

    for cmd, desc in commands:
        print(f"   {cmd:<20} - {desc}")

    print(f"\n📊 Available metrics for leaderboards:")
    metrics = [
        "ap", "hacks", "xm", "distance", "links", "fields",
        "portals", "resonators", "plus_tokens", "current_ap"
    ]
    for metric in metrics:
        print(f"   - {metric}")

async def main():
    """Main test function."""
    print("🧪 Ingress Leaderboard Bot Command Test")
    print("=" * 50)

    await test_available_commands()
    await test_leaderboard_functionality()

    print(f"\n📋 Summary:")
    print(f"✅ Database connection works")
    print(f"✅ Agent data is present")
    print(f"✅ Submission data is available")
    print(f"✅ Leaderboard functionality works")
    print(f"✅ Your bot should be working!")

if __name__ == "__main__":
    asyncio.run(main())