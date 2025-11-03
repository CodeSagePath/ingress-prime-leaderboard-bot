#!/usr/bin/env python3
"""
Test script to verify that leaderboard data is being queried correctly.
This script will check if the test data is being properly inserted and retrieved.
"""

import asyncio
import sys
import os
import tempfile
import traceback
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_data_verification():
    """Test that data is being properly inserted and retrieved."""
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
            
            # Import the fixed leaderboard function
            from bot.services.leaderboard_fixed import get_leaderboard
            
            print("✅ Fixed leaderboard function imported successfully")
            
            # Add test data
            async with async_session() as session:
                # Add test agents
                agent1 = Agent(telegram_id=123, codename="TestAgent1", faction="ENL")
                agent2 = Agent(telegram_id=456, codename="TestAgent2", faction="RES")
                session.add_all([agent1, agent2])
                await session.flush()
                
                print(f"✅ Added agents: {agent1.codename} (ID: {agent1.id}), {agent2.codename} (ID: {agent2.id})")
                
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
                
                print(f"✅ Added submissions: {submission1.id} (AP: {submission1.ap}), {submission2.id} (AP: {submission2.ap})")
                
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
                
                # Commit the transaction to make sure data is saved
                await session.commit()
                
                print("✅ Test data added successfully")
            
            # Verify data was inserted correctly
            async with async_session() as session:
                # Check agents
                result = await session.execute(select(Agent))
                agents = result.scalars().all()
                print(f"✅ Found {len(agents)} agents in database")
                for agent in agents:
                    print(f"   Agent: {agent.codename} (ID: {agent.id}, Faction: {agent.faction})")
                
                # Check submissions
                result = await session.execute(select(Submission))
                submissions = result.scalars().all()
                print(f"✅ Found {len(submissions)} submissions in database")
                for submission in submissions:
                    print(f"   Submission: Agent ID {submission.agent_id}, AP: {submission.ap}, Time Span: {submission.time_span}")
                
                # Check verifications
                result = await session.execute(select(Verification))
                verifications = result.scalars().all()
                print(f"✅ Found {len(verifications)} verifications in database")
                for verification in verifications:
                    print(f"   Verification: Submission ID {verification.submission_id}, Status: {verification.status}")
            
            # Test the leaderboard function with data
            async with async_session() as session:
                try:
                    result = await get_leaderboard(session, 10)
                    print(f"✅ Leaderboard function executed successfully with data: {len(result)} entries")
                    
                    if result:
                        for i, (codename, faction, metric_value, metrics_dict) in enumerate(result, start=1):
                            print(f"   {i}. {codename} [{faction}] - {metric_value} AP, metrics: {metrics_dict}")
                    else:
                        print("   No leaderboard results returned")
                except Exception as e:
                    print(f"❌ Error executing leaderboard function with data: {e}")
                    traceback.print_exc()
                    return False
            
            # Test with a simpler query to understand what's happening
            async with async_session() as session:
                try:
                    # Let's check if the join is working correctly
                    result = await session.execute(
                        select(Agent.codename, Agent.faction, func.sum(Submission.ap))
                        .join(Submission, Submission.agent_id == Agent.id)
                        .group_by(Agent.id)
                    )
                    simple_results = result.all()
                    print(f"✅ Simple query returned {len(simple_results)} results")
                    for row in simple_results:
                        print(f"   {row.codename} [{row.faction}] - {row[2]} AP")
                except Exception as e:
                    print(f"❌ Error with simple query: {e}")
                    traceback.print_exc()
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
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Verifying leaderboard data retrieval...")
    print("=" * 60)
    success = asyncio.run(test_data_verification())
    
    if success:
        print("\n" + "=" * 60)
        print("✅ DATA VERIFICATION COMPLETED")
    else:
        print("\n" + "=" * 60)
        print("❌ DATA VERIFICATION FAILED")
        sys.exit(1)