#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Primestats Adapter Module

This module processes Ingress Prime stat text and converts it into a structured format
compatible with the leaderboard bot's data models and display formatter.
"""

import os
import re
from typing import Dict, List, Optional, Tuple


def save_current_cycle(cycle_name: str) -> bool:
    """
    Save the current cycle name to a file named "current_cycle.txt".
    
    Args:
        cycle_name (str): The cycle name to save
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not cycle_name or not cycle_name.strip():
        return False
        
    try:
        # Get the directory of the current script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "current_cycle.txt")
        
        # Write the cycle name to the file, overwriting any existing content
        with open(file_path, 'w') as f:
            f.write(cycle_name.strip())
            
        return True
    except (IOError, OSError, PermissionError) as e:
        print(f"Error saving current cycle to file: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error saving current cycle: {e}")
        return False


def parse_pasted_stats(text: str) -> Optional[Dict]:
    """
    Parse raw stat text from Ingress Prime export.
    
    Args:
        text (str): Raw stat text from Ingress Prime export
    
    Returns:
        Optional[Dict]: Parsed statistics as a dictionary, or None if parsing failed
    """
    try:
        # Check if input text is empty or None
        if not text or not text.strip():
            print("Error: Input text is empty or None")
            return None
            
        # Split the text into lines
        lines = text.strip().split('\n')
        
        # Check if we have at least 2 lines (header and data)
        if len(lines) < 2:
            print("Error: Input doesn't contain at least 2 lines (header and data)")
            return None
        
        # Extract header and data lines
        header_line = lines[0].strip()
        data_line = lines[1].strip()
        
        # Check if header or data line is empty
        if not header_line or not data_line:
            print("Error: Header or data line is empty")
            return None
        
        # Try the space-separated approach first (based on sample data format)
        result = _parse_space_separated(header_line, data_line)
        if result and _validate_critical_fields(result):
            # Save the cycle name to file if it was extracted
            if result.get("cycle_name"):
                save_current_cycle(result["cycle_name"])
            return result
            
        # If space-separated approach fails, try the fixed-width column approach
        result = _parse_with_fixed_columns(header_line, data_line)
        if result and _validate_critical_fields(result):
            # Save the cycle name to file if it was extracted
            if result.get("cycle_name"):
                save_current_cycle(result["cycle_name"])
            return result
            
        # If fixed-width approach fails, try the dynamic column position approach
        column_positions = _parse_header_columns(header_line)
        if not column_positions:
            print("Error: Failed to parse header columns")
            return None
            
        # Parse the data line using the column positions
        result = _parse_data_columns(data_line, column_positions)
        if not result:
            print("Error: Failed to parse data columns")
            return None
            
        # Validate critical fields
        if not _validate_critical_fields(result):
            print("Error: Critical fields validation failed")
            return None
            
        # Save the cycle name to file if it was extracted
        if result.get("cycle_name"):
            save_current_cycle(result["cycle_name"])
            
        return result
    except Exception as e:
        print(f"Error parsing stats: {e}")
        return None


def _parse_header_columns(header_line: str) -> Optional[Dict[str, Tuple[int, int]]]:
    """
    Parse the header line to identify column positions.
    
    Args:
        header_line (str): The header line from Ingress Prime export
        
    Returns:
        Optional[Dict[str, Tuple[int, int]]]: Dictionary mapping column names to (start, end) positions
    """
    try:
        # Check if header_line is empty
        if not header_line or not header_line.strip():
            print("Error: Header line is empty")
            return None
            
        # Define the expected column headers in order
        expected_columns = [
            "Time Span",
            "Agent Name",
            "Agent Faction",
            "Date (yyyy-mm-dd)",
            "Time (hh:mm:ss)",
            "Level",
            "Lifetime AP",
            "Current AP",
            "Unique Portals Visited",
            "Unique Portals Drone Visited",
            "Furthest Drone Distance",
            "Portals Discovered",
            "XM Collected",
            "OPR Agreements",
            "Portal Scans Uploaded",
            "Uniques Scout Controlled",
            "Resonators Deployed",
            "Links Created",
            "Control Fields Created",
            "Mind Units Captured",
            "Longest Link Ever Created",
            "Largest Control Field",
            "XM Recharged",
            "Portals Captured",
            "Unique Portals Captured",
            "Mods Deployed",
            "Hacks",
            "Drone Hacks",
            "Glyph Hack Points",
            "Completed Hackstreaks",
            "Longest Sojourner Streak",
            "Resonators Destroyed",
            "Portals Neutralized",
            "Enemy Links Destroyed",
            "Enemy Fields Destroyed",
            "Battle Beacon Combatant",
            "Drones Returned",
            "Machina Links Destroyed",
            "Machina Resonators Destroyed",
            "Machina Portals Neutralized",
            "Machina Portals Reclaimed",
            "Max Time Portal Held",
            "Max Time Link Maintained",
            "Max Link Length x Days",
            "Max Time Field Held",
            "Largest Field MUs x Days",
            "Forced Drone Recalls",
            "Distance Walked",
            "Kinetic Capsules Completed",
            "Unique Missions Completed",
            "Research Bounties Completed",
            "Research Days Completed",
            "Mission Day(s) Attended",
            "NL-1331 Meetup(s) Attended",
            "First Saturday Events",
            "Second Sunday Events",
            "+Delta Tokens",
            "+Delta Reso Points",
            "+Delta Field Points",
            "Agents Recruited",
            "Recursions",
            "Months Subscribed"
        ]
        
        # Create a mapping from our internal field names to the header names
        field_to_header = {
            "time_span": "Time Span",
            "agent_name": "Agent Name",
            "agent_faction": "Agent Faction",
            "date": "Date (yyyy-mm-dd)",
            "time": "Time (hh:mm:ss)",
            "level": "Level",
            "lifetime_ap": "Lifetime AP",
            "current_ap": "Current AP",
            "unique_portals_visited": "Unique Portals Visited",
            "unique_portals_drone_visited": "Unique Portals Drone Visited",
            "furthest_drone_distance": "Furthest Drone Distance",
            "portals_discovered": "Portals Discovered",
            "xm_collected": "XM Collected",
            "opr_agreements": "OPR Agreements",
            "portal_scans_uploaded": "Portal Scans Uploaded",
            "uniques_scout_controlled": "Uniques Scout Controlled",
            "resonators_deployed": "Resonators Deployed",
            "links_created": "Links Created",
            "control_fields_created": "Control Fields Created",
            "mind_units_captured": "Mind Units Captured",
            "longest_link_ever_created": "Longest Link Ever Created",
            "largest_control_field": "Largest Control Field",
            "xm_recharged": "XM Recharged",
            "portals_captured": "Portals Captured",
            "unique_portals_captured": "Unique Portals Captured",
            "mods_deployed": "Mods Deployed",
            "hacks": "Hacks",
            "drone_hacks": "Drone Hacks",
            "glyph_hack_points": "Glyph Hack Points",
            "completed_hackstreaks": "Completed Hackstreaks",
            "longest_sojourner_streak": "Longest Sojourner Streak",
            "resonators_destroyed": "Resonators Destroyed",
            "portals_neutralized": "Portals Neutralized",
            "enemy_links_destroyed": "Enemy Links Destroyed",
            "enemy_fields_destroyed": "Enemy Fields Destroyed",
            "battle_beacon_combatant": "Battle Beacon Combatant",
            "drones_returned": "Drones Returned",
            "machina_links_destroyed": "Machina Links Destroyed",
            "machina_resonators_destroyed": "Machina Resonators Destroyed",
            "machina_portals_neutralized": "Machina Portals Neutralized",
            "machina_portals_reclaimed": "Machina Portals Reclaimed",
            "max_time_portal_held": "Max Time Portal Held",
            "max_time_link_maintained": "Max Time Link Maintained",
            "max_link_length_x_days": "Max Link Length x Days",
            "max_time_field_held": "Max Time Field Held",
            "largest_field_mus_x_days": "Largest Field MUs x Days",
            "forced_drone_recalls": "Forced Drone Recalls",
            "distance_walked": "Distance Walked",
            "kinetic_capsules_completed": "Kinetic Capsules Completed",
            "unique_missions_completed": "Unique Missions Completed",
            "research_bounties_completed": "Research Bounties Completed",
            "research_days_completed": "Research Days Completed",
            "mission_days_attended": "Mission Day(s) Attended",
            "nl1331_meetups_attended": "NL-1331 Meetup(s) Attended",
            "first_saturday_events": "First Saturday Events",
            "second_sunday_events": "Second Sunday Events",
            "delta_tokens": "+Delta Tokens",
            "delta_reso_points": "+Delta Reso Points",
            "delta_field_points": "+Delta Field Points",
            "agents_recruited": "Agents Recruited",
            "recursions": "Recursions",
            "months_subscribed": "Months Subscribed"
        }
        
        # Find the positions of each column header
        column_positions = {}
        
        # For each expected column, find its position in the header line
        for field_name, header_name in field_to_header.items():
            try:
                pos = header_line.find(header_name)
                if pos != -1:
                    column_positions[field_name] = (pos, pos + len(header_name))
            except Exception as e:
                print(f"Error finding position for header '{header_name}': {e}")
                # Continue with next header instead of failing completely
                continue
        
        # Verify we found at least the minimum required columns
        MIN_REQUIRED_COLUMNS = 7
        required_fields = ["time_span", "agent_name", "agent_faction", "date", "time", "level", "lifetime_ap"]
        found_required = sum(1 for field in required_fields if field in column_positions)
        
        if found_required < MIN_REQUIRED_COLUMNS:
            print(f"Error: Only found {found_required} out of {MIN_REQUIRED_COLUMNS} required columns")
            return None
            
        return column_positions
    except Exception as e:
        print(f"Error parsing header columns: {e}")
        return None


def _parse_data_columns(data_line: str, column_positions: Dict[str, Tuple[int, int]]) -> Optional[Dict]:
    """
    Parse the data line using the column positions.
    
    Args:
        data_line (str): The data line from Ingress Prime export
        column_positions (Dict[str, Tuple[int, int]]): Dictionary mapping column names to (start, end) positions
        
    Returns:
        Optional[Dict]: Parsed statistics as a dictionary, or None if parsing failed
    """
    try:
        # Check if data_line is empty
        if not data_line or not data_line.strip():
            print("Error: Data line is empty")
            return None
            
        # Check if column_positions is empty
        if not column_positions:
            print("Error: Column positions dictionary is empty")
            return None
            
        # Create a dictionary with placeholder values for all expected fields
        result = {
            "time_span": None,
            "agent_name": None,
            "agent_faction": None,
            "date": None,
            "time": None,
            "level": None,
            "lifetime_ap": None,
            "current_ap": None,
            "unique_portals_visited": None,
            "unique_portals_drone_visited": None,
            "furthest_drone_distance": None,
            "portals_discovered": None,
            "xm_collected": None,
            "opr_agreements": None,
            "portal_scans_uploaded": None,
            "uniques_scout_controlled": None,
            "resonators_deployed": None,
            "links_created": None,
            "control_fields_created": None,
            "mind_units_captured": None,
            "longest_link_ever_created": None,
            "largest_control_field": None,
            "xm_recharged": None,
            "portals_captured": None,
            "unique_portals_captured": None,
            "mods_deployed": None,
            "hacks": None,
            "drone_hacks": None,
            "glyph_hack_points": None,
            "completed_hackstreaks": None,
            "longest_sojourner_streak": None,
            "resonators_destroyed": None,
            "portals_neutralized": None,
            "enemy_links_destroyed": None,
            "enemy_fields_destroyed": None,
            "battle_beacon_combatant": None,
            "drones_returned": None,
            "machina_links_destroyed": None,
            "machina_resonators_destroyed": None,
            "machina_portals_neutralized": None,
            "machina_portals_reclaimed": None,
            "max_time_portal_held": None,
            "max_time_link_maintained": None,
            "max_link_length_x_days": None,
            "max_time_field_held": None,
            "largest_field_mus_x_days": None,
            "forced_drone_recalls": None,
            "distance_walked": None,
            "kinetic_capsules_completed": None,
            "unique_missions_completed": None,
            "research_bounties_completed": None,
            "research_days_completed": None,
            "mission_days_attended": None,
            "nl1331_meetups_attended": None,
            "first_saturday_events": None,
            "second_sunday_events": None,
            "delta_tokens": None,
            "delta_reso_points": None,
            "delta_field_points": None,
            "agents_recruited": None,
            "recursions": None,
            "months_subscribed": None,
            "cycle_name": None,
            "cycle_points": None
        }
        
        # Sort columns by their start position
        sorted_columns = sorted(column_positions.items(), key=lambda x: x[1][0])
        
        # Extract values for each column
        for i, (field_name, (start_pos, end_pos)) in enumerate(sorted_columns):
            try:
                # Check if start_pos is within bounds of data_line
                if start_pos >= len(data_line):
                    print(f"Warning: Start position {start_pos} for field '{field_name}' is beyond data line length")
                    continue
                
                # Determine the end position for this column
                # If this is the last column, use the end of the line
                if i == len(sorted_columns) - 1:
                    value = data_line[start_pos:].strip()
                else:
                    next_start_pos = sorted_columns[i+1][1][0]
                    # Check if next_start_pos is within bounds of data_line
                    if next_start_pos > len(data_line):
                        value = data_line[start_pos:].strip()
                    else:
                        value = data_line[start_pos:next_start_pos].strip()
                
                # Skip empty values
                if not value:
                    continue
                    
                # Convert value to appropriate type based on field with specific handling for key fields
                if field_name == "time_span":
                    # Time Span is typically "ALL TIME" or a specific time period
                    result[field_name] = value.strip()
                elif field_name == "agent_name":
                    # Agent Name may contain spaces, ensure we capture the full name
                    result[field_name] = value.strip()
                elif field_name == "agent_faction":
                    # Normalize faction to standard format
                    result[field_name] = _normalize_faction(value.strip())
                elif field_name == "date":
                    # Date should be in yyyy-mm-dd format
                    date_str = value.strip()
                    # Basic validation for date format
                    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                        result[field_name] = date_str
                    else:
                        # Try to handle different date formats if needed
                        result[field_name] = date_str
                elif field_name == "time":
                    # Time should be in hh:mm:ss format
                    time_str = value.strip()
                    # Basic validation for time format
                    if re.match(r'^\d{2}:\d{2}:\d{2}$', time_str):
                        result[field_name] = time_str
                    else:
                        # Try to handle different time formats if needed
                        result[field_name] = time_str
                elif field_name == "level":
                    # Level should be an integer between 1 and 16
                    try:
                        level = int(value)
                        if 1 <= level <= 16:
                            result[field_name] = level
                        else:
                            print(f"Warning: Level {level} is out of range (1-16)")
                            result[field_name] = value  # Keep as string if out of range
                    except (ValueError, TypeError) as e:
                        print(f"Warning: Could not parse level '{value}': {e}")
                        result[field_name] = value
                elif field_name in ["lifetime_ap", "current_ap"]:
                    # AP values should be integers
                    try:
                        result[field_name] = int(value)
                    except (ValueError, TypeError) as e:
                        print(f"Warning: Could not parse AP value '{value}' for {field_name}: {e}")
                        result[field_name] = value
                elif field_name in ["unique_portals_visited", "unique_portals_drone_visited",
                                   "furthest_drone_distance", "portals_discovered", "xm_collected",
                                   "opr_agreements", "portal_scans_uploaded", "uniques_scout_controlled",
                                   "resonators_deployed", "links_created", "control_fields_created",
                                   "mind_units_captured", "longest_link_ever_created",
                                   "largest_control_field", "xm_recharged", "portals_captured",
                                   "unique_portals_captured", "mods_deployed", "hacks", "drone_hacks",
                                   "glyph_hack_points", "completed_hackstreaks", "longest_sojourner_streak",
                                   "resonators_destroyed", "portals_neutralized", "enemy_links_destroyed",
                                   "enemy_fields_destroyed", "battle_beacon_combatant", "drones_returned",
                                   "machina_links_destroyed", "machina_resonators_destroyed",
                                   "machina_portals_neutralized", "machina_portals_reclaimed",
                                   "max_time_portal_held", "max_time_link_maintained", "max_link_length_x_days",
                                   "max_time_field_held", "largest_field_mus_x_days", "forced_drone_recalls",
                                   "distance_walked", "kinetic_capsules_completed", "unique_missions_completed",
                                   "research_bounties_completed", "research_days_completed", "mission_days_attended",
                                   "nl1331_meetups_attended", "first_saturday_events", "second_sunday_events",
                                   "delta_tokens", "delta_reso_points", "delta_field_points",
                                   "agents_recruited", "recursions", "months_subscribed"]:
                    # All other numeric fields
                    try:
                        result[field_name] = int(value)
                    except (ValueError, TypeError) as e:
                        print(f"Warning: Could not parse numeric value '{value}' for {field_name}: {e}")
                        # If conversion fails, keep as string
                        result[field_name] = value
                else:
                    # For any other fields, just store the string value
                    result[field_name] = value
            except Exception as e:
                print(f"Error parsing column {field_name}: {e}")
                # Continue with next column instead of failing completely
                continue
        
        # Process cycle columns
        try:
            _process_cycle_columns(result, column_positions, data_line)
        except Exception as e:
            print(f"Error processing cycle columns: {e}")
            # Continue even if cycle processing fails
        
        return result
    except Exception as e:
        print(f"Error parsing data columns: {e}")
        return None


def _parse_with_fixed_columns(header_line: str, data_line: str) -> Optional[Dict]:
    """
    Parse the data using a fixed column width approach based on the header format.
    
    Args:
        header_line (str): The header line from Ingress Prime export
        data_line (str): The data line from Ingress Prime export
        
    Returns:
        Optional[Dict]: Parsed statistics as a dictionary, or None if parsing failed
    """
    try:
        # Check if header_line or data_line is empty
        if not header_line or not header_line.strip():
            print("Error: Header line is empty")
            return None
            
        if not data_line or not data_line.strip():
            print("Error: Data line is empty")
            return None
            
        # Define the expected column headers and their approximate widths
        # These are based on the sample format and may need adjustment
        column_definitions = [
            ("time_span", "Time Span", 10),
            ("agent_name", "Agent Name", 15),
            ("agent_faction", "Agent Faction", 13),
            ("date", "Date (yyyy-mm-dd)", 17),
            ("time", "Time (hh:mm:ss)", 15),
            ("level", "Level", 7),
            ("lifetime_ap", "Lifetime AP", 12),
            ("current_ap", "Current AP", 12),
            ("unique_portals_visited", "Unique Portals Visited", 22),
            ("unique_portals_drone_visited", "Unique Portals Drone Visited", 28),
            ("furthest_drone_distance", "Furthest Drone Distance", 23),
            ("portals_discovered", "Portals Discovered", 18),
            ("xm_collected", "XM Collected", 13),
            ("opr_agreements", "OPR Agreements", 15),
            ("portal_scans_uploaded", "Portal Scans Uploaded", 22),
            ("uniques_scout_controlled", "Uniques Scout Controlled", 24),
            ("resonators_deployed", "Resonators Deployed", 20),
            ("links_created", "Links Created", 15),
            ("control_fields_created", "Control Fields Created", 23),
            ("mind_units_captured", "Mind Units Captured", 20),
            ("longest_link_ever_created", "Longest Link Ever Created", 26),
            ("largest_control_field", "Largest Control Field", 22),
            ("xm_recharged", "XM Recharged", 14),
            ("portals_captured", "Portals Captured", 17),
            ("unique_portals_captured", "Unique Portals Captured", 23),
            ("mods_deployed", "Mods Deployed", 15),
            ("hacks", "Hacks", 7),
            ("drone_hacks", "Drone Hacks", 13),
            ("glyph_hack_points", "Glyph Hack Points", 18),
            ("completed_hackstreaks", "Completed Hackstreaks", 22),
            ("longest_sojourner_streak", "Longest Sojourner Streak", 23),
            ("resonators_destroyed", "Resonators Destroyed", 20),
            ("portals_neutralized", "Portals Neutralized", 19),
            ("enemy_links_destroyed", "Enemy Links Destroyed", 21),
            ("enemy_fields_destroyed", "Enemy Fields Destroyed", 22),
            ("battle_beacon_combatant", "Battle Beacon Combatant", 24),
            ("drones_returned", "Drones Returned", 17),
            ("machina_links_destroyed", "Machina Links Destroyed", 23),
            ("machina_resonators_destroyed", "Machina Resonators Destroyed", 27),
            ("machina_portals_neutralized", "Machina Portals Neutralized", 27),
            ("machina_portals_reclaimed", "Machina Portals Reclaimed", 25),
            ("max_time_portal_held", "Max Time Portal Held", 21),
            ("max_time_link_maintained", "Max Time Link Maintained", 24),
            ("max_link_length_x_days", "Max Link Length x Days", 23),
            ("max_time_field_held", "Max Time Field Held", 21),
            ("largest_field_mus_x_days", "Largest Field MUs x Days", 25),
            ("forced_drone_recalls", "Forced Drone Recalls", 21),
            ("distance_walked", "Distance Walked", 17),
            ("kinetic_capsules_completed", "Kinetic Capsules Completed", 26),
            ("unique_missions_completed", "Unique Missions Completed", 25),
            ("research_bounties_completed", "Research Bounties Completed", 27),
            ("research_days_completed", "Research Days Completed", 24),
            ("mission_days_attended", "Mission Day(s) Attended", 24),
            ("nl1331_meetups_attended", "NL-1331 Meetup(s) Attended", 27),
            ("first_saturday_events", "First Saturday Events", 22),
            ("second_sunday_events", "Second Sunday Events", 22),
            ("delta_tokens", "+Delta Tokens", 14),
            ("delta_reso_points", "+Delta Reso Points", 18),
            ("delta_field_points", "+Delta Field Points", 19),
            ("agents_recruited", "Agents Recruited", 17),
            ("recursions", "Recursions", 11),
            ("months_subscribed", "Months Subscribed", 17)
        ]
        
        # Create a dictionary with placeholder values for all expected fields
        result = {field_name: None for field_name, _, _ in column_definitions}
        
        # Extract values using fixed column widths
        current_pos = 0
        for field_name, header_name, width in column_definitions:
            try:
                if current_pos >= len(data_line):
                    print(f"Warning: Current position {current_pos} is beyond data line length")
                    break
                    
                # Extract the value for this column
                end_pos = min(current_pos + width, len(data_line))
                value = data_line[current_pos:end_pos].strip()
                
                # Skip empty values
                if not value:
                    current_pos += width
                    continue
                    
                # Convert value to appropriate type based on field with specific handling for key fields
                if field_name == "time_span":
                    # Time Span is typically "ALL TIME" or a specific time period
                    result[field_name] = value.strip()
                elif field_name == "agent_name":
                    # Agent Name may contain spaces, ensure we capture the full name
                    result[field_name] = value.strip()
                elif field_name == "agent_faction":
                    # Normalize faction to standard format
                    result[field_name] = _normalize_faction(value.strip())
                elif field_name == "date":
                    # Date should be in yyyy-mm-dd format
                    date_str = value.strip()
                    # Basic validation for date format
                    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                        result[field_name] = date_str
                    else:
                        # Try to handle different date formats if needed
                        result[field_name] = date_str
                elif field_name == "time":
                    # Time should be in hh:mm:ss format
                    time_str = value.strip()
                    # Basic validation for time format
                    if re.match(r'^\d{2}:\d{2}:\d{2}$', time_str):
                        result[field_name] = time_str
                    else:
                        # Try to handle different time formats if needed
                        result[field_name] = time_str
                elif field_name == "level":
                    # Level should be an integer between 1 and 16
                    try:
                        level = int(value)
                        if 1 <= level <= 16:
                            result[field_name] = level
                        else:
                            print(f"Warning: Level {level} is out of range (1-16)")
                            result[field_name] = value  # Keep as string if out of range
                    except (ValueError, TypeError) as e:
                        print(f"Warning: Could not parse level '{value}': {e}")
                        result[field_name] = value
                elif field_name in ["lifetime_ap", "current_ap"]:
                    # AP values should be integers
                    try:
                        result[field_name] = int(value)
                    except (ValueError, TypeError) as e:
                        print(f"Warning: Could not parse AP value '{value}' for {field_name}: {e}")
                        result[field_name] = value
                elif field_name in ["unique_portals_visited", "unique_portals_drone_visited",
                                   "furthest_drone_distance", "portals_discovered", "xm_collected",
                                   "opr_agreements", "portal_scans_uploaded", "uniques_scout_controlled",
                                   "resonators_deployed", "links_created", "control_fields_created",
                                   "mind_units_captured", "longest_link_ever_created",
                                   "largest_control_field", "xm_recharged", "portals_captured",
                                   "unique_portals_captured", "mods_deployed", "hacks", "drone_hacks",
                                   "glyph_hack_points", "completed_hackstreaks", "longest_sojourner_streak",
                                   "resonators_destroyed", "portals_neutralized", "enemy_links_destroyed",
                                   "enemy_fields_destroyed", "battle_beacon_combatant", "drones_returned",
                                   "machina_links_destroyed", "machina_resonators_destroyed",
                                   "machina_portals_neutralized", "machina_portals_reclaimed",
                                   "max_time_portal_held", "max_time_link_maintained", "max_link_length_x_days",
                                   "max_time_field_held", "largest_field_mus_x_days", "forced_drone_recalls",
                                   "distance_walked", "kinetic_capsules_completed", "unique_missions_completed",
                                   "research_bounties_completed", "research_days_completed", "mission_days_attended",
                                   "nl1331_meetups_attended", "first_saturday_events", "second_sunday_events",
                                   "delta_tokens", "delta_reso_points", "delta_field_points",
                                   "agents_recruited", "recursions", "months_subscribed"]:
                    # All other numeric fields
                    try:
                        result[field_name] = int(value)
                    except (ValueError, TypeError) as e:
                        print(f"Warning: Could not parse numeric value '{value}' for {field_name}: {e}")
                        # If conversion fails, keep as string
                        result[field_name] = value
                else:
                    # For any other fields, just store the string value
                    result[field_name] = value
                    
                current_pos += width
            except Exception as e:
                print(f"Error parsing column {field_name}: {e}")
                # Continue with next column instead of failing completely
                current_pos += width
                continue
        
        # Process cycle columns for fixed-width approach
        try:
            _process_cycle_columns_fixed_width(result, data_line)
        except Exception as e:
            print(f"Error processing cycle columns for fixed-width approach: {e}")
            # Continue even if cycle processing fails
        
        return result
    except Exception as e:
        print(f"Error parsing with fixed columns: {e}")
        return None


def _parse_space_separated(header_line: str, data_line: str) -> Optional[Dict]:
    """
    Parse the data using a space-separated approach based on the sample format.
    
    Args:
        header_line (str): The header line from Ingress Prime export
        data_line (str): The data line from Ingress Prime export
        
    Returns:
        Optional[Dict]: Parsed statistics as a dictionary, or None if parsing failed
    """
    try:
        # Check if header_line or data_line is empty
        if not header_line or not header_line.strip():
            print("Error: Header line is empty")
            return None
            
        if not data_line or not data_line.strip():
            print("Error: Data line is empty")
            return None
            
        # Define the expected column headers in order (multi-word headers)
        expected_headers = [
            "Time Span",
            "Agent Name",
            "Agent Faction",
            "Date (yyyy-mm-dd)",
            "Time (hh:mm:ss)",
            "Level",
            "Lifetime AP",
            "Current AP",
            "Unique Portals Visited",
            "Unique Portals Drone Visited",
            "Furthest Drone Distance",
            "Portals Discovered",
            "XM Collected",
            "OPR Agreements",
            "Portal Scans Uploaded",
            "Uniques Scout Controlled",
            "Resonators Deployed",
            "Links Created",
            "Control Fields Created",
            "Mind Units Captured",
            "Longest Link Ever Created",
            "Largest Control Field",
            "XM Recharged",
            "Portals Captured",
            "Unique Portals Captured",
            "Mods Deployed",
            "Hacks",
            "Drone Hacks",
            "Glyph Hack Points",
            "Completed Hackstreaks",
            "Longest Sojourner Streak",
            "Resonators Destroyed",
            "Portals Neutralized",
            "Enemy Links Destroyed",
            "Enemy Fields Destroyed",
            "Battle Beacon Combatatant",
            "Drones Returned",
            "Machina Links Destroyed",
            "Machina Resonators Destroyed",
            "Machina Portals Neutralized",
            "Machina Portals Reclaimed",
            "Max Time Portal Held",
            "Max Time Link Maintained",
            "Max Link Length x Days",
            "Max Time Field Held",
            "Largest Field MUs x Days",
            "Forced Drone Recalls",
            "Distance Walked",
            "Kinetic Capsules Completed",
            "Unique Missions Completed",
            "Research Bounties Completed",
            "Research Days Completed",
            "Mission Day(s) Attended",
            "NL-1331 Meetup(s) Attended",
            "First Saturday Events",
            "Second Sunday Events",
            "+Delta Tokens",
            "+Delta Reso Points",
            "+Delta Field Points",
            "Agents Recruited",
            "Recursions",
            "Months Subscribed"
        ]
        
        # Split data into columns by spaces
        data_columns = data_line.split()
        
        # Check if we have the minimum required columns
        MIN_REQUIRED_COLUMNS = 7
        if len(data_columns) < MIN_REQUIRED_COLUMNS:
            print(f"Error: Not enough data columns ({len(data_columns)}), minimum required: {MIN_REQUIRED_COLUMNS}")
            return None
        
        # Create header columns by matching expected headers
        header_columns = []
        data_idx = 0
        
        for header in expected_headers:
            # Count how many words are in this header
            header_words = header.split()
            word_count = len(header_words)
            
            # Add the full header to header_columns
            header_columns.append(header)
            
            # Skip the corresponding number of words in data_columns
            data_idx += word_count
        
        # Check if we have enough data columns
        if len(data_columns) < data_idx:
            # Pad data columns with empty strings
            data_columns.extend([''] * (data_idx - len(data_columns)))
        
        # Create a dictionary with placeholder values for all expected fields
        result = {
            "time_span": None,
            "agent_name": None,
            "agent_faction": None,
            "date": None,
            "time": None,
            "level": None,
            "lifetime_ap": None,
            "current_ap": None,
            "unique_portals_visited": None,
            "unique_portals_drone_visited": None,
            "furthest_drone_distance": None,
            "portals_discovered": None,
            "xm_collected": None,
            "opr_agreements": None,
            "portal_scans_uploaded": None,
            "uniques_scout_controlled": None,
            "resonators_deployed": None,
            "links_created": None,
            "control_fields_created": None,
            "mind_units_captured": None,
            "longest_link_ever_created": None,
            "largest_control_field": None,
            "xm_recharged": None,
            "portals_captured": None,
            "unique_portals_captured": None,
            "mods_deployed": None,
            "hacks": None,
            "drone_hacks": None,
            "glyph_hack_points": None,
            "completed_hackstreaks": None,
            "longest_sojourner_streak": None,
            "resonators_destroyed": None,
            "portals_neutralized": None,
            "enemy_links_destroyed": None,
            "enemy_fields_destroyed": None,
            "battle_beacon_combatant": None,
            "drones_returned": None,
            "machina_links_destroyed": None,
            "machina_resonators_destroyed": None,
            "machina_portals_neutralized": None,
            "machina_portals_reclaimed": None,
            "max_time_portal_held": None,
            "max_time_link_maintained": None,
            "max_link_length_x_days": None,
            "max_time_field_held": None,
            "largest_field_mus_x_days": None,
            "forced_drone_recalls": None,
            "distance_walked": None,
            "kinetic_capsules_completed": None,
            "unique_missions_completed": None,
            "research_bounties_completed": None,
            "research_days_completed": None,
            "mission_days_attended": None,
            "nl1331_meetups_attended": None,
            "first_saturday_events": None,
            "second_sunday_events": None,
            "delta_tokens": None,
            "delta_reso_points": None,
            "delta_field_points": None,
            "agents_recruited": None,
            "recursions": None,
            "months_subscribed": None
        }
        
        # Create a mapping from header to result key
        header_to_key = {
            "Time Span": "time_span",
            "Agent Name": "agent_name",
            "Agent Faction": "agent_faction",
            "Date (yyyy-mm-dd)": "date",
            "Time (hh:mm:ss)": "time",
            "Level": "level",
            "Lifetime AP": "lifetime_ap",
            "Current AP": "current_ap",
            "Unique Portals Visited": "unique_portals_visited",
            "Unique Portals Drone Visited": "unique_portals_drone_visited",
            "Furthest Drone Distance": "furthest_drone_distance",
            "Portals Discovered": "portals_discovered",
            "XM Collected": "xm_collected",
            "OPR Agreements": "opr_agreements",
            "Portal Scans Uploaded": "portal_scans_uploaded",
            "Uniques Scout Controlled": "uniques_scout_controlled",
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
            "Hacks": "hacks",
            "Drone Hacks": "drone_hacks",
            "Glyph Hack Points": "glyph_hack_points",
            "Completed Hackstreaks": "completed_hackstreaks",
            "Longest Sojourner Streak": "longest_sojourner_streak",
            "Resonators Destroyed": "resonators_destroyed",
            "Portals Neutralized": "portals_neutralized",
            "Enemy Links Destroyed": "enemy_links_destroyed",
            "Enemy Fields Destroyed": "enemy_fields_destroyed",
            "Battle Beacon Combatatant": "battle_beacon_combatant",
            "Drones Returned": "drones_returned",
            "Machina Links Destroyed": "machina_links_destroyed",
            "Machina Resonators Destroyed": "machina_resonators_destroyed",
            "Machina Portals Neutralized": "machina_portals_neutralized",
            "Machina Portals Reclaimed": "machina_portals_reclaimed",
            "Max Time Portal Held": "max_time_portal_held",
            "Max Time Link Maintained": "max_time_link_maintained",
            "Max Link Length x Days": "max_link_length_x_days",
            "Max Time Field Held": "max_time_field_held",
            "Largest Field MUs x Days": "largest_field_mus_x_days",
            "Forced Drone Recalls": "forced_drone_recalls",
            "Distance Walked": "distance_walked",
            "Kinetic Capsules Completed": "kinetic_capsules_completed",
            "Unique Missions Completed": "unique_missions_completed",
            "Research Bounties Completed": "research_bounties_completed",
            "Research Days Completed": "research_days_completed",
            "Mission Day(s) Attended": "mission_days_attended",
            "NL-1331 Meetup(s) Attended": "nl1331_meetups_attended",
            "First Saturday Events": "first_saturday_events",
            "Second Sunday Events": "second_sunday_events",
            "+Delta Tokens": "delta_tokens",
            "+Delta Reso Points": "delta_reso_points",
            "+Delta Field Points": "delta_field_points",
            "Agents Recruited": "agents_recruited",
            "Recursions": "recursions",
            "Months Subscribed": "months_subscribed"
        }
        
        # Map data to result using the header_to_key mapping
        data_idx = 0
        for header in expected_headers:
            try:
                key = header_to_key.get(header)
                if key and data_idx < len(data_columns):
                    value = data_columns[data_idx].strip()
                    
                    # Special handling for specific fields
                    if key == "agent_faction":
                        result[key] = _normalize_faction(value)
                    elif key == "level":
                        try:
                            level = int(value)
                            if 1 <= level <= 16:
                                result[key] = level
                            else:
                                print(f"Warning: Level {level} is out of range (1-16)")
                                result[key] = value  # Keep as string if out of range
                        except (ValueError, TypeError) as e:
                            print(f"Warning: Could not parse level '{value}': {e}")
                            pass
                    elif key in ["lifetime_ap", "current_ap", "unique_portals_visited",
                               "unique_portals_drone_visited", "furthest_drone_distance",
                               "portals_discovered", "xm_collected", "opr_agreements",
                               "portal_scans_uploaded", "uniques_scout_controlled",
                               "resonators_deployed", "links_created", "control_fields_created",
                               "mind_units_captured", "longest_link_ever_created",
                               "largest_control_field", "xm_recharged", "portals_captured",
                               "unique_portals_captured", "mods_deployed", "hacks", "drone_hacks",
                               "glyph_hack_points", "completed_hackstreaks", "longest_sojourner_streak",
                               "resonators_destroyed", "portals_neutralized", "enemy_links_destroyed",
                               "enemy_fields_destroyed", "battle_beacon_combatant", "drones_returned",
                               "machina_links_destroyed", "machina_resonators_destroyed",
                               "machina_portals_neutralized", "machina_portals_reclaimed",
                               "max_time_portal_held", "max_time_link_maintained", "max_link_length_x_days",
                               "max_time_field_held", "largest_field_mus_x_days", "forced_drone_recalls",
                               "distance_walked", "kinetic_capsules_completed", "unique_missions_completed",
                               "research_bounties_completed", "research_days_completed", "mission_days_attended",
                               "nl1331_meetups_attended", "first_saturday_events", "second_sunday_events",
                               "delta_tokens", "delta_reso_points", "delta_field_points",
                               "agents_recruited", "recursions", "months_subscribed"]:
                        try:
                            result[key] = int(value)
                        except (ValueError, TypeError) as e:
                            print(f"Warning: Could not parse numeric value '{value}' for {key}: {e}")
                            pass
                    else:
                        result[key] = value
                    
                    # Count how many words are in this header to advance data_idx correctly
                    header_words = header.split()
                    data_idx += len(header_words)
            except Exception as e:
                print(f"Error processing header '{header}': {e}")
                # Continue with next header instead of failing completely
                header_words = header.split()
                data_idx += len(header_words)
                continue
        
        # Process cycle columns for space-separated approach
        try:
            _process_cycle_columns_space_separated(result, header_columns, data_columns)
        except Exception as e:
            print(f"Error processing cycle columns for space-separated approach: {e}")
            # Continue even if cycle processing fails
        
        # Save the cycle name to file if it was extracted
        if result and result.get("cycle_name"):
            save_current_cycle(result["cycle_name"])
        
        return result
    except Exception as e:
        print(f"Error parsing space separated data: {e}")
        return None


def _normalize_faction(faction: str) -> Optional[str]:
    """
    Normalize faction names to standard format.
    
    Args:
        faction (str): Raw faction name from the data
        
    Returns:
        Optional[str]: Normalized faction name (ENL, RES) or None if invalid
    """
    try:
        # Check if faction is empty or None
        if not faction:
            print("Error: Faction is empty or None")
            return None
            
        # Check if faction is a string
        if not isinstance(faction, str):
            print(f"Error: Faction is not a string: {type(faction)}")
            return None
            
        faction_lower = faction.lower().strip()
        
        if faction_lower in ["enlightened", "enl"]:
            return "ENL"
        elif faction_lower in ["resistance", "res"]:
            return "RES"
        
        # Log invalid faction for debugging
        print(f"Error: Invalid faction: {faction}")
        # Return None for invalid factions
        return None
    except Exception as e:
        print(f"Error normalizing faction: {e}")
        return None


def _process_cycle_columns(result: Dict, column_positions: Dict[str, Tuple[int, int]], data_line: str) -> None:
    """
    Process cycle columns to identify active cycle and extract cycle information.
    
    Args:
        result (Dict): The result dictionary to update with cycle information
        column_positions (Dict[str, Tuple[int, int]]): Dictionary mapping column names to (start, end) positions
        data_line (str): The data line from Ingress Prime export
    """
    try:
        # Check if result, column_positions, or data_line is empty
        if not result:
            print("Error: Result dictionary is empty")
            return
            
        if not column_positions:
            print("Error: Column positions dictionary is empty")
            return
            
        if not data_line or not data_line.strip():
            print("Error: Data line is empty")
            return
        
        # Find all cycle columns (headers starting with '+')
        cycle_columns = []
        
        # Sort columns by their start position
        sorted_columns = sorted(column_positions.items(), key=lambda x: x[1][0])
        
        # Extract all column headers from the header line
        for field_name, (start_pos, end_pos) in sorted_columns:
            try:
                # Check if start_pos is within bounds of data_line
                if start_pos >= len(data_line):
                    print(f"Warning: Start position {start_pos} for field '{field_name}' is beyond data line length")
                    continue
                
                # Determine the end position for this column
                if field_name == sorted_columns[-1][0]:  # If this is the last column
                    header_end = len(data_line)
                else:
                    # Find the next column's start position
                    next_idx = sorted_columns.index((field_name, (start_pos, end_pos))) + 1
                    if next_idx < len(sorted_columns):
                        header_end = sorted_columns[next_idx][1][0]
                    else:
                        header_end = len(data_line)
                
                # Check if header_end is within bounds of data_line
                if header_end > len(data_line):
                    header_end = len(data_line)
                
                # Extract the header name
                header_name = data_line[start_pos:header_end].strip()
                
                # Check if this is a cycle column (starts with '+')
                if header_name.startswith('+'):
                    cycle_columns.append((field_name, header_name, start_pos, header_end))
            except Exception as e:
                print(f"Error processing column '{field_name}' for cycle detection: {e}")
                # Continue with next column instead of failing completely
                continue
        
        # If no cycle columns found, return
        if not cycle_columns:
            return
        
        # Find the active cycle column (the one with data)
        active_cycle = None
        active_cycle_value = None
        
        for field_name, header_name, start_pos, end_pos in cycle_columns:
            try:
                # Check if start_pos is within bounds of data_line
                if start_pos >= len(data_line):
                    print(f"Warning: Start position {start_pos} for cycle column '{header_name}' is beyond data line length")
                    continue
                
                # Extract the value for this cycle column
                if field_name == sorted_columns[-1][0]:  # If this is the last column
                    value = data_line[start_pos:].strip()
                else:
                    # Find the next column's start position
                    next_idx = [col[0] for col in sorted_columns].index(field_name) + 1
                    if next_idx < len(sorted_columns):
                        next_start_pos = sorted_columns[next_idx][1][0]
                        # Check if next_start_pos is within bounds of data_line
                        if next_start_pos > len(data_line):
                            value = data_line[start_pos:].strip()
                        else:
                            value = data_line[start_pos:next_start_pos].strip()
                    else:
                        value = data_line[start_pos:].strip()
                
                # Check if this cycle column has a valid value
                if value and value.strip():
                    try:
                        # Try to convert to integer to validate it's a number
                        int_value = int(value)
                        active_cycle = header_name
                        active_cycle_value = int_value
                        break  # Found the active cycle
                    except (ValueError, TypeError):
                        # Not a valid number, continue to next cycle column
                        continue
            except Exception as e:
                print(f"Error processing cycle column '{header_name}': {e}")
                # Continue with next cycle column instead of failing completely
                continue
        
        # If we found an active cycle, update the result
        if active_cycle and active_cycle_value is not None:
            # Extract cycle name (remove the '+' prefix)
            cycle_name = active_cycle[1:].strip()  # Remove the '+' and any extra spaces
            result["cycle_name"] = cycle_name
            result["cycle_points"] = active_cycle_value
    except Exception as e:
        print(f"Error processing cycle columns: {e}")
        # If there's an error, we'll just leave cycle_name and cycle_points as None
        pass


def _process_cycle_columns_fixed_width(result: Dict, data_line: str) -> None:
    """
    Process cycle columns for the fixed-width approach to identify active cycle and extract cycle information.
    
    Args:
        result (Dict): The result dictionary to update with cycle information
        data_line (str): The data line from Ingress Prime export
    """
    try:
        # Check if result or data_line is empty
        if not result:
            print("Error: Result dictionary is empty")
            return
            
        if not data_line or not data_line.strip():
            print("Error: Data line is empty")
            return
            
        # Define the expected cycle columns and their positions
        # These are based on the sample format and may need adjustment
        cycle_column_definitions = [
            ("delta_tokens", "+Delta Tokens", 14),
            ("delta_reso_points", "+Delta Reso Points", 18),
            ("delta_field_points", "+Delta Field Points", 19)
        ]
        
        # Find the active cycle column (the one with data)
        active_cycle = None
        active_cycle_value = None
        
        current_pos = 0
        for field_name, header_name, width in cycle_column_definitions:
            try:
                if current_pos >= len(data_line):
                    print(f"Warning: Current position {current_pos} is beyond data line length")
                    break
                
                # Extract the value for this cycle column
                end_pos = min(current_pos + width, len(data_line))
                value = data_line[current_pos:end_pos].strip()
                
                # Check if this cycle column has a valid value
                if value and value.strip():
                    try:
                        # Try to convert to integer to validate it's a number
                        int_value = int(value)
                        active_cycle = header_name
                        active_cycle_value = int_value
                        break  # Found the active cycle
                    except (ValueError, TypeError):
                        # Not a valid number, continue to next cycle column
                        pass
                
                current_pos += width
            except Exception as e:
                print(f"Error processing cycle column '{header_name}': {e}")
                # Continue with next cycle column instead of failing completely
                current_pos += width
                continue
        
        # If we found an active cycle, update the result
        if active_cycle and active_cycle_value is not None:
            # Extract cycle name (remove the '+' prefix)
            cycle_name = active_cycle[1:].strip()  # Remove the '+' and any extra spaces
            result["cycle_name"] = cycle_name
            result["cycle_points"] = active_cycle_value
    except Exception as e:
        print(f"Error processing cycle columns for fixed-width approach: {e}")
        # If there's an error, we'll just leave cycle_name and cycle_points as None
        pass


def _validate_critical_fields(result: Dict) -> bool:
    """
    Validate critical fields in the parsed data.
    
    Args:
        result (Dict): The parsed data dictionary
        
    Returns:
        bool: True if all critical fields are valid, False otherwise
    """
    try:
        # Validate Agent Name (must not be empty)
        agent_name = result.get("agent_name")
        if not agent_name or not str(agent_name).strip():
            print("Error: Agent Name is empty or invalid")
            return False
            
        # Validate Faction (must be valid: "ENL" or "RES")
        agent_faction = result.get("agent_faction")
        if agent_faction not in ["ENL", "RES"]:
            print(f"Error: Invalid faction: {agent_faction}")
            return False
            
        # Validate Level (must be a number between 1 and 16)
        level = result.get("level")
        try:
            level_int = int(level)
            if not (1 <= level_int <= 16):
                print(f"Error: Invalid level: {level_int} (must be between 1 and 16)")
                return False
        except (ValueError, TypeError):
            print(f"Error: Level is not a valid number: {level}")
            return False
            
        # Validate Date (must be in valid format)
        date = result.get("date")
        if not date or not re.match(r'^\d{4}-\d{2}-\d{2}$', str(date)):
            print(f"Error: Invalid date format: {date} (expected yyyy-mm-dd)")
            return False
            
        # Validate Time (must be in valid format)
        time = result.get("time")
        if not time or not re.match(r'^\d{2}:\d{2}:\d{2}$', str(time)):
            print(f"Error: Invalid time format: {time} (expected hh:mm:ss)")
            return False
            
        # Validate AP values (must be valid numbers)
        for ap_field in ["lifetime_ap", "current_ap"]:
            ap_value = result.get(ap_field)
            try:
                # Convert to int to validate it's a number
                if ap_value is not None:
                    int(ap_value)
            except (ValueError, TypeError):
                print(f"Error: Invalid AP value for {ap_field}: {ap_value}")
                return False
                
        # Validate cycle data if present
        cycle_name = result.get("cycle_name")
        cycle_points = result.get("cycle_points")
        
        if cycle_name is not None:
            if not cycle_name or not str(cycle_name).strip():
                print("Error: Cycle name is empty")
                return False
                
        if cycle_points is not None:
            try:
                # Convert to int to validate it's a number
                int(cycle_points)
            except (ValueError, TypeError):
                print(f"Error: Invalid cycle points: {cycle_points}")
                return False
                
        return True
    except Exception as e:
        print(f"Error validating critical fields: {e}")
        return False


def _process_cycle_columns_space_separated(result: Dict, header_columns: List[str], data_columns: List[str]) -> None:
    """
    Process cycle columns for the space-separated approach to identify active cycle and extract cycle information.
    
    Args:
        result (Dict): The result dictionary to update with cycle information
        header_columns (List[str]): List of header column names
        data_columns (List[str]): List of data column values
    """
    try:
        # Find the active cycle column (the one with data)
        active_cycle = None
        active_cycle_value = None
        
        # Check each header column to see if it's a cycle column (starts with '+')
        for i, header in enumerate(header_columns):
            if header.startswith('+') and i < len(data_columns):
                value = data_columns[i].strip()
                
                # Check if this cycle column has a valid value
                if value:
                    try:
                        # Try to convert to integer to validate it's a number
                        int_value = int(value)
                        active_cycle = header
                        active_cycle_value = int_value
                        break  # Found the active cycle
                    except (ValueError, TypeError):
                        # Not a valid number, continue to next cycle column
                        continue
        
        # If we found an active cycle, update the result
        if active_cycle and active_cycle_value is not None:
            # Extract cycle name (remove the '+' prefix)
            cycle_name = active_cycle[1:].strip()  # Remove the '+' and any extra spaces
            result["cycle_name"] = cycle_name
            result["cycle_points"] = active_cycle_value
    except Exception as e:
        print(f"Error processing cycle columns for space-separated approach: {e}")
        # If there's an error, we'll just leave cycle_name and cycle_points as None
        pass