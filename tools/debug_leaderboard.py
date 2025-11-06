#!/usr/bin/env python3
"""
Debug script to identify the exact issue with the leaderboard function.
"""

import asyncio
import sys
import os
import tempfile
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def debug_leaderboard():
    """Debug the leaderboard function step by step."""
    try:
        # Import necessary modules
        from sqlalchemy import create_engine, select, func, text
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
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
            
            # Test basic JSON functions in SQLite
            async with engine.begin() as conn:
                try:
                    result = await conn.execute(text("SELECT json_group_object('key', 1)"))
                    print(f"✅ json_group_object test: {result.fetchone()}")
                except Exception as e:
                    print(f"❌ json_group_object test failed: {e}")
                
                try:
                    result = await conn.execute(text("SELECT json_each('{\"key\": 1}')"))
                    print(f"✅ json_each test: {result.fetchall()}")
                except Exception as e:
                    print(f"❌ json_each test failed: {e}")
            
            # Import models
            from bot.models import Base, Agent, Submission, Verification, VerificationStatus
            
            # Create tables
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            print("✅ Database tables created successfully")
            
            # Test the leaderboard function with a simple query first
            async with async_session() as session:
                try:
                    # Test a simple query first
                    result = await session.execute(select(func.count()))
                    print(f"✅ Simple query test: {result.scalar()}")
                except Exception as e:
                    print(f"❌ Simple query test failed: {e}")
                    return False
            
            # Import the leaderboard function
            from bot.services.leaderboard import get_leaderboard
            
            print("✅ Leaderboard function imported successfully")
            
            # Test the leaderboard function with no data
            async with async_session() as session:
                try:
                    result = await get_leaderboard(session, 10)
                    print(f"✅ Leaderboard function executed successfully with empty result: {len(result)} entries")
                except Exception as e:
                    print(f"❌ Error executing leaderboard function: {e}")
                    import traceback
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
        print(f"❌ Error in debug setup: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Debugging leaderboard functionality...")
    success = asyncio.run(debug_leaderboard())
    
    if success:
        print("\n✅ DEBUG COMPLETED: The leaderboard functionality works correctly")
    else:
        print("\n❌ DEBUG FAILED: There are issues with the leaderboard functionality")
        sys.exit(1)