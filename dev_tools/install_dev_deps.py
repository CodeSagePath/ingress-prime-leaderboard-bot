#!/usr/bin/env python3
"""
Install development dependencies for Ingress Prime Leaderboard Bot
This script will install all required packages to resolve import warnings
"""

import subprocess
import sys
import os

def install_package(package):
    """Install a single package using pip."""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return True
    except subprocess.CalledProcessError:
        return False

def main():
    print("🔧 Installing development dependencies for Ingress Prime Leaderboard Bot")
    print("=" * 70)

    # Read requirements.txt
    requirements_path = os.path.join(os.path.dirname(__file__), "requirements.txt")

    if not os.path.exists(requirements_path):
        print("❌ requirements.txt not found!")
        return False

    print(f"📋 Reading dependencies from: {requirements_path}")

    with open(requirements_path, 'r') as f:
        requirements = []
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                requirements.append(line)

    print(f"📦 Found {len(requirements)} packages to install:")
    for req in requirements:
        print(f"   - {req}")

    print(f"\n🚀 Starting installation...")

    successful = []
    failed = []

    for package in requirements:
        package_name = package.split('==')[0].split('>=')[0]
        print(f"\n📦 Installing {package}...")

        if install_package(package):
            print(f"✅ {package} installed successfully")
            successful.append(package)
        else:
            print(f"❌ Failed to install {package}")
            failed.append(package)

    print(f"\n{'='*70}")
    print(f"📊 Installation Summary:")
    print(f"✅ Successfully installed: {len(successful)} packages")
    print(f"❌ Failed to install: {len(failed)} packages")

    if successful:
        print(f"\n✅ Installed packages:")
        for pkg in successful:
            print(f"   - {pkg}")

    if failed:
        print(f"\n❌ Failed packages:")
        for pkg in failed:
            print(f"   - {pkg}")
        print(f"\n💡 You may need to install these manually:")
        print(f"   - Use: pip install {' '.join(failed)}")
        print(f"   - Or check if you're using the correct Python environment")

    # Test specific imports that were mentioned in the warning
    print(f"\n🔍 Testing specific imports mentioned in warnings...")

    test_imports = [
        ('apscheduler.schedulers.asyncio', 'APScheduler'),
        ('redis', 'Redis'),
        ('rq', 'Redis Queue'),
        ('sqlalchemy', 'SQLAlchemy'),
        ('telegram', 'Python Telegram Bot'),
        ('uvicorn', 'Uvicorn ASGI Server'),
        ('dotenv', 'Python-dotenv')
    ]

    print(f"\n🧪 Import Test Results:")
    print("-" * 40)

    for module, description in test_imports:
        try:
            __import__(module)
            print(f"✅ {module} - {description}")
        except ImportError:
            print(f"❌ {module} - {description} (still missing)")

    return len(failed) == 0

if __name__ == "__main__":
    success = main()
    if not success:
        print(f"\n⚠️  Some packages failed to install. Import warnings may persist.")
    else:
        print(f"\n🎉 All packages installed successfully! Import warnings should be resolved.")

    sys.exit(0 if success else 1)