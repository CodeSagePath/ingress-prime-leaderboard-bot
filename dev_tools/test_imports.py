#!/usr/bin/env python3
"""
Test script to verify all required imports for the Ingress Prime Leaderboard Bot.
This script will help identify any import issues before deployment.
"""

import sys

def test_imports():
    """Test all required imports for the bot."""
    print("🔍 Testing Python package imports...")
    print("=" * 50)

    # Core Python modules
    core_modules = [
        'asyncio',
        'logging',
        'sqlite3',
        're',
        'datetime',
        'json',
        'pathlib',
        'typing'
    ]

    # Third-party packages (check if available)
    third_party = [
        'apscheduler.schedulers.asyncio',
        'dotenv',
        'redis',
        'rq',
        'uvicorn',
        'sqlalchemy',
        'sqlalchemy.ext.asyncio',
        'sqlalchemy.orm',
        'telegram',
        'telegram.ext',
        'telegram.error'
    ]

    all_good = True

    print("📦 Core Python Modules:")
    for module in core_modules:
        try:
            __import__(module)
            print(f"✅ {module}")
        except ImportError as e:
            print(f"❌ {module}: {e}")
            all_good = False
        except Exception as e:
            print(f"⚠️  {module}: {e}")

    print(f"\n📦 Third-Party Packages:")
    for module in third_party:
        try:
            __import__(module)
            print(f"✅ {module}")
        except ImportError as e:
            print(f"❌ {module}: {e}")
            all_good = False
        except Exception as e:
            print(f"⚠️  {module}: {e}")

    print(f"\n📦 Bot-Specific Imports:")

    # Test bot-specific imports
    bot_imports = [
        'bot.models',
        'bot.services.leaderboard',
        'bot.utils.beta_tokens',
        'bot.dashboard',
        'bot.database',
        'bot.jobs.backup'
    ]

    for module in bot_imports:
        try:
            __import__(module)
            print(f"✅ {module}")
        except ImportError as e:
            print(f"❌ {module}: {e}")
            all_good = False
        except Exception as e:
            print(f"⚠️  {module}: {e}")

    print("\n" + "=" * 50)

    if all_good:
        print("🎉 All imports successful!")
        print("📋 Your bot should run without import issues.")
    else:
        print("⚠️  Some imports failed.")
        print("💡 Install missing packages with: pip install -r requirements.txt")

    return all_good

def test_specific_imports():
    """Test specific imports that were mentioned in warnings."""
    print("\n🔍 Testing specific imports mentioned in warnings...")
    print("=" * 50)

    specific_tests = [
        ('apscheduler.schedulers.asyncio', 'APScheduler async scheduler'),
        ('redis', 'Redis client'),
        ('rq', 'Redis Queue'),
        ('sqlalchemy', 'SQLAlchemy ORM'),
        ('telegram', 'python-telegram-bot'),
        ('uvicorn', 'ASGI server')
    ]

    all_good = True

    for module, description in specific_tests:
        try:
            __import__(module)
            print(f"✅ {module} - {description}")
        except ImportError as e:
            print(f"❌ {module} - {description}: {e}")
            all_good = False
        except Exception as e:
            print(f"⚠️  {module} - {description}: {e}")

    print("\n" + "=" * 50)

    if all_good:
        print("🎉 All specific imports working!")
    else:
        print("❌ Some specific imports failed.")

    return all_good

if __name__ == "__main__":
    print("🧪 Ingress Prime Leaderboard Bot - Import Test")
    print("=" * 50)

    # Add current directory to path
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    # Run tests
    general_success = test_imports()
    specific_success = test_specific_imports()

    overall_success = general_success and specific_success

    print(f"\n{'🎉 All tests passed!' if overall_success else '⚠️ Some tests failed.'}")

    sys.exit(0 if overall_success else 1)