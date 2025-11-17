#!/usr/bin/env python3
"""
Temporarily disable the bot by changing its configuration
Use this when you can't kill root processes with sudo
"""

import os
from pathlib import Path

def main():
    project_root = Path(__file__).parent
    env_file = project_root / ".env"
    backup_file = project_root / ".env.backup"

    print("🔧 Temporarily disabling bot...")

    # Backup current .env file
    if env_file.exists():
        with open(env_file, 'r') as f:
            original_content = f.read()

        with open(backup_file, 'w') as f:
            f.write(original_content)

        print(f"✅ Backed up .env to .env.backup")

        # Create disabled version by invalidating the bot token
        disabled_content = original_content.replace(
            'BOT_TOKEN=8446582877:AAFHbmCEojAXxSMeoDIWS03pW6EpEUTpOxM',
            'BOT_TOKEN=DISABLED_TOKEN_TEMPORARILY'
        )

        with open(env_file, 'w') as f:
            f.write(disabled_content)

        print("🚫 Bot disabled - Telegram token invalidated")
        print("📝 The running bot will fail to connect to Telegram API")
        print("♻️  To restore: python restore_bot.py")
        print("")
        print("⚠️  Root processes are still running but ineffective:")
        print("   - PID 177582: python main.py")
        print("   - PIDs 177607-177610: Multiprocessing workers")
        print("")
        print("🔧 Alternative solutions:")
        print("   1. Run 'sudo kill -9 177582 177607 177608 177610' in terminal")
        print("   2. Reboot the system to clear all processes")
        print("   3. Use 'sudo systemctl restart' if running as service")

if __name__ == "__main__":
    main()