#!/bin/bash
# Force stop all bot processes - enhanced version

echo "🛑 Force stopping all Ingress Leaderboard Bot processes..."

# Function to stop process by PID
stop_process() {
    local pid=$1
    if ps -p "$pid" > /dev/null 2>&1; then
        echo "  Stopping process $pid..."
        if kill "$pid" 2>/dev/null; then
            sleep 2
            # Check if it's still running and force kill if needed
            if ps -p "$pid" > /dev/null 2>&1; then
                echo "  Force killing process $pid..."
                kill -9 "$pid" 2>/dev/null || true
            fi
            echo "  ✅ Process $pid stopped"
        else
            echo "  ⚠️  No permission to kill process $pid (may require sudo)"
        fi
    fi
}

# Find all bot-related processes
echo "🔍 Searching for bot processes..."

# Main processes
MAIN_PROCESSES=$(ps aux | grep "python main.py" | grep -v grep | awk '{print $2}')
echo "Found main processes: $MAIN_PROCESSES"

# Multiprocessing related processes
MULTI_PROCESSES=$(ps aux | grep "multiprocessing.*bot" | grep -v grep | awk '{print $2}')
echo "Found multiprocessing processes: $MULTI_PROCESSES"

# Python processes from this directory
LOCAL_PROCESSES=$(ps aux | grep "/home/codesagepath/Documents/TGBot/ingress_leaderboard" | grep -v grep | awk '{print $2}')
echo "Found local processes: $LOCAL_PROCESSES"

# Stop all processes
ALL_PIDS="$MAIN_PROCESSES $MULTI_PROCESSES $LOCAL_PROCESSES"

for pid in $ALL_PIDS; do
    if [ -n "$pid" ] && [ "$pid" != "$$" ]; then
        stop_process "$pid"
    fi
done

# Clean up any leftover PID files
echo "🧹 Cleaning up PID files..."
find . -name "*.pid" -delete 2>/dev/null || true

# Verify no processes are still running
echo "🔍 Verifying processes are stopped..."
REMAINING=$(ps aux | grep "python main.py" | grep -v grep | wc -l)

if [ "$REMAINING" -eq 0 ]; then
    echo "✅ All bot processes stopped successfully!"
else
    echo "⚠️  Some processes may still be running:"
    ps aux | grep "python main.py" | grep -v grep
    echo ""
    echo "You may need to run 'sudo ./force_stop.sh' to kill remaining processes"
fi

echo "📝 Bot logs are still available in bot.log if you need to check them"