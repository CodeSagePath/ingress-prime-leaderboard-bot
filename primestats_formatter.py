#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Primestats Formatter Module

This module formats parsed Ingress Prime stats into a Telegram-friendly string
in the same style as primestatsbot.
"""

def format_primestats(parsed: dict) -> str:
    """
    Format parsed stat values into a Telegram-friendly string in primestatsbot style.
    
    Args:
        parsed (dict): Dictionary of parsed stat values with keys like agent_name, 
                       level, lifetime_ap, hacks, glyph_hack_points, etc.
    
    Returns:
        str: Formatted string suitable for Telegram (text-only)
    """
    # Define the categories and their corresponding stat names
    categories = {
        "General": {
            "Time Span": "time_span",
            "Agent Name": "agent_name",
            "Agent Faction": "agent_faction",
            "Date (yyyy-mm-dd)": "date",
            "Time (hh:mm:ss)": "time",
            "Level": "level",
            "Lifetime AP": "lifetime_ap",
            "Current AP": "current_ap"
        },
        "Discovery": {
            "Unique Portals Visited": "unique_portals_visited",
            "Unique Portals Drone Visited": "unique_portals_drone_visited",
            "Furthest Drone Distance": "furthest_drone_distance",
            "Portals Discovered": "portals_discovered",
            "Seer Points": "seer_points",
            "XM Collected": "xm_collected",
            "OPR Agreements": "opr_agreements",
            "Portal Scans Uploaded": "portal_scans_uploaded",
            "Uniques Scout Controlled": "uniques_scout_controlled"
        },
        "Building": {
            "Resonators Deployed": "resonators_deployed",
            "Links Created": "links_created",
            "Control Fields Created": "control_fields_created",
            "Mind Units Captured": "mind_units_captured",
            "Longest Link Ever Created": "longest_link_ever_created",
            "Largest Control Field": "largest_control_field",
            "XM Recharged": "xm_recharged",
            "Portals Captured": "portals_captured",
            "Unique Portals Captured": "unique_portals_captured",
            "Mods Deployed": "mods_deployed",
            "Links Active": "links_active",
            "Portals Owned": "portals_owned",
            "Control Fields Active": "control_fields_active",
            "Mind Unit Control": "mind_unit_control"
        },
        "Resource Gathering": {
            "Hacks": "hacks",
            "Drone Hacks": "drone_hacks",
            "Glyph Hack Points": "glyph_hack_points"
        },
        "Streaks": {
            "Longest Hacking Streak": "longest_hacking_streak",
            "Current Hacking Streak": "current_hacking_streak",
            "Longest Sojourner Streak": "longest_sojourner_streak",
            "Completed Hackstreaks": "completed_hackstreaks"
        },
        "Combat": {
            "Resonators Destroyed": "resonators_destroyed",
            "Portals Neutralized": "portals_neutralized",
            "Enemy Links Destroyed": "enemy_links_destroyed",
            "Enemy Fields Destroyed": "enemy_fields_destroyed",
            "Battle Beacon Combatant": "battle_beacon_combatant",
            "Drones Returned": "drones_returned"
        },
        "Defense": {
            "Max Time Portal Held": "max_time_portal_held",
            "Max Time Link Maintained": "max_time_link_maintained",
            "Max Link Length x Days": "max_link_length_x_days",
            "Max Time Field Held": "max_time_field_held",
            "Largest Field MUs x Days": "largest_field_mus_x_days",
            "Forced Drone Recalls": "forced_drone_recalls"
        },
        "Health": {
            "Distance Walked": "distance_walked",
            "Kinetic Capsules Completed": "kinetic_capsules_completed"
        },
        "Missions": {
            "Unique Missions Completed": "unique_missions_completed"
        },
        "Events": {
            "Mission Day(s) Attended": "mission_days_attended",
            "NL-1331 Meetup(s) Attended": "nl1331_meetups_attended",
            "First Saturday Events": "first_saturday_events",
            "Second Sunday Events": "second_sunday_events",
            "Clear Fields Events": "clear_fields_events",
            "OPR Live Events": "opr_live_events",
            "Prime Challenges": "prime_challenges",
            "Intel Ops Missions": "intel_ops_missions",
            "Stealth Ops Missions": "stealth_ops_missions",
            "Didact Fields Created": "didact_fields_created",
            "EOS Points Earned": "eos_points_earned",
            "Solstice XM Recharged": "solstice_xm_recharged",
            "Kythera": "kythera"
        },
        "Mentoring": {
            "Agents Recruited": "agents_recruited"
        },
        "Recursion": {
            "Recursions": "recursions"
        },
        "Subscription": {
            "Months Subscribed": "months_subscribed"
        }
    }
    
    # Define units for each stat
    units = {
        "Lifetime AP": "AP",
        "Current AP": "AP",
        "Furthest Drone Distance": "km",
        "XM Collected": "XM",
        "Mind Units Captured": "MUs",
        "Longest Link Ever Created": "km",
        "Largest Control Field": "MUs",
        "Mind Unit Control": "MUs",
        "Longest Hacking Streak": "days",
        "Current Hacking Streak": "days",
        "Longest Sojourner Streak": "days",
        "Max Time Portal Held": "days",
        "Max Time Link Maintained": "days",
        "Max Link Length x Days": "km-days",
        "Max Time Field Held": "days",
        "Largest Field MUs x Days": "MU-days",
        "Distance Walked": "km",
        "Solstice XM Recharged": "XM"
    }
    
    # Initialize the result string
    result = ""
    
    # Process each category
    for category_name, stats in categories.items():
        category_stats = []
        
        # Process each stat in the category
        for display_name, key_name in stats.items():
            # Check if the stat exists in the parsed data
            if key_name in parsed and parsed[key_name] is not None:
                value = parsed[key_name]
                
                # Format numeric values with comma separators for thousands
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    try:
                        # Format as integer if it's a whole number, otherwise keep as float
                        if float(value).is_integer():
                            formatted_value = "{:,}".format(int(value))
                        else:
                            formatted_value = "{:,}".format(value)
                    except (ValueError, TypeError):
                        formatted_value = str(value)
                else:
                    formatted_value = str(value)
                
                # Get the unit for this stat if it exists
                unit = units.get(display_name, "")
                
                # Format the stat line
                if unit:
                    stat_line = f"{display_name}: {formatted_value} [{unit}]"
                else:
                    stat_line = f"{display_name}: {formatted_value}"
                
                category_stats.append(stat_line)
        
        # Add the category to the result if it has any stats
        if category_stats:
            # Add a blank line before each category (except the first one)
            if result:
                result += "\n\n"
            
            # Add the category header
            result += f"-- {category_name} --\n"
            
            # Add all stats in the category
            result += "\n".join(category_stats)
    
    return result