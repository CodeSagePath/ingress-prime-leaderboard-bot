#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for the current cycle storage functionality.
"""

import os
import sys
import tempfile
import shutil

# Add the current directory to the path so we can import primestats_adapter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import primestats_adapter

def test_save_current_cycle():
    """Test the save_current_cycle function."""
    print("Testing save_current_cycle function...")
    
    # Test with a valid cycle name
    test_cycle_name = "Test Cycle 2023"
    result = primestats_adapter.save_current_cycle(test_cycle_name)
    
    if result:
        print("✓ Successfully saved cycle name")
        
        # Check if the file was created and contains the correct content
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "current_cycle.txt")
        
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read().strip()
            
            if content == test_cycle_name:
                print("✓ File contains the correct cycle name")
            else:
                print(f"✗ File contains incorrect content: {content}")
                return False
        else:
            print("✗ File was not created")
            return False
    else:
        print("✗ Failed to save cycle name")
        return False
    
    # Test with an empty cycle name
    result = primestats_adapter.save_current_cycle("")
    if not result:
        print("✓ Correctly rejected empty cycle name")
    else:
        print("✗ Incorrectly accepted empty cycle name")
        return False
    
    # Test with None
    result = primestats_adapter.save_current_cycle(None)
    if not result:
        print("✓ Correctly rejected None cycle name")
    else:
        print("✗ Incorrectly accepted None cycle name")
        return False
    
    # Test with whitespace-only
    result = primestats_adapter.save_current_cycle("   ")
    if not result:
        print("✓ Correctly rejected whitespace-only cycle name")
    else:
        print("✗ Incorrectly accepted whitespace-only cycle name")
        return False
    
    # Test overwriting with a new cycle name
    new_cycle_name = "New Test Cycle 2024"
    result = primestats_adapter.save_current_cycle(new_cycle_name)
    
    if result:
        print("✓ Successfully overwrote cycle name")
        
        # Check if the file contains the new content
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "current_cycle.txt")
        
        with open(file_path, 'r') as f:
            content = f.read().strip()
        
        if content == new_cycle_name:
            print("✓ File contains the new cycle name")
        else:
            print(f"✗ File contains incorrect content: {content}")
            return False
    else:
        print("✗ Failed to overwrite cycle name")
        return False
    
    print("All tests passed!")
    return True

def test_parse_pasted_stats_integration():
    """Test the integration of cycle storage with parse_pasted_stats function."""
    print("\nTesting integration with parse_pasted_stats function...")
    
    # Sample data with cycle information (using space-separated format from sample_data.txt)
    sample_data = """Time Span Agent Name Agent Faction Date (yyyy-mm-dd) Time (hh:mm:ss) Level Lifetime AP Current AP Unique Portals Visited Unique Portals Drone Visited Furthest Drone Distance Portals Discovered XM Collected OPR Agreements Portal Scans Uploaded Uniques Scout Controlled Resonators Deployed Links Created Control Fields Created Mind Units Captured Longest Link Ever Created Largest Control Field XM Recharged Portals Captured Unique Portals Captured Mods Deployed Hacks Drone Hacks Glyph Hack Points Completed Hackstreaks Longest Sojourner Streak Resonators Destroyed Portals Neutralized Enemy Links Destroyed Enemy Fields Destroyed Battle Beacon Combatant Drones Returned Machina Links Destroyed Machina Resonators Destroyed Machina Portals Neutralized Machina Portals Reclaimed Max Time Portal Held Max Time Link Maintained Max Link Length x Days Max Time Field Held Largest Field MUs x Days Forced Drone Recalls Distance Walked Kinetic Capsules Completed Unique Missions Completed Research Bounties Completed Research Days Completed Mission Day(s) Attended NL-1331 Meetup(s) Attended First Saturday Events Second Sunday Events +Delta Tokens +Delta Reso Points +Delta Field Points Agents Recruited Recursions Months Subscribed
ALL TIME TestAgent ENL 2023-11-01 12:34:56 16 100000000 50000000 100 200 300 400 500 600 700 800 900 1000 1100 1200 1300 1400 1500 1600 1700 1800 1900 2000 2100 2200 2300 2400 2500 2600 2700 2800 2900 3000 3100 3200 3300 3400 3500 3600 3700 3800 3900 4000 4100 4200 4300 4400 4500 4600 4700 4800 4900 5000 5100 5200 5300 5400 5500 5600 5700 5800 5900 6000 6100 6200 6300 6400 6500 6600 6700 6800 6900 7000 7100 7200 7300 7400 7500 7600 7700 7800 7900 8000 8100 8200 8300 8400 8500 8600 8700 8800 8900 9000 9100 9200 9300 9400 9500 9600 9700 9800 9900 10000 100 200 300 1 2 3"""
    
    # Parse the stats
    result = primestats_adapter.parse_pasted_stats(sample_data)
    
    if result and result.get("cycle_name") == "Delta Tokens":
        print("✓ Successfully extracted cycle name from stats")
        
        # Check if the file was created and contains the correct content
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "current_cycle.txt")
        
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read().strip()
            
            if content == "Delta Tokens":
                print("✓ File contains the correct cycle name from parsed stats")
                return True
            else:
                print(f"✗ File contains incorrect content: {content}")
                return False
        else:
            print("✗ File was not created")
            return False
    else:
        print("✗ Failed to extract cycle name from stats")
        return False

if __name__ == "__main__":
    print("Running tests for current cycle storage functionality...\n")
    
    success = True
    success &= test_save_current_cycle()
    success &= test_parse_pasted_stats_integration()
    
    if success:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed!")
        sys.exit(1)