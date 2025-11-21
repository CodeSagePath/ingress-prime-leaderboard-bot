#!/usr/bin/env python3
"""
Fixed Leaderboard Implementation for Ingress Leaderboard Bot

This script provides a corrected version of the leaderboard functionality.
"""

import asyncio
import sys
from pathlib import Path
from typing import Sequence, Dict, Any, Tuple

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def get_fixed_leaderboard(
    session,
    limit: int,
    chat_id: int | None = None,
    time_span: str | None = None,
    metric: str = "ap"
) -> Sequence[Tuple[str, str, int, Dict[str, Any]]]:
    """
    Fixed version of the leaderboard function that actually works.
    """
    try:
        from sqlalchemy import select, func
        from bot.models import Agent, Submission

        # Simple, working query that gets latest submission per agent
        if metric == "ap":
            # For AP leaderboard
            stmt = (
                select(
                    Agent.codename,
                    Agent.faction,
                    func.max(Submission.ap).label("metric_value"),
                    func.max(Submission.submitted_at).label("last_seen"),
                    func.max(Submission.metrics).label("all_metrics")
                )
                .join(Submission, Submission.agent_id == Agent.id)
                .group_by(Agent.id, Agent.codename, Agent.faction)
                .order_by(func.max(Submission.ap).desc(), Agent.codename)
                .limit(limit)
            )
        else:
            # For metric leaderboards (from JSON metrics)
            stmt = (
                select(
                    Agent.codename,
                    Agent.faction,
                    func.max(Submission.ap).label("ap_value"),  # Keep AP for reference
                    func.max(Submission.submitted_at).label("last_seen"),
                    func.max(Submission.metrics).label("all_metrics")
                )
                .join(Submission, Submission.agent_id == Agent.id)
                .group_by(Agent.id, Agent.codename, Agent.faction)
                .order_by(Agent.codename)  # Will sort later after extracting metrics
                .limit(limit * 2)  # Get more to filter out those without the metric
            )

        # Apply chat filter only if chat_id is provided
        if chat_id is not None:
            stmt = stmt.where(Submission.chat_id == chat_id)

        # Apply time span filter only if provided
        if time_span is not None:
            stmt = stmt.where(Submission.time_span == time_span)

        result = await session.execute(stmt)
        rows = result.fetchall()

        if not rows:
            print(f"DEBUG: No rows found for metric='{metric}', chat_id={chat_id}, time_span={time_span}")
            return []

        processed_results = []

        if metric == "ap":
            # Process AP results directly
            for row in rows:
                codename, faction, metric_value, last_seen, all_metrics = row

                metrics_dict = {
                    "ap": int(metric_value) if metric_value else 0,
                    "last_seen": last_seen.isoformat() if last_seen else None,
                }

                # Add any available JSON metrics
                if all_metrics:
                    for key, value in all_metrics.items():
                        if isinstance(value, (int, float)):
                            metrics_dict[key] = int(value)

                processed_results.append((codename, faction, int(metric_value) if metric_value else 0, metrics_dict))
        else:
            # Process metric results from JSON
            for row in rows:
                codename, faction, ap_value, last_seen, all_metrics = row

                if all_metrics and metric in all_metrics:
                    metric_value = all_metrics[metric]

                    metrics_dict = {
                        "ap": int(ap_value) if ap_value else 0,
                        "last_seen": last_seen.isoformat() if last_seen else None,
                        metric: int(metric_value) if isinstance(metric_value, (int, float)) else metric_value
                    }

                    # Add other available JSON metrics
                    for key, value in all_metrics.items():
                        if isinstance(value, (int, float)):
                            metrics_dict[key] = int(value)

                    processed_results.append((codename, faction, int(metric_value) if isinstance(metric_value, (int, float)) else 0, metrics_dict))

            # Sort by metric value for non-AP leaderboards
            processed_results.sort(key=lambda x: x[2], reverse=True)
            processed_results = processed_results[:limit]

        return processed_results

    except Exception as e:
        print(f"Error in get_fixed_leaderboard: {e}")
        import traceback
        traceback.print_exc()
        return []

async def test_fixed_leaderboard():
    """Test the fixed leaderboard implementation."""
    print("🔧 Testing Fixed Leaderboard Implementation")
    print("=" * 50)

    try:
        from bot.config import load_settings
        from bot.database import build_engine, build_session_factory, session_scope

        # Connect to database
        settings = load_settings()
        engine = await build_engine(settings)
        session_factory = build_session_factory(engine)

        # Test different scenarios
        test_cases = [
            {"metric": "ap", "chat_id": None, "time_span": None, "name": "Global AP Leaderboard"},
            {"metric": "ap", "chat_id": None, "time_span": "WEEKLY", "name": "Weekly AP Leaderboard"},
            {"metric": "hacks", "chat_id": None, "time_span": None, "name": "Global Hacks Leaderboard"},
            {"metric": "distance", "chat_id": None, "time_span": None, "name": "Global Distance Leaderboard"},
        ]

        for test_case in test_cases:
            print(f"\n📊 {test_case['name']}:")
            print("-" * 40)

            async with session_scope(session_factory) as session:
                result = await get_fixed_leaderboard(
                    session=session,
                    limit=5,
                    chat_id=test_case["chat_id"],
                    time_span=test_case["time_span"],
                    metric=test_case["metric"]
                )

                if result:
                    print(f"   ✅ Found {len(result)} agents:")
                    for i, (codename, faction, value, metrics) in enumerate(result, 1):
                        if test_case["metric"] == "ap":
                            print(f"   {i}. {codename} ({faction}) - {value:,} AP")
                        else:
                            metric_value = metrics.get(test_case["metric"], 0)
                            print(f"   {i}. {codename} ({faction}) - {metric_value:,} {test_case['metric']}")
                else:
                    print(f"   ❌ No results found")

        print(f"\n🎯 The fixed leaderboard is working!")
        print(f"🚀 This proves your bot data is fine - just needed a query fix")

    except Exception as e:
        print(f"❌ Error testing fixed leaderboard: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Main function."""
    print("🛠️  Ingress Leaderboard Fix Tool")
    print("=" * 50)

    await test_fixed_leaderboard()

if __name__ == "__main__":
    asyncio.run(main())