#!/usr/bin/env python3
"""
🚀 Deploy Commands - Deploy command updates to running bot
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from bot.command_manager import get_command_manager
from bot.app import build_application

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def deploy_commands_to_telegram():
    """Deploy command updates to Telegram directly."""
    print("🚀 Deploying Commands to Telegram Bot")
    print("=" * 50)

    try:
        # Load bot configuration
        from bot.config import load_settings
        settings = load_settings()

        if not settings.telegram_token:
            print("❌ Error: TELEGRAM_TOKEN not found in environment")
            return False

        print(f"✅ Bot token loaded for: {settings.telegram_token[:10]}...")

        # Build application
        print("🔧 Building Telegram application...")
        application = await build_application()

        # Get command manager and update commands
        print("📋 Updating bot commands...")
        manager = get_command_manager()

        # Update Telegram commands
        success = await manager.update_telegram_commands(application)

        if success:
            print("✅ Commands deployed successfully to Telegram!")
            print()
            print("📊 Current Commands:")
            commands = manager.commands_config.get('commands', [])
            for cmd in commands:
                if cmd.get('enabled', True):
                    status = "✅"
                    emoji = cmd.get('emoji', '🔹')
                    print(f"  {status} /{cmd['command']:<15} {emoji} {cmd['description']}")
            return True
        else:
            print("❌ Failed to deploy commands to Telegram")
            return False

    except Exception as e:
        print(f"❌ Error deploying commands: {e}")
        logger.error(f"Deployment error: {e}")
        return False


async def deploy_commands_to_server(config_file: str = None):
    """Deploy command configuration to server files."""
    print("📁 Deploying Commands Configuration")
    print("=" * 50)

    try:
        manager = get_command_manager()

        if config_file and os.path.exists(config_file):
            print(f"📥 Loading configuration from: {config_file}")
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Validate configuration
            if 'commands' not in config:
                print("❌ Invalid configuration: missing 'commands' field")
                return False

            manager.commands_config = config
            print("✅ Configuration loaded successfully")

        # Save to main config file
        if manager.save_commands():
            print(f"✅ Configuration saved to: {manager.config_path}")
        else:
            print("❌ Failed to save configuration")
            return False

        # Show summary
        commands = manager.commands_config.get('commands', [])
        enabled = sum(1 for cmd in commands if cmd.get('enabled', True))
        disabled = len(commands) - enabled

        print()
        print("📊 Deployment Summary:")
        print(f"   Total Commands: {len(commands)}")
        print(f"   Enabled: {enabled}")
        print(f"   Disabled: {disabled}")

        categories = manager.commands_config.get('categories', {})
        print(f"   Categories: {len(categories)}")

        return True

    except Exception as e:
        print(f"❌ Error deploying configuration: {e}")
        logger.error(f"Configuration deployment error: {e}")
        return False


def deploy_commands_to_server_files():
    """Deploy command files to server locations."""
    print("📂 Deploying Command Files to Server")
    print("=" * 50)

    source_dir = project_root / "bot"
    target_dirs = [
        project_root / "server" / "bot",
        project_root / "deploy" / "bot"
    ]

    files_to_deploy = [
        "commands_config.json",
        "command_manager.py"
    ]

    deployed_files = []

    for target_dir in target_dirs:
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            print(f"📁 Created directory: {target_dir}")

        for file_name in files_to_deploy:
            source_file = source_dir / file_name
            target_file = target_dir / file_name

            if source_file.exists():
                import shutil
                shutil.copy2(source_file, target_file)
                deployed_files.append(str(target_file))
                print(f"✅ Copied: {file_name} → {target_dir}")

    print()
    print(f"📦 Deployed {len(deployed_files)} files")

    return len(deployed_files) > 0


def create_deployment_package():
    """Create a deployment package with all command files."""
    print("📦 Creating Deployment Package")
    print("=" * 50)

    import zipfile
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package_name = f"bot_commands_deploy_{timestamp}.zip"

    files_to_include = [
        "bot/commands_config.json",
        "bot/command_manager.py",
        "tools/update_commands.py",
        "tools/server_commands_api.py",
        "tools/deploy_commands.py"
    ]

    try:
        with zipfile.ZipFile(package_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in files_to_include:
                full_path = project_root / file_path
                if full_path.exists():
                    zipf.write(full_path, file_path)
                    print(f"✅ Added: {file_path}")

        print()
        print(f"📦 Deployment package created: {package_name}")
        print(f"   Size: {os.path.getsize(package_name):,} bytes")

        return package_name

    except Exception as e:
        print(f"❌ Error creating deployment package: {e}")
        return None


async def main():
    """Main deployment function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Deploy bot commands to server and Telegram",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Deployment Targets:
  telegram    - Deploy commands to Telegram bot
  config      - Deploy configuration files
  server      - Deploy command files to server directories
  package     - Create deployment package
  all         - Deploy to all targets
        """
    )

    parser.add_argument(
        'target',
        choices=['telegram', 'config', 'server', 'package', 'all'],
        help='Deployment target'
    )

    parser.add_argument(
        '--config-file',
        help='Configuration file to deploy (for config target)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deployed without making changes'
    )

    args = parser.parse_args()

    print("🚀 Bot Commands Deployment Tool")
    print("=" * 50)
    print(f"Target: {args.target}")
    print(f"Dry Run: {args.dry_run}")
    if args.config_file:
        print(f"Config File: {args.config_file}")
    print()

    success_count = 0
    total_attempts = 0

    if args.target in ['telegram', 'all']:
        total_attempts += 1
        if not args.dry_run:
            print("🔵 Deploying to Telegram...")
            if await deploy_commands_to_telegram():
                success_count += 1
        else:
            print("🔵 [DRY RUN] Would deploy to Telegram")
            success_count += 1

    if args.target in ['config', 'all']:
        total_attempts += 1
        if not args.dry_run:
            print("🔵 Deploying configuration...")
            if await deploy_commands_to_server(args.config_file):
                success_count += 1
        else:
            print("🔵 [DRY RUN] Would deploy configuration")
            success_count += 1

    if args.target in ['server', 'all']:
        total_attempts += 1
        if not args.dry_run:
            print("🔵 Deploying to server directories...")
            if deploy_commands_to_server_files():
                success_count += 1
        else:
            print("🔵 [DRY RUN] Would deploy to server directories")
            success_count += 1

    if args.target in ['package', 'all']:
        total_attempts += 1
        if not args.dry_run:
            print("🔵 Creating deployment package...")
            package = create_deployment_package()
            if package:
                success_count += 1
        else:
            print("🔵 [DRY RUN] Would create deployment package")
            success_count += 1

    # Summary
    print()
    print("📊 Deployment Summary")
    print("=" * 30)
    print(f"Successful: {success_count}/{total_attempts}")

    if success_count == total_attempts:
        print("✅ All deployments completed successfully!")
    elif success_count > 0:
        print("⚠️  Partial deployment completed")
    else:
        print("❌ All deployments failed")

    # Exit with appropriate code
    sys.exit(0 if success_count > 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())