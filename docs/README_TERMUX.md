# Ingress Leaderboard Bot - Termux Compatible Version

This is a Termux-compatible version of the Ingress Leaderboard Bot with web dashboard functionality removed for better compatibility with Android/Termux environments.

## What's Removed

- **FastAPI** - Web framework used for the dashboard
- **Uvicorn** - ASGI server for running the web dashboard
- **Web Dashboard** - The HTML-based leaderboard and admin interface

## What's Included

- ✅ Full Telegram bot functionality
- ✅ Stats parsing and submission
- ✅ Leaderboard commands
- ✅ Database storage (SQLite)
- ✅ Background jobs and scheduling
- ✅ Message autodelete
- ✅ Backup functionality
- ✅ Verification system

## Installation in Termux

1. **Install required packages:**
   ```bash
   pkg update && pkg upgrade
   pkg install python python-pip git
   ```

2. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd ingress-prime-leaderboard-bot
   ```

3. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Set up your environment variables:**
   Create a `.env` file with your bot configuration:
   ```env
   BOT_TOKEN=your_telegram_bot_token
   DATABASE_URL=sqlite+aiosqlite:///./bot.db
   REDIS_URL=redis://localhost:6379/0
   AUTODELETE_DELAY_SECONDS=300
   AUTODELETE_ENABLED=true
   LEADERBOARD_SIZE=10
   GROUP_MESSAGE_RETENTION_MINUTES=60
   TEXT_ONLY_MODE=false
   ADMIN_USER_IDS=your_admin_user_id
   # Backup settings
   BACKUP_ENABLED=false
   BACKUP_SCHEDULE=0 2 * * *
   BACKUP_RETENTION_COUNT=7
   BACKUP_COMPRESS=true
   ```

6. **Run the bot:**
   ```bash
   python run_termux.py
   ```

## Available Commands

- `/start` - Start the bot and see available commands
- `/submit` - Submit your Ingress Prime stats
- `/leaderboard` - View the current leaderboard
- `/help` - Get help with bot commands
- `/verify` - Initiate verification for private stats
- `/confirm <code>` - Confirm verification with code
- `/backup` - Trigger manual backup (if enabled)

## Configuration Options

All the original bot functionality is preserved, except for the web dashboard. You can still:

- Configure leaderboard size
- Set up automatic message deletion
- Enable/disable text-only mode
- Configure backup settings
- Set admin user IDs
- Manage group privacy settings

## Differences from Full Version

| Feature | Full Version | Termux Version |
|---------|-------------|---------------|
| Telegram Bot | ✅ | ✅ |
| Stats Parsing | ✅ | ✅ |
| Leaderboard Commands | ✅ | ✅ |
| Database Storage | ✅ | ✅ |
| Background Jobs | ✅ | ✅ |
| Web Dashboard | ✅ | ❌ |
| Admin Web Interface | ✅ | ❌ |
| Real-time Web Updates | ✅ | ❌ |

## Notes

- The bot uses SQLite for data storage, which works well in Termux
- Redis is optional - if not available, some features may be limited
- All bot commands work exactly the same as the full version
- You can still view leaderboards and manage settings through Telegram commands

## Future Hosting

If you later decide to host on a VPS or server, you can:
1. Use the full version with web dashboard
2. Keep using this Termux version (all core functionality works)
3. Migrate your database easily (just copy the `bot.db` file)

## Troubleshooting

**Import Errors:** Make sure you're using the Termux requirements and not the full requirements.

**Permission Issues:** Ensure Termux has storage access if needed.

**Redis Connection:** Redis is optional. The bot will work without it, but some features may be limited.

**Database Issues:** The bot will create the SQLite database automatically on first run.