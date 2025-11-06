#!/bin/bash

# =============================================================================
# Quick Deploy Script for Ingress Prime Leaderboard Bot
# =============================================================================
# Simplified deployment script for servers with venv setup

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

# Configuration
BOT_DIR="/var/www/ingress-prime-leaderboard-bot"
SERVICE_NAME="ingress-bot"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

print_status "🚀 Starting quick deployment..."

# Step 1: Install dependencies
print_status "Installing system dependencies..."
apt update
apt install -y python3.11 python3.11-venv python3-pip python3-dev git redis-server sqlite3 supervisor

# Step 2: Setup bot directory
print_status "Setting up bot directory..."
mkdir -p ${BOT_DIR}
cd ${BOT_DIR}

# Step 3: Clone or update repository
if [ -d ".git" ]; then
    print_status "Updating existing repository..."
    git pull origin master
else
    print_status "Cloning repository..."
    git clone https://github.com/CodeSagePath/ingress-prime-leaderboard-bot.git .
fi

# Step 4: Setup virtual environment
print_status "Setting up Python virtual environment..."
python3.11 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

# Step 5: Setup environment
if [ ! -f .env ]; then
    print_warning "Creating .env file - you MUST edit it!"
    cp .env.example .env
    chown www-data:www-data .env
    chmod 600 .env

    echo ""
    print_warning "⚠️  IMPORTANT: Edit .env file with your configuration:"
    echo "  - nano ${BOT_DIR}/.env"
    echo "  - Set BOT_TOKEN (required)"
    echo "  - Set ADMIN_USER_IDS (required)"
    echo "  - Set SECURITY_ADMIN_TOKEN (required)"
    echo ""
    read -p "Press Enter after configuring .env..."
fi

# Step 6: Create necessary directories
print_status "Creating directories..."
mkdir -p logs data
chown -R www-data:www-data logs data

# Step 7: Start Redis
print_status "Starting Redis..."
systemctl enable redis-server
systemctl start redis-server

# Step 8: Create supervisor config
print_status "Creating supervisor configuration..."
cat > /etc/supervisor/conf.d/${SERVICE_NAME}.conf << EOF
[program:${SERVICE_NAME}]
command=${BOT_DIR}/venv/bin/python main.py
directory=${BOT_DIR}
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=${BOT_DIR}/logs/bot.log
stdout_logfile_maxbytes=100MB
stdout_logfile_backups=5
environment=PATH="${BOT_DIR}/venv/bin"
EOF

# Step 9: Start the bot
print_status "Starting the bot..."
supervisorctl reread
supervisorctl update
supervisorctl start ${SERVICE_NAME}

# Step 10: Show status
print_status "Deployment completed! Checking status..."
sleep 3
supervisorctl status ${SERVICE_NAME}

# Step 11: Final instructions
echo ""
print_status "🎉 Deployment completed successfully!"
echo ""
echo "📋 Important files:"
echo "  - Configuration: ${BOT_DIR}/.env"
echo "  - Logs: ${BOT_DIR}/logs/bot.log"
echo ""
echo "🔧 Management commands:"
echo "  - Status: sudo supervisorctl status ${SERVICE_NAME}"
echo "  - Restart: sudo supervisorctl restart ${SERVICE_NAME}"
echo "  - Logs: sudo supervisorctl tail -f ${SERVICE_NAME}"
echo ""
echo "🔍 Test the bot:"
echo "  - Find your bot on Telegram and send /start"
echo "  - Check logs: sudo tail -f ${BOT_DIR}/logs/bot.log"
echo ""
print_warning "⚠️  Remember to:"
echo "  - Edit ${BOT_DIR}/.env with your actual bot token"
echo "  - Configure firewall if needed"
echo "  - Set up SSL for production dashboard access"