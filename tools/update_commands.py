#!/usr/bin/env python3
"""
🛠️ Command Update Tool - CLI for updating bot commands
Usage: python tools/update_commands.py [action] [options]
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from bot.command_manager import get_command_manager


def list_commands():
    """List all configured commands."""
    manager = get_command_manager()
    commands_config = manager.commands_config

    print("🔧 Bot Commands Configuration")
    print("=" * 50)

    commands = commands_config.get('commands', [])
    categories = commands_config.get('categories', {})

    # Group commands by category
    categorized_commands = {}
    for cmd in commands:
        category = cmd.get('category', 'other')
        if category not in categorized_commands:
            categorized_commands[category] = []
        categorized_commands[category].append(cmd)

    for category, cmd_list in categorized_commands.items():
        category_info = categories.get(category, {})
        category_name = category_info.get('name', category.title())
        category_emoji = category_info.get('emoji', '📁')

        print(f"\n{category_emoji} {category_name}")
        print("-" * 30)

        for cmd in sorted(cmd_list, key=lambda x: x['command']):
            status = "✅" if cmd.get('enabled', True) else "❌"
            emoji = cmd.get('emoji', '🔹')
            print(f"  {status} /{cmd['command']:<15} {emoji} {cmd['description']}")


def add_command(command, description, category="basic", emoji="🔹"):
    """Add a new command."""
    manager = get_command_manager()

    if manager.add_command(command, description, category, emoji):
        print(f"✅ Command '/{command}' added successfully!")
        print(f"   Description: {description}")
        print(f"   Category: {category}")
        print(f"   Emoji: {emoji}")
        return True
    else:
        print(f"❌ Failed to add command '/{command}'")
        return False


def remove_command(command):
    """Remove a command."""
    manager = get_command_manager()

    # Show command info before removal
    cmd_info = manager.get_command_info(command)
    if cmd_info:
        print(f"ℹ️  Removing command: /{command}")
        print(f"   Description: {cmd_info['description']}")

        confirm = input("\nAre you sure? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Command removal cancelled")
            return False

    if manager.remove_command(command):
        print(f"✅ Command '/{command}' removed successfully!")
        return True
    else:
        print(f"❌ Failed to remove command '/{command}'")
        return False


def toggle_command(command):
    """Toggle command enabled status."""
    manager = get_command_manager()

    new_status = manager.toggle_command(command)
    if new_status is not None:
        status_text = "enabled" if new_status else "disabled"
        print(f"✅ Command '/{command}' {status_text}!")
        return True
    else:
        print(f"❌ Command '/{command}' not found")
        return False


def export_commands(file_path):
    """Export commands configuration."""
    manager = get_command_manager()

    if manager.export_commands(file_path):
        print(f"✅ Commands exported to: {file_path}")
        return True
    else:
        print(f"❌ Failed to export commands to: {file_path}")
        return False


def import_commands(file_path):
    """Import commands configuration."""
    manager = get_command_manager()

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False

    if manager.import_commands(file_path):
        print(f"✅ Commands imported from: {file_path}")
        return True
    else:
        print(f"❌ Failed to import commands from: {file_path}")
        return False


def reload_commands():
    """Reload commands from configuration."""
    manager = get_command_manager()
    manager.reload_commands()
    print("✅ Commands reloaded from configuration!")


def show_menu_layout():
    """Show current menu layout."""
    manager = get_command_manager()
    layout = manager.get_menu_layout()
    commands = manager.commands_config.get('commands', [])

    print("📋 Menu Layout Configuration")
    print("=" * 50)

    for menu_name, rows in layout.items():
        print(f"\n🔸 {menu_name.title()} Menu:")
        for row in rows:
            row_items = []
            for cmd_name in row:
                # Find command info
                cmd_info = next((cmd for cmd in commands if cmd['command'] == cmd_name), None)
                if cmd_info:
                    emoji = cmd_info.get('emoji', '🔹')
                    row_items.append(f"{emoji} {cmd_name}")
                else:
                    row_items.append(f"❓ {cmd_name}")

            print(f"  {'  '.join(row_items)}")


def backup_commands():
    """Create a backup of current commands configuration."""
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"commands_backup_{timestamp}.json"

    return export_commands(backup_file)


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Update bot commands without BotFather",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list                          # List all commands
  %(prog)s add tournament "View tournament standings" --category stats --emoji 🎯
  %(prog)s remove old_command           # Remove a command
  %(prog)s toggle test_command          # Enable/disable a command
  %(prog)s export backup.json           # Export commands to file
  %(prog)s import new_commands.json     # Import commands from file
  %(prog)s menu                         # Show menu layout
  %(prog)s backup                       # Create backup
        """
    )

    subparsers = parser.add_subparsers(dest='action', help='Available actions')

    # List commands
    subparsers.add_parser('list', help='List all commands')

    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new command')
    add_parser.add_argument('command', help='Command name (without /)')
    add_parser.add_argument('description', help='Command description')
    add_parser.add_argument('--category', default='basic', help='Command category (default: basic)')
    add_parser.add_argument('--emoji', default='🔹', help='Command emoji (default: 🔹)')

    # Remove command
    subparsers.add_parser('remove', help='Remove a command').add_argument('command', help='Command name (without /)')

    # Toggle command
    subparsers.add_parser('toggle', help='Toggle command enabled status').add_argument('command', help='Command name (without /)')

    # Export/Import
    subparsers.add_parser('export', help='Export commands to file').add_argument('file', help='Output file path')
    subparsers.add_parser('import', help='Import commands from file').add_argument('file', help='Input file path')

    # Other actions
    subparsers.add_parser('reload', help='Reload commands from configuration')
    subparsers.add_parser('menu', help='Show menu layout')
    subparsers.add_parser('backup', help='Create backup of commands')

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        return

    # Execute the requested action
    success = True

    if args.action == 'list':
        list_commands()
    elif args.action == 'add':
        success = add_command(args.command, args.description, args.category, args.emoji)
    elif args.action == 'remove':
        success = remove_command(args.command)
    elif args.action == 'toggle':
        success = toggle_command(args.command)
    elif args.action == 'export':
        success = export_commands(args.file)
    elif args.action == 'import':
        success = import_commands(args.file)
    elif args.action == 'reload':
        reload_commands()
    elif args.action == 'menu':
        show_menu_layout()
    elif args.action == 'backup':
        success = backup_commands()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()