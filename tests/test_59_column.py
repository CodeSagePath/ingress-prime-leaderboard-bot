#!/usr/bin/env python3

# Test script to verify the 59-column format fix
import sys
import os
sys.path.append('/home/codesagepath/Documents/TGBot/ingress_leaderboard/ingress-prime-leaderboard-bot')

from bot.main import _parse_space_separated_dataset, SPACE_SEPARATED_COLUMN_SETS

def test_59_column_format():
    # User's submission data (59 tokens)
    user_data = """ALL TIME 9saw Enlighted 2025-11-03 17:29:06 16 170494447 47877734 2541 91 1 37 755156240 5391 2 1 136602 19411 13524 2527938523 752 64044768 527989119 18190 2094 16564 146843 1825 1026082 100 579 86831 17101 16190 10632 4 7 2506 22018 2548 1041 351 252 10797 206 36462476 6 3153 473 47 1689 192 2 26 3 1 970 3"""

    # Expected header for the new 59-column format
    expected_header = " ".join(SPACE_SEPARATED_COLUMN_SETS[3])  # Index 3 for the new format

    print(f"Number of column sets: {len(SPACE_SEPARATED_COLUMN_SETS)}")
    for i, columns in enumerate(SPACE_SEPARATED_COLUMN_SETS):
        print(f"Format {i}: {len(columns)} columns")

    print(f"\nExpected header (59 columns):")
    print(expected_header)
    print(f"Length: {len(expected_header.split())}")

    # Test parsing
    lines = [expected_header, user_data]
    try:
        result = _parse_space_separated_dataset(lines)
        print(f"\n✅ Parsing successful!")
        print(f"Parsed {len(result)} fields")
        key_fields = ['Agent Name', 'Agent Faction', 'Date (yyyy-mm-dd)', 'Time (hh:mm:ss)', 'Level']
        for field in key_fields:
            if field in result:
                print(f"  {field}: {result[field]}")
    except Exception as e:
        print(f"\n❌ Parsing failed: {e}")
        return False

    return True

if __name__ == "__main__":
    success = test_59_column_format()
    sys.exit(0 if success else 1)