#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Debug script for the parse_pasted_stats function.
"""

import os
import sys

# Add the current directory to the path so we can import primestats_adapter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import primestats_adapter

# Sample data with cycle information (using space-separated format from sample_data.txt)
sample_data = """Time Span Agent Name Agent Faction Date (yyyy-mm-dd) Time (hh:mm:ss) Level Lifetime AP Current AP Unique Portals Visited Unique Portals Drone Visited Furthest Drone Distance Portals Discovered XM Collected OPR Agreements Portal Scans Uploaded Uniques Scout Controlled Resonators Deployed Links Created Control Fields Created Mind Units Captured Longest Link Ever Created Largest Control Field XM Recharged Portals Captured Unique Portals Captured Mods Deployed Hacks Drone Hacks Glyph Hack Points Completed Hackstreaks Longest Sojourner Streak Resonators Destroyed Portals Neutralized Enemy Links Destroyed Enemy Fields Destroyed Battle Beacon Combatant Drones Returned Machina Links Destroyed Machina Resonators Destroyed Machina Portals Neutralized Machina Portals Reclaimed Max Time Portal Held Max Time Link Maintained Max Link Length x Days Max Time Field Held Largest Field MUs x Days Forced Drone Recalls Distance Walked Kinetic Capsules Completed Unique Missions Completed Research Bounties Completed Research Days Completed Mission Day(s) Attended NL-1331 Meetup(s) Attended First Saturday Events Second Sunday Events +Delta Tokens +Delta Reso Points +Delta Field Points Agents Recruited Recursions Months Subscribed
ALL TIME TestAgent ENL 2023-11-01 12:34:56 16 100000000 50000000 100 200 300 400 500 600 700 800 900 1000 1100 1200 1300 1400 1500 1600 1700 1800 1900 2000 2100 2200 2300 2400 2500 2600 2700 2800 2900 3000 3100 3200 3300 3400 3500 3600 3700 3800 3900 4000 4100 4200 4300 4400 4500 4600 4700 4800 4900 5000 5100 5200 5300 5400 5500 5600 5700 5800 5900 6000 6100 6200 6300 6400 6500 6600 6700 6800 6900 7000 7100 7200 7300 7400 7500 7600 7700 7800 7900 8000 8100 8200 8300 8400 8500 8600 8700 8800 8900 9000 9100 9200 9300 9400 9500 9600 9700 9800 9900 10000 100 200 300 1 2 3"""

print("Parsing sample data...")
result = primestats_adapter.parse_pasted_stats(sample_data)

if result:
    print("Parsing successful!")
    print(f"Cycle name: {result.get('cycle_name')}")
    print(f"Cycle points: {result.get('cycle_points')}")
else:
    print("Parsing failed!")