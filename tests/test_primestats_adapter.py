#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test module for primestats_adapter.py

This module contains test cases to verify the functionality of the parse_pasted_stats function
and related helper functions in the primestats_adapter module.
"""

import os
import re
import tempfile
import unittest
from unittest.mock import patch, mock_open

from primestats_adapter import parse_pasted_stats, _parse_stat_line, _normalize_faction, _extract_cycle_info, _read_current_cycle, _write_current_cycle


class TestPrimestatsAdapter(unittest.TestCase):
    """Test cases for the primestats_adapter module"""

    def setUp(self):
        """Set up test fixtures"""
        self.valid_line_with_cycle = "ALL TIME AgentName Enlightened 2023-11-01 12:34:56 16 12345678 9012345 100 200 300 400 500 600 700 800 900 1000 1100 1200 1300 1400 1500 1600 1700 1800 1900 2000 2100 2200 2300 2400 2500 2600 2700 2800 2900 3000 3100 3200 3300 3400 3500 3600 3700 3800 3900 4000 4100 4200 4300 4400 4500 4600 4700 4800 4900 5000 5100 5200 5300 5400 5500 5600 5700 +Theta 1500"
        self.valid_line_without_cycle = "ALL TIME AgentName Resistance 2023-11-01 12:34:56 16 12345678 9012345 100 200 300 400 500 600 700 800 900 1000 1100 1200 1300 1400 1500 1600 1700 1800 1900 2000 2100 2200 2300 2400 2500 2600 2700 2800 2900 3000 3100 3200 3300 3400 3500 3600 3700 3800 3900 4000 4100 4200 4300 4400 4500 4600 4700 4800 4900 5000 5100 5200 5300 5400 5500 5600 5700"
        self.valid_line_with_multiple_agents = f"""{self.valid_line_with_cycle}
ALL TIME Agent2 Resistance 2023-11-01 12:34:56 16 87654321 1234567 100 200 300 400 500 600 700 800 900 1000 1100 1200 1300 1400 1500 1600 1700 1800 1900 2000 2100 2200 2300 2400 2500 2600 2700 2800 2900 3000 3100 3200 3300 3400 3500 3600 3700 3800 3900 4000 4100 4200 4300 4400 4500 4600 4700 4800 4900 5000 5100 5200 5300 5400 5500 5600 5700 +Gamma 2000"""
        self.invalid_line_missing_date = "ALL TIME AgentName Enlightened 12:34:56 16 12345678 9012345"
        self.invalid_line_malformed = "This is not a valid stat line"
        self.header_line = "Time Span Agent Name Agent Faction Date (yyyy-mm-dd) Time (hh:mm:ss) Level Lifetime AP Current AP Unique Portals Visited Unique Portals Drone Visited Furthest Drone Distance Portals Discovered XM Collected OPR Agreements Portal Scans Uploaded Uniques Scout Controlled Resonators Deployed Links Created Control Fields Created Mind Units Captured Longest Link Ever Created Largest Control Field XM Recharged Portals Captured Unique Portals Captured Mods Deployed Hacks Drone Hacks Glyph Hack Points Completed Hackstreaks Longest Sojourner Streak Resonators Destroyed Portals Neutralized Enemy Links Destroyed Enemy Fields Destroyed Battle Beacon Combatant Drones Returned Machina Links Destroyed Machina Resonators Destroyed Machina Portals Neutralized Machina Portals Reclaimed Max Time Portal Held Max Time Link Maintained Max Link Length x Days Max Time Field Held Largest Field MUs x Days Forced Drone Recalls Distance Walked Kinetic Capsules Completed Unique Missions Completed Research Bounties Completed Research Days Completed Mission Day(s) Attended NL-1331 Meetup(s) Attended First Saturday Events Second Sunday Events +Delta Tokens +Delta Reso Points +Delta Field Points Agents Recruited Recursions Months Subscribed"
        self.multi_line_with_header = f"""{self.header_line}
{self.valid_line_with_cycle}
{self.valid_line_without_cycle}"""

    def test_normalize_faction(self):
        """Test faction normalization"""
        # Test Enlightened variations
        self.assertEqual(_normalize_faction("Enlightened"), "ENL")
        self.assertEqual(_normalize_faction("enlightened"), "ENL")
        self.assertEqual(_normalize_faction("ENL"), "ENL")
        self.assertEqual(_normalize_faction("enl"), "ENL")
        
        # Test Resistance variations
        self.assertEqual(_normalize_faction("Resistance"), "RES")
        self.assertEqual(_normalize_faction("resistance"), "RES")
        self.assertEqual(_normalize_faction("RES"), "RES")
        self.assertEqual(_normalize_faction("res"), "RES")
        
        # Test invalid faction
        self.assertIsNone(_normalize_faction("Invalid"))
        self.assertIsNone(_normalize_faction(""))

    def test_extract_cycle_info(self):
        """Test cycle information extraction"""
        # Test with cycle token and points
        parts = ["ALL", "TIME", "AgentName", "Enlightened", "2023-11-01", "12:34:56", "16", "12345678", "9012345", "100", "200", "300", "400", "500", "600", "700", "800", "900", "1000", "1100", "1200", "1300", "1400", "1500", "1600", "1700", "1800", "1900", "2000", "2100", "2200", "2300", "2400", "2500", "2600", "2700", "2800", "2900", "3000", "3100", "3200", "3300", "3400", "3500", "3600", "3700", "3800", "3900", "4000", "4100", "4200", "4300", "4400", "4500", "4600", "4700", "4800", "4900", "5000", "5100", "5200", "5300", "5400", "5500", "5600", "5700", "+Theta", "1500"]
        cycle_name, cycle_points = _extract_cycle_info(parts)
        self.assertEqual(cycle_name, "Theta")
        self.assertEqual(cycle_points, 1500)
        
        # Test with cycle token but no points
        parts = ["ALL", "TIME", "AgentName", "Enlightened", "2023-11-01", "12:34:56", "16", "12345678", "9012345", "100", "200", "300", "400", "500", "600", "700", "800", "900", "1000", "1100", "1200", "1300", "1400", "1500", "1600", "1700", "1800", "1900", "2000", "2100", "2200", "2300", "2400", "2500", "2600", "2700", "2800", "2900", "3000", "3100", "3200", "3300", "3400", "3500", "3600", "3700", "3800", "3900", "4000", "4100", "4200", "4300", "4400", "4500", "4600", "4700", "4800", "4900", "5000", "5100", "5200", "5300", "5400", "5500", "5600", "5700", "+Gamma"]
        cycle_name, cycle_points = _extract_cycle_info(parts)
        self.assertEqual(cycle_name, "Gamma")
        self.assertIsNone(cycle_points)
        
        # Test without cycle token
        parts = ["ALL", "TIME", "AgentName", "Enlightened", "2023-11-01", "12:34:56", "16", "12345678", "9012345", "100", "200", "300", "400", "500", "600", "700", "800", "900", "1000", "1100", "1200", "1300", "1400", "1500", "1600", "1700", "1800", "1900", "2000", "2100", "2200", "2300", "2400", "2500", "2600", "2700", "2800", "2900", "3000", "3100", "3200", "3300", "3400", "3500", "3600", "3700", "3800", "3900", "4000", "4100", "4200", "4300", "4400", "4500", "4600", "4700", "4800", "4900", "5000", "5100", "5200", "5300", "5400", "5500", "5600", "5700"]
        cycle_name, cycle_points = _extract_cycle_info(parts)
        self.assertIsNone(cycle_name)
        self.assertIsNone(cycle_points)

    def test_parse_stat_line_valid_with_cycle(self):
        """Test parsing a valid stat line with cycle information"""
        result = _parse_stat_line(self.valid_line_with_cycle, None)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['agent_name'], "AgentName")
        self.assertEqual(result['agent_faction'], "ENL")
        self.assertEqual(result['date'], "2023-11-01")
        self.assertEqual(result['time'], "12:34:56")
        self.assertEqual(result['level'], 16)
        self.assertEqual(result['lifetime_ap'], 12345678)
        self.assertEqual(result['current_ap'], 9012345)
        self.assertEqual(result['cycle_name'], "Theta")
        self.assertEqual(result['cycle_points'], 1500)
        self.assertEqual(result['raw_line'], self.valid_line_with_cycle)
        # Check some additional fields
        self.assertEqual(result['unique_portals_visited'], 100)
        self.assertEqual(result['unique_portals_drone_visited'], 200)
        self.assertEqual(result['furthest_drone_distance'], 300)

    def test_parse_stat_line_valid_without_cycle(self):
        """Test parsing a valid stat line without cycle information"""
        result = _parse_stat_line(self.valid_line_without_cycle, "Gamma")
        
        self.assertIsNotNone(result)
        self.assertEqual(result['agent_name'], "AgentName")
        self.assertEqual(result['agent_faction'], "RES")
        self.assertEqual(result['date'], "2023-11-01")
        self.assertEqual(result['time'], "12:34:56")
        self.assertEqual(result['level'], 16)
        self.assertEqual(result['lifetime_ap'], 12345678)
        self.assertEqual(result['current_ap'], 9012345)
        self.assertEqual(result['cycle_name'], "Gamma")  # From current_cycle parameter
        self.assertIsNone(result['cycle_points'])
        self.assertEqual(result['raw_line'], self.valid_line_without_cycle)
        # Check some additional fields
        self.assertEqual(result['unique_portals_visited'], 100)
        self.assertEqual(result['unique_portals_drone_visited'], 200)
        self.assertEqual(result['furthest_drone_distance'], 300)

    def test_parse_stat_line_invalid_missing_date(self):
        """Test parsing an invalid stat line with missing date"""
        result = _parse_stat_line(self.invalid_line_missing_date, None)
        self.assertIsNone(result)

    def test_parse_stat_line_invalid_malformed(self):
        """Test parsing a malformed stat line"""
        result = _parse_stat_line(self.invalid_line_malformed, None)
        self.assertIsNone(result)

    @patch('primestats_adapter._read_current_cycle')
    @patch('primestats_adapter._write_current_cycle')
    def test_parse_pasted_stats_with_cycle_token(self, mock_write_cycle, mock_read_cycle):
        """Test parsing pasted stats with cycle token"""
        mock_read_cycle.return_value = None
        
        results = parse_pasted_stats(self.valid_line_with_cycle)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['cycle_name'], "Theta")
        self.assertEqual(results[0]['cycle_points'], 1500)
        # Verify that current cycle was updated
        mock_write_cycle.assert_called_once_with("Theta")

    @patch('primestats_adapter._read_current_cycle')
    @patch('primestats_adapter._write_current_cycle')
    def test_parse_pasted_stats_without_cycle_token(self, mock_write_cycle, mock_read_cycle):
        """Test parsing pasted stats without cycle token"""
        mock_read_cycle.return_value = "Gamma"
        
        results = parse_pasted_stats(self.valid_line_without_cycle)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['cycle_name'], "Gamma")  # From current_cycle.txt
        self.assertIsNone(results[0]['cycle_points'])
        # Verify that current cycle was not updated
        mock_write_cycle.assert_not_called()

    @patch('primestats_adapter._read_current_cycle')
    @patch('primestats_adapter._write_current_cycle')
    def test_parse_pasted_stats_multiple_agents(self, mock_write_cycle, mock_read_cycle):
        """Test parsing pasted stats with multiple agents"""
        mock_read_cycle.return_value = None
        
        results = parse_pasted_stats(self.valid_line_with_multiple_agents)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['agent_name'], "AgentName")
        self.assertEqual(results[0]['agent_faction'], "ENL")
        self.assertEqual(results[0]['cycle_name'], "Theta")
        self.assertEqual(results[0]['cycle_points'], 1500)
        
        self.assertEqual(results[1]['agent_name'], "Agent2")
        self.assertEqual(results[1]['agent_faction'], "RES")
        self.assertEqual(results[1]['cycle_name'], "Gamma")
        self.assertEqual(results[1]['cycle_points'], 2000)
        
        # Verify that current cycle was updated to the last detected cycle
        mock_write_cycle.assert_called_with("Gamma")
        # Check that it was called twice, once for each cycle
        self.assertEqual(mock_write_cycle.call_count, 2)

    @patch('primestats_adapter._read_current_cycle')
    @patch('primestats_adapter._write_current_cycle')
    def test_parse_pasted_stats_with_header(self, mock_write_cycle, mock_read_cycle):
        """Test parsing pasted stats with header line"""
        mock_read_cycle.return_value = None
        
        results = parse_pasted_stats(self.multi_line_with_header)
        
        self.assertEqual(len(results), 2)
        # Verify that the header line was skipped
        self.assertNotEqual(results[0]['agent_name'], "Time")
        self.assertNotEqual(results[1]['agent_name'], "Time")

    @patch('primestats_adapter._read_current_cycle')
    @patch('primestats_adapter._write_current_cycle')
    def test_parse_pasted_stats_invalid_lines(self, mock_write_cycle, mock_read_cycle):
        """Test parsing pasted stats with invalid lines"""
        mock_read_cycle.return_value = None
        
        mixed_text = f"""{self.valid_line_with_cycle}
{self.invalid_line_missing_date}
{self.invalid_line_malformed}
{self.valid_line_without_cycle}"""
        
        results = parse_pasted_stats(mixed_text)
        
        # Only valid lines should be parsed
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['agent_name'], "AgentName")
        self.assertEqual(results[1]['agent_name'], "AgentName")

    def test_read_current_cycle_file_exists(self):
        """Test reading current cycle when file exists"""
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data="Theta")):
            result = _read_current_cycle()
            self.assertEqual(result, "Theta")

    def test_read_current_cycle_file_not_exists(self):
        """Test reading current cycle when file doesn't exist"""
        with patch('os.path.exists', return_value=False):
            result = _read_current_cycle()
            self.assertIsNone(result)

    def test_write_current_cycle(self):
        """Test writing current cycle to file"""
        with patch('builtins.open', mock_open()) as mock_file:
            _write_current_cycle("Gamma")
            mock_file.assert_called_once_with('current_cycle.txt', 'w')
            mock_file().write.assert_called_once_with("Gamma")

    @patch('primestats_adapter._read_current_cycle')
    @patch('primestats_adapter._write_current_cycle')
    def test_parse_pasted_stats_empty_input(self, mock_write_cycle, mock_read_cycle):
        """Test parsing empty input"""
        mock_read_cycle.return_value = None
        
        results = parse_pasted_stats("")
        self.assertEqual(len(results), 0)
        mock_write_cycle.assert_not_called()

    @patch('primestats_adapter._read_current_cycle')
    @patch('primestats_adapter._write_current_cycle')
    def test_parse_pasted_stats_whitespace_only(self, mock_write_cycle, mock_read_cycle):
        """Test parsing whitespace-only input"""
        mock_read_cycle.return_value = None
        
        results = parse_pasted_stats("   \n  \n  ")
        self.assertEqual(len(results), 0)
        mock_write_cycle.assert_not_called()

    @patch('primestats_adapter._read_current_cycle')
    @patch('primestats_adapter._write_current_cycle')
    def test_parse_pasted_stats_with_additional_fields(self, mock_write_cycle, mock_read_cycle):
        """Test parsing stat line with additional fields"""
        mock_read_cycle.return_value = None
        
        # Create a line with additional fields
        line_with_additional = "ALL TIME AgentName Enlightened 2023-11-01 12:34:56 16 12345678 9012345 100 200 300 400 500 600 700 800 900 1000 1100 1200 1300 1400 1500 1600 1700 1800 1900 2000 2100 2200 2300 2400 2500 2600 2700 2800 2900 3000 3100 3200 3300 3400 3500 3600 3700 3800 3900 4000 4100 4200 4300 4400 4500 4600 4700 4800 4900 5000 5100 5200 5300 5400 5500 5600 5700 +Theta 1500"
        
        results = parse_pasted_stats(line_with_additional)
        
        self.assertEqual(len(results), 1)
        result = results[0]
        
        # Check that additional fields are parsed
        self.assertEqual(result['unique_portals_visited'], 100)
        self.assertEqual(result['unique_portals_drone_visited'], 200)
        self.assertEqual(result['furthest_drone_distance'], 300)
        self.assertEqual(result['portals_discovered'], 400)
        self.assertEqual(result['xm_collected'], 500)

    @patch('primestats_adapter._read_current_cycle')
    @patch('primestats_adapter._write_current_cycle')
    def test_parse_pasted_stats_glm_cases(self, mock_write_cycle, mock_read_cycle):
        """Validate GLM scenarios for parse_pasted_stats"""
        base_tokens_with_cycle = self.valid_line_with_cycle.split()
        base_tokens_without_cycle = self.valid_line_without_cycle.split()
        no_seconds_tokens = base_tokens_without_cycle.copy()
        no_seconds_tokens[5] = "07:05"
        line_no_seconds = " ".join(no_seconds_tokens)
        cycle_no_points_tokens = base_tokens_with_cycle.copy()
        cycle_no_points_tokens.pop()
        line_cycle_no_points = " ".join(cycle_no_points_tokens)
        float_metric_tokens = base_tokens_with_cycle.copy()
        float_metric_tokens[11] = "300.5"
        line_float_metric = " ".join(float_metric_tokens)
        missing_metric_tokens = base_tokens_with_cycle.copy()
        missing_metric_tokens[10] = "--"
        line_missing_metric = " ".join(missing_metric_tokens)
        invalid_level_tokens = base_tokens_with_cycle.copy()
        invalid_level_tokens[6] = "--"
        line_invalid_level = " ".join(invalid_level_tokens)
        propagated_cycle_first = base_tokens_with_cycle.copy()
        propagated_cycle_first[2] = "AgentAlpha"
        propagated_cycle_first[-2] = "+Lambda"
        propagated_cycle_first[-1] = "500"
        propagated_cycle_second = base_tokens_without_cycle.copy()
        propagated_cycle_second[2] = "AgentBeta"
        propagated_cycle_input = "\n".join([
            " ".join(propagated_cycle_first),
            " ".join(propagated_cycle_second),
        ])
        test_cases = [
            {
                "name": "basic_cycle",
                "text": self.valid_line_with_cycle,
                "initial_cycle": None,
                "expected": [
                    {"agent_name": "AgentName", "cycle_name": "Theta", "cycle_points": 1500, "time": "12:34:56"},
                ],
                "expected_cycle_updates": ["Theta"],
            },
            {
                "name": "cycle_from_file",
                "text": self.valid_line_without_cycle,
                "initial_cycle": "Sigma",
                "expected": [
                    {"agent_name": "AgentName", "cycle_name": "Sigma", "cycle_points": None, "time": "12:34:56"},
                ],
                "expected_cycle_updates": [],
            },
            {
                "name": "normalized_time",
                "text": line_no_seconds,
                "initial_cycle": "Omega",
                "expected": [
                    {"agent_name": "AgentName", "cycle_name": "Omega", "cycle_points": None, "time": "07:05:00"},
                ],
                "expected_cycle_updates": [],
            },
            {
                "name": "cycle_without_points",
                "text": line_cycle_no_points,
                "initial_cycle": None,
                "expected": [
                    {"agent_name": "AgentName", "cycle_name": "Theta", "cycle_points": None, "time": "12:34:56"},
                ],
                "expected_cycle_updates": ["Theta"],
            },
            {
                "name": "float_metric",
                "text": line_float_metric,
                "initial_cycle": None,
                "expected": [
                    {"agent_name": "AgentName", "cycle_name": "Theta", "cycle_points": 1500, "furthest_drone_distance": 300.5},
                ],
                "expected_cycle_updates": ["Theta"],
            },
            {
                "name": "metric_none",
                "text": line_missing_metric,
                "initial_cycle": None,
                "expected": [
                    {"agent_name": "AgentName", "cycle_name": "Theta", "cycle_points": 1500, "unique_portals_drone_visited": None},
                ],
                "expected_cycle_updates": ["Theta"],
            },
            {
                "name": "invalid_level",
                "text": line_invalid_level,
                "initial_cycle": None,
                "expected": [],
                "expected_cycle_updates": [],
            },
            {
                "name": "cycle_propagation",
                "text": propagated_cycle_input,
                "initial_cycle": None,
                "expected": [
                    {"agent_name": "AgentAlpha", "cycle_name": "Lambda", "cycle_points": 500},
                    {"agent_name": "AgentBeta", "cycle_name": "Lambda", "cycle_points": None},
                ],
                "expected_cycle_updates": ["Lambda"],
            },
        ]
        for case in test_cases:
            mock_read_cycle.reset_mock()
            mock_write_cycle.reset_mock()
            mock_read_cycle.return_value = case["initial_cycle"]
            result = parse_pasted_stats(case["text"])
            self.assertEqual(len(result), len(case["expected"]), case["name"])
            for index, expected_record in enumerate(case["expected"]):
                record = result[index]
                for key, value in expected_record.items():
                    self.assertEqual(record.get(key), value, f"{case['name']}:{key}")
            self.assertEqual([mock_call.args[0] for mock_call in mock_write_cycle.call_args_list], case["expected_cycle_updates"], case["name"])
            self.assertEqual(mock_read_cycle.call_count, 1, case["name"])


if __name__ == '__main__':
    unittest.main()