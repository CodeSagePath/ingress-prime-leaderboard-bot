#!/usr/bin/env python3
"""
Test script to simulate the /leaderboard command execution.
"""

import asyncio
import sys
import os
import tempfile
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_leaderboard_command():
    """Test the /leaderboard command execution."""
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
            
            # Import the leaderboard function
            from bot.services.leaderboard import get_leaderboard
            
            print("✅ Leaderboard function imported successfully")
            
            # Add some test data
            async with async_session() as session:
                # Add test agents
                agent1 = Agent(telegram_id=123, codename="TestAgent1", faction="ENL")
                agent2 = Agent(telegram_id=456, codename="TestAgent2", faction="RES")
                agent3 = Agent(telegram_id=789, codename="TestAgent3", faction="ENL")
                session.add_all([agent1, agent2, agent3])
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
                submission3 = Submission(
                    agent_id=agent3.id,
                    chat_id=None,
                    ap=1500,
                    metrics={"mu": 150, "links": 75},
                    time_span="ALL TIME"
                )
                session.add_all([submission1, submission2, submission3])
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
                verification3 = Verification(
                    submission_id=submission3.id,
                    screenshot_path="",
                    status=VerificationStatus.rejected.value
                )
                session.add_all([verification1, verification2, verification3])
                
                print("✅ Test data added successfully")
            
            # Test the /leaderboard command execution
            async with async_session() as session:
                try:
                    # Simulate the /leaderboard command execution
                    result = await get_leaderboard(session, 10)
                    print(f"✅ /leaderboard command executed successfully: {len(result)} entries")
                    
                    # Print the results in a format similar to the bot
                    if result:
                        print("\n🏆 *Leaderboard* 🏆")
                        for i, (codename, faction, metric_value, metrics_dict) in enumerate(result, start=1):
                            # Determine verification status
                            if metrics_dict.get("verified_ap", 0) > 0:
                                status = "✅"
                            elif metrics_dict.get("pending_ap", 0) > 0:
                                status = "⏳"
                            else:
                                status = "❌"
                            
                            print(f"{i}. {codename} [{faction}] {status} — {metric_value:,} AP")
                    else:
                        print("\nNo submissions yet.")
                    
                    print("\n✅ No AttributeError was thrown during /leaderboard command execution")
                    
                except AttributeError as e:
                    print(f"❌ AttributeError during /leaderboard command execution: {e}")
                    return False
                except Exception as e:
                    print(f"❌ Other error during /leaderboard command execution: {e}")
                    return False
            
            # Test the /leaderboard command with time_span filter
            async with async_session() as session:
                try:
                    # Simulate the /leaderboard command with time_span filter
                    result = await get_leaderboard(session, 10, time_span="ALL TIME")
                    print(f"✅ /leaderboard command with time_span filter executed successfully: {len(result)} entries")
                    
                except AttributeError as e:
                    print(f"❌ AttributeError during /leaderboard command with time_span filter: {e}")
                    return False
                except Exception as e:
                    print(f"❌ Other error during /leaderboard command with time_span filter: {e}")
                    return False
            
            # Test the /leaderboard command with metric filter
            async with async_session() as session:
                try:
                    # Simulate the /leaderboard command with metric filter
                    result = await get_leaderboard(session, 10, metric="mu")
                    print(f"✅ /leaderboard command with metric filter executed successfully: {len(result)} entries")
                    
                except AttributeError as e:
                    print(f"❌ AttributeError during /leaderboard command with metric filter: {e}")
                    return False
                except Exception as e:
                    print(f"❌ Other error during /leaderboard command with metric filter: {e}")
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
    print("Testing /leaderboard command execution...")
    success = asyncio.run(test_leaderboard_command())
    
    if success:
        print("\n✅ ALL TESTS PASSED: The /leaderboard command works correctly without throwing AttributeError")
    else:
        print("\n❌ TESTS FAILED: There are issues with the /leaderboard command")
        sys.exit(1)