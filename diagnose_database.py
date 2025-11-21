#!/usr/bin/env python3
"""
Database Diagnostics Script for Ingress Leaderboard Bot

This script helps diagnose the current database setup and test connection scenarios.
"""

import asyncio
import sys
import os
from pathlib import Path
import sqlite3
import subprocess
from urllib.parse import urlparse

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def diagnose_current_setup():
    """Diagnose the current database setup."""
    print("🔍 Diagnosing Current Database Setup")
    print("=" * 50)

    # Check current .env configuration
    env_path = project_root / ".env"
    if not env_path.exists():
        print("❌ .env file not found!")
        return

    print(f"✅ .env file found: {env_path}")

    # Read and parse DATABASE_URL
    with open(env_path, 'r') as f:
        for line in f:
            if line.startswith('DATABASE_URL='):
                db_url = line.split('=', 1)[1].strip()
                print(f"📊 Current DATABASE_URL: {db_url}")

                # Parse the URL
                parsed = urlparse(db_url)
                print(f"🔧 Database Type: {parsed.scheme}")

                if parsed.scheme.startswith('sqlite'):
                    # Check if SQLite file exists
                    db_path = parsed.path.lstrip('/')
                    full_path = project_root / db_path
                    if full_path.exists():
                        print(f"✅ SQLite file exists: {full_path}")
                        # Check file size
                        size = full_path.stat().st_size
                        if size < 1024:  # Less than 1KB
                            print("⚠️  Database file is very small (likely empty)")
                        else:
                            print(f"✅ Database file size: {size:,} bytes")

                        # Check if tables exist
                        try:
                            conn = sqlite3.connect(str(full_path))
                            cursor = conn.cursor()
                            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                            tables = cursor.fetchall()
                            if tables:
                                print(f"📋 Tables found: {[t[0] for t in tables]}")

                                # Check agent count
                                cursor.execute("SELECT COUNT(*) FROM agents")
                                agent_count = cursor.fetchone()[0]
                                print(f"👥 Agents in database: {agent_count}")

                                # Check submission count
                                cursor.execute("SELECT COUNT(*) FROM submissions")
                                submission_count = cursor.fetchone()[0]
                                print(f"📈 Submissions in database: {submission_count}")

                            else:
                                print("❌ No tables found in database")
                            conn.close()
                        except Exception as e:
                            print(f"❌ Error reading database: {e}")
                    else:
                        print(f"❌ SQLite file does not exist: {full_path}")

                elif parsed.scheme in ('postgresql', 'mysql'):
                    print(f"🌐 Remote database detected")
                    print(f"🖥️  Host: {parsed.hostname}")
                    print(f"🔌 Port: {parsed.port}")
                    print(f"📁 Database: {parsed.path[1:]}")
                    print(f"👤 Username: {parsed.username}")

                break
        else:
            print("❌ DATABASE_URL not found in .env file!")

async def test_server_connectivity(server_ip):
    """Test connectivity to Ubuntu server."""
    print(f"\n🌐 Testing Connectivity to {server_ip}")
    print("=" * 50)

    # Test ping
    try:
        result = subprocess.run(['ping', '-c', '3', server_ip],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Server is reachable via ping")
        else:
            print("❌ Server is not reachable via ping")
            print(result.stderr)
    except subprocess.TimeoutExpired:
        print("❌ Ping timeout - server not reachable")
    except Exception as e:
        print(f"❌ Ping failed: {e}")

    # Test common database ports
    common_ports = {
        5432: "PostgreSQL",
        3306: "MySQL/MariaDB",
        6379: "Redis",
        27017: "MongoDB"
    }

    print("\n🔌 Testing Database Ports:")
    for port, service in common_ports.items():
        try:
            # Use nc (netcat) to test port connectivity
            result = subprocess.run(['nc', '-z', '-w3', server_ip, str(port)],
                                  capture_output=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ Port {port} ({service}) is open")
            else:
                print(f"❌ Port {port} ({service}) is closed")
        except FileNotFoundError:
            print(f"⚠️  nc (netcat) not available, skipping port test")
            break
        except Exception as e:
            print(f"❌ Error testing port {port}: {e}")

async def suggest_connection_scenarios(server_ip):
    """Suggest different connection scenarios."""
    print(f"\n💡 Suggested Connection Scenarios for {server_ip}")
    print("=" * 50)

    scenarios = [
        {
            "name": "PostgreSQL on Ubuntu Server",
            "env_var": f"DATABASE_URL=postgresql://username:password@{server_ip}:5432/ingress_bot",
            "description": "If you have PostgreSQL running on your server"
        },
        {
            "name": "MySQL on Ubuntu Server",
            "env_var": f"DATABASE_URL=mysql+pymysql://username:password@{server_ip}:3306/ingress_bot",
            "description": "If you have MySQL/MariaDB running on your server"
        },
        {
            "name": "SQLite File Transfer",
            "env_var": "DATABASE_URL=sqlite+aiosqlite:///./data/server_bot.db",
            "description": "Copy SQLite file from server to local machine"
        },
        {
            "name": "SSH Tunnel to PostgreSQL",
            "env_var": "DATABASE_URL=postgresql://username:password@localhost:5432/ingress_bot",
            "description": "Secure tunnel to remote PostgreSQL (requires SSH setup)"
        }
    ]

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{i}. {scenario['name']}")
        print(f"   Description: {scenario['description']}")
        print(f"   Update .env with: {scenario['env_var']}")

async def main():
    """Main diagnostic function."""
    print("🤖 Ingress Leaderboard Bot Database Diagnostics")
    print("=" * 60)

    # Diagnose current setup
    await diagnose_current_setup()

    # Ask for server IP
    server_ip = input("\n🔢 Enter your Ubuntu server IP address: ").strip()

    if server_ip:
        # Test connectivity
        await test_server_connectivity(server_ip)

        # Suggest scenarios
        await suggest_connection_scenarios(server_ip)

        print(f"\n📋 Next Steps:")
        print(f"1. Choose a connection scenario from above")
        print(f"2. Update your .env file with the new DATABASE_URL")
        print(f"3. Test the connection with: python test_connection.py")
        print(f"4. Restart your bot with: python main.py")

    else:
        print("\n❌ Server IP required for connectivity testing")

    print(f"\n📖 For detailed setup instructions, see: DATABASE_CONNECTION_GUIDE.md")

if __name__ == "__main__":
    asyncio.run(main())