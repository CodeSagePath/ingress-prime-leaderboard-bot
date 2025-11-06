#!/usr/bin/env python3
"""
Test script to verify that the leaderboard command still works correctly
after the datetime serialization fix.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.database import build_engine, init_models
from bot.config import load_settings
from bot.models import Agent, Submission
from bot.services.leaderboard import get_leaderboard

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def setup_test_data(session_factory: async_sessionmaker):
    """Set up test data for leaderboard testing."""
    logger.info("Setting up test data...")
    
    async with session_factory() as session:
        # Create test agents
        agents = [
            Agent(telegram_id=1001, codename="TestAgent1", faction="ENL"),
            Agent(telegram_id=1002, codename="TestAgent2", faction="RES"),
            Agent(telegram_id=1003, codename="TestAgent3", faction="ENL"),
            Agent(telegram_id=1004, codename="TestAgent4", faction="RES"),
        ]
        
        for agent in agents:
            session.add(agent)
        
        await session.flush()
        
        # Create test submissions with datetime objects in metrics
        from datetime import datetime, timezone
        from bot.main import convert_datetime_to_iso
        
        submissions = [
            # Agent1 submissions
            Submission(
                agent_id=agents[0].id,
                ap=10000,
                metrics=convert_datetime_to_iso({
                    "timestamp": datetime.now(timezone.utc),
                    "portals_captured": 50,
                    "links_created": 25
                }),
                time_span="ALL TIME"
            ),
            Submission(
                agent_id=agents[0].id,
                ap=15000,
                metrics=convert_datetime_to_iso({
                    "timestamp": datetime.now(timezone.utc),
                    "portals_captured": 75,
                    "links_created": 40
                }),
                time_span="WEEKLY"
            ),
            
            # Agent2 submissions
            Submission(
                agent_id=agents[1].id,
                ap=12000,
                metrics=convert_datetime_to_iso({
                    "timestamp": datetime.now(timezone.utc),
                    "portals_captured": 60,
                    "links_created": 30
                }),
                time_span="ALL TIME"
            ),
            
            # Agent3 submissions
            Submission(
                agent_id=agents[2].id,
                ap=8000,
                metrics=convert_datetime_to_iso({
                    "timestamp": datetime.now(timezone.utc),
                    "portals_captured": 40,
                    "links_created": 20
                }),
                time_span="ALL TIME"
            ),
            
            # Agent4 submissions
            Submission(
                agent_id=agents[3].id,
                ap=18000,
                metrics=convert_datetime_to_iso({
                    "timestamp": datetime.now(timezone.utc),
                    "portals_captured": 90,
                    "links_created": 45
                }),
                time_span="ALL TIME"
            ),
        ]
        
        for submission in submissions:
            session.add(submission)
        
        await session.commit()
        logger.info("Test data setup completed")

async def test_leaderboard_functionality(session_factory: async_sessionmaker):
    """Test the leaderboard functionality with the new datetime fix."""
    logger.info("Testing leaderboard functionality...")
    
    async with session_factory() as session:
        # Test 1: Basic leaderboard without filters
        logger.info("Test 1: Basic leaderboard without filters")
        try:
            rows = await get_leaderboard(session, limit=10)
            logger.info(f"✅ Basic leaderboard returned {len(rows)} rows")
            for i, (codename, faction, metric_value, metrics_dict) in enumerate(rows, start=1):
                logger.info(f"  {i}. {codename} [{faction}] - {metric_value} AP")
        except Exception as e:
            logger.error(f"❌ Basic leaderboard test failed: {e}")
            return False
        
        # Test 2: Leaderboard with time_span filter
        logger.info("Test 2: Leaderboard with time_span filter")
        try:
            rows = await get_leaderboard(session, limit=10, time_span="WEEKLY")
            logger.info(f"✅ Weekly leaderboard returned {len(rows)} rows")
            for i, (codename, faction, metric_value, metrics_dict) in enumerate(rows, start=1):
                logger.info(f"  {i}. {codename} [{faction}] - {metric_value} AP")
        except Exception as e:
            logger.error(f"❌ Weekly leaderboard test failed: {e}")
            return False
        
        # Test 3: Leaderboard with chat_id filter
        logger.info("Test 3: Leaderboard with chat_id filter")
        try:
            rows = await get_leaderboard(session, limit=10, chat_id=12345)
            logger.info(f"✅ Chat-specific leaderboard returned {len(rows)} rows")
            for i, (codename, faction, metric_value, metrics_dict) in enumerate(rows, start=1):
                logger.info(f"  {i}. {codename} [{faction}] - {metric_value} AP")
        except Exception as e:
            logger.error(f"❌ Chat-specific leaderboard test failed: {e}")
            return False
        
        # Test 4: Leaderboard with custom metric
        logger.info("Test 4: Leaderboard with custom metric")
        try:
            rows = await get_leaderboard(session, limit=10, metric="ap")
            logger.info(f"✅ Custom metric leaderboard returned {len(rows)} rows")
            for i, (codename, faction, metric_value, metrics_dict) in enumerate(rows, start=1):
                logger.info(f"  {i}. {codename} [{faction}] - {metric_value} AP")
        except Exception as e:
            logger.error(f"❌ Custom metric leaderboard test failed: {e}")
            return False
        
        # Test 5: Verify that metrics with datetime objects are properly serialized
        logger.info("Test 5: Verify datetime serialization in metrics")
        try:
            result = await session.execute(select(Submission))
            submissions = result.scalars().all()
            
            for submission in submissions:
                # This should not raise an exception if datetime objects are properly serialized
                metrics = submission.metrics
                logger.info(f"  Submission {submission.id} metrics: {metrics}")
                
                # Verify that the metrics can be JSON serialized
                import json
                json_str = json.dumps(metrics)
                logger.info(f"  Submission {submission.id} JSON serialization successful")
            
            logger.info("✅ Datetime serialization in metrics test passed")
        except Exception as e:
            logger.error(f"❌ Datetime serialization in metrics test failed: {e}")
            return False
    
    logger.info("🎉 All leaderboard functionality tests passed!")
    return True

async def cleanup_test_data(session_factory: async_sessionmaker):
    """Clean up test data."""
    logger.info("Cleaning up test data...")
    
    async with session_factory() as session:
        from sqlalchemy import delete
        
        # Get test agent IDs
        result = await session.execute(select(Agent.id).where(Agent.telegram_id.in_([1001, 1002, 1003, 1004])))
        agent_ids = [row[0] for row in result.all()]
        
        if agent_ids:
            # Delete test submissions
            await session.execute(delete(Submission).where(Submission.agent_id.in_(agent_ids)))
            # Delete test agents
            await session.execute(delete(Agent).where(Agent.id.in_(agent_ids)))
            await session.commit()
    
    logger.info("Test data cleanup completed")

async def main():
    """Main test function."""
    logger.info("Starting leaderboard functionality tests after datetime fix...")
    
    # Set up database
    settings = load_settings()
    engine = build_engine(settings)
    await init_models(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    
    try:
        # Set up test data
        await setup_test_data(session_factory)
        
        # Test leaderboard functionality
        leaderboard_test_passed = await test_leaderboard_functionality(session_factory)
        
        # Clean up test data
        await cleanup_test_data(session_factory)
        
        # Summary
        if leaderboard_test_passed:
            logger.info("🎉 All leaderboard functionality tests passed! The previous fix is still working correctly after the datetime serialization changes.")
            return True
        else:
            logger.error("❌ Some leaderboard functionality tests failed. The previous fix may have been affected by the datetime serialization changes.")
            return False
    except Exception as e:
        logger.error(f"❌ Test setup or cleanup failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(main())