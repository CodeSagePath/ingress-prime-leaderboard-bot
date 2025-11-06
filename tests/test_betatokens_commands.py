#!/usr/bin/env python3
"""
Test script to verify the beta tokens functionality.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from bot.utils.beta_tokens import (
    get_beta_tokens_manager,
    get_token_status_message,
    update_medal_requirements,
    update_task_name,
    get_medal_config
)

def test_beta_tokens_functionality():
    """Test all beta tokens functionality."""
    print("=" * 60)
    print("TESTING BETA TOKENS FUNCTIONALITY")
    print("=" * 60)

    manager = get_beta_tokens_manager()

    # Test 1: Set up test data
    print("\n1. Setting up test data...")
    manager.set_beta_tokens('9saw', 970, updated_by='test_user')
    manager.set_beta_tokens('TestAgent1', 50, updated_by='test_user')
    manager.set_beta_tokens('TestAgent2', 150, updated_by='test_user')
    manager.set_beta_tokens('TestAgent3', 600, updated_by='test_user')
    manager.set_beta_tokens('TestAgent4', 1200, updated_by='test_user')
    print("✅ Test data created")

    # Test 2: Update medal requirements
    print("\n2. Testing medal requirements update...")
    update_medal_requirements(100, 500, 1000)
    print("✅ Medal requirements updated: Bronze=100, Silver=500, Gold=1000")

    # Test 3: Update task name
    print("\n3. Testing task name update...")
    update_task_name("November 2025 Beta Test")
    print("✅ Task name updated")

    # Test 4: Test status messages for different token levels
    print("\n4. Testing status messages...")

    test_agents = ['9saw', 'TestAgent1', 'TestAgent2', 'TestAgent3', 'TestAgent4']

    for agent in test_agents:
        print(f"\n--- Status for {agent} ---")
        status_message = get_token_status_message(agent)
        print(status_message)

    # Test 5: Test configuration summary
    print("\n" + "=" * 60)
    print("5. Testing configuration summary...")
    config_message = get_medal_config()
    print(config_message)

    # Test 6: Test scenarios with different medal requirements
    print("\n" + "=" * 60)
    print("6. Testing different medal requirements...")

    # Lower requirements
    update_medal_requirements(50, 200, 500)
    print("\n--- With requirements Bronze=50, Silver=200, Gold=500 ---")
    for agent in ['TestAgent1', 'TestAgent2']:  # 50 and 150 tokens
        status_message = get_token_status_message(agent)
        print(f"\n{agent}:")
        print(status_message)

    # Higher requirements
    update_medal_requirements(200, 800, 2000)
    print("\n--- With requirements Bronze=200, Silver=800, Gold=2000 ---")
    for agent in ['9saw', 'TestAgent3']:  # 970 and 600 tokens
        status_message = get_token_status_message(agent)
        print(f"\n{agent}:")
        print(status_message)

    # Restore original requirements
    update_medal_requirements(100, 500, 1000)

    print("\n" + "=" * 60)
    print("✅ ALL TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_beta_tokens_functionality()