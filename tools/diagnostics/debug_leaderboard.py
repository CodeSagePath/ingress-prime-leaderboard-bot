#!/usr/bin/env python3
"""
Debug Leaderboard Script for Ingress Leaderboard Bot

This script helps debug why leaderboards return no data.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def debug_database_content():
    """Debug the actual content and structure of the database."""
    print("🔍 Debugging Database Content")
    print("=" * 40)

    try:
        from bot.config import load_settings
        from bot.database import build_engine, build_session_factory, session_scope
        from bot.models import Agent, Submission
        from sqlalchemy import select, func, text

        # Connect to database
        settings = load_settings()
        engine = await build_engine(settings)
        session_factory = build_session_factory(engine)

        async with session_scope(session_factory) as session:
            # Check agents
            print("👥 Agents in database:")
            result = await session.execute(select(Agent.id, Agent.codename, Agent.faction))
            agents = result.fetchall()
            for agent in agents:
                print(f"   ID {agent.id}: {agent.codename} ({agent.faction})")

            # Check submissions with all details
            print(f"\n📊 Submissions in database:")
            result = await session.execute(
                select(
                    Submission.id,
                    Submission.agent_id,
                    Submission.chat_id,
                    Submission.ap,
                    Submission.time_span,
                    Submission.submitted_at
                ).order_by(Submission.submitted_at.desc())
            )
            submissions = result.fetchall()
            for sub in submissions:
                chat_info = f"Chat {sub.chat_id}" if sub.chat_id else "No Chat"
                print(f"   ID {sub.id}: Agent {sub.agent_id} - {sub.ap:,} AP ({sub.time_span}) - {chat_info}")

            # Check what chat IDs exist
            print(f"\n💬 Chat IDs in submissions:")
            result = await session.execute(
                select(Submission.chat_id, func.count(Submission.id))
                .group_by(Submission.chat_id)
                .order_by(Submission.chat_id)
            )
            chat_counts = result.fetchall()
            for chat_id, count in chat_counts:
                chat_name = f"Chat {chat_id}" if chat_id else "NULL/Global"
                print(f"   {chat_name}: {count} submissions")

            # Test different chat_id scenarios
            print(f"\n🧪 Testing leaderboard scenarios:")

            # Test 1: Global leaderboard (no chat filtering)
            print(f"\n1. Global leaderboard (chat_id=None):")
            try:
                from bot.leaderboard import get_leaderboard
                result = await get_leaderboard(
                    session=session,
                    limit=5,
                    chat_id=None,  # This should return all submissions
                    time_span="ALL TIME",
                    metric="ap"
                )
                if result:
                    print(f"   ✅ Found {len(result)} agents")
                    for i, (codename, faction, value, metrics) in enumerate(result[:3], 1):
                        print(f"   {i}. {codename} ({faction}) - {value:,} AP")
                else:
                    print(f"   ❌ No results")
            except Exception as e:
                print(f"   ❌ Error: {e}")

            # Test 2: Specific chat leaderboard
            if chat_counts:
                first_chat_id = chat_counts[0][0]
                if first_chat_id:
                    print(f"\n2. Chat-specific leaderboard (chat_id={first_chat_id}):")
                    try:
                        result = await get_leaderboard(
                            session=session,
                            limit=5,
                            chat_id=first_chat_id,
                            time_span="ALL TIME",
                            metric="ap"
                        )
                        if result:
                            print(f"   ✅ Found {len(result)} agents")
                            for i, (codename, faction, value, metrics) in enumerate(result[:3], 1):
                                print(f"   {i}. {codename} ({faction}) - {value:,} AP")
                        else:
                            print(f"   ❌ No results")
                    except Exception as e:
                        print(f"   ❌ Error: {e}")

            # Test 3: Simple query without complex joins
            print(f"\n3. Simple query test:")
            try:
                result = await session.execute(
                    select(
                        Agent.codename,
                        Agent.faction,
                        func.max(Submission.ap).label("max_ap")
                    )
                    .join(Submission, Submission.agent_id == Agent.id)
                    .group_by(Agent.id, Agent.codename, Agent.faction)
                    .order_by(func.max(Submission.ap).desc())
                    .limit(3)
                )
                simple_results = result.fetchall()
                if simple_results:
                    print(f"   ✅ Found {len(simple_results)} agents with simple query")
                    for i, (codename, faction, max_ap) in enumerate(simple_results, 1):
                        print(f"   {i}. {codename} ({faction}) - {max_ap:,} AP")
                else:
                    print(f"   ❌ No results with simple query")
            except Exception as e:
                print(f"   ❌ Error: {e}")

    except Exception as e:
        print(f"❌ Debug error: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Main debug function."""
    print("🧪 Ingress Leaderboard Debug Tool")
    print("=" * 50)

    await debug_database_content()

if __name__ == "__main__":
    asyncio.run(main())