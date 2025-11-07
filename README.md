# Ingress Prime Leaderboard Bot

A comprehensive Telegram bot for Ingress Prime players that tracks AP (Access Points), multiple metrics, and provides competitive leaderboards with flexible submission formats.

## Table of Contents
- [Project Description](#project-description)
- [Key Features](#key-features)
- [Setup Instructions](#setup-instructions)
- [Environment Variables](#environment-variables)
- [Commands](#commands)
- [Leaderboard Capabilities](#leaderboard-capabilities)
- [Submit Format](#submit-format)
- [Flexible Column Support](#flexible-column-support)
- [Backup Configuration](#backup-configuration)
- [Deployment Instructions](#deployment-instructions)
- [Troubleshooting](#troubleshooting)

## Project Description

The Ingress Prime Leaderboard Bot is a feature-rich Telegram bot designed to help Ingress Prime players track and compare their performance across multiple metrics. The bot supports direct Ingress Prime data export pasting, comprehensive leaderboards, and works seamlessly with various column configurations.

Key features:
- **Direct Ingress Prime Export Support** - Paste data exactly as exported from the app
- **Comprehensive Leaderboards** - Multiple metrics and time periods
- **Flexible Column Mapping** - Works with 59, 67, 70+ column configurations
- **User-Friendly Submission** - Reply-based submission flow with examples
- **Multiple Metrics** - AP, hacks, XM collected, portals captured, links created, and more
- **Time Period Support** - All time, weekly, monthly, daily rankings
- **Smart Group Integration** - Reply detection and mention handling
- **Automatic Data Validation** - Format checking and duplicate prevention
- **Background Job Processing** - Redis Queue for efficient task management

The bot is built with Python 3.11+, uses SQLAlchemy with aiosqlite for database operations, Redis for background job processing, and the python-telegram-bot library for Telegram integration.

## Key Features

### 🚀 **Enhanced User Experience**
- **Reply-Based Submission**: Use `/submit` and reply with your data (no more long commands)
- **Clear Format Examples**: Bot shows exactly how Ingress Prime data should look
- **Smart Group Handling**: No @mention needed when replying to submit instructions
- **Detailed Confirmation**: See recorded stats with agent name, AP, and cycle points

### 📊 **Comprehensive Leaderboards**
- **Multiple Metrics**: AP, hacks, XM collected, portals captured, links created, fields created, distance walked, and more
- **Time Periods**: All time, weekly, monthly, daily rankings
- **Faction Support**: Filter by ENL/RES factions
- **Custom Limits**: View top 5 to 50 agents

### 🔧 **Technical Features**
- **Flexible Column Mapping**: Handles any Ingress Prime export format (59-70+ columns)
- **Smart Error Handling**: Clear guidance when format is incorrect
- **Duplicate Detection**: Prevents double submissions
- **Text Mode Support**: Optimized for older devices
- **Privacy Controls**: Automatic message deletion and group privacy settings

## Setup Instructions

### Prerequisites

- Python 3.11 or higher
- Redis server
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/ingress-prime-leaderboard-bot.git
   cd ingress-prime-leaderboard-bot
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   ```
   Edit the `.env` file with your configuration:
   ```
   BOT_TOKEN=your_telegram_bot_token
   DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
   REDIS_URL=redis://localhost:6379/0
   LEADERBOARD_SIZE=10
   AUTODELETE_ENABLED=true
   AUTODELETE_DELAY_SECONDS=300
   ```

5. **Start Redis server**
   ```bash
   redis-server
   ```

6. **Run the bot**
   ```bash
   python main.py
   ```

### Docker Setup

1. **Build the Docker image**
   ```bash
   docker build -t ingress-leaderboard-bot .
   ```

2. **Run with Docker Compose**
   Create a `docker-compose.yml` file:
   ```yaml
   version: '3.8'
   services:
     bot:
       build: .
       environment:
         - BOT_TOKEN=your_telegram_bot_token
         - DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
         - REDIS_URL=redis://redis:6379/0
         - LEADERBOARD_SIZE=10
         - AUTODELETE_ENABLED=true
         - AUTODELETE_DELAY_SECONDS=300
       depends_on:
         - redis
     redis:
       image: redis:alpine
       ports:
         - "6379:6379"
   ```

   Run the services:
   ```bash
   docker-compose up
   ```

## Environment Variables

The bot uses the following environment variables for configuration:

### Required Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `BOT_TOKEN` | Telegram Bot Token from [@BotFather](https://t.me/BotFather) | None | `123456789:ABCdefGHijKLmnoPqrsTuVwxyz` |
| `DATABASE_URL` | Database connection URL | `sqlite+aiosqlite:///./bot.db` | `sqlite+aiosqlite:///./bot.db` |
| `REDIS_URL` | Redis connection URL for background jobs | `redis://localhost:6379/0` | `redis://redis:6379/0` |

### Optional Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `LEADERBOARD_SIZE` | Number of agents to show on the leaderboard | `10` | `15` |
| `AUTODELETE_ENABLED` | Enable automatic deletion of bot messages | `true` | `false` |
| `AUTODELETE_DELAY_SECONDS` | Delay before deleting messages (in seconds) | `300` | `600` |
| `GROUP_MESSAGE_RETENTION_MINUTES` | Minutes to keep group messages before cleanup | `60` | `120` |
| `ADMIN_USER_IDS` | Comma-separated list of admin user IDs | `""` (empty) | `123456789,987654321` |
| `TEXT_ONLY_MODE` | Disable emojis and markdown for better performance on old devices | `false` | `true` |

### Backup Configuration Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `BACKUP_ENABLED` | Enable/disable remote backups | `false` | `true` |
| `BACKUP_RCLONE_REMOTE` | Rclone remote name for cloud storage | `""` (empty) | `gdrive` |
| `BACKUP_DESTINATION_PATH` | Backup destination path on remote storage | `ingress-bot-backups` | `my-bot-backups` |
| `BACKUP_SCHEDULE` | Backup schedule (daily or weekly) | `daily` | `weekly` |
| `BACKUP_RETENTION_COUNT` | Number of backups to retain | `7` | `14` |
| `BACKUP_COMPRESS` | Compress backup files | `true` | `false` |

### Database Configuration

The bot supports SQLite by default, but you can use any database supported by SQLAlchemy. For production, consider using PostgreSQL:

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost/ingress_bot
```

## Commands

The bot supports the following commands:

### **User Commands**

**/start** - Welcome message and basic bot information

**/help** - Display help message with all available commands and examples

**/submit** - Submit your Ingress Prime stats with improved reply-based flow (send /submit, then reply with your data)

**/leaderboard** - Display leaderboards with multiple metrics and time periods

**/myrank** - Check your personal ranking

**/top10** - Show top 10 agents (same as /leaderboard)

**/top <faction>** - Show top agents for specific faction (ENL or RES)

**/settings** - Configure display preferences (date format, number format, leaderboard size, etc.)

**/betatokens** - Check your Beta tokens status and requirements

### **Group Commands**

**/privacy** - Configure group privacy settings (public/soft/strict) - Group admins only

### **Admin Commands**

**/stats** - Display usage statistics and bot performance - Admin users only

**/backup** - Trigger a manual database backup - Admin users only

**/broadcast** - Send broadcast message to all users - Admin users only

### **Command Usage Examples**

**Basic Commands**
```
/start                          # Welcome message
/help                           # Show help and examples
/submit                         # Start submission flow
/top10                          # Show top 10 agents
/top ENL                        # Top Enlightened agents
```

**Leaderboard Commands**
```
/leaderboard                    # All time AP (default)
/leaderboard weekly             # Weekly AP
/leaderboard hacks              # Top hackers (weekly)
/leaderboard xm                 # Top XM collectors
/leaderboard weekly hacks       # Weekly hackers
/leaderboard all links          # All time link creators
/leaderboard monthly portals 20 # Top 20 monthly portal capturers
```

**Personal Ranking Commands**
```
/myrank                         # Your all time AP rank
/myrank weekly                  # Your weekly AP rank
/myrank hacks                   # Your hack rank
/myrank xm weekly               # Your weekly XM rank
```

**Submit Flow Example**
```
User: /submit

Bot: [Sends detailed instructions with format examples]

User: [Replies with Ingress Prime data]

Bot: ✅ Stats recorded successfully!
    👤 Agent: YourName
    ⚡ Lifetime AP: 55,000,000
    🏆 Cycle Points: 970
```

**Supported Leaderboard Metrics**
- `ap` - Action Points (default)
- `hacks` - Portal hacks performed
- `xm` - XM collected
- `portals` - Portals captured
- `links` - Links created
- `fields` - Fields created
- `distance` - Distance walked
- `destroyed` - Resonators destroyed
- `neutralized` - Portals neutralized
- `resonators` - Resonators deployed
- `mods` - Mods deployed

**Supported Time Periods**
- `all` - All time statistics (default for AP)
- `weekly` - This week (default for other metrics)
- `monthly` - This month
- `daily` - Today

## Leaderboard Capabilities

The bot supports comprehensive leaderboard functionality with multiple metrics and time periods, going far beyond just AP-based rankings.

### Supported Metrics

**Primary Metrics:**
- **AP (Action Points)** - Default metric, shows total action points
- **Hacks** - Number of portal hacks performed
- **XM Collected** - Total XM collected
- **Portals Captured** - Number of portals captured
- **Links Created** - Number of links created
- **Fields Created** - Number of control fields created
- **Distance Walked** - Total distance walked

**Combat Metrics:**
- **Resonators Destroyed** - Number of enemy resonators destroyed
- **Portals Neutralized** - Number of enemy portals neutralized

**Support Metrics:**
- **Resonators Deployed** - Number of resonators deployed
- **Mods Deployed** - Number of mods deployed

### Time Periods

- **ALL TIME** - Lifetime statistics (default for AP)
- **WEEKLY** - This week's statistics (default for other metrics)
- **MONTHLY** - This month's statistics
- **DAILY** - Today's statistics

### Command Examples

```bash
# Basic commands
/leaderboard                    # All time AP leaderboard
/leaderboard 20                 # Top 20 agents (all time AP)

# Time period specific
/leaderboard weekly             # Weekly AP leaderboard
/leaderboard monthly            # Monthly AP leaderboard
/leaderboard all                # All time AP leaderboard
/leaderboard daily              # Daily AP leaderboard

# Metric specific
/leaderboard hacks              # Top hackers (weekly)
/leaderboard xm                 # Top XM collectors (weekly)
/leaderboard portals            # Top portal capturers (weekly)
/leaderboard links              # Top link creators (weekly)
/leaderboard fields             # Top field creators (weekly)
/leaderboard distance           # Top distance walkers (weekly)

# Combined commands
/leaderboard weekly hacks       # Weekly hackers leaderboard
/leaderboard monthly xm         # Monthly XM collectors
/leaderboard all links          # All time link creators
/leaderboard weekly 15          # Top 15 weekly hackers
```

### Features

- **Smart Defaults**: AP defaults to ALL TIME, other metrics default to WEEKLY
- **Flexible Arguments**: Arguments can be in any order, multiple synonyms supported
- **Number Formatting**: Numbers formatted with commas (e.g., 1,234,567)
- **Faction Display**: Shows agent faction [ENL]/[RES] tags
- **Performance**: Text-only mode available for older devices

## Submit Format

The bot now uses an improved reply-based submission flow that's much more user-friendly:

### New Submit Flow (Recommended)

1. **Send `/submit` command**
   ```
   User: /submit
   ```

2. **Bot sends detailed instructions**
   ```
   📊 **STATS SUBMISSION** 📊

   Please paste your Ingress Prime export data.

   📋 **FORMAT EXAMPLE:**
   Copy your data from Ingress Prime app and paste it exactly as shown:

   ```
   Time Span Agent Name Agent Faction Date (yyyy-mm-dd) Time (hh:mm:ss) Level Lifetime AP Current AP ...
   ALL TIME YourName Enlightened 2025-11-07 04:40:52 13 55000000 15000000 ...
   ```

   ✅ **Simply reply to this message with your data**
   💡 **Make sure to include both the header line and your data line**
   ```

3. **Reply with your data**
   ```
   User: [Replies with Ingress Prime export data]
   ```

4. **Bot confirms with details**
   ```
   ✅ **Stats recorded successfully!**

   👤 **Agent:** YourName
   ⚡ **Lifetime AP:** 55,000,000
   🏆 **Cycle Points:** 970
   ```

### Benefits

- **No More Long Commands**: Simply use `/submit` and reply
- **Clear Examples**: See exactly what format to use
- **Better Group Experience**: No @mention needed when replying to instructions
- **Detailed Confirmation**: See your recorded stats immediately
- **Flexible Format**: Works with any column configuration (59, 67, 70+ columns)

## Flexible Column Support

The bot supports flexible column mapping that can handle varying Ingress Prime export configurations while maintaining compatibility with existing formats.

### Problem Solved

Previously, users with different column configurations (59, 67, 70+ columns) would get "Unsupported header format" errors when trying to submit their data.

### Solution

Implemented intelligent column mapping that:

- **Essential Column Detection**: Ensures required columns (Time Span, Agent Name, Agent Faction) are present
- **Smart Column Matching**: Uses look-ahead matching to identify multi-word column names
- **Graceful Error Handling**: Provides clear error messages when essential columns are missing
- **Flexible Column Count**: Handles varying numbers of columns (fewer or more than expected)
- **Unknown Column Handling**: Preserves unexpected columns with clear labeling

### Supported Configurations

✅ **59-column configuration** - Successfully parsed
✅ **67-column configuration** - Successfully parsed
✅ **70-column configuration** - Successfully parsed
✅ **Minimal configurations** - Successfully handled missing optional columns
✅ **Different column orders** - Successfully parsed
✅ **Unknown columns** - Handled gracefully

### Backward Compatibility

- ✅ All existing predefined column formats continue to work exactly as before
- ✅ No breaking changes to existing functionality
- ✅ Graceful fallback to original parsing methods

## Backup Configuration

The bot supports automatic database backups to cloud storage services using rclone. This feature helps protect your data by creating regular backups that can be restored if needed.

### Key Features

- **Automatic Scheduled Backups**: Configure daily or weekly backups
- **Cloud Storage Support**: Works with Google Drive, Dropbox, and other rclone-supported services
- **Compression**: Optional gzip compression to reduce storage space
- **Retention Policy**: Automatically clean up old backups based on configurable retention
- **Manual Backups**: Admin users can trigger manual backups using the `/backup` command
- **Admin Notifications**: Get notified when backups succeed or fail

### Backup Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `BACKUP_ENABLED` | Enable/disable remote backups | `false` | `true` |
| `BACKUP_RCLONE_REMOTE` | Rclone remote name for cloud storage | `""` (empty) | `gdrive` |
| `BACKUP_DESTINATION_PATH` | Backup destination path on remote storage | `ingress-bot-backups` | `my-bot-backups` |
| `BACKUP_SCHEDULE` | Backup schedule (daily or weekly) | `daily` | `weekly` |
| `BACKUP_RETENTION_COUNT` | Number of backups to retain | `7` | `14` |
| `BACKUP_COMPRESS` | Compress backup files | `true` | `false` |

### Quick Setup

1. Install rclone on your system:
   ```bash
   curl https://rclone.org/install.sh | sudo bash
   ```

2. Configure rclone with your cloud storage:
   ```bash
   rclone config
   ```

3. Set the backup environment variables in your `.env` file:
   ```bash
   BACKUP_ENABLED=true
   BACKUP_RCLONE_REMOTE=your_remote_name
   BACKUP_DESTINATION_PATH=ingress-bot-backups
   BACKUP_SCHEDULE=daily
   BACKUP_RETENTION_COUNT=7
   BACKUP_COMPRESS=true
   ```

4. Restart the bot to apply the configuration

## Deployment Instructions

### Railway Deployment

Railway is a cloud platform that makes it easy to deploy applications. Follow these steps to deploy the Ingress Prime Leaderboard Bot on Railway:

1. **Prepare your repository**
   - Ensure your code is pushed to a Git repository
   - Make sure all necessary files are included (Dockerfile, requirements.txt, etc.)

2. **Create a Railway account**
   - Sign up at [railway.app](https://railway.app)
   - Install the Railway CLI or connect your GitHub account

3. **Create a new project**
   ```bash
   railway login
   railway init
   ```
   Or connect your GitHub repository through the Railway dashboard

4. **Set environment variables**
   ```bash
   railway variables add BOT_TOKEN=your_telegram_bot_token
   railway variables add DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
   railway variables add REDIS_URL=redis://redis:6379/0
   railway variables add LEADERBOARD_SIZE=10
   railway variables add AUTODELETE_ENABLED=true
   railway variables add AUTODELETE_DELAY_SECONDS=300
   ```
   Or set them through the Railway dashboard

5. **Add Redis service**
   ```bash
   railway add redis
   ```
   This will create a Redis service and update your `REDIS_URL` automatically

6. **Deploy the application**
   ```bash
   railway up
   ```
   Or push to your connected Git repository to trigger automatic deployment

7. **Monitor your deployment**
   - Check the logs in the Railway dashboard
   - Monitor the service status and performance

### Railway-specific Considerations

- **Database**: Railway's ephemeral filesystem means SQLite data will be lost on redeployment. For production, consider using Railway's PostgreSQL service:
  ```bash
  railway add postgresql
  ```
  Then update your `DATABASE_URL` environment variable accordingly.

- **Redis**: Railway provides a managed Redis service that's automatically configured when you add it to your project.

- **Scaling**: Railway automatically scales your application based on demand. The bot is designed to be stateless, with all data stored in the database and Redis.

- **Monitoring**: Use Railway's built-in monitoring tools to track your bot's performance and resource usage.

### Linode Server Deployment

Deploy your bot on a Linode server for maximum performance and control.

#### 1. Provision a Linode

1. **Create a Linode instance**
   - Choose **Ubuntu 24.04 LTS** (stable, long-term support version)
   - Recommended specs: 2GB RAM, 1 CPU, 25GB SSD (or higher for production)
   - Select a region closest to your users

2. **SSH into your server**
   ```bash
   ssh root@your_linode_ip
   ```

#### 2. Server Setup (Ubuntu 24.04 LTS)

1. **Update system packages**
   ```bash
   apt update && apt upgrade -y
   ```

2. **Install required packages**
   ```bash
   apt install python3 python3-pip python3-venv git redis-server nginx -y
   ```

3. **Install Node.js for PM2 (process manager)**
   ```bash
   curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
   apt-get install -y nodejs
   npm install -g pm2
   ```

4. **Configure and start services**
   ```bash
   systemctl enable redis-server
   systemctl start redis-server
   systemctl enable nginx
   systemctl start nginx
   ```

#### 3. Deploy the Bot

1. **Clone your repository**
   ```bash
   cd /var/www
   git clone git@github.com:CodeSagePath/ingress-prime-leaderboard-bot.git
   cd ingress-prime-leaderboard-bot
   ```

2. **Create virtual environment**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   nano .env
   # Configure your bot token, admin IDs, etc.
   ```

4. **Test the bot**
   ```bash
   python main.py
   ```

#### 4. Configure PM2 for Process Management

1. **Create PM2 ecosystem file**
   ```bash
   nano ecosystem.config.js
   ```

2. **Add the following configuration**:
   ```javascript
   module.exports = {
     apps: [{
       name: 'ingress-bot',
       script: 'main.py',
       interpreter: '/var/www/ingress-prime-leaderboard-bot/venv/bin/python',
       cwd: '/var/www/ingress-prime-leaderboard-bot',
       instances: 1,
       autorestart: true,
       watch: false,
       max_memory_restart: '500M',
       env: {
         NODE_ENV: 'production'
       }
     }]
   };
   ```

3. **Start the bot with PM2**
   ```bash
   pm2 start ecosystem.config.js
   pm2 save
   pm2 startup
   ```

#### 5. Configure Nginx (Optional but Recommended)

1. **Create Nginx configuration**
   ```bash
   nano /etc/nginx/sites-available/ingress-bot
   ```

2. **Add basic reverse proxy (if you want web dashboard)**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://localhost:8085;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

3. **Enable the site**
   ```bash
   ln -s /etc/nginx/sites-available/ingress-bot /etc/nginx/sites-enabled/
   nginx -t
   systemctl restart nginx
   ```

#### 6. Set Up SSL Certificate (Recommended)

```bash
# Install Certbot
apt install certbot python3-certbot-nginx -y

# Get SSL certificate
certbot --nginx -d your-domain.com
```

#### 7. Configure Firewall (Ubuntu 24.04 LTS)

```bash
# Install and configure UFW firewall
apt install ufw -y

# Default policies
ufw default deny incoming
ufw default allow outgoing

# Allow necessary ports
ufw allow ssh
ufw allow 80
ufw allow 443

# Enable firewall
ufw enable
```

#### 8. Monitoring and Maintenance

1. **Monitor with PM2**
   ```bash
   pm2 status
   pm2 logs ingress-bot
   pm2 monit
   ```

2. **Set up log rotation**
   ```bash
   nano /etc/logrotate.d/ingress-bot
   ```

3. **Backup script (optional)**
   ```bash
   # Create backup script
   nano /var/www/ingress-prime-leaderboard-bot/backup.sh
   # Add to crontab for daily backups
   crontab -e
   # Add: 0 2 * * * /var/www/ingress-prime-leaderboard-bot/backup.sh
   ```

### Docker Deployment (Alternative)

If you prefer Docker deployment, use the provided Dockerfile:

1. **Build and run with Docker**
   ```bash
   docker build -t ingress-bot .
   docker run -d --name ingress-bot --env-file .env ingress-bot
   ```

2. **Use Docker Compose for complete stack**
   ```bash
   docker-compose up -d
   ```

## Troubleshooting

### Common Issues and Solutions

#### Bot doesn't respond to commands

**Possible causes:**
- Bot token is incorrect or revoked
- Bot is not running
- Network connectivity issues

**Solutions:**
1. Verify your bot token is correct and hasn't been revoked
2. Check the bot logs for error messages
3. Ensure the bot is running and connected to the internet
4. Try sending `/start` to the bot to see if it responds

#### Database connection errors

**Possible causes:**
- Database URL is incorrect
- Database server is not running
- Permission issues

**Solutions:**
1. Verify your `DATABASE_URL` environment variable is correct
2. If using SQLite, ensure the directory is writable
3. If using PostgreSQL, ensure the server is running and accessible
4. Check database credentials and permissions

#### Redis connection errors

**Possible causes:**
- Redis server is not running
- Redis URL is incorrect
- Network connectivity issues

**Solutions:**
1. Verify your `REDIS_URL` environment variable is correct
2. Ensure the Redis server is running
3. Check network connectivity between the bot and Redis
4. Verify Redis credentials if authentication is enabled

#### Message deletion not working

**Possible causes:**
- Bot doesn't have delete permissions in the chat
- `AUTODELETE_ENABLED` is set to false
- Redis job processing is not working

**Solutions:**
1. Ensure the bot has admin rights with message deletion permissions in the chat
2. Verify `AUTODELETE_ENABLED` is set to `true`
3. Check Redis is running and accessible
4. Verify the `AUTODELETE_DELAY_SECONDS` value is reasonable

#### Leaderboard not updating

**Possible causes:**
- No submissions have been made
- Database query issues
- Caching issues

**Solutions:**
1. Ensure agents have submitted their AP using `/submit`
2. Check the database for submissions data
3. Restart the bot to clear any cached data
4. Check the logs for database errors

#### Registration process not working

**Possible causes:**
- Telegram API issues
- Database connection problems
- Invalid faction input

**Solutions:**
1. Ensure you're entering a valid faction (ENL or RES)
2. Check the bot logs for error messages
3. Verify database connectivity
4. Try cancelling with `/cancel` and restarting the registration process

### Getting Help

If you encounter issues not covered here:
1. Check the bot logs for detailed error messages
2. Verify all environment variables are set correctly
3. Ensure all dependencies are installed and up to date
4. Create an issue in the project repository with details about your problem
