#!/usr/bin/env python3
"""
Quick verification script for Ingress Prime Leaderboard Bot imports
Run this after installing dependencies to verify everything works
"""

import sys
import importlib.util

def check_import(module_name, description=""):
    """Check if a module can be imported."""
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is not None:
            print(f"✅ {module_name} {description}")
            return True
        else:
            print(f"❌ {module_name} {description} - Not found")
            return False
    except ImportError:
        print(f"❌ {module_name} {description} - Import failed")
        return False
    except Exception as e:
        print(f"⚠️  {module_name} {description} - Error: {e}")
        return False

def main():
    print("🔍 Import Verification for Ingress Prime Leaderboard Bot")
    print("=" * 60)

    # Core Python modules (should always work)
    print("\n📦 Core Python Modules:")
    core_modules = [
        ("asyncio", ""),
        ("logging", ""),
        ("sqlite3", ""),
        ("re", ""),
        ("datetime", ""),
        ("json", ""),
        ("pathlib", ""),
        ("typing", ""),
    ]

    for module, desc in core_modules:
        check_import(module, desc)

    # Third-party packages that were causing warnings
    print("\n📦 Third-Party Packages (These were causing warnings):")
    third_party = [
        ("apscheduler.schedulers.asyncio", "APScheduler"),
        ("redis", "Redis client"),
        ("rq", "Redis Queue"),
        ("sqlalchemy", "SQLAlchemy ORM"),
        ("sqlalchemy.ext.asyncio", "SQLAlchemy Async"),
        ("sqlalchemy.orm", "SQLAlchemy ORM"),
        ("telegram", "Python Telegram Bot"),
        ("telegram.ext", "PTB Extensions"),
        ("telegram.error", "PTB Errors"),
        ("dotenv", "Python-dotenv"),
        ("uvicorn", "ASGI Server"),
        ("fastapi", "FastAPI"),
    ]

    for module, desc in third_party:
        check_import(module, desc)

    # Summary
    print("\n" + "=" * 60)
    print("📋 Quick Fix Guide:")
    print("If you see ❌ marks above, run:")
    print("pip install -r requirements.txt")
    print("\nOr install specific packages:")
    print("pip install APScheduler redis rq SQLAlchemy python-telegram-bot python-dotenv uvicorn fastapi aiosqlite")

    print(f"\n💡 For deployment on Ubuntu 24.04 LTS:")
    print("The deploy-linode.sh script handles dependency installation automatically!")

    print(f"\n🎯 Once all packages are installed:")
    print("- ✅ Pylance import warnings will disappear")
    print("- ✅ Bot will run without import errors")
    print("- ✅ All features will be available")

if __name__ == "__main__":
    main()