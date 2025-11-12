#!/bin/bash
# Ingress Prime Leaderboard Bot Startup Script
# This script manages the unified bot with integrated dashboard
# Ensures only one bot instance is running with proper process management

BOT_DIR="/home/codesagepath/Documents/TGBot/ingress_leaderboard"
VENV_PATH="$BOT_DIR/venv"
PIDFILE="$BOT_DIR/bot.pid"

cd "$BOT_DIR"

# Function to check if process is running
is_running() {
    if [ -f "$PIDFILE" ]; then
        PID=$(cat "$PIDFILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            # Check if this is our bot process
            if ps -p "$PID" -o command= | grep -q "python.*bot"; then
                return 0
            else
                # PID exists but it's not our bot
                rm -f "$PIDFILE"
                return 1
            fi
        else
            # PID file exists but process is dead
            rm -f "$PIDFILE"
            return 1
        fi
    else
        # No PID file, check if any bot processes are running
        PID=$(ps aux | grep "python.*bot" | grep -v grep | awk '{print $2}' | head -1)
        if [ -n "$PID" ]; then
            echo "$PID" > "$PIDFILE"
            return 0
        fi
    fi
    return 1
}

# Function to stop the bot
stop_bot() {
    if is_running; then
        PID=$(cat "$PIDFILE")
        echo "Stopping bot (PID: $PID)..."
        kill "$PID"
        sleep 5

        # Force kill if still running
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Force killing bot..."
            kill -9 "$PID"
            sleep 2
        fi

        rm -f "$PIDFILE"
        echo "Bot stopped."
    else
        echo "Bot is not running."
    fi
}

# Function to start the bot
start_bot() {
    if is_running; then
        echo "Bot is already running (PID: $(cat $PIDFILE))"
        return 1
    fi

    echo "Starting bot..."

    # Make sure services are running
    systemctl start valkey 2>/dev/null || true

    # Activate virtual environment and start unified bot
    source "$VENV_PATH/bin/activate"
    nohup python server.py > bot.log 2>&1 &
    PID=$!

    # Wait a moment to see if it starts successfully
    sleep 3

    if ps -p "$PID" > /dev/null 2>&1; then
        echo "$PID" > "$PIDFILE"
        echo "Bot started successfully (PID: $PID)"
        echo "Log file: $BOT_DIR/bot.log"
        return 0
    else
        echo "Bot failed to start. Check bot.log for errors."
        return 1
    fi
}

# Function to check status
status_bot() {
    if is_running; then
        PID=$(cat "$PIDFILE")
        echo "Bot is running (PID: $PID)"
        return 0
    else
        echo "Bot is not running."
        return 1
    fi
}

# Main script logic
case "$1" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        stop_bot
        sleep 2
        start_bot
        ;;
    status)
        status_bot
        ;;
    logs)
        if [ -f "bot.log" ]; then
            if [ "$2" = "-f" ]; then
                tail -f bot.log
            else
                tail -n 20 bot.log
            fi
        else
            echo "No log file found."
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [-f]}"
        echo ""
        echo "Commands:"
        echo "  start         - Start the unified bot (Telegram + Dashboard)"
        echo "  stop          - Stop the bot"
        echo "  restart       - Restart the bot"
        echo "  status        - Check if bot is running"
        echo "  logs          - Show last 20 lines of bot log"
        echo "  logs -f       - Follow log output in real-time"
        exit 1
        ;;
esac

exit $?