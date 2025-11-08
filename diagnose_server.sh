#!/bin/bash
# Quick diagnostic script for server issues

echo "🔧 Diagnosing Server Issues..."

cd /home/botadmin/bots/ingress-prime-leaderboard-bot

# Check database
echo "📊 Database Status:"
sqlite3 ./data/bot.db "SELECT COUNT(*) as agents FROM agents;" 2>/dev/null || echo "Database not accessible"
sqlite3 ./data/bot.db "SELECT COUNT(*) as submissions FROM submissions;" 2>/dev/null || echo "Database not accessible"

# Check if data exists
if [ -f "./data/bot.db" ]; then
    echo "✅ Database file exists"
    sqlite3 ./data/bot.db "SELECT codename, faction FROM agents LIMIT 5;" 2>/dev/null || echo "No agents in database"
else
    echo "❌ Database file doesn't exist"
fi

# Check bot process
echo ""
echo "🤖 Bot Process Status:"
pm2 list | grep ingress-bot

# Check recent logs
echo ""
echo "📋 Recent Bot Logs (last 20 lines):"
pm2 logs ingress-bot --lines 20 2>/dev/null || echo "No logs available"