#!/usr/bin/env python3
"""
Bot Database Query & Fix Script
Your bot uses async sessions with models in bot/models.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def check_database_data():
    """Check if data exists in your database"""
    print("=" * 70)
    print("🔍 CHECKING DATABASE DATA")
    print("=" * 70)
    
    try:
        from bot.database import build_session_factory
        from bot.models import Agent, Submission, WeeklyStat
        
        # Build session factory
        session_factory = build_session_factory()
        
        async with session_factory() as session:
            print("\n✅ Database connection successful\n")
            
            # Check agents
            from sqlalchemy import select, func
            
            agent_count = await session.scalar(select(func.count(Agent.id)))
            print(f"👤 Total Agents: {agent_count}")
            
            if agent_count > 0:
                agents = await session.execute(select(Agent).limit(5))
                print("\n   Recent agents:")
                for agent in agents.scalars():
                    print(f"   - {agent.player_name} (ID: {agent.id})")
            
            # Check submissions
            submission_count = await session.scalar(select(func.count(Submission.id)))
            print(f"\n📊 Total Submissions: {submission_count}")
            
            if submission_count > 0:
                submissions = await session.execute(select(Submission).limit(5))
                print("\n   Recent submissions:")
                for sub in submissions.scalars():
                    print(f"   - Agent ID: {sub.agent_id}, AP: {sub.lifetime_ap}")
            
            # Check weekly stats
            weekly_count = await session.scalar(select(func.count(WeeklyStat.id)))
            print(f"\n📈 Total Weekly Stats: {weekly_count}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def debug_leaderboard_query():
    """Debug why leaderboard queries return no data"""
    print("\n" + "=" * 70)
    print("🔎 DEBUGGING LEADERBOARD QUERY")
    print("=" * 70)
    
    try:
        from bot.database import build_session_factory
        from bot.models import Submission, Agent
        from sqlalchemy import select, desc, func
        
        session_factory = build_session_factory()
        
        async with session_factory() as session:
            # Raw count
            total = await session.scalar(select(func.count(Submission.id)))
            print(f"\nTotal submissions in DB: {total}")
            
            if total == 0:
                print("⚠️  No submissions found! This is the problem.")
                print("\n💡 Data was 'saved' but never committed to database.")
                print("   Check your save logic for missing session.commit()")
                return
            
            # Try to build leaderboard query
            print("\n📊 Attempting leaderboard query:")
            
            # Most basic query
            query = select(Submission, Agent).join(Agent).order_by(desc(Submission.lifetime_ap)).limit(10)
            results = await session.execute(query)
            rows = results.all()
            
            print(f"   Query returned: {len(rows)} rows")
            
            if rows:
                print("\n   Leaderboard (by AP):")
                for submission, agent in rows:
                    print(f"   {agent.player_name}: {submission.lifetime_ap} AP")
            else:
                print("   ❌ Query returned 0 rows")
                print("   This means JOIN is failing - check foreign key relationship")
                
                # Debug join
                print("\n   Checking Agent-Submission relationship:")
                agents = await session.execute(select(Agent).limit(3))
                for agent in agents.scalars():
                    print(f"   - Agent: {agent.player_name} (ID: {agent.id})")
                    # Check if agent has submissions
                    agent_subs = await session.execute(
                        select(Submission).where(Submission.agent_id == agent.id)
                    )
                    count = len(agent_subs.scalars().all())
                    print(f"     └─ Has {count} submissions")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def inspect_agent_model():
    """Inspect Agent model to find missing fields"""
    print("\n" + "=" * 70)
    print("🔍 INSPECTING AGENT MODEL")
    print("=" * 70)
    
    try:
        from bot.models import Agent
        from sqlalchemy import inspect as sa_inspect
        
        mapper = sa_inspect(Agent)
        
        print("\n✅ Agent Model Columns:")
        for column in mapper.columns:
            print(f"   - {column.name}: {column.type} (nullable: {column.nullable})")
        
        # Check for created_at
        column_names = [c.name for c in mapper.columns]
        if 'created_at' in column_names:
            print("\n✅ 'created_at' field EXISTS")
        else:
            print("\n❌ 'created_at' field MISSING")
            print("   This is causing: 'created_at' is an invalid keyword argument for Agent")
            
        # Check relationships
        print("\n📌 Agent Relationships:")
        for rel in mapper.relationships:
            print(f"   - {rel.key} -> {rel.mapper.class_.__name__}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def inspect_submission_model():
    """Inspect Submission model"""
    print("\n" + "=" * 70)
    print("🔍 INSPECTING SUBMISSION MODEL")
    print("=" * 70)
    
    try:
        from bot.models import Submission
        from sqlalchemy import inspect as sa_inspect
        
        mapper = sa_inspect(Submission)
        
        print("\n✅ Submission Model Columns:")
        for column in mapper.columns:
            nullable = "✓" if column.nullable else "✗"
            print(f"   - {column.name}: {column.type} [{nullable}]")
        
        print("\n📌 Submission Relationships:")
        for rel in mapper.relationships:
            print(f"   - {rel.key} -> {rel.mapper.class_.__name__}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def show_fix_examples():
    """Show what needs to be fixed"""
    print("\n" + "=" * 70)
    print("🔧 FIXES NEEDED")
    print("=" * 70)
    
    print("""
1️⃣  ISSUE: 'created_at' is an invalid keyword argument for Agent
   
   FIX: In bot/models.py, make sure Agent model has:
   
   ```python
   from datetime import datetime
   from sqlalchemy import DateTime
   from sqlalchemy.orm import mapped_column
   
   class Agent(Base):
       __tablename__ = 'agents'
       
       id = mapped_column(Integer, primary_key=True)
       player_name = mapped_column(String(255), unique=True, nullable=False)
       user_id = mapped_column(BigInteger, nullable=False)
       faction = mapped_column(String(50), nullable=True)
       
       # ADD THIS IF MISSING:
       created_at = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
       updated_at = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
   ```
   
   OR if you don't want timestamps, remove created_at from your save code.

2️⃣  ISSUE: Leaderboard returns "No data available"
   
   This means either:
   a) Data isn't being committed to database (missing session.commit())
   b) Foreign key constraint failing (agent_id doesn't exist)
   c) Query filtering out all results
   
   FIX: Check your submission save function:
   
   ```python
   async def save_submission(user_id: int, data: dict):
       async with resilient_session_scope() as session:
           # Create/get agent
           agent = await session.execute(
               select(Agent).where(Agent.player_name == data['player_name'])
           )
           agent = agent.scalar_one_or_none()
           
           if not agent:
               agent = Agent(
                   player_name=data['player_name'],
                   user_id=user_id,
                   faction=data.get('faction')
               )
               session.add(agent)
               await session.flush()  # ← Important! Get agent.id
           
           # Create submission
           submission = Submission(
               agent_id=agent.id,  # ← Make sure this is set
               lifetime_ap=int(data['ap']),
               hacks=int(data.get('hacks', 0))
           )
           session.add(submission)
           
           await session.commit()  # ← Make sure this happens!
           return submission
   ```

3️⃣  ISSUE: Event loop error in scheduler
   
   FIX: In app.py, replace:
   
   ```python
   # ❌ WRONG
   scheduler.add_job(
       lambda: asyncio.create_task(health_checker.comprehensive_health_check()),
       'interval',
       minutes=5
   )
   
   # ✅ RIGHT
   def schedule_async_job(async_func, scheduler, app):
       def wrapper():
           asyncio.run_coroutine_threadsafe(
               async_func(),
               app.bot.loop
           )
       scheduler.add_job(wrapper, 'interval', minutes=5)
   
   schedule_async_job(health_checker.comprehensive_health_check, scheduler, app)
   ```
""")


async def main():
    print("\n🤖 BOT DATABASE FIX GUIDE\n")
    
    await check_database_data()
    await debug_leaderboard_query()
    await inspect_agent_model()
    await inspect_submission_model()
    await show_fix_examples()
    
    print("\n" + "=" * 70)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
    