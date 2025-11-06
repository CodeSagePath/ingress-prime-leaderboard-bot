#!/usr/bin/env python3
"""
Test script to verify the parsing of the 59-column data format.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from primestats_adapter import parse_pasted_stats
from bot.utils.beta_tokens import get_beta_tokens_manager

# Sample data in the exact format provided (raw format without commas)
sample_data = "ALL TIME 9saw Enlightened 2025-11-03 17:29:06 16 170494447 47877734 2541 91 1 37 755156240 5391 2 1 136602 19411 13524 2527938523 752 64044768 527989119 18190 2094 16564 146843 1825 1026082 100 579 86831 17101 16190 10632 4 7 2506 22018 2548 1041 351 252 10797 206 36462476 6 3153 473 47 1689 192 2 26 3 1 970 3"

def test_parsing():
    """Test parsing of the sample data."""
    print("Testing 59-column data format parsing...")
    print(f"Sample data: {sample_data}")
    print(f"Number of tokens: {len(sample_data.split())}")
    print()

    results = parse_pasted_stats(sample_data)
    result = results[0] if results else None

    if result is None:
        print("❌ Parsing failed - returned None")
        return False

    print("✅ Parsing successful!")
    print(f"Agent: {result.get('agent_name', 'N/A')}")
    print(f"Faction: {result.get('agent_faction', 'N/A')}")
    print(f"Time span: {result.get('time_span', 'N/A')}")
    print(f"Date: {result.get('date', 'N/A')}")
    print(f"Time: {result.get('time', 'N/A')}")
    print(f"Level: {result.get('level', 'N/A')}")
    print(f"Lifetime AP: {result.get('lifetime_ap', 'N/A')}")
    print(f"Current AP: {result.get('current_ap', 'N/A')}")
    print(f"Beta Tokens: {result.get('beta_tokens', 'N/A')}")
    print()

    # Count metrics
    metrics_count = len([k for k in result.keys() if k not in [
        'agent_name', 'agent_faction', 'time_span', 'date', 'time',
        'cycle_name', 'cycle_points'
    ]])
    print(f"Number of metrics parsed: {metrics_count}")

    # Show all keys
    print("\nParsed keys:")
    for key in sorted(result.keys()):
        print(f"  {key}: {result[key]}")

    return True

def test_beta_tokens():
    """Test beta tokens management."""
    print("\n" + "="*50)
    print("Testing Beta Tokens Management...")
    print("="*50)

    manager = get_beta_tokens_manager()

    # Test setting beta tokens
    print("\n1. Setting beta tokens for '9saw':")
    manager.set_beta_tokens('9saw', 970, updated_by='test_user')
    tokens = manager.get_beta_tokens('9saw')
    print(f"   Beta tokens for 9saw: {tokens}")

    # Test getting all agents
    print("\n2. Getting all agents with tokens:")
    all_agents = manager.get_agents_with_tokens()
    for agent, tokens in all_agents.items():
        print(f"   {agent}: {tokens}")

    # Test export to text
    print("\n3. Export data as text:")
    print(manager.export_to_text())

    return True

if __name__ == "__main__":
    success = test_parsing()
    if success:
        test_beta_tokens()
        print("\n✅ All tests completed successfully!")
    else:
        print("\n❌ Tests failed!")
        sys.exit(1)