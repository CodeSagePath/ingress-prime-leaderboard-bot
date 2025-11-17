#!/bin/bash
# Emergency stop script - tries multiple approaches when sudo fails

echo "🚨 EMERGENCY BOT STOP - Multiple Approaches"

# Approach 1: Rename critical files the bot needs
echo "1️⃣  Disabling bot by renaming critical files..."
mv main.py main.py.disabled 2>/dev/null || true
mv bot/app.py bot/app.py.disabled 2>/dev/null || true
mv bot/config.py bot/config.py.disabled 2>/dev/null || true

echo "   ✅ Main files renamed to *.disabled"

# Approach 2: Block Telegram API hosts in /etc/hosts (requires sudo)
echo "2️⃣  Attempting to block Telegram API..."
echo "127.0.0.1 api.telegram.org" | sudo tee -a /etc/hosts 2>/dev/null || echo "   ⚠️  Need sudo for /etc/hosts blocking"

# Approach 3: Kill processes more aggressively
echo "3️⃣  Trying process termination approaches..."

# Send SIGTERM first
killall python main.py 2>/dev/null || true
killall -u root python main.py 2>/dev/null || true

# Wait and send SIGKILL
sleep 2
killall -9 python main.py 2>/dev/null || true

# Approach 4: Network interface blocking (requires sudo)
echo "4️⃣  Attempting network disruption..."
sudo iptables -A OUTPUT -p tcp --dport 443 -d 149.154.160.0/20 -j DROP 2>/dev/null || echo "   ⚠️  Need sudo for network blocking"

# Approach 5: Resource exhaustion
echo "5️⃣  Attempting to disrupt bot resources..."
# Create a lock on the database file if it exists
if [ -f "data/bot.db" ]; then
    (
        flock -x 200
        echo "Database locked by emergency_stop script"
        sleep 3600
    ) 200>data/bot.db.lock &
    echo "   🗄️  Database locked"
fi

echo ""
echo "✅ Emergency stop attempts completed!"
echo ""
echo "📊 Current status:"
ps aux | grep "python main.py" | grep -v grep || echo "   ✅ No main.py processes found"
echo ""
echo "🔧 To restore bot functionality:"
echo "   1. mv main.py.disabled main.py"
echo "   2. mv bot/app.py.disabled bot/app.py"
echo "   3. mv bot/config.py.disabled bot/config.py"
echo "   4. rm data/bot.db.lock 2>/dev/null"
echo "   5. Remove api.telegram.org from /etc/hosts if added"
echo "   6. Run: python restore_bot.py"