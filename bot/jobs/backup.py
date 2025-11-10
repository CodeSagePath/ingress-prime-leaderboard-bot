import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

from telegram import Update
from telegram.error import TelegramError

from ..config import Settings
from ..database import session_scope
from ..models import Agent

logger = logging.getLogger(__name__)


async def create_database_backup(database_url: str, backup_path: str, compress: bool = True) -> str:
    """
    Create a backup of the database.
    
    Args:
        database_url: The database URL
        backup_path: Path where the backup should be saved
        compress: Whether to compress the backup file
        
    Returns:
        Path to the created backup file
    """
    logger.info(f"Creating database backup from {database_url} to {backup_path}")
    
    # Extract database file path from SQLite URL
    if database_url.startswith("sqlite"):
        # Format: sqlite+aiosqlite:///./bot.db
        db_file_path = database_url.split(":///")[-1]
        if not os.path.isabs(db_file_path):
            # Make it relative to the current working directory
            db_file_path = os.path.join(os.getcwd(), db_file_path)
        
        # Create a temporary backup file
        temp_backup_path = backup_path
        if compress:
            temp_backup_path += ".temp"
        
        try:
            # Copy the database file
            import shutil
            shutil.copy2(db_file_path, temp_backup_path)
            
            # Compress if requested
            if compress:
                import gzip
                compressed_path = backup_path + ".gz"
                with open(temp_backup_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        f_out.writelines(f_in)
                
                # Remove the temporary uncompressed file
                os.remove(temp_backup_path)
                backup_path = compressed_path
                logger.info(f"Database backup compressed to {backup_path}")
            else:
                logger.info(f"Database backup created at {backup_path}")
                
            return backup_path
        except Exception as e:
            logger.error(f"Error creating database backup: {e}")
            # Clean up any partial files
            if os.path.exists(temp_backup_path):
                os.remove(temp_backup_path)
            if compress and os.path.exists(backup_path + ".gz"):
                os.remove(backup_path + ".gz")
            raise
    else:
        # For non-SQLite databases, we would need a different approach
        error_msg = f"Backup not implemented for database type: {database_url}"
        logger.error(error_msg)
        raise NotImplementedError(error_msg)


async def upload_backup_with_rclone(
    backup_path: str, 
    rclone_remote: str, 
    destination_path: str
) -> bool:
    """
    Upload a backup file to remote storage using rclone.
    
    Args:
        backup_path: Path to the backup file to upload
        rclone_remote: Name of the rclone remote
        destination_path: Destination path on the remote storage
        
    Returns:
        True if upload was successful, False otherwise
    """
    logger.info(f"Uploading backup {backup_path} to {rclone_remote}:{destination_path}")
    
    try:
        # Generate a timestamped filename
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = os.path.basename(backup_path)
        name, ext = os.path.splitext(filename)
        remote_filename = f"{name}_{timestamp}{ext}"
        remote_path = f"{rclone_remote}:{destination_path}/{remote_filename}"
        
        # Build rclone command
        cmd = [
            "rclone", "copy", backup_path, remote_path,
            "--progress", "--create-empty-src-dirs"
        ]
        
        # Execute rclone command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            logger.info(f"Backup successfully uploaded to {remote_path}")
            return True
        else:
            error_msg = stderr.decode().strip()
            logger.error(f"rclone upload failed with error: {error_msg}")
            return False
    except Exception as e:
        logger.error(f"Error uploading backup with rclone: {e}")
        return False


async def cleanup_old_backups(
    rclone_remote: str, 
    destination_path: str, 
    retention_count: int
) -> bool:
    """
    Clean up old backups based on retention policy.
    
    Args:
        rclone_remote: Name of the rclone remote
        destination_path: Destination path on the remote storage
        retention_count: Number of backups to retain
        
    Returns:
        True if cleanup was successful, False otherwise
    """
    logger.info(f"Cleaning up old backups in {rclone_remote}:{destination_path}, keeping {retention_count} most recent")
    
    try:
        # List all backups in the destination path
        cmd = [
            "rclone", "lsf", f"{rclone_remote}:{destination_path}",
            "--format", "tp"
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error(f"rclone list failed with error: {error_msg}")
            return False
        
        # Parse the output to get backup files sorted by modification time
        output = stdout.decode().strip()
        if not output:
            logger.info("No backups found to clean up")
            return True
        
        # Parse each line: timestamp;size;path
        backup_files = []
        for line in output.split('\n'):
            if not line:
                continue
            try:
                parts = line.split(';')
                if len(parts) >= 3:
                    timestamp = int(parts[0])
                    size = int(parts[1])
                    path = parts[2]
                    backup_files.append((timestamp, size, path))
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse rclone output line: {line}, error: {e}")
                continue
        
        # Sort by timestamp (newest first)
        backup_files.sort(key=lambda x: x[0], reverse=True)
        
        # Delete old backups beyond retention count
        if len(backup_files) > retention_count:
            for _, _, path in backup_files[retention_count:]:
                delete_cmd = [
                    "rclone", "delete", f"{rclone_remote}:{destination_path}/{path}"
                ]
                
                delete_process = await asyncio.create_subprocess_exec(
                    *delete_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                delete_stdout, delete_stderr = await delete_process.communicate()
                
                if delete_process.returncode == 0:
                    logger.info(f"Deleted old backup: {path}")
                else:
                    error_msg = delete_stderr.decode().strip()
                    logger.error(f"Failed to delete old backup {path}: {error_msg}")
        
        logger.info("Backup cleanup completed")
        return True
    except Exception as e:
        logger.error(f"Error cleaning up old backups: {e}")
        return False


async def perform_backup(settings: Settings, application=None) -> bool:
    """
    Perform a complete backup operation.
    
    Args:
        settings: Bot settings
        application: Telegram application instance (optional, for notifications)
        
    Returns:
        True if backup was successful, False otherwise
    """
    if not settings.backup_enabled:
        logger.info("Backup is disabled in settings")
        return True
    
    if not settings.backup_rclone_remote:
        logger.error("Backup rclone remote not configured")
        return False
    
    logger.info("Starting backup process")
    
    # Create a temporary directory for the backup
    with tempfile.TemporaryDirectory() as temp_dir:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_filename = f"ingress_bot_backup_{timestamp}.db"
        backup_path = os.path.join(temp_dir, backup_filename)
        
        try:
            # Create database backup
            backup_file = await create_database_backup(
                settings.database_url, 
                backup_path, 
                settings.backup_compress
            )
            
            # Upload backup to remote storage
            upload_success = await upload_backup_with_rclone(
                backup_file,
                settings.backup_rclone_remote,
                settings.backup_destination_path
            )
            
            if not upload_success:
                logger.error("Backup upload failed")
                return False
            
            # Clean up old backups
            cleanup_success = await cleanup_old_backups(
                settings.backup_rclone_remote,
                settings.backup_destination_path,
                settings.backup_retention_count
            )
            
            if not cleanup_success:
                logger.warning("Backup cleanup failed, but backup was successful")
            
            logger.info("Backup process completed successfully")
            
            # Notify admins if application is provided
            if application and settings.admin_user_ids:
                await notify_admins_backup_success(application, settings.admin_user_ids)
            
            return True
        except Exception as e:
            logger.error(f"Backup process failed: {e}")
            
            # Notify admins about failure if application is provided
            if application and settings.admin_user_ids:
                await notify_admins_backup_failure(application, settings.admin_user_ids, str(e))
            
            return False


async def notify_admins_backup_success(application, admin_user_ids: list[int]) -> None:
    """
    Notify admins about successful backup.
    
    Args:
        application: Telegram application instance
        admin_user_ids: List of admin user IDs
    """
    message = "✅ Database backup completed successfully."
    
    for admin_id in admin_user_ids:
        try:
            await application.bot.send_message(chat_id=admin_id, text=message)
        except TelegramError as e:
            logger.error(f"Failed to notify admin {admin_id} about backup success: {e}")


async def notify_admins_backup_failure(application, admin_user_ids: list[int], error: str) -> None:
    """
    Notify admins about backup failure.
    
    Args:
        application: Telegram application instance
        admin_user_ids: List of admin user IDs
        error: Error message
    """
    message = f"❌ Database backup failed: {error}"
    
    for admin_id in admin_user_ids:
        try:
            await application.bot.send_message(chat_id=admin_id, text=message)
        except TelegramError as e:
            logger.error(f"Failed to notify admin {admin_id} about backup failure: {e}")


async def manual_backup_command(update: Update, context) -> None:
    """
    Handle the /backup command for manual backup triggering.
    
    Args:
        update: Telegram update
        context: Telegram context
    """
    if not update.message or not update.effective_user:
        return
    
    settings: Settings = context.application.bot_data["settings"]
    
    # Check if the user is an admin
    if update.effective_user.id not in settings.admin_user_ids:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    # Check if backup is enabled
    if not settings.backup_enabled:
        await update.message.reply_text("Backup is disabled in the bot configuration.")
        return
    
    # Check if rclone remote is configured
    if not settings.backup_rclone_remote:
        await update.message.reply_text("Backup rclone remote is not configured.")
        return
    
    # Send initial message
    status_message = await update.message.reply_text("Starting manual backup process...")
    
    # Perform backup
    success = await perform_backup(settings, context.application)
    
    # Update status message
    if success:
        await status_message.edit_text("✅ Manual backup completed successfully.")
    else:
        await status_message.edit_text("❌ Manual backup failed. Check logs for details.")