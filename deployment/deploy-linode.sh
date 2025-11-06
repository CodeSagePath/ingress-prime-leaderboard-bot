#!/bin/bash

# Ubuntu 24.04 LTS Linode Deployment Script for Ingress Prime Leaderboard Bot
# This script automates the deployment process on a fresh Ubuntu 24.04 LTS Linode server

set -e

echo "🚀 Starting Ingress Prime Leaderboard Bot deployment on Ubuntu 24.04 LTS Linode..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

# Update system
print_status "Updating system packages..."
apt update && apt upgrade -y

# Install required packages
print_status "Installing Python 3.11, Redis, Nginx, Git..."
apt install python3.11 python3.11-venv python3-pip git redis-server nginx -y

# Install Node.js for PM2
print_status "Installing Node.js and PM2..."
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt-get install -y nodejs
npm install -g pm2

# Create application directory
print_status "Creating application directory..."
mkdir -p /var/www/ingress-prime-leaderboard-bot
cd /var/www

# Clone repository
REPO_URL="git@github.com:CodeSagePath/ingress-prime-leaderboard-bot.git"
print_status "Cloning repository from: $REPO_URL"

# Check if SSH key exists for GitHub
if [ ! -f ~/.ssh/id_rsa ]; then
    print_status "Generating SSH key for GitHub..."
    ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa

    print_status "SSH key generated. Please add this public key to your GitHub account:"
    echo ""
    cat ~/.ssh/id_rsa.pub
    echo ""
    print_warning "Copy the SSH public key above and add it to GitHub at:"
    print_warning "https://github.com/settings/keys"
    echo ""
    read -p "Press Enter once you've added the SSH key to GitHub..."

    # Add GitHub to known_hosts
    ssh-keyscan -H github.com >> ~/.ssh/known_hosts
fi

# Test SSH connection to GitHub
print_status "Testing SSH connection to GitHub..."
if ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
    print_status "SSH connection to GitHub successful!"
else
    print_status "SSH key already exists, testing connection..."
    if ! ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
        print_warning "SSH connection to GitHub failed. Please check your SSH key setup."
        print_warning "Your public key:"
        cat ~/.ssh/id_rsa.pub
        echo ""
        print_warning "Add this key to GitHub: https://github.com/settings/keys"
        read -p "Press Enter to continue anyway (will use HTTPS fallback)..."

        # Fallback to HTTPS if SSH fails
        REPO_URL="https://github.com/CodeSagePath/ingress-prime-leaderboard-bot.git"
        print_warning "Falling back to HTTPS repository URL"
    else
        print_status "SSH connection to GitHub successful!"
    fi
fi

git clone $REPO_URL ingress-prime-leaderboard-bot
cd ingress-prime-leaderboard-bot

# Create virtual environment
print_status "Creating Python virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
print_status "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Setup environment variables
print_status "Setting up environment configuration..."
if [ ! -f .env ]; then
    cp .env.example .env
    print_warning "Please edit .env file with your bot configuration:"
    print_warning "  - BOT_TOKEN (required)"
    print_warning "  - ADMIN_USER_IDS (required)"
    print_warning "  - DASHBOARD_ADMIN_TOKEN (recommended)"
    print_warning "  - REDIS_URL (if using custom Redis config)"
    echo
    read -p "Press Enter to continue, or Ctrl+C to edit .env first..."
fi

# Test the bot
print_status "Testing bot configuration..."
if python main.py --test 2>/dev/null; then
    print_status "Bot test passed!"
else
    print_warning "Bot test failed. Please check your .env configuration."
fi

# Setup PM2 ecosystem
print_status "Configuring PM2 for process management..."
cp ecosystem.config.js ecosystem.config.js.backup

# Setup logging directory
print_status "Creating log directory..."
mkdir -p /var/log/ingress-bot

# Start the bot with PM2
print_status "Starting bot with PM2..."
pm2 start ecosystem.config.js
pm2 save

# Setup PM2 startup script
pm2 startup

# Configure firewall
print_status "Configuring firewall..."
ufw allow ssh
ufw allow 80
ufw allow 443
ufw --force enable

# Setup log rotation
print_status "Setting up log rotation..."
cat > /etc/logrotate.d/ingress-bot << EOF
/var/log/ingress-bot/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 www-data www-data
    postrotate
        pm2 reload ingress-bot
    endscript
}
EOF

# Print deployment summary
echo ""
print_status "🎉 Deployment completed successfully!"
echo ""
echo "Next steps:"
echo "1. Configure your bot token in .env file if not done already"
echo "2. Test your bot on Telegram"
echo "3. Set up domain name and SSL (optional):"
echo "   - Point your domain to this server's IP"
echo "   - Run: certbot --nginx -d your-domain.com"
echo ""
echo "Useful commands:"
echo "- Check bot status: pm2 status"
echo "- View logs: pm2 logs ingress-bot"
echo "- Restart bot: pm2 restart ingress-bot"
echo "- Monitor: pm2 monit"
echo ""
echo "Bot is now running on your Linode server! 🚀"