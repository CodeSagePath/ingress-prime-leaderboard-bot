"""
Dynamic key-value mapping system for processing Ingress data submissions.

This module allows users to define custom mappings between header names and data positions,
making the bot flexible to handle different Ingress export formats.
"""

import logging
from typing import Dict, List, Optional, Tuple
import json
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DataMapping:
    """Represents a key-value mapping for data processing."""
    keys: List[str]  # Header names
    values: List[str]  # Corresponding data values
    description: str = ""
    created_by: Optional[int] = None  # Telegram user ID
    is_active: bool = True


class DynamicMappingManager:
    """Manages dynamic key-value mappings for data processing."""

    def __init__(self):
        self.mappings: Dict[str, DataMapping] = {}
        self._load_default_mappings()

    def _load_default_mappings(self):
        """Load default Ingress field mappings."""
        # Standard Ingress export format
        standard_keys = [
            "time_span", "agent_name", "agent_faction", "date", "time", "level",
            "lifetime_ap", "current_ap", "cycle_points", "verified_level"
        ]
        self.mappings["standard"] = DataMapping(
            keys=standard_keys,
            values=["", "", "", "", "", "", "", "", "", ""],
            description="Standard Ingress Prime export format"
        )

        # Common variations
        space_separated_keys = [
            "Time Span", "Agent Name", "Agent Faction", "Date (yyyy-mm-dd)",
            "Time (hh:mm:ss)", "Level", "Lifetime AP", "Current AP",
            "Cycle Points", "Verified Level"
        ]
        self.mappings["space_separated"] = DataMapping(
            keys=space_separated_keys,
            values=["", "", "", "", "", "", "", "", "", ""],
            description="Space-separated Ingress export format"
        )

    def create_mapping(self,
                      mapping_id: str,
                      keys_string: str,
                      values_string: str,
                      description: str = "",
                      created_by: Optional[int] = None) -> bool:
        """
        Create a new mapping from comma-separated keys and values.

        Args:
            mapping_id: Unique identifier for this mapping
            keys_string: Comma-separated keys (e.g., "keyA, keyB, keyC")
            values_string: Comma-separated values (e.g., "valueA, valueB, valueC")
            description: Optional description of the mapping
            created_by: Telegram user ID who created this mapping

        Returns:
            True if mapping was created successfully, False otherwise
        """
        try:
            # Parse keys and values
            keys = [key.strip() for key in keys_string.split(',') if key.strip()]
            values = [value.strip() for value in values_string.split(',') if value.strip()]

            # Validate keys and values have same length
            if len(keys) != len(values):
                logger.error(f"Keys ({len(keys)}) and values ({len(values)}) count mismatch")
                return False

            # Store the mapping
            self.mappings[mapping_id] = DataMapping(
                keys=keys,
                values=values,
                description=description,
                created_by=created_by,
                is_active=True
            )

            logger.info(f"Created mapping '{mapping_id}' with {len(keys)} key-value pairs")
            return True

        except Exception as e:
            logger.error(f"Error creating mapping '{mapping_id}': {e}")
            return False

    def get_mapping(self, mapping_id: str) -> Optional[DataMapping]:
        """Get a mapping by ID."""
        return self.mappings.get(mapping_id)

    def list_mappings(self) -> Dict[str, DataMapping]:
        """Get all available mappings."""
        return self.mappings.copy()

    def delete_mapping(self, mapping_id: str) -> bool:
        """Delete a mapping."""
        if mapping_id in self.mappings:
            del self.mappings[mapping_id]
            logger.info(f"Deleted mapping '{mapping_id}'")
            return True
        return False

    def process_data_with_mapping(self,
                                 mapping_id: str,
                                 data_line: str) -> Dict[str, str]:
        """
        Process a data line using a specific mapping.

        Args:
            mapping_id: ID of the mapping to use
            data_line: The data line to process (space or tab separated)

        Returns:
            Dictionary mapping keys to their extracted values
        """
        mapping = self.get_mapping(mapping_id)
        if not mapping:
            logger.error(f"Mapping '{mapping_id}' not found")
            return {}

        try:
            # Split the data line (handle both space and tab separated)
            if '\t' in data_line:
                data_values = [val.strip() for val in data_line.split('\t')]
            else:
                data_values = data_line.split()

            # Create key-value pairs
            result = {}
            for i, key in enumerate(mapping.keys):
                if i < len(data_values):
                    result[key] = data_values[i]
                else:
                    result[key] = ""  # Default empty value if missing

            logger.debug(f"Processed data with mapping '{mapping_id}': {len(result)} fields extracted")
            return result

        except Exception as e:
            logger.error(f"Error processing data with mapping '{mapping_id}': {e}")
            return {}

    def extract_leaderboard_relevant_data(self,
                                        processed_data: Dict[str, str]) -> Dict[str, any]:
        """
        Extract only leaderboard-relevant data from processed data.

        Args:
            processed_data: Dictionary of all processed key-value pairs

        Returns:
            Dictionary with only leaderboard-relevant fields
        """
        # Define leaderboard-relevant field mappings
        leaderboard_fields = {
            # Basic info
            "agent_name": ["agent name", "name", "codename"],
            "agent_faction": ["agent faction", "faction", "team"],
            "level": ["level", "player level"],
            "ap": ["lifetime ap", "ap", "total ap"],
            "current_ap": ["current ap"],
            "time_span": ["time span", "period"],

            # Metrics
            "hacks": ["hacks", "portal hacks"],
            "xm_collected": ["xm collected", "xm", "total xm"],
            "portals_captured": ["portals captured", "portals"],
            "resonators_deployed": ["resonators deployed", "resonators"],
            "links_created": ["links created", "links"],
            "fields_created": ["control fields created", "fields", "control fields"],
            "mods_deployed": ["mods deployed", "mods"],
            "resonators_destroyed": ["resonators destroyed"],
            "portals_neutralized": ["portals neutralized", "neutralized"],
            "distance_walked": ["distance walked", "distance", "km walked"]
        }

        # Extract relevant data
        result = {}

        for field_name, possible_keys in leaderboard_fields.items():
            # Try to find the value for this field
            value = None
            for key in processed_data:
                if key.lower() in [pk.lower() for pk in possible_keys]:
                    value = processed_data[key]
                    break

            if value is not None:
                # Try to convert numeric values
                if field_name not in ["agent_name", "agent_faction", "time_span"]:
                    try:
                        # Remove commas and convert to int
                        clean_value = value.replace(',', '').replace(' ', '')
                        result[field_name] = int(clean_value)
                    except ValueError:
                        result[field_name] = value  # Keep as string if conversion fails
                else:
                    result[field_name] = value

        return result

    def to_dict(self) -> Dict:
        """Convert mappings to dictionary for storage."""
        return {
            mapping_id: {
                "keys": mapping.keys,
                "values": mapping.values,
                "description": mapping.description,
                "created_by": mapping.created_by,
                "is_active": mapping.is_active
            }
            for mapping_id, mapping in self.mappings.items()
        }

    def from_dict(self, data: Dict):
        """Load mappings from dictionary."""
        for mapping_id, mapping_data in data.items():
            self.mappings[mapping_id] = DataMapping(
                keys=mapping_data["keys"],
                values=mapping_data["values"],
                description=mapping_data.get("description", ""),
                created_by=mapping_data.get("created_by"),
                is_active=mapping_data.get("is_active", True)
            )


# Global instance
_mapping_manager = None

def get_mapping_manager() -> DynamicMappingManager:
    """Get the global mapping manager instance."""
    global _mapping_manager
    if _mapping_manager is None:
        _mapping_manager = DynamicMappingManager()
    return _mapping_manager