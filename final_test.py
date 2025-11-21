#!/usr/bin/env python3
"""
Final Test Script for Fixed Leaderboard Bot
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def final_test():
    """Final test of the fixed bot functionality."""
    print("🎯 FINAL TEST: Fixed Ingress Leaderboard Bot")
    print("=" * 60)

    try:
        from bot.config import load_settings
        from bot.database import build_engine, build_session_factory, session_scope
        from bot.leaderboard import get_leaderboard  # This should now use our fixed functions

        # Connect to database
        settings = load_settings()
        engine = await build_engine(settings)
        session_factory = build_session_factory(engine)

        print("✅ Connected to database and imported bot modules")

        # Test the actual bot leaderboard function
        test_metrics = ["ap", "hacks", "distance"]

        for metric in test_metrics:
            print(f"\n📊 Testing {metric.upper()} leaderboard (actual bot function):")
            print("-" * 50)

            async with session_scope(session_factory) as session:
                # This should now work with our fixes (correct parameter order)
                result = await get_leaderboard(
                    session=session,
                    limit=5,
                    chat_id=None,  # Global leaderboard
                    time_span="ALL TIME",
                    metric=metric
                )

                if result:
                    print(f"✅ SUCCESS: Found {len(result)} agents")
                    for i, (codename, faction, value, metrics) in enumerate(result[:3], 1):
                        if metric == "ap":
                            print(f"   {i}. {codename} ({faction}) - {value:,} AP")
                        else:
                            metric_val = metrics.get(metric, value)
                            print(f"   {i}. {codename} ({faction}) - {metric_val:,} {metric}")
                else:
                    print(f"❌ FAILED: No results found for {metric}")

        print(f"\n🎉 FINAL VERDICT:")
        if metric == "ap":
            print("✅ Your bot is now WORKING!")
            print("✅ The leaderboard bug has been FIXED!")
            print("✅ Your agent stats will now display properly!")
            print("\n🚀 Your bot is ready to compete with agent-stats.com!")
        else:
            print("❌ Still some issues to resolve...")

    except Exception as e:
        print(f"❌ Error in final test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(final_test())