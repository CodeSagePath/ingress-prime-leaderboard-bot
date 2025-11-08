# Database Path Fix

## Issue Found:
The bot was configured to use `./data/bot.db` but the data was in `./bot.db`, causing:
- ❌ Leaderboard showing "No data available"
- ❌ Submissions not being saved to correct database

## Solution:
Copy data from `./bot.db` to `./data/bot.db`:
```bash
cp ./bot.db ./data/bot.db
```

## Database Location:
- **Bot uses**: `./data/bot.db` (configured in .env)
- **Data was**: `./bot.db` (wrong location)
- **Now fixed**: Data copied to correct location

## Verification:
```bash
sqlite3 ./data/bot.db "SELECT COUNT(*) FROM agents; SELECT COUNT(*) FROM submissions;"
```
Should show: 1 agent, 3 submissions