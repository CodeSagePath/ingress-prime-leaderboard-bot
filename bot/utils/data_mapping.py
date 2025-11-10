"""
Dynamic key-value mapping system for processing Ingress data submissions.

This module allows users to define custom mappings between header names and data positions,
making the bot flexible to handle different Ingress export formats.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from .field_mapper import get_field_mapper

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

    def process_key_value_data(self,
                              header_line: str,
                              data_line: str) -> Dict[str, str]:
        """
        Process data in key-value format using header and data lines.

        Args:
            header_line: Line containing field names (comma-separated)
            data_line: Line containing corresponding values (comma-separated)

        Returns:
            Dictionary mapping field names to their values
        """
        try:
            # Parse headers and values
            headers = [header.strip() for header in header_line.split(',') if header.strip()]
            values = [value.strip() for value in data_line.split(',') if value.strip()]

            # Create key-value pairs
            result = {}
            for i, header in enumerate(headers):
                if i < len(values):
                    result[header] = values[i]
                else:
                    result[header] = ""  # Default empty value if missing

            logger.debug(f"Processed key-value data: {len(result)} fields extracted")
            return result

        except Exception as e:
            logger.error(f"Error processing key-value data: {e}")
            return {}

    def create_mapping_from_headers(self,
                                   mapping_id: str,
                                   header_line: str,
                                   description: str = "",
                                   created_by: Optional[int] = None) -> bool:
        """
        Create a mapping from a header line.

        Args:
            mapping_id: Unique identifier for this mapping
            header_line: Comma-separated header names
            description: Optional description of the mapping
            created_by: Telegram user ID who created this mapping

        Returns:
            True if mapping was created successfully, False otherwise
        """
        try:
            # Parse headers
            headers = [header.strip() for header in header_line.split(',') if header.strip()]

            # Create empty values (will be filled when processing data)
            values = [""] * len(headers)

            # Store the mapping
            self.mappings[mapping_id] = DataMapping(
                keys=headers,
                values=values,
                description=description,
                created_by=created_by,
                is_active=True
            )

            logger.info(f"Created mapping '{mapping_id}' from {len(headers)} headers")
            return True

        except Exception as e:
            logger.error(f"Error creating mapping '{mapping_id}' from headers: {e}")
            return False

    def extract_leaderboard_relevant_data(self,
                                        processed_data: Dict[str, str]) -> Dict[str, any]:
        """
        Extract only leaderboard-relevant data from processed data.

        Args:
            processed_data: Dictionary of all processed key-value pairs

        Returns:
            Dictionary with only leaderboard-relevant fields
        """
        # Get the field mapper to determine which fields are supported
        field_mapper = get_field_mapper()
        supported_fields = field_mapper.get_available_leaderboard_fields()

        # Extract relevant data using exact field names
        result = {}

        for field_name in supported_fields:
            if field_name in processed_data:
                value = processed_data[field_name]

                # Basic info fields that should remain as strings
                string_fields = {"Agent Name", "Agent Faction", "Time Span"}

                if field_name not in string_fields:
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