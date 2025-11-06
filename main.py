#!/usr/bin/env python3
"""
Main entry point for the Ingress Prime Leaderboard Bot
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    from bot.main import main
    main()