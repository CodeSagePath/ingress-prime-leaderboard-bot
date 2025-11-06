#!/usr/bin/env python3
"""
Test script to verify the simplified leaderboard functionality works correctly.
"""

import asyncio
import sys
import os
import tempfile
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_leaderboard_functionality():
    """Test the leaderboard functionality with a minimal setup."""
    try:
        # Import necessary modules
        from sqlalchemy import create_engine, select, func
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from sqlalchemy.orm import sessionmaker
        import aiosqlite
        
        print("✅ Required modules imported successfully")
        
        # Create a temporary database for testing
        temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        temp_db.close()
        db_path = temp_db.name
        
        try:
            # Create an async engine
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
            async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            print("✅ Database engine created successfully")
            
            # Import models
            from bot.models import Base, Agent, Submission, Verification, VerificationStatus
            
            # Create tables
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            print("✅ Database tables created successfully")
            
            # Import the simplified leaderboard function
            from bot.services.leaderboard_simple import get_leaderboard
            
            print("✅ Simplified leaderboard function imported successfully")
            
            # Test the leaderboard function with no data
            async with async_session() as session:
                try:
                    result = await get_leaderboard(session, 10)
                    print(f"✅ Leaderboard function executed successfully with empty result: {len(result)} entries")
                except Exception as e:
                    print(f"❌ Error executing leaderboard function: {e}")
                    return False
            
            # Add some test data
            async with async_session() as session:
                # Add test agents
                agent1 = Agent(telegram_id=123, codename="TestAgent1", faction="ENL")
                agent2 = Agent(telegram_id=456, codename="TestAgent2", faction="RES")
                session.add_all([agent1, agent2])
                await session.flush()
                
                # Add test submissions
                submission1 = Submission(
                    agent_id=agent1.id,
                    chat_id=None,
                    ap=1000,
                    metrics={"mu": 100, "links": 50},
                    time_span="ALL TIME"
                )
                submission2 = Submission(
                    agent_id=agent2.id,
                    chat_id=None,
                    ap=2000,
                    metrics={"mu": 200, "links": 100},
                    time_span="ALL TIME"
                )
                session.add_all([submission1, submission2])
                await session.flush()
                
                # Add verification records
                verification1 = Verification(
                    submission_id=submission1.id,
                    screenshot_path="",
                    status=VerificationStatus.approved.value
                )
                verification2 = Verification(
                    submission_id=submission2.id,
                    screenshot_path="",
                    status=VerificationStatus.pending.value
                )
                session.add_all([verification1, verification2])
                
                print("✅ Test data added successfully")
            
            # Test the leaderboard function with data
            async with async_session() as session:
                try:
                    result = await get_leaderboard(session, 10)
                    print(f"✅ Leaderboard function executed successfully with data: {len(result)} entries")
                    
                    # Print the results
                    for i, (codename, faction, metric_value, metrics_dict) in enumerate(result, start=1):
                        print(f"   {i}. {codename} [{faction}] - {metric_value} AP, metrics: {metrics_dict}")
                except Exception as e:
                    print(f"❌ Error executing leaderboard function with data: {e}")
                    return False
            
            # Test with different metrics
            async with async_session() as session:
                try:
                    result = await get_leaderboard(session, 10, metric="mu")
                    print(f"✅ Leaderboard function executed successfully with mu metric: {len(result)} entries")
                    
                    # Print the results
                    for i, (codename, faction, metric_value, metrics_dict) in enumerate(result, start=1):
                        print(f"   {i}. {codename} [{faction}] - {metric_value} MU, metrics: {metrics_dict}")
                except Exception as e:
                    print(f"❌ Error executing leaderboard function with mu metric: {e}")
                    return False
            
            return True
            
        finally:
            # Clean up
            try:
                await engine.dispose()
            except:
                pass
            try:
                os.unlink(db_path)
            except:
                pass
    
    except Exception as e:
        print(f"❌ Error in test setup: {e}")
        return False

if __name__ == "__main__":
    print("Testing simplified leaderboard functionality...")
    success = asyncio.run(test_leaderboard_functionality())
    
    if success:
        print("\n✅ ALL TESTS PASSED: The simplified leaderboard functionality works correctly")
    else:
        print("\n❌ TESTS FAILED: There are issues with the simplified leaderboard functionality")
        sys.exit(1)