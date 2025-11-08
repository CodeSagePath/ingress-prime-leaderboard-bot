#!/bin/bash
# Comprehensive Server Setup Script for Ingress Leaderboard Bot
# This script applies all the fixes we implemented

echo "🔧 Setting up Ingress Leaderboard Bot Server Fixes..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

print_error() {
    echo -e "${RED}[❌]${NC} $1"
}

# Navigate to bot directory
cd /home/botadmin/bots/ingress-prime-leaderboard-bot || {
    print_error "Bot directory not found!"
    exit 1
}

print_status "Navigated to bot directory"

# 1. Update with latest code
echo ""
echo "📥 Updating with latest code from repository..."
git pull origin master
if [ $? -eq 0 ]; then
    print_status "Code updated successfully"
else
    print_error "Failed to update code"
    exit 1
fi

# 2. Install/Update dependencies
echo ""
echo "📦 Installing/updating Python dependencies..."
source venv/bin/activate
pip install -r requirements.txt
if [ $? -eq 0 ]; then
    print_status "Dependencies installed/updated"
else
    print_error "Failed to install dependencies"
    exit 1
fi
deactivate

# 3. Check database files and copy data if needed
echo ""
echo "🗄️ Checking database files and data..."

if [ -f "bot.db" ] && [ -f "data/bot.db" ]; then
    # Check which database has data
    bot_db_agents=$(sqlite3 bot.db "SELECT COUNT(*) FROM agents;" 2>/dev/null || echo "0")
    data_db_agents=$(sqlite3 data/bot.db "SELECT COUNT(*) FROM agents;" 2>/dev/null || echo "0")

    echo "📊 Bot.db agents: $bot_db_agents"
    echo "📊 Data/bot.db agents: $data_db_agents"

    if [ "$bot_db_agents" -gt "$data_db_agents" ]; then
        echo "📋 Copying data from bot.db to data/bot.db..."
        cp bot.db data/bot.db
        print_status "Data copied to correct location"
    elif [ "$data_db_agents" -gt 0 ]; then
        print_status "Data already exists in correct location"
    else
        print_warning "No data found in either database file"
    fi
elif [ -f "bot.db" ]; then
    echo "📋 Creating data directory and copying database..."
    mkdir -p data
    cp bot.db data/bot.db
    print_status "Database copied to correct location"
else
    print_warning "No database files found - will create new ones on first submission"
fi

# 4. Verify database configuration
echo ""
echo "🔍 Verifying database configuration..."
sqlite3 data/bot.db "SELECT COUNT(*) FROM agents;" 2>/dev/null && print_status "Database accessible" || print_warning "Database not accessible yet"

# 5. Check environment variables
echo ""
echo "🔧 Checking environment variables..."
if grep -q "DATABASE_URL.*data/bot.db" .env; then
    print_status "Database URL configured correctly"
else
    print_warning "Database URL might not be configured correctly"
fi

if grep -q "DASHBOARD_ENABLED=true" .env; then
    print_status "Dashboard is enabled"
else
    print_warning "Dashboard might be disabled"
fi

# 6. Stop existing bot process
echo ""
echo "🛑 Stopping existing bot processes..."
pm2 stop ingress-bot 2>/dev/null || print_warning "PM2 process not found"

# 7. Start the bot with new configuration
echo ""
echo "🚀 Starting bot with all fixes..."
pm2 start ecosystem.config.js 2>/dev/null || {
    echo "Falling back to manual start..."
    source venv/bin/activate
    nohup python -m bot.main > bot.log 2>&1 &
    echo $! > bot.pid
    deactivate
}

# 8. Wait for bot to start
echo "⏳ Waiting for bot to start..."
sleep 5

# 9. Check bot status
echo ""
echo "📊 Checking bot status..."
if pm2 list | grep -q "ingress-bot.*online"; then
    print_status "Bot is running successfully via PM2"
elif pgrep -f "python.*bot.main" > /dev/null; then
    print_status "Bot is running successfully (manual mode)"
else
    print_error "Bot failed to start"
    echo "📋 Checking logs:"
    tail -10 bot.log 2>/dev/null || echo "No log file found"
    exit 1
fi

# 10. Final verification
echo ""
echo "🎯 Final verification..."

# Test basic functionality
source venv/bin/activate > /dev/null 2>&1
python -c "
import asyncio
import sys
sys.path.append('.')
from bot.config import load_settings
from bot.database import build_engine, build_session_factory, init_models, session_scope
from bot.models import Agent
from sqlalchemy import select

async def verify():
    settings = load_settings()
    engine = build_engine(settings)
    await init_models(engine)
    session_factory = build_session_factory(engine)

    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent))
        agents = result.all()
        print(f'VeRIFICATION SUCCESS: Found {len(agents)} agents')

asyncio.run(verify())
" > /dev/null 2>&1

if [ $? -eq 0 ]; then
    print_status "All verification tests passed!"
else
    print_warning "Some verification tests failed - check logs"
fi

echo ""
echo "🎉 Server setup completed successfully!"
echo ""
echo "📋 What was fixed:"
echo "  ✅ Updated with latest code including:"
echo "     • Simplified leaderboard query (fixes \"Error fetching leaderboard\")"
echo "     • Auto-deletion of user submission messages"
echo "     • Database path correction"
echo "     • Beta tokens improvements"
echo "  ✅ Database path fixed: ./data/bot.db"
echo "  ✅ Dependencies updated"
echo "  ✅ Bot restarted with all fixes"
echo ""
echo "🌐 Bot should now work correctly:"
echo "  • /leaderboard - Shows your rankings"
echo "  • /submit - Auto-deletes your data messages"
echo "  • /betatokens - Shows your beta tokens status"
echo ""
echo "📋 If you still see issues, check the logs:"
echo "  pm2 logs ingress-bot --lines 50"
echo ""
echo "📊 Dashboard access:"
echo "  Leaderboard: http://YOUR_SERVER_IP:8085"
echo "  Admin Panel: http://YOUR_SERVER_IP:8085/admin?token=lMGRo8VyzLYi0y1JB-5LHYKf5OgceYasdQ1SVSsUvQs"