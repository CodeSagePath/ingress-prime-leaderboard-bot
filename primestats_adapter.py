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


def parse_pasted_stats(text: str) -> List[Dict]:
    """
    Parse one or more lines of raw stat text from Ingress Prime export.
    
    Args:
        text (str): Raw stat text from Ingress Prime export, potentially containing
                   multiple lines of agent statistics.
    
    Returns:
        List[Dict]: A list of dictionaries, each containing parsed statistics for one agent.
                    Each dict includes at least: agent_name, agent_faction, date, time, 
                    level, lifetime_ap, current_ap, cycle_name, cycle_points, raw_line.
    """
    # Initialize variables
    results = []
    current_cycle = _read_current_cycle()
    
    # Split text into lines and process each line
    lines = text.strip().split('\n')
    
    # Skip header line if present (check for common header patterns)
    if lines and re.search(r'Time Span|Agent Name|Date \(yyyy-mm-dd\)', lines[0]):
        lines = lines[1:]
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Parse the line
        parsed_line = _parse_stat_line(line, current_cycle)
        
        if parsed_line:
            # Update current cycle if a new one is detected
            if parsed_line.get('cycle_name') and parsed_line['cycle_name'] != current_cycle:
                current_cycle = parsed_line['cycle_name']
                _write_current_cycle(current_cycle)
            
            results.append(parsed_line)
    
    return results


def _parse_stat_line(line: str, current_cycle: Optional[str]) -> Optional[Dict]:
    """
    Parse a single line of Ingress Prime statistics.
    
    Args:
        line (str): A single line of statistics text
        current_cycle (Optional[str]): The current cycle name from previous parsing
    
    Returns:
        Optional[Dict]: Parsed statistics as a dictionary, or None if parsing failed
    """
    # Split the line into components
    parts = line.split()
    
    # Check if we have enough parts for basic parsing
    if len(parts) < 8:  # Minimum required: time_span, agent_name, faction, date, time, level, lifetime_ap, current_ap
        return None
    
    try:
        # Handle "ALL TIME" as a single time span
        if parts[0] == "ALL" and parts[1] == "TIME":
            time_span = "ALL TIME"
            agent_name = parts[2]
            faction_raw = parts[3]
            date_str = parts[4]
            time_str = parts[5]
            level = int(parts[6])
            lifetime_ap = int(parts[7])
            current_ap = int(parts[8])
            # Adjust the parts list for additional field parsing
            parts = parts[1:]  # Skip the "ALL" part
        else:
            # Standard format
            time_span = parts[0]
            agent_name = parts[1]
            faction_raw = parts[2]
            date_str = parts[3]
            time_str = parts[4]
            level = int(parts[5])
            lifetime_ap = int(parts[6])
            current_ap = int(parts[7])
        
        # Validate date format (YYYY-MM-DD)
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return None
            
        # Validate time format (HH:MM or HH:MM:SS)
        if not re.match(r'^\d{2}:\d{2}(:\d{2})?$', time_str):
            return None
        
        # Convert faction to match enum values in bot/models.py
        faction = _normalize_faction(faction_raw)
        if not faction:
            return None
        
        # Initialize result with required fields
        result = {
            'agent_name': agent_name,
            'agent_faction': faction,
            'date': date_str,
            'time': time_str,
            'level': level,
            'lifetime_ap': lifetime_ap,
            'current_ap': current_ap,
            'cycle_name': None,
            'cycle_points': None,
            'raw_line': line
        }
        
        # Look for cycle tokens (+Theta, +Gamma, +Delta, +Beta, +Lambda)
        cycle_name, cycle_points = _extract_cycle_info(parts)
        
        if cycle_name:
            result['cycle_name'] = cycle_name
            result['cycle_points'] = cycle_points
        elif current_cycle:
            result['cycle_name'] = current_cycle
            # Try to find cycle points in the line even if cycle name isn't present
            _, cycle_points = _extract_cycle_info(parts)
            if cycle_points is not None:
                result['cycle_points'] = cycle_points
        
        # Parse additional fields based on the header structure
        _parse_additional_fields(result, parts)
        
        return result
        
    except (ValueError, IndexError):
        # Skip lines with parsing errors
        return None


def _normalize_faction(faction_raw: str) -> Optional[str]:
    """
    Normalize faction name to match enum values in bot/models.py.
    
    Args:
        faction_raw (str): Raw faction name from the stat text
    
    Returns:
        Optional[str]: Normalized faction name ("ENL" or "RES") or None if invalid
    """
    faction_lower = faction_raw.lower()
    if faction_lower in ['enlightened', 'enl']:
        return "ENL"
    elif faction_lower in ['resistance', 'res']:
        return "RES"
    return None


def _extract_cycle_info(parts: List[str]) -> Tuple[Optional[str], Optional[int]]:
    """
    Extract cycle name and points from the line parts.
    
    Args:
        parts (List[str]): Split parts of the stat line
    
    Returns:
        Tuple[Optional[str], Optional[int]]: Cycle name and points if found
    """
    cycle_name = None
    cycle_points = None
    
    # Look for tokens that start with '+'
    for i, part in enumerate(parts):
        if part.startswith('+'):
            cycle_name = part[1:]  # Remove the '+' prefix
            # Try to get the next part as cycle points
            if i + 1 < len(parts):
                try:
                    cycle_points = int(parts[i + 1])
                except ValueError:
                    cycle_points = None
            break
    
    return cycle_name, cycle_points


def _parse_additional_fields(result: Dict, parts: List[str]) -> None:
    """
    Parse additional fields from the stat line and add them to the result dictionary.
    
    Args:
        result (Dict): The result dictionary to update
        parts (List[str]): Split parts of the stat line
    """
    # Define field mappings based on the header structure
    # This is a simplified mapping - in a real implementation, you might want
    # to make this more comprehensive or configurable
    
    field_mappings = {
        8: 'unique_portals_visited',
        9: 'unique_portals_drone_visited',
        10: 'furthest_drone_distance',
        11: 'portals_discovered',
        12: 'xm_collected',
        13: 'opr_agreements',
        14: 'portal_scans_uploaded',
        15: 'uniques_scout_controlled',
        16: 'resonators_deployed',
        17: 'links_created',
        18: 'control_fields_created',
        19: 'mind_units_captured',
        20: 'longest_link_ever_created',
        21: 'largest_control_field',
        22: 'xm_recharged',
        23: 'portals_captured',
        24: 'unique_portals_captured',
        25: 'mods_deployed',
        26: 'hacks',
        27: 'drone_hacks',
        28: 'glyph_hack_points',
        29: 'completed_hackstreaks',
        30: 'longest_sojourner_streak',
        31: 'resonators_destroyed',
        32: 'portals_neutralized',
        33: 'enemy_links_destroyed',
        34: 'enemy_fields_destroyed',
        35: 'battle_beacon_combatant',
        36: 'drones_returned',
        37: 'machina_links_destroyed',
        38: 'machina_resonators_destroyed',
        39: 'machina_portals_neutralized',
        40: 'machina_portals_reclaimed',
        41: 'max_time_portal_held',
        42: 'max_time_link_maintained',
        43: 'max_link_length_x_days',
        44: 'max_time_field_held',
        45: 'largest_field_mus_x_days',
        46: 'forced_drone_recalls',
        47: 'distance_walked',
        48: 'kinetic_capsules_completed',
        49: 'unique_missions_completed',
        50: 'research_bounties_completed',
        51: 'research_days_completed',
        52: 'mission_days_attended',
        53: 'nl1331_meetups_attended',
        54: 'first_saturday_events',
        55: 'second_sunday_events',
        56: 'delta_tokens',  # This might be +Delta Tokens
        57: 'delta_reso_points',
        58: 'delta_field_points',
        59: 'agents_recruited',
        60: 'recursions',
        61: 'months_subscribed'
    }
    
    # Parse each field if it exists
    for index, field_name in field_mappings.items():
        if index < len(parts):
            try:
                # Try to parse as integer first
                result[field_name] = int(parts[index])
            except ValueError:
                # If not an integer, keep as string
                result[field_name] = parts[index]


def _read_current_cycle() -> Optional[str]:
    """
    Read the current cycle name from the current_cycle.txt file.
    
    Returns:
        Optional[str]: The current cycle name if the file exists, None otherwise
    """
    try:
        if os.path.exists('current_cycle.txt'):
            with open('current_cycle.txt', 'r') as f:
                return f.read().strip()
    except IOError:
        pass
    return None


def _write_current_cycle(cycle_name: str) -> None:
    """
    Write the current cycle name to the current_cycle.txt file.
    
    Args:
        cycle_name (str): The cycle name to write
    """
    try:
        with open('current_cycle.txt', 'w') as f:
            f.write(cycle_name)
    except IOError:
        pass