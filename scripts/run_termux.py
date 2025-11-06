#!/usr/bin/env python3
"""
Termux-compatible launcher for the Ingress Leaderboard Bot
Excludes FastAPI and uvicorn web dashboard functionality
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from bot.main_termux_full import main as run_bot

if __name__ == "__main__":
    # Set up basic logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    print("🤖 Starting Ingress Leaderboard Bot (Termux Version)")
    print("📱 Web dashboard functionality disabled for Termux compatibility")

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped gracefully")
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        sys.exit(1)