#!/bin/bash

# restore_bot.sh
# Restores bot functionality by renaming disabled files,
# removing DB lock, cleaning /etc/hosts, and running restore script.

set -e

echo "🔧 Restoring bot files..."

# 1–3. Restore renamed Python files if they exist
[ -f main.py.disabled ] && mv main.py.disabled main.py && echo "Restored main.py"
[ -f bot/app.py.disabled ] && mv bot/app.py.disabled bot/app.py && echo "Restored bot/app.py"
[ -f bot/config.py.disabled ] && mv bot/config.py.disabled bot/config.py && echo "Restored bot/config.py"

# 4. Remove DB lock
rm -f data/bot.db.lock
echo "Removed data/bot.db.lock (if it existed)"

# 5. Remove api.telegram.org from /etc/hosts
if grep -q "api.telegram.org" /etc/hosts; then
    echo "Removing api.telegram.org entry from /etc/hosts..."
    sudo sed -i '/api.telegram.org/d' /etc/hosts
else
    echo "No api.telegram.org entry found in /etc/hosts"
fi

# 6. Run restore script
echo "Running python restore_bot.py..."
python restore_bot.py

echo "✅ Bot restoration complete!"
