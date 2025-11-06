#!/usr/bin/env python3
"""
Import Analysis Report for Ingress Prime Leaderboard Bot
Shows current import state and identifies any remaining issues
"""

import re
import sys
import os

def analyze_imports(file_path):
    """Analyze imports in the given file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        imports = []

        for i, line in enumerate(lines, 1):
            line = line.strip()
            if line.startswith('import ') or line.startswith('from '):
                imports.append((i, line))

        return imports
    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        return []

def main():
    print("🔍 Ingress Prime Leaderboard Bot - Import Analysis")
    print("=" * 60)

    # Add current directory to path for relative imports
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    # Analyze main.py imports
    print(f"\n📋 Analyzing imports in bot/main.py...")

    file_path = os.path.join(current_dir, 'bot', 'main.py')
    imports = analyze_imports(file_path)

    if not imports:
        print("❌ No imports found or file not accessible")
        return

    print(f"✅ Found {len(imports)} import statements")

    # Categorize imports
    categories = {
        'Core Python': [],
        'Third Party': [],
        'Local/Project': []
    }

    for line_num, import_stmt in imports:
        if import_stmt.startswith('from .') or import_stmt.startswith('from bot'):
            categories['Local/Project'].append((line_num, import_stmt))
        elif any(lib in import_stmt for lib in ['apscheduler', 'sqlalchemy', 'telegram', 'redis', 'rq', 'dotenv', 'uvicorn']):
            categories['Third Party'].append((line_num, import_stmt))
        else:
            categories['Core Python'].append((line_num, import_stmt))

    # Display results
    for category, items in categories.items():
        if items:
            print(f"\n📦 {category}:")
            for line_num, import_stmt in items:
                print(f"   {line_num:4d}: {import_stmt}")

    # Check for specific issues that were mentioned
    print(f"\n🔍 Specific Import Issues - Status:")
    print("=" * 40)

    issues = {
        'SQLAlchemy case import': any('case' in stmt[1] for stmt in imports if 'sqlalchemy' in stmt[1]),
        'APScheduler async import': any('apscheduler.schedulers.asyncio' in stmt[1] for stmt in imports),
        'Duplicate asyncio import': len([stmt for stmt in imports if stmt[1] == 'import asyncio']) <= 1,
        'Unused imports removed': not any(stmt[1] in ['import json', 'from pathlib import Path'] for stmt in imports)
    }

    for issue, status in issues.items():
        status_icon = "✅" if status else "❌"
        print(f"   {status_icon} {issue}")

    # Summary
    print(f"\n📊 Summary:")
    print(f"   - Total imports: {len(imports)}")
    print(f"   - Core Python: {len(categories['Core Python'])}")
    print(f"   - Third Party: {len(categories['Third Party'])}")
    print(f"   - Local/Project: {len(categories['Local/Project'])}")

    all_good = all(issues.values())
    if all_good:
        print(f"\n🎉 All import issues have been resolved!")
        print(f"📋 The bot should run without Pylance import warnings.")
    else:
        print(f"\n⚠️  Some import issues may still exist.")

    return all_good

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)