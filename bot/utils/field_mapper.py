"""
Key-value field mapping system for Ingress leaderboard data processing.

This module defines the mapping between leaderboard commands and the corresponding
data field names from the Ingress export format. It provides a centralized
way to manage which fields are used by the bot and allows for easy extension
when new data fields are added.
"""

from typing import Dict, Optional, Set
import logging

logger = logging.getLogger(__name__)

class DataFieldMapper:
    """Maps leaderboard commands to their corresponding data field names."""

    def __init__(self):
        # Define the mapping between command suffixes and display names
        self.command_display_map = {
            "": "Lifetime AP",  # Default leaderboard
            "hacks": "Hacks",
            "xm": "XM Collected",
            "portals": "Portals Captured",
            "links": "Links Created",
            "fields": "Control Fields Created",
            "distance": "Distance Walked",
            "resonators": "Resonators Deployed",
            "betatokens": "+Beta Tokens",
            "beta": "+Beta Tokens"  # Alternative command
        }

        # Define the mapping between display names and actual field names from data
        # This uses the exact field names from the Ingress export format
        self.display_field_map = {
            "Lifetime AP": "Lifetime AP",
            "Hacks": "Hacks",
            "XM Collected": "XM Collected",
            "Portals Captured": "Portals Captured",
            "Links Created": "Links Created",
            "Control Fields Created": "Control Fields Created",
            "Distance Walked": "Distance Walked",
            "Resonators Deployed": "Resonators Deployed",
            "Resonators Destroyed": "Resonators Destroyed",
            "+Beta Tokens": "+Beta Tokens"
        }

        # Additional fields that might be available in the data but not used in commands
        self.available_fields = {
            "Time Span": "Time Span",
            "Agent Name": "Agent Name",
            "Agent Faction": "Agent Faction",
            "Date (yyyy-mm-dd)": "Date (yyyy-mm-dd)",
            "Time (hh:mm:ss)": "Time (hh:mm:ss)",
            "Level": "Level",
            "Current AP": "Current AP",
            "Unique Portals Visited": "Unique Portals Visited",
            "Unique Portals Drone Visited": "Unique Portals Drone Visited",
            "Furthest Drone Distance": "Furthest Drone Distance",
            "Portals Discovered": "Portals Discovered",
            "XM Collected": "XM Collected",
            "OPR Agreements": "OPR Agreements",
            "Portal Scans Uploaded": "Portal Scans Uploaded",
            "Uniques Scout Controlled": "Uniques Scout Controlled",
            "Resonators Deployed": "Resonators Deployed",
            "Links Created": "Links Created",
            "Control Fields Created": "Control Fields Created",
            "Mind Units Captured": "Mind Units Captured",
            "Longest Link Ever Created": "Longest Link Ever Created",
            "Largest Control Field": "Largest Control Field",
            "XM Recharged": "XM Recharged",
            "Portals Captured": "Portals Captured",
            "Unique Portals Captured": "Unique Portals Captured",
            "Mods Deployed": "Mods Deployed",
            "Hacks": "Hacks",
            "Drone Hacks": "Drone Hacks",
            "Glyph Hack Points Completed": "Glyph Hack Points Completed",
            "Hackstreaks": "Hackstreaks",
            "Longest Sojourner Streak": "Longest Sojourner Streak",
            "Resonators Destroyed": "Resonators Destroyed",
            "Portals Neutralized": "Portals Neutralized",
            "Enemy Links Destroyed": "Enemy Links Destroyed",
            "Enemy Fields Destroyed": "Enemy Fields Destroyed",
            "Battle Beacon": "Battle Beacon",
            "Combatant Drones Returned": "Combatant Drones Returned",
            "Machina Links Destroyed": "Machina Links Destroyed",
            "Machina Resonators Destroyed": "Machina Resonators Destroyed",
            "Machina Portals Neutralized": "Machina Portals Neutralized",
            "Machina Portals Reclaimed": "Machina Portals Reclaimed",
            "Max Time Portal Held": "Max Time Portal Held",
            "Max Time Link Maintained": "Max Time Link Maintained",
            "Max Link Length x Days": "Max Link Length x Days",
            "Max Time Field Held": "Max Time Field Held",
            "Largest Field MUs x Days": "Largest Field MUs x Days",
            "Forced Drone Recalls": "Forced Drone Recalls",
            "Distance Walked": "Distance Walked",
            "Kinetic Capsules Completed": "Kinetic Capsules Completed",
            "Unique Missions Completed": "Unique Missions Completed",
            "Research Bounties Completed": "Research Bounties Completed",
            "Research Days Completed": "Research Days Completed",
            "Mission Day(s) Attended": "Mission Day(s) Attended",
            "NL-1331 Meetup(s) Attended": "NL-1331 Meetup(s) Attended",
            "First Saturday Events": "First Saturday Events",
            "Second Sunday Events": "Second Sunday Events",
            "+Beta Tokens": "+Beta Tokens",
            "Agents Recruited": "Agents Recruited",
            "Recursions": "Recursions",
            "Months Subscribed": "Months Subscribed"
        }

    def get_field_for_command(self, command_suffix: str) -> Optional[str]:
        """
        Get the data field name for a given command suffix.

        Args:
            command_suffix: The suffix part of the command (e.g., 'xm', 'distance')

        Returns:
            The actual field name from the data, or None if not found
        """
        display_name = self.command_display_map.get(command_suffix)
        if display_name:
            return self.display_field_map.get(display_name)
        return None

    def get_display_name_for_command(self, command_suffix: str) -> Optional[str]:
        """
        Get the display name for a given command suffix.

        Args:
            command_suffix: The suffix part of the command

        Returns:
            The display name for the metric, or None if not found
        """
        return self.command_display_map.get(command_suffix)

    def get_all_command_mappings(self) -> Dict[str, str]:
        """
        Get all command to field mappings.

        Returns:
            Dictionary mapping command suffixes to field names
        """
        mappings = {}
        for command_suffix, display_name in self.command_display_map.items():
            field_name = self.display_field_map.get(display_name)
            if field_name:
                mappings[command_suffix] = field_name
        return mappings

    def get_available_leaderboard_fields(self) -> Set[str]:
        """
        Get all fields that are available for leaderboard commands.

        Returns:
            Set of field names that have corresponding leaderboard commands
        """
        return set(self.display_field_map.values())

    def get_all_available_fields(self) -> Set[str]:
        """
        Get all fields that are available in the data format.

        Returns:
            Set of all field names from the Ingress export format
        """
        return set(self.available_fields.values())

    def is_field_supported(self, field_name: str) -> bool:
        """
        Check if a field is supported by the leaderboard system.

        Args:
            field_name: The field name to check

        Returns:
            True if the field has a corresponding leaderboard command
        """
        return field_name in self.get_available_leaderboard_fields()

    def extract_supported_data(self, all_data: Dict[str, str]) -> Dict[str, str]:
        """
        Extract only the data fields that are supported by the leaderboard system.

        Args:
            all_data: Dictionary containing all parsed data fields

        Returns:
            Dictionary containing only supported fields
        """
        supported_fields = self.get_available_leaderboard_fields()
        return {
            field: value for field, value in all_data.items()
            if field in supported_fields
        }

    def add_custom_mapping(self, command_suffix: str, field_name: str, display_name: str = None) -> bool:
        """
        Add a custom mapping for a new command.

        Args:
            command_suffix: The command suffix (e.g., 'custom_metric')
            field_name: The actual field name from the data
            display_name: Optional display name (defaults to field_name)

        Returns:
            True if mapping was added successfully
        """
        try:
            if display_name is None:
                display_name = field_name

            self.command_display_map[command_suffix] = display_name
            self.display_field_map[display_name] = field_name

            logger.info(f"Added custom mapping: {command_suffix} -> {field_name}")
            return True

        except Exception as e:
            logger.error(f"Error adding custom mapping: {e}")
            return False

    def remove_mapping(self, command_suffix: str) -> bool:
        """
        Remove a mapping for a command.

        Args:
            command_suffix: The command suffix to remove

        Returns:
            True if mapping was removed successfully
        """
        try:
            if command_suffix in self.command_display_map:
                display_name = self.command_display_map[command_suffix]
                del self.command_display_map[command_suffix]

                # Also remove from display_field_map if not used by other commands
                if display_name not in self.command_display_map.values():
                    self.display_field_map.pop(display_name, None)

                logger.info(f"Removed mapping: {command_suffix}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error removing mapping: {e}")
            return False


# Global instance
_field_mapper = None

def get_field_mapper() -> DataFieldMapper:
    """Get the global field mapper instance."""
    global _field_mapper
    if _field_mapper is None:
        _field_mapper = DataFieldMapper()
    return _field_mapper