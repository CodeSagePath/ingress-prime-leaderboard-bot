#!/usr/bin/env python3
"""
Restore bot configuration after using disable_bot.py
"""

import os
from pathlib import Path

def main():
    project_root = Path(__file__).parent
    env_file = project_root / ".env"
    backup_file = project_root / ".env.backup"

    print("♻️  Restoring bot configuration...")

    if backup_file.exists():
        with open(backup_file, 'r') as f:
            original_content = f.read()

        with open(env_file, 'w') as f:
            f.write(original_content)

        print("✅ Bot configuration restored from .env.backup")
        print("🤖 You can now start the bot normally with: ./start.sh start")
    else:
        print("❌ No backup file found (.env.backup)")

if __name__ == "__main__":
    main()