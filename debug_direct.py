#!/usr/bin/env python3
"""
Direct debug of the leaderboard function
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def debug_direct():
    """Debug the actual leaderboard function directly."""
    print("🔍 Direct Debug of Leaderboard Function")
    print("=" * 50)

    try:
        from bot.config import load_settings
        from bot.database import build_engine, build_session_factory, session_scope
        from bot.leaderboard import _get_ap_leaderboard  # Import the actual function

        # Connect to database
        settings = load_settings()
        engine = await build_engine(settings)
        session_factory = build_session_factory(engine)

        print("✅ Connected to database")

        # Test the AP leaderboard function directly
        print(f"\n📊 Testing _get_ap_leaderboard directly:")
        async with session_scope(session_factory) as session:
            result = await _get_ap_leaderboard(
                session=session,
                limit=5,
                chat_id=None,  # Global leaderboard
                time_span="WEEKLY"  # Match the actual data
            )

            print(f"Result type: {type(result)}")
            print(f"Result length: {len(result) if result else 'None'}")

            if result:
                print(f"✅ SUCCESS: Found {len(result)} agents")
                for i, (codename, faction, value, metrics) in enumerate(result, 1):
                    print(f"   {i}. {codename} ({faction}) - {value:,} AP")
                    print(f"      Metrics: {list(metrics.keys())}")
            else:
                print(f"❌ No results found")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_direct())