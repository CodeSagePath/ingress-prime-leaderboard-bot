#!/usr/bin/env python3
"""
🔧 Command Manager - Dynamic Bot Command Management
Manages bot commands without requiring BotFather
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from telegram import BotCommand, Update
from telegram.ext import Application, ContextTypes

logger = logging.getLogger(__name__)


class CommandManager:
    """Manages bot commands dynamically from configuration files."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the command manager.

        Args:
            config_path: Path to commands configuration file
        """
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), "commands_config.json"
        )
        self.commands_config: Dict[str, Any] = {}
        self.commands: List[BotCommand] = []
        self.load_commands()

    def load_commands(self) -> None:
        """Load commands from configuration file."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.commands_config = json.load(f)

                # Convert config to BotCommand objects
                self.commands = []
                for cmd_config in self.commands_config.get('commands', []):
                    if cmd_config.get('enabled', True):
                        self.commands.append(BotCommand(
                            command=cmd_config['command'],
                            description=cmd_config['description']
                        ))

                logger.info(f"Loaded {len(self.commands)} commands from config")
            else:
                logger.warning(f"Commands config file not found: {self.config_path}")
                self.create_default_config()

        except Exception as e:
            logger.error(f"Error loading commands config: {e}")
            self.commands_config = {}
            self.commands = []

    def create_default_config(self) -> None:
        """Create a default configuration file."""
        default_config = {
            "commands": [
                {
                    "command": "start",
                    "description": "🎮 Start bot and get welcome message",
                    "category": "basic",
                    "emoji": "🎮",
                    "enabled": True
                },
                {
                    "command": "help",
                    "description": "❓ Show comprehensive help and commands",
                    "category": "basic",
                    "emoji": "❓",
                    "enabled": True
                },
                {
                    "command": "commands",
                    "description": "📋 Interactive commands menu (recommended)",
                    "category": "basic",
                    "emoji": "📋",
                    "enabled": True
                }
            ],
            "menu_layout": {
                "main": [
                    ["leaderboard", "myrank"],
                    ["submit", "importfile"]
                ]
            },
            "categories": {
                "basic": {
                    "name": "Basic Commands",
                    "emoji": "🔰",
                    "description": "Essential bot commands"
                }
            },
            "last_updated": datetime.now().isoformat(),
            "version": "1.0.0"
        }

        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            logger.info(f"Created default commands config: {self.config_path}")
        except Exception as e:
            logger.error(f"Error creating default config: {e}")

    def save_commands(self) -> bool:
        """Save current commands configuration to file."""
        try:
            self.commands_config['last_updated'] = datetime.now().isoformat()

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.commands_config, f, indent=2, ensure_ascii=False)

            logger.info(f"Commands configuration saved to: {self.config_path}")
            return True

        except Exception as e:
            logger.error(f"Error saving commands config: {e}")
            return False

    async def update_telegram_commands(self, application: Application) -> bool:
        """Update Telegram bot commands dynamically.

        Args:
            application: Telegram application instance

        Returns:
            True if successful, False otherwise
        """
        try:
            # Filter only enabled commands
            enabled_commands = []
            for cmd_config in self.commands_config.get('commands', []):
                if cmd_config.get('enabled', True):
                    enabled_commands.append(BotCommand(
                        command=cmd_config['command'],
                        description=cmd_config['description']
                    ))

            await application.bot.set_my_commands(enabled_commands)
            logger.info(f"Updated Telegram with {len(enabled_commands)} commands")
            return True

        except Exception as e:
            logger.error(f"Error updating Telegram commands: {e}")
            return False

    def add_command(self, command: str, description: str,
                   category: str = "basic", emoji: str = "🔹",
                   enabled: bool = True) -> bool:
        """Add a new command to the configuration.

        Args:
            command: Command name (without /)
            description: Command description
            category: Command category
            emoji: Command emoji
            enabled: Whether command is enabled

        Returns:
            True if successful, False otherwise
        """
        try:
            new_command = {
                "command": command,
                "description": description,
                "category": category,
                "emoji": emoji,
                "enabled": enabled
            }

            # Check if command already exists
            existing_commands = self.commands_config.get('commands', [])
            for i, cmd in enumerate(existing_commands):
                if cmd['command'] == command:
                    existing_commands[i] = new_command
                    break
            else:
                existing_commands.append(new_command)

            self.commands_config['commands'] = existing_commands
            return self.save_commands()

        except Exception as e:
            logger.error(f"Error adding command '{command}': {e}")
            return False

    def remove_command(self, command: str) -> bool:
        """Remove a command from the configuration.

        Args:
            command: Command name to remove (without /)

        Returns:
            True if successful, False otherwise
        """
        try:
            commands = self.commands_config.get('commands', [])
            self.commands_config['commands'] = [
                cmd for cmd in commands if cmd['command'] != command
            ]
            return self.save_commands()

        except Exception as e:
            logger.error(f"Error removing command '{command}': {e}")
            return False

    def toggle_command(self, command: str) -> Optional[bool]:
        """Toggle a command's enabled status.

        Args:
            command: Command name to toggle (without /)

        Returns:
            New enabled status or None if command not found
        """
        try:
            commands = self.commands_config.get('commands', [])
            for cmd in commands:
                if cmd['command'] == command:
                    cmd['enabled'] = not cmd['enabled']
                    if self.save_commands():
                        return cmd['enabled']
                    return None
            return None

        except Exception as e:
            logger.error(f"Error toggling command '{command}': {e}")
            return None

    def get_command_info(self, command: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific command.

        Args:
            command: Command name (without /)

        Returns:
            Command information dictionary or None if not found
        """
        commands = self.commands_config.get('commands', [])
        for cmd in commands:
            if cmd['command'] == command:
                return cmd.copy()
        return None

    def get_commands_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Get all commands in a specific category.

        Args:
            category: Category name

        Returns:
            List of command dictionaries
        """
        commands = self.commands_config.get('commands', [])
        return [cmd for cmd in commands if cmd.get('category') == category]

    def get_menu_layout(self) -> Dict[str, List[List[str]]]:
        """Get the menu layout configuration.

        Returns:
            Menu layout dictionary
        """
        return self.commands_config.get('menu_layout', {})

    def update_menu_layout(self, layout: Dict[str, List[List[str]]]) -> bool:
        """Update the menu layout configuration.

        Args:
            layout: New menu layout

        Returns:
            True if successful, False otherwise
        """
        try:
            self.commands_config['menu_layout'] = layout
            return self.save_commands()

        except Exception as e:
            logger.error(f"Error updating menu layout: {e}")
            return False

    def reload_commands(self) -> None:
        """Reload commands from configuration file."""
        self.load_commands()
        logger.info("Commands reloaded from configuration")

    def export_commands(self, file_path: str) -> bool:
        """Export commands configuration to a file.

        Args:
            file_path: Path to export file

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.commands_config, f, indent=2, ensure_ascii=False)
            logger.info(f"Commands exported to: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Error exporting commands: {e}")
            return False

    def import_commands(self, file_path: str) -> bool:
        """Import commands configuration from a file.

        Args:
            file_path: Path to import file

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)

            # Validate imported config
            if 'commands' not in imported_config:
                logger.error("Invalid commands configuration: missing 'commands' field")
                return False

            self.commands_config = imported_config
            success = self.save_commands()

            if success:
                self.load_commands()  # Reload after saving
                logger.info(f"Commands imported from: {file_path}")

            return success

        except Exception as e:
            logger.error(f"Error importing commands: {e}")
            return False


# Global command manager instance
command_manager = CommandManager()


def get_command_manager() -> CommandManager:
    """Get the global command manager instance."""
    return command_manager


# Utility functions for command management
async def update_bot_commands(application: Application) -> bool:
    """Update bot commands using the global command manager.

    Args:
        application: Telegram application instance

    Returns:
        True if successful, False otherwise
    """
    manager = get_command_manager()
    return await manager.update_telegram_commands(application)


def add_new_command(command: str, description: str,
                   category: str = "basic", emoji: str = "🔹") -> bool:
    """Add a new command using the global command manager.

    Args:
        command: Command name (without /)
        description: Command description
        category: Command category
        emoji: Command emoji

    Returns:
        True if successful, False otherwise
    """
    manager = get_command_manager()
    return manager.add_command(command, description, category, emoji)


def remove_bot_command(command: str) -> bool:
    """Remove a command using the global command manager.

    Args:
        command: Command name (without /)

    Returns:
        True if successful, False otherwise
    """
    manager = get_command_manager()
    return manager.remove_command(command)