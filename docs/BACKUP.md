# Backup Configuration Guide

This guide explains how to set up and configure remote backups for the Ingress leaderboard bot using rclone.

## Prerequisites

1. Install rclone on your system:
   ```
   curl https://rclone.org/install.sh | sudo bash
   ```

2. Verify rclone installation:
   ```
   rclone version
   ```

## Setting up rclone

1. Configure rclone with your preferred cloud storage service:
   ```
   rclone config
   ```

2. Follow the interactive setup process. Here are examples for popular services:

   ### Google Drive
   - Choose "n" for New remote
   - Enter a name (e.g., "gdrive")
   - Choose "13" for Google Drive
   - Leave client_id and client_secret blank for default
   - Choose "N" for auto config
   - Follow the link to authenticate with Google
   - Choose "Y" to confirm this is OK

   ### Dropbox
   - Choose "n" for New remote
   - Enter a name (e.g., "dropbox")
   - Choose "10" for Dropbox
   - Leave client_id and client_secret blank for default
   - Choose "N" for auto config
   - Follow the link to authenticate with Dropbox
   - Choose "Y" to confirm this is OK

3. Test your rclone configuration:
   ```
   rclone ls <your_remote_name>:
   ```

## Environment Variables

Add the following environment variables to your `.env` file:

```bash
# Enable/disable remote backups
BACKUP_ENABLED=true

# Rclone remote name (as configured in rclone config)
BACKUP_RCLONE_REMOTE=gdrive

# Backup destination path on the remote storage
BACKUP_DESTINATION_PATH=ingress-bot-backups

# Backup schedule (daily or weekly)
BACKUP_SCHEDULE=daily

# Number of backups to retain
BACKUP_RETENTION_COUNT=7

# Compress backup files (true/false)
BACKUP_COMPRESS=true
```

## Configuration Options

### BACKUP_ENABLED
- **Values**: `true` or `false`
- **Default**: `false`
- **Description**: Enable or disable the backup functionality

### BACKUP_RCLONE_REMOTE
- **Values**: String (rclone remote name)
- **Default**: `""` (empty)
- **Description**: The name of the rclone remote configured for cloud storage

### BACKUP_DESTINATION_PATH
- **Values**: String (path on remote storage)
- **Default**: `"ingress-bot-backups"`
- **Description**: The directory path on the remote storage where backups will be stored

### BACKUP_SCHEDULE
- **Values**: `"daily"` or `"weekly"`
- **Default**: `"daily"`
- **Description**: How often to run automatic backups
  - `daily`: Runs at 2 AM UTC every day
  - `weekly`: Runs at 2 AM UTC on Sundays

### BACKUP_RETENTION_COUNT
- **Values**: Integer (number of backups)
- **Default**: `7`
- **Description**: Number of backup files to retain. Older backups will be automatically deleted.

### BACKUP_COMPRESS
- **Values**: `true` or `false`
- **Default**: `true`
- **Description**: Whether to compress backup files using gzip

## Manual Backup

Admin users can trigger a manual backup using the `/backup` command in Telegram. The bot will report the status of the backup operation.

## Backup Process

1. **Database Backup**: The bot creates a copy of the SQLite database
2. **Compression**: If enabled, the backup file is compressed using gzip
3. **Upload**: The backup file is uploaded to the configured cloud storage using rclone
4. **Cleanup**: Old backups are deleted based on the retention policy
5. **Notification**: Admin users are notified of the backup status (success/failure)

## Troubleshooting

### Common Issues

1. **rclone command not found**
   - Ensure rclone is installed and available in the system PATH
   - Check with `which rclone`

2. **Authentication errors**
   - Verify your rclone configuration with `rclone config`
   - Test the connection with `rclone ls <remote_name>:`

3. **Permission errors**
   - Ensure the bot has write permissions to the backup directory
   - Check cloud storage permissions

4. **Backup fails silently**
   - Check the bot logs for error messages
   - Verify all required environment variables are set

### Testing Your Configuration

1. Test rclone connectivity:
   ```
   rclone ls <your_remote_name>:
   ```

2. Test file upload:
   ```
   echo "test" > test.txt
   rclone copy test.txt <your_remote_name>:<destination_path>
   rclone ls <your_remote_name>:<destination_path>
   ```

3. Check bot logs for backup-related messages:
   ```
   tail -f bot.log | grep backup
   ```

## Security Considerations

1. Keep your rclone configuration file secure
2. Use dedicated cloud storage accounts for backups
3. Regularly review backup retention policies
4. Monitor backup notifications for failures

## Best Practices

1. Test your backup configuration regularly
2. Verify backup files can be restored
3. Monitor available storage space
4. Set up alerts for backup failures
5. Consider encrypting sensitive backup data