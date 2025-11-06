#!/bin/bash

# =============================================================================
# Ingress Prime Leaderboard Bot - Server Setup Script (venv-based)
# =============================================================================
# This script sets up the bot on a server using Python virtual environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BOT_DIR="/var/www/ingress-prime-leaderboard-bot"
BOT_USER="www-data"
SERVICE_NAME="ingress-bot"
PYTHON_VERSION="python3.11"

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

print_status "🚀 Starting Ingress Prime Leaderboard Bot server setup..."

# Update system packages
print_status "Updating system packages..."
apt update && apt upgrade -y

# Install required system packages
print_status "Installing system dependencies..."
apt install -y \
    ${PYTHON_VERSION} \
    ${PYTHON_VERSION}-venv \
    ${PYTHON_VERSION}-pip \
    python3-dev \
    build-essential \
    git \
    curl \
    redis-server \
    nginx \
    sqlite3 \
    supervisor \
    htop \
    vnstat \
    unzip

# Create application directory
print_status "Creating application directory..."
mkdir -p ${BOT_DIR}
cd ${BOT_DIR}

# Clone or update repository
if [ -d ".git" ]; then
    print_status "Updating existing repository..."
    git pull origin master
else
    print_status "Cloning repository..."
    # Use HTTPS as fallback if SSH is not configured
    REPO_URL="https://github.com/CodeSagePath/ingress-prime-leaderboard-bot.git"
    git clone ${REPO_URL} .
fi

# Set ownership
print_status "Setting file permissions..."
chown -R ${BOT_USER}:${BOT_USER} ${BOT_DIR}
chmod -R 755 ${BOT_DIR}

# Create Python virtual environment
print_status "Creating Python virtual environment..."
sudo -u ${BOT_USER} ${PYTHON_VERSION} -m venv venv

# Activate virtual environment and install dependencies
print_status "Installing Python dependencies..."
sudo -u ${BOT_USER} ${BOT_DIR}/venv/bin/pip install --upgrade pip
sudo -u ${BOT_USER} ${BOT_DIR}/venv/bin/pip install -r requirements.txt

# Setup environment configuration
print_status "Setting up environment configuration..."
if [ ! -f .env ]; then
    sudo -u ${BOT_USER} cp .env.example .env
    print_warning "Please edit .env file with your configuration:"
    print_warning "  - BOT_TOKEN (required)"
    print_warning "  - ADMIN_USER_IDS (required)"
    print_warning "  - SECURITY_ADMIN_TOKEN (required)"
    print_warning "  - DATABASE_URL (default: SQLite works fine)"
    print_warning "  - REDIS_URL (default: redis://localhost:6379/0)"
    echo
    read -p "Press Enter to continue after configuring .env..."
fi

# Create required directories
print_status "Creating required directories..."
sudo -u ${BOT_USER} mkdir -p logs data backups
chmod 755 logs data backups

# Setup Redis
print_status "Configuring Redis..."
systemctl enable redis-server
systemctl start redis-server

# Test Redis connection
if redis-cli ping > /dev/null 2>&1; then
    print_status "Redis is running correctly"
else
    print_error "Redis is not responding"
    exit 1
fi

# Create supervisor configuration
print_status "Setting up supervisor configuration..."
cat > /etc/supervisor/conf.d/${SERVICE_NAME}.conf << EOF
[program:${SERVICE_NAME}]
command=${BOT_DIR}/venv/bin/python main.py
directory=${BOT_DIR}
user=${BOT_USER}
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=${BOT_DIR}/logs/bot.log
stdout_logfile_maxbytes=100MB
stdout_logfile_backups=5
environment=PATH="${BOT_DIR}/venv/bin"
EOF

# Reread supervisor configuration and start bot
supervisorctl reread
supervisorctl update
supervisorctl start ${SERVICE_NAME}

# Setup log rotation
print_status "Setting up log rotation..."
cat > /etc/logrotate.d/${SERVICE_NAME} << EOF
${BOT_DIR}/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 ${BOT_USER} ${BOT_USER}
    postrotate
        supervisorctl restart ${SERVICE_NAME}
    endscript
}
EOF

# Configure firewall
print_status "Configuring firewall..."
if command -v ufw >/dev/null 2>&1; then
    ufw allow ssh
    ufw allow 80
    ufw allow 443
    # Allow dashboard port if enabled
    DASHBOARD_PORT=$(grep DASHBOARD_PORT ${BOT_DIR}/.env | cut -d'=' -f2 || echo 8000)
    if [ "$DASHBOARD_PORT" != "0" ]; then
        ufw allow ${DASHBOARD_PORT}
    fi
    ufw --force enable
fi

# Setup Nginx for dashboard (optional)
DASHBOARD_ENABLED=$(grep DASHBOARD_ENABLED ${BOT_DIR}/.env | cut -d'=' -f2 || echo false)
if [ "$DASHBOARD_ENABLED" = "true" ]; then
    print_status "Configuring Nginx for dashboard..."
    DASHBOARD_PORT=$(grep DASHBOARD_PORT ${BOT_DIR}/.env | cut -d'=' -f2 || echo 8000)

    cat > /etc/nginx/sites-available/${SERVICE_NAME} << EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:${DASHBOARD_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:${DASHBOARD_PORT}/health;
        access_log off;
    }
}
EOF

    ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx
fi

# Create management scripts
print_status "Creating management scripts..."
sudo -u ${BOT_USER} mkdir -p ${BOT_DIR}/scripts

# Bot management script
cat > ${BOT_DIR}/scripts/manage.sh << 'EOF'
#!/bin/bash

BOT_DIR="/var/www/ingress-prime-leaderboard-bot"
SERVICE_NAME="ingress-bot"

case "$1" in
    start)
        sudo supervisorctl start ${SERVICE_NAME}
        echo "Bot started"
        ;;
    stop)
        sudo supervisorctl stop ${SERVICE_NAME}
        echo "Bot stopped"
        ;;
    restart)
        sudo supervisorctl restart ${SERVICE_NAME}
        echo "Bot restarted"
        ;;
    status)
        sudo supervisorctl status ${SERVICE_NAME}
        ;;
    logs)
        sudo supervisorctl tail -f ${SERVICE_NAME}
        ;;
    update)
        echo "Updating bot..."
        cd ${BOT_DIR}
        sudo git pull origin master
        sudo ${BOT_DIR}/venv/bin/pip install -r requirements.txt
        sudo supervisorctl restart ${SERVICE_NAME}
        echo "Bot updated and restarted"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|update}"
        exit 1
        ;;
esac
EOF

chmod +x ${BOT_DIR}/scripts/manage.sh

# Health check script
cat > ${BOT_DIR}/scripts/health-check.sh << 'EOF'
#!/bin/bash

BOT_DIR="/var/www/ingress-prime-leaderboard-bot"
LOG_FILE="${BOT_DIR}/logs/health-check.log"

# Check if bot process is running
if ! pgrep -f "python main.py" > /dev/null; then
    echo "$(date): Bot process not running" >> ${LOG_FILE}
    echo "❌ Bot process not running"
    exit 1
fi

# Check Redis connection
if ! redis-cli ping > /dev/null 2>&1; then
    echo "$(date): Redis not responding" >> ${LOG_FILE}
    echo "❌ Redis not responding"
    exit 1
fi

# Check supervisor status
if ! supervisorctl status ingress-bot | grep RUNNING > /dev/null; then
    echo "$(date): Supervisor process not running" >> ${LOG_FILE}
    echo "❌ Supervisor process not running"
    exit 1
fi

echo "$(date): Health check passed" >> ${LOG_FILE}
echo "✅ All systems healthy"
EOF

chmod +x ${BOT_DIR}/scripts/health-check.sh

# Create systemd service for health monitoring
cat > /etc/systemd/system/${SERVICE_NAME}-health.service << EOF
[Unit]
Description=Ingress Bot Health Check
After=network.target

[Service]
Type=oneshot
ExecStart=${BOT_DIR}/scripts/health-check.sh
User=${BOT_USER}

[Install]
WantedBy=multi-user.target
EOF

# Create health check timer
cat > /etc/systemd/system/${SERVICE_NAME}-health.timer << EOF
[Unit]
Description=Run Ingress Bot health check every 5 minutes

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}-health.timer
systemctl start ${SERVICE_NAME}-health.timer

# Add crontab for automatic updates and backups
sudo -u ${BOT_USER} crontab -l > /tmp/crontab_temp 2>/dev/null || true
cat >> /tmp/crontab_temp << EOF

# Ingress Bot automated tasks
# Weekly updates - Sundays at 2 AM
0 2 * * 0 cd ${BOT_DIR} && git pull origin master && ${BOT_DIR}/venv/bin/pip install -r requirements.txt && supervisorctl restart ${SERVICE_NAME}

# Daily backup at 3 AM
0 3 * * * cd ${BOT_DIR} && ${BOT_DIR}/venv/bin/python -c "
import os
from datetime import datetime
backup_dir = '${BOT_DIR}/backups'
os.makedirs(backup_dir, exist_ok=True)
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
os.system(f'cp ${BOT_DIR}/data/bot.db {backup_dir}/bot_backup_{timestamp}.db 2>/dev/null || true')
print(f'Backup created: {backup_dir}/bot_backup_{timestamp}.db')
" >> ${BOT_DIR}/logs/backup.log 2>&1
EOF

sudo -u ${BOT_USER} crontab /tmp/crontab_temp
rm /tmp/crontab_temp

# Final status check
print_status "🎉 Server setup completed successfully!"
echo ""

# Show status
echo "📊 Current Status:"
supervisorctl status ${SERVICE_NAME}
echo ""

print_info "🔧 Management Commands:"
echo "- Start/stop/restart: sudo ${BOT_DIR}/scripts/manage.sh [start|stop|restart]"
echo "- View logs: sudo ${BOT_DIR}/scripts/manage.sh logs"
echo "- Update bot: sudo ${BOT_DIR}/scripts/manage.sh update"
echo "- Health check: sudo ${BOT_DIR}/scripts/health-check.sh"
echo ""

print_info "📁 Important Files:"
echo "- Configuration: ${BOT_DIR}/.env"
echo "- Logs: ${BOT_DIR}/logs/"
echo "- Data: ${BOT_DIR}/data/"
echo "- Backups: ${BOT_DIR}/backups/"
echo ""

print_info "🌐 Services:"
echo "- Bot: Running via supervisor"
echo "- Redis: systemctl status redis-server"
echo "- Nginx: systemctl status nginx (if dashboard enabled)"
echo "- Health checks: systemctl status ${SERVICE_NAME}-health.timer"
echo ""

print_warning "⚠️  Important Notes:"
echo "- Make sure to configure your .env file properly"
echo "- Monitor logs regularly: sudo ${BOT_DIR}/scripts/manage.sh logs"
echo "- Set up SSL certificate for production: sudo certbot --nginx"
echo "- Configure firewall rules as needed"
echo "- Regular backups are automated but verify they work"
echo ""

print_status "🚀 Your Ingress Prime Leaderboard Bot is now running!"