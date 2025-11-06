#!/usr/bin/env python3

# Simple test to verify column counts
def test_column_counts():
    # Define the format tuples directly
    format_60 = (
        "Time Span", "Agent Name", "Agent Faction", "Date (yyyy-mm-dd)", "Time (hh:mm:ss)", "Level",
        "Lifetime AP", "Current AP", "Unique Portals Visited", "Unique Portals Drone Visited", "Furthest Drone Distance",
        "Portals Discovered", "XM Collected", "OPR Agreements", "Portal Scans Uploaded", "Uniques Scout Controlled",
        "Resonators Deployed", "Links Created", "Control Fields Created", "Mind Units Captured", "Longest Link Ever Created",
        "Largest Control Field", "XM Recharged", "Portals Captured", "Unique Portals Captured", "Mods Deployed", "Hacks",
        "Drone Hacks", "Glyph Hack Points", "Completed Hackstreaks", "Longest Sojourner Streak", "Resonators Destroyed",
        "Portals Neutralized", "Enemy Links Destroyed", "Enemy Fields Destroyed", "Battle Beacon Combatant", "Drones Returned",
        "Machina Links Destroyed", "Machina Resonators Destroyed", "Machina Portals Neutralized", "Machina Portals Reclaimed",
        "Max Time Portal Held", "Max Time Link Maintained", "Max Link Length x Days", "Max Time Field Held", "Largest Field MUs x Days",
        "Forced Drone Recalls", "Distance Walked", "Kinetic Capsules Completed", "Unique Missions Completed",
        "Research Bounties Completed", "Research Days Completed", "First Saturday Events", "Second Sunday Events",
        "OPR Live Events", "+Delta Tokens", "+Delta Reso Points", "+Delta Field Points", "Recursions", "Months Subscribed"
    )

    format_57 = (
        "Time Span", "Agent Name", "Agent Faction", "Date (yyyy-mm-dd)", "Time (hh:mm:ss)", "Level",
        "Lifetime AP", "Current AP", "Unique Portals Visited", "Unique Portals Drone Visited", "Furthest Drone Distance",
        "Portals Discovered", "XM Collected", "OPR Agreements", "Portal Scans Uploaded", "Uniques Scout Controlled",
        "Resonators Deployed", "Links Created", "Control Fields Created", "Mind Units Captured", "Longest Link Ever Created",
        "Largest Control Field", "XM Recharged", "Portals Captured", "Unique Portals Captured", "Mods Deployed", "Hacks",
        "Drone Hacks", "Glyph Hack Points", "Completed Hackstreaks", "Longest Sojourner Streak", "Resonators Destroyed",
        "Portals Neutralized", "Enemy Links Destroyed", "Enemy Fields Destroyed", "Battle Beacon Combatant", "Drones Returned",
        "Machina Links Destroyed", "Machina Resonators Destroyed", "Machina Portals Neutralized", "Machina Portals Reclaimed",
        "Max Time Portal Held", "Max Time Link Maintained", "Max Link Length x Days", "Max Time Field Held", "Largest Field MUs x Days",
        "Forced Drone Recalls", "Distance Walked", "Kinetic Capsules Completed", "Unique Missions Completed",
        "Research Bounties Completed", "Research Days Completed", "First Saturday Events", "Second Sunday Events",
        "OPR Live Events", "+Beta Tokens", "Recursions"
    )

    format_58 = (
        "Time Span", "Agent Name", "Agent Faction", "Date (yyyy-mm-dd)", "Time (hh:mm:ss)", "Level",
        "Lifetime AP", "Current AP", "Unique Portals Visited", "Unique Portals Drone Visited", "Furthest Drone Distance",
        "Portals Discovered", "XM Collected", "OPR Agreements", "Portal Scans Uploaded", "Uniques Scout Controlled",
        "Resonators Deployed", "Links Created", "Control Fields Created", "Mind Units Captured", "Longest Link Ever Created",
        "Largest Control Field", "XM Recharged", "Portals Captured", "Unique Portals Captured", "Mods Deployed", "Hacks",
        "Drone Hacks", "Glyph Hack Points", "Completed Hackstreaks", "Longest Sojourner Streak", "Resonators Destroyed",
        "Portals Neutralized", "Enemy Links Destroyed", "Enemy Fields Destroyed", "Battle Beacon Combatant", "Drones Returned",
        "Machina Links Destroyed", "Machina Resonators Destroyed", "Machina Portals Neutralized", "Machina Portals Reclaimed",
        "Max Time Portal Held", "Max Time Link Maintained", "Max Link Length x Days", "Max Time Field Held", "Largest Field MUs x Days",
        "Forced Drone Recalls", "Distance Walked", "Kinetic Capsules Completed", "Unique Missions Completed",
        "Research Bounties Completed", "Research Days Completed", "NL-1331 Meetup(s) Attended", "First Saturday Events",
        "Second Sunday Events", "OPR Live Events", "+Beta Tokens", "Recursions"
    )

    # New 59-column format
    format_59 = (
        "Time Span", "Agent Name", "Agent Faction", "Date (yyyy-mm-dd)", "Time (hh:mm:ss)", "Level",
        "Lifetime AP", "Current AP", "Unique Portals Visited", "Unique Portals Drone Visited", "Furthest Drone Distance",
        "Portals Discovered", "XM Collected", "OPR Agreements", "Portal Scans Uploaded", "Uniques Scout Controlled",
        "Resonators Deployed", "Links Created", "Control Fields Created", "Mind Units Captured", "Longest Link Ever Created",
        "Largest Control Field", "XM Recharged", "Portals Captured", "Unique Portals Captured", "Mods Deployed", "Hacks",
        "Drone Hacks", "Glyph Hack Points", "Completed Hackstreaks", "Longest Sojourner Streak", "Resonators Destroyed",
        "Portals Neutralized", "Enemy Links Destroyed", "Enemy Fields Destroyed", "Battle Beacon Combatant", "Drones Returned",
        "Machina Links Destroyed", "Machina Resonators Destroyed", "Machina Portals Neutralized", "Machina Portals Reclaimed",
        "Max Time Portal Held", "Max Time Link Maintained", "Max Link Length x Days", "Max Time Field Held", "Largest Field MUs x Days",
        "Forced Drone Recalls", "Distance Walked", "Kinetic Capsules Completed", "Unique Missions Completed",
        "Research Bounties Completed", "Research Days Completed", "NL-1331 Meetup(s) Attended", "First Saturday Events",
        "Second Sunday Events", "OPR Live Events", "+Beta Tokens", "Recursions", "Months Subscribed"
    )

    # User's submission data
    user_submission = "ALL TIME 9saw Enlighted 2025-11-03 17:29:06 16 170494447 47877734 2541 91 1 37 755156240 5391 2 1 136602 19411 13524 2527938523 752 64044768 527989119 18190 2094 16564 146843 1825 1026082 100 579 86831 17101 16190 10632 4 7 2506 22018 2548 1041 351 252 10797 206 36462476 6 3153 473 47 1689 192 2 26 3 1 970 3"
    user_tokens = user_submission.split()

    print("Column format analysis:")
    print(f"Format 0 (60 columns): {len(format_60)}")
    print(f"Format 1 (57 columns): {len(format_57)}")
    print(f"Format 2 (58 columns): {len(format_58)}")
    print(f"Format 3 (59 columns): {len(format_59)}")
    print(f"User submission: {len(user_tokens)}")

    # Check if user tokens match the 59-column format
    if len(user_tokens) == len(format_59):
        print("✅ User submission matches the new 59-column format!")

        # Map first few tokens to verify
        print("\nFirst 10 field mappings:")
        for i in range(min(10, len(format_59))):
            if i < len(user_tokens):
                print(f"  {format_59[i]}: {user_tokens[i]}")

        return True
    else:
        print("❌ User submission doesn't match any format")
        return False

if __name__ == "__main__":
    success = test_column_counts()
    if success:
        print("\n🎉 Fix should work!")
    else:
        print("\n❌ Fix needs adjustment")