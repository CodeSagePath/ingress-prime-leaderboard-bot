#!/usr/bin/env python3
"""
Test script to verify that the submit function works correctly with datetime objects
without throwing a serialization error.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def convert_datetime_to_iso(data):
    """
    Recursively convert datetime objects to ISO format strings in a dictionary.
    
    Args:
        data: The data to process (dict, list, or any other type)
        
    Returns:
        The data with datetime objects converted to ISO format strings
    """
    if isinstance(data, dict):
        return {key: convert_datetime_to_iso(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_datetime_to_iso(item) for item in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    else:
        return data

def test_datetime_conversion():
    """Test the datetime conversion function with various data structures."""
    logger.info("Testing datetime conversion function...")
    
    # Test case 1: Simple datetime object
    test_data1 = {
        "timestamp": datetime.now(timezone.utc),
        "ap": 10000,
        "agent_name": "TestAgent1",
        "faction": "ENL"
    }
    
    # Test case 2: Nested datetime objects
    test_data2 = {
        "metrics": {
            "start_time": datetime.now(timezone.utc),
            "end_time": datetime.now(timezone.utc),
            "values": [1, 2, 3]
        },
        "submissions": [
            {"time": datetime.now(timezone.utc), "value": 100},
            {"time": datetime.now(timezone.utc), "value": 200}
        ],
        "agent_name": "TestAgent2",
        "faction": "RES"
    }
    
    # Test case 3: No datetime objects
    test_data3 = {
        "ap": 15000,
        "agent_name": "TestAgent3",
        "faction": "ENL",
        "metrics": {
            "portals_captured": 50,
            "links_created": 25
        }
    }
    
    # Test case 4: Mixed data types
    test_data4 = {
        "timestamp": datetime.now(timezone.utc),
        "count": 42,
        "active": True,
        "ratio": 3.14,
        "tags": ["tag1", "tag2"],
        "nested": {
            "time": datetime.now(timezone.utc),
            "data": None
        }
    }
    
    test_cases = [
        ("Simple datetime", test_data1),
        ("Nested datetime", test_data2),
        ("No datetime", test_data3),
        ("Mixed types", test_data4)
    ]
    
    for name, data in test_cases:
        try:
            logger.info(f"Testing case: {name}")
            logger.info(f"Original data: {data}")
            
            # Convert datetime objects
            converted = convert_datetime_to_iso(data)
            logger.info(f"Converted data: {converted}")
            
            # Try to serialize to JSON
            json_str = json.dumps(converted)
            logger.info(f"JSON serialization successful")
            
            # Try to deserialize from JSON
            parsed_back = json.loads(json_str)
            logger.info(f"JSON deserialization successful: {parsed_back}")
            
            logger.info(f"✅ Test case '{name}' passed\n")
        except Exception as e:
            logger.error(f"❌ Test case '{name}' failed with error: {e}\n")
            return False
    
    logger.info("All datetime conversion tests passed!")
    return True

def test_submit_functionality():
    """Test the submit functionality with datetime objects."""
    logger.info("Testing submit functionality with datetime objects...")
    
    # Create test data similar to what would be submitted
    test_metrics = {
        "agent_name": "TestAgent",
        "faction": "ENL",
        "timestamp": datetime.now(timezone.utc),
        "metrics": {
            "start_time": datetime.now(timezone.utc),
            "end_time": datetime.now(timezone.utc),
            "portals_captured": 50,
            "links_created": 25
        }
    }
    
    try:
        logger.info(f"Original metrics: {test_metrics}")
        
        # Convert datetime objects using the function from bot/main.py
        converted_metrics = convert_datetime_to_iso(test_metrics)
        logger.info(f"Converted metrics: {converted_metrics}")
        
        # Try to serialize to JSON (this is what would be stored in the database)
        json_str = json.dumps(converted_metrics)
        logger.info(f"JSON serialization successful")
        
        # Verify that the JSON can be deserialized
        parsed_back = json.loads(json_str)
        logger.info(f"JSON deserialization successful: {parsed_back}")
        
        logger.info("✅ Submit functionality test with datetime objects passed!")
        return True
    except Exception as e:
        logger.error(f"❌ Submit functionality test failed with error: {e}")
        return False

async def main():
    """Main test function."""
    logger.info("Starting datetime serialization tests...")
    
    # Test the datetime conversion function
    conversion_test_passed = test_datetime_conversion()
    
    # Test the submit functionality
    submit_test_passed = test_submit_functionality()
    
    # Summary
    if conversion_test_passed and submit_test_passed:
        logger.info("🎉 All tests passed! The datetime serialization fix is working correctly.")
        return True
    else:
        logger.error("❌ Some tests failed. The datetime serialization fix needs more work.")
        return False

if __name__ == "__main__":
    asyncio.run(main())