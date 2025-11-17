#!/usr/bin/env python3
"""
Robust Data Validation Module for Ingress Prime Leaderboard Bot
Handles various data formats, validates player data, and provides detailed error reporting
"""

import json
import csv
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone
from pathlib import Path
import re

logger = logging.getLogger(__name__)


class DataValidationError(Exception):
    """Custom exception for data validation errors"""
    pass


class DataValidator:
    """
    Validate and normalize player data from various formats
    Handles inconsistent data gracefully with detailed error reporting
    """

    # Supported field mappings for different data sources
    FIELD_MAPPINGS = {
        'agent_name': ['agent_name', 'agentname', 'player_name', 'playername', 'name', 'agent'],
        'ap': ['ap', 'action_points', 'access_points', 'score', 'total_ap'],
        'hacks': ['hacks', 'total_hacks', 'hack_count', 'num_hacks'],
        'xm_recharged': ['xm_recharged', 'xm', 'xm_collected', 'total_xm', 'xm_recharge'],
        'level': ['level', 'player_level', 'agent_level', 'lvl'],
        'faction': ['faction', 'team', 'side', 'enlightened', 'resistance', 'aliens'],
        'portal_destroyed': ['portal_destroyed', 'portals_destroyed', 'destroyed_portals', 'portal_kills'],
        'resos_deployed': ['resos_deployed', 'resonators_deployed', 'deployed_resonators', 'total_deploy'],
        'mus_acquired': ['mus_acquired', 'mus', 'unique_missions', 'missions_completed', 'mission_count'],
        'timestamp': ['timestamp', 'date', 'datetime', 'submitted_at', 'created_at']
    }

    # Faction normalisation
    FACTION_NORMALIZATION = {
        'enlightened': ['enl', 'enlightened', 'green', 'aliens', 'xm', 'frog'],
        'resistance': ['res', 'resistance', 'blue', 'human', 'smurf']
    }

    @staticmethod
    def normalize_field_name(field_name: str) -> Optional[str]:
        """Normalize field names to standard fields"""
        if not field_name:
            return None

        # Clean the field name
        normalized = field_name.lower().strip().replace(' ', '_').replace('-', '_')

        # Remove common prefixes/suffixes
        normalized = re.sub(r'^(player_|agent_|user_)', '', normalized)
        normalized = re.sub(r'(_count|_total|_num)$', '', normalized)

        # Find matching standard field
        for standard_field, variants in DataValidator.FIELD_MAPPINGS.items():
            if normalized in variants:
                return standard_field

        return None

    @staticmethod
    def normalize_faction(faction_value: Any) -> Optional[str]:
        """Normalize faction to standard values"""
        if not faction_value:
            return None

        faction_str = str(faction_value).lower().strip()

        # Direct mapping
        for standard_faction, variants in DataValidator.FACTION_NORMALIZATION.items():
            if faction_str in variants:
                return standard_faction

        # Pattern matching
        if any(word in faction_str for word in ['enl', 'green', 'alien']):
            return 'enlightened'
        elif any(word in faction_str for word in ['res', 'blue', 'human']):
            return 'resistance'

        return None

    @staticmethod
    def validate_player_data(data: Dict[str, Any], strict: bool = False) -> Dict[str, Any]:
        """
        Validate and clean player data.

        Args:
            data: Raw player data dictionary
            strict: If True, required fields must be present

        Returns:
            Dictionary with 'valid': bool, 'cleaned_data': dict, 'errors': list, 'warnings': list
        """
        result = {
            'valid': True,
            'cleaned_data': {},
            'errors': [],
            'warnings': []
        }

        try:
            # Normalize field names first
            normalized_data = {}
            for field_name, value in data.items():
                normalized_field = DataValidator.normalize_field_name(field_name)
                if normalized_field:
                    # Skip duplicates - keep first occurrence
                    if normalized_field not in normalized_data:
                        normalized_data[normalized_field] = value
                elif strict:
                    result['warnings'].append(f"Unknown field ignored: {field_name}")

            # Validate required fields
            required_fields = ['agent_name', 'ap', 'hacks', 'xm_recharged', 'level', 'faction']

            for field in required_fields:
                value = normalized_data.get(field)

                if value is None or value == '':
                    if strict:
                        result['valid'] = False
                        result['errors'].append(f"Missing required field: {field}")
                    else:
                        result['warnings'].append(f"Missing optional field: {field}")
                    continue

                try:
                    # Type-specific validation
                    if field == 'agent_name':
                        cleaned_name = str(value).strip()
                        if not cleaned_name:
                            raise ValueError("Agent name cannot be empty")
                        if len(cleaned_name) > 100:
                            cleaned_name = cleaned_name[:100]
                            result['warnings'].append(f"Agent name truncated to 100 characters")
                        result['cleaned_data'][field] = cleaned_name

                    elif field == 'faction':
                        normalized_faction = DataValidator.normalize_faction(value)
                        if not normalized_faction:
                            result['warnings'].append(f"Could not determine faction: {value}")
                            result['cleaned_data'][field] = 'unknown'
                        else:
                            result['cleaned_data'][field] = normalized_faction

                    elif field in ['ap', 'hacks', 'xm_recharged', 'level', 'portal_destroyed', 'resos_deployed', 'mus_acquired']:
                        # Handle numeric fields
                        # Convert string numbers with commas, spaces, etc.
                        if isinstance(value, str):
                            value = value.replace(',', '').replace(' ', '').strip()

                        num_value = float(value)

                        # Check for negative values
                        if num_value < 0:
                            if field in ['ap', 'hacks', 'xm_recharged', 'level']:
                                raise ValueError(f"{field} cannot be negative")
                            else:
                                result['warnings'].append(f"Negative value for {field}, setting to 0")
                                num_value = 0

                        # Convert to int for whole number fields
                        if field in ['level', 'hacks', 'portal_destroyed', 'resos_deployed', 'mus_acquired']:
                            result['cleaned_data'][field] = int(round(num_value))
                        else:
                            result['cleaned_data'][field] = num_value

                except (ValueError, TypeError) as e:
                    if strict or field in required_fields[:5]:  # First 5 are critical
                        result['valid'] = False
                        result['errors'].append(f"Invalid {field}: {str(e)}")
                    else:
                        result['warnings'].append(f"Invalid {field}, skipping: {str(e)}")

            # Validate optional fields
            optional_fields = ['portal_destroyed', 'resos_deployed', 'mus_acquired', 'timestamp']

            for field in optional_fields:
                if field in normalized_data:
                    value = normalized_data[field]
                    try:
                        if field == 'timestamp':
                            # Try to parse timestamp
                            if isinstance(value, str):
                                # Try multiple timestamp formats
                                timestamp_formats = [
                                    '%Y-%m-%d %H:%M:%S',
                                    '%Y-%m-%dT%H:%M:%S',
                                    '%Y-%m-%dT%H:%M:%SZ',
                                    '%Y-%m-%d',
                                    '%Y-%m-%d %H:%M'
                                ]

                                parsed_timestamp = None
                                for fmt in timestamp_formats:
                                    try:
                                        parsed_timestamp = datetime.strptime(value, fmt)
                                        break
                                    except ValueError:
                                        continue

                                if parsed_timestamp:
                                    result['cleaned_data'][field] = parsed_timestamp.isoformat()
                                else:
                                    result['warnings'].append(f"Could not parse timestamp: {value}")
                            elif isinstance(value, datetime):
                                result['cleaned_data'][field] = value.isoformat()
                        else:
                            # Handle numeric optional fields
                            if isinstance(value, str):
                                value = value.replace(',', '').replace(' ', '').strip()

                            if value:  # Only process if not empty
                                num_value = float(value)
                                if num_value < 0:
                                    result['warnings'].append(f"Negative value for {field}, setting to 0")
                                    num_value = 0

                                result['cleaned_data'][field] = int(round(num_value))

                    except (ValueError, TypeError) as e:
                        result['warnings'].append(f"Invalid optional field {field}: {str(e)}")

            # Add metadata
            result['cleaned_data']['validated_at'] = datetime.now(timezone.utc).isoformat()
            result['cleaned_data']['validation_version'] = '1.0'

        except Exception as e:
            result['valid'] = False
            result['errors'].append(f"Unexpected validation error: {str(e)}")
            logger.error(f"Data validation error: {e}", exc_info=True)

        return result

    @staticmethod
    def validate_batch(data_list: List[Dict[str, Any]], strict: bool = False) -> Dict[str, Any]:
        """
        Validate multiple player records.

        Args:
            data_list: List of player data dictionaries
            strict: Enable strict validation mode

        Returns:
            Dictionary with validation statistics and results
        """
        if not isinstance(data_list, list):
            return {
                'valid': False,
                'total_count': 0,
                'valid_count': 0,
                'invalid_count': 0,
                'warning_count': 0,
                'results': [],
                'summary_errors': ['Input is not a list'],
                'global_warnings': []
            }

        results = []
        valid_count = 0
        invalid_count = 0
        warning_count = 0
        global_warnings = []

        for i, record in enumerate(data_list):
            if not isinstance(record, dict):
                results.append({
                    'index': i,
                    'valid': False,
                    'cleaned_data': None,
                    'errors': ['Record is not a dictionary'],
                    'warnings': []
                })
                invalid_count += 1
                continue

            validation_result = DataValidator.validate_player_data(record, strict)
            validation_result['index'] = i
            results.append(validation_result)

            if validation_result['valid']:
                valid_count += 1
            else:
                invalid_count += 1

            warning_count += len(validation_result['warnings'])

        # Check for duplicate agent names
        agent_names = []
        for result in results:
            if result['valid'] and 'cleaned_data' in result:
                agent_name = result['cleaned_data'].get('agent_name')
                if agent_name:
                    agent_names.append(agent_name.lower())

        duplicates = [name for name in set(agent_names) if agent_names.count(name) > 1]
        if duplicates:
            global_warnings.append(f"Found {len(duplicates)} duplicate agent names: {duplicates[:5]}")

        return {
            'valid': invalid_count == 0,
            'total_count': len(data_list),
            'valid_count': valid_count,
            'invalid_count': invalid_count,
            'warning_count': warning_count,
            'results': results,
            'summary_errors': [],
            'global_warnings': global_warnings,
            'duplicate_agent_names': duplicates
        }

    @staticmethod
    def get_validation_summary(batch_result: Dict[str, Any]) -> str:
        """Generate a human-readable validation summary"""
        if batch_result['total_count'] == 0:
            return "❌ No records to validate"

        summary_parts = []

        # Success rate
        success_rate = (batch_result['valid_count'] / batch_result['total_count']) * 100
        if success_rate == 100:
            summary_parts.append(f"✅ All {batch_result['total_count']} records are valid")
        elif success_rate >= 80:
            summary_parts.append(f"⚠️ {batch_result['valid_count']}/{batch_result['total_count']} records valid ({success_rate:.1f}%)")
        else:
            summary_parts.append(f"❌ Only {batch_result['valid_count']}/{batch_result['total_count']} records valid ({success_rate:.1f}%)")

        # Warnings
        if batch_result['warning_count'] > 0:
            summary_parts.append(f"⚠️ {batch_result['warning_count']} warnings found")

        # Global issues
        if batch_result['global_warnings']:
            summary_parts.extend([f"🔸 {warning}" for warning in batch_result['global_warnings'][:3]])

        # Top errors
        error_counts = {}
        for result in batch_result['results']:
            for error in result['errors']:
                error_counts[error] = error_counts.get(error, 0) + 1

        if error_counts:
            top_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            summary_parts.extend([f"🔸 {error} ({count} times)" for error, count in top_errors])

        return "\n".join(summary_parts)


# Convenience function for quick validation
def validate_players_data(data: Union[Dict, List[Dict]], strict: bool = False) -> Dict[str, Any]:
    """
    Quick validation function that accepts single record or batch

    Args:
        data: Single player dict or list of player dicts
        strict: Enable strict validation

    Returns:
        Validation result dictionary
    """
    if isinstance(data, dict):
        result = DataValidator.validate_player_data(data, strict)
        return {
            'valid': result['valid'],
            'results': [result],
            'total_count': 1,
            'valid_count': 1 if result['valid'] else 0,
            'invalid_count': 0 if result['valid'] else 1,
            'warning_count': len(result['warnings']),
            'global_warnings': [],
            'summary_errors': result['errors']
        }
    elif isinstance(data, list):
        return DataValidator.validate_batch(data, strict)
    else:
        return {
            'valid': False,
            'results': [],
            'total_count': 0,
            'valid_count': 0,
            'invalid_count': 0,
            'warning_count': 0,
            'global_warnings': [],
            'summary_errors': ['Input must be a dictionary or list of dictionaries']
        }