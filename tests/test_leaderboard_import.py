#!/usr/bin/env python3
"""
Minimal test script to verify the leaderboard.py file can be imported without errors.
This avoids importing the entire application which has many dependencies.
"""

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # Import only the necessary modules for leaderboard functionality
    from sqlalchemy import func, select, case, literal_column
    from sqlalchemy.ext.asyncio import AsyncSession
    print("✅ SQLAlchemy imports successful")
    
    # Try to import the models that leaderboard.py uses
    try:
        from bot.models import Agent, Submission, Verification, VerificationStatus
        print("✅ Models import successful")
    except ImportError as e:
        print(f"⚠️  Models import failed: {e}")
        # Create mock classes for testing
        class Agent:
            pass
        class Submission:
            pass
        class Verification:
            pass
        class VerificationStatus:
            approved = type('obj', (object,), {'value': 'approved'})
            pending = type('obj', (object,), {'value': 'pending'})
            rejected = type('obj', (object,), {'value': 'rejected'})
        print("✅ Using mock models for testing")
    
    # Now try to import the leaderboard module
    try:
        from bot.services.leaderboard import get_leaderboard
        print("✅ Leaderboard module import successful")
        print("✅ Test 1 PASSED: The leaderboard.py file can be imported without syntax errors")
    except ImportError as e:
        print(f"❌ Leaderboard module import failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error importing leaderboard module: {e}")
        sys.exit(1)
        
except Exception as e:
    print(f"❌ Failed to import required modules: {e}")
    sys.exit(1)