"""
Beta Tokens Management Module

This module provides functionality to manually manage +Beta Tokens values
since they change frequently (within ~90 days) and need manual updates.
Also includes medal tier tracking and progress calculation.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass


@dataclass
class MedalTier:
    """Represents a medal tier with its requirements."""
    name: str
    required_tokens: int
    emoji: str


class BetaTokensManager:
    """Manages +Beta Tokens values for agents with medal tier tracking."""

    def __init__(self, data_file: Optional[str] = None, config_file: Optional[str] = None):
        """
        Initialize the Beta Tokens Manager.

        Args:
            data_file: Path to the beta tokens data file. If None, uses default location.
            config_file: Path to the configuration file. If None, uses default location.
        """
        if data_file is None:
            # Store in bot/data directory
            self.data_file = Path(__file__).parent.parent.parent / "data" / "beta_tokens.json"
        else:
            self.data_file = Path(data_file)

        if config_file is None:
            # Store configuration in bot/data directory
            self.config_file = Path(__file__).parent.parent.parent / "data" / "beta_tokens_config.json"
        else:
            self.config_file = Path(config_file)

        # Ensure data directory exists
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing data
        self._data = self._load_data()
        self._config = self._load_config()

    def _load_data(self) -> Dict:
        """Load beta tokens data from file."""
        if not self.data_file.exists():
            return {}

        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load beta tokens data: {e}")
            return {}

    def _load_config(self) -> Dict:
        """Load configuration data from file."""
        if not self.config_file.exists():
            # Create default configuration
            default_config = {
                "medal_tiers": {
                    "bronze": {"required_tokens": 100, "emoji": "🥉"},
                    "silver": {"required_tokens": 500, "emoji": "🥈"},
                    "gold": {"required_tokens": 1000, "emoji": "🥇"}
                },
                "task_name": "Current Beta Task",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            self._save_config(default_config)
            return default_config

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load config data: {e}")
            # Return default configuration if file is corrupted
            return {
                "medal_tiers": {
                    "bronze": {"required_tokens": 100, "emoji": "🥉"},
                    "silver": {"required_tokens": 500, "emoji": "🥈"},
                    "gold": {"required_tokens": 1000, "emoji": "🥇"}
                },
                "task_name": "Current Beta Task",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

    def _save_config(self, config: Dict) -> None:
        """Save configuration data to file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Error: Could not save config data: {e}")

    def _save_data(self) -> None:
        """Save beta tokens data to file."""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Error: Could not save beta tokens data: {e}")

    def get_beta_tokens(self, agent_name: str) -> Optional[int]:
        """
        Get beta tokens value for an agent.

        Args:
            agent_name: The agent's codename

        Returns:
            Beta tokens value or None if not found
        """
        agent_data = self._data.get(agent_name)
        if agent_data is None:
            return None
        if isinstance(agent_data, dict):
            return agent_data.get("tokens")
        return agent_data  # For backward compatibility

    def set_beta_tokens(self, agent_name: str, tokens: int, updated_by: Optional[str] = None) -> None:
        """
        Set beta tokens value for an agent.

        Args:
            agent_name: The agent's codename
            tokens: Beta tokens value
            updated_by: Optional identifier of who updated this (e.g., admin username)
        """
        self._data[agent_name] = {
            "tokens": tokens,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by
        }
        self._save_data()

    def remove_agent(self, agent_name: str) -> bool:
        """
        Remove an agent from beta tokens tracking.

        Args:
            agent_name: The agent's codename

        Returns:
            True if agent was removed, False if not found
        """
        if agent_name in self._data:
            del self._data[agent_name]
            self._save_data()
            return True
        return False

    def get_all_agents(self) -> Dict[str, Dict]:
        """
        Get all agents and their beta tokens data.

        Returns:
            Dictionary mapping agent names to their beta tokens data
        """
        return self._data.copy()

    def get_agents_with_tokens(self) -> Dict[str, int]:
        """
        Get all agents with their beta tokens values.

        Returns:
            Dictionary mapping agent names to their beta tokens values
        """
        return {agent: data["tokens"] for agent, data in self._data.items()}

    def update_tokens(self, agent_name: str, tokens: int, updated_by: Optional[str] = None) -> bool:
        """
        Update beta tokens for an agent (alias for set_beta_tokens).

        Args:
            agent_name: The agent's codename
            tokens: New beta tokens value
            updated_by: Optional identifier of who updated this

        Returns:
            True if update was successful
        """
        if tokens < 0:
            return False

        self.set_beta_tokens(agent_name, tokens, updated_by)
        return True

    def bulk_update(self, updates: Dict[str, int], updated_by: Optional[str] = None) -> Dict[str, bool]:
        """
        Bulk update beta tokens for multiple agents.

        Args:
            updates: Dictionary mapping agent names to their new beta tokens values
            updated_by: Optional identifier of who updated this

        Returns:
            Dictionary mapping agent names to success status
        """
        results = {}
        for agent_name, tokens in updates.items():
            if tokens >= 0:
                self.set_beta_tokens(agent_name, tokens, updated_by)
                results[agent_name] = True
            else:
                results[agent_name] = False

        return results

    def export_to_text(self) -> str:
        """
        Export beta tokens data as formatted text.

        Returns:
            Formatted string with all beta tokens data
        """
        if not self._data:
            return "No beta tokens data available."

        lines = ["Beta Tokens Data", "=" * 50]
        lines.append(f"{'Agent':<20} {'Tokens':<10} {'Updated At':<20} {'Updated By':<15}")
        lines.append("-" * 70)

        for agent_name, data in sorted(self._data.items()):
            tokens = data.get("tokens", 0)
            updated_at = data.get("updated_at", "Unknown")
            updated_by = data.get("updated_by", "Unknown")

            # Format datetime if possible
            try:
                dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                formatted_time = dt.strftime("%Y-%m-%d %H:%M")
            except:
                formatted_time = updated_at[:19] if len(updated_at) > 19 else updated_at

            lines.append(f"{agent_name:<20} {tokens:<10} {formatted_time:<20} {updated_by:<15}")

        return "\n".join(lines)

    def get_medal_tiers(self) -> Dict[str, MedalTier]:
        """
        Get the current medal tier configuration.

        Returns:
            Dictionary mapping tier names to MedalTier objects
        """
        tiers = {}
        for tier_name, tier_data in self._config.get("medal_tiers", {}).items():
            tiers[tier_name] = MedalTier(
                name=tier_name.capitalize(),
                required_tokens=tier_data.get("required_tokens", 0),
                emoji=tier_data.get("emoji", "🎖️")
            )
        return tiers

    def set_medal_tier_requirements(self, bronze: int, silver: int, gold: int) -> None:
        """
        Update the medal tier requirements.

        Args:
            bronze: Required tokens for bronze medal
            silver: Required tokens for silver medal
            gold: Required tokens for gold medal
        """
        self._config["medal_tiers"] = {
            "bronze": {"required_tokens": bronze, "emoji": "🥉"},
            "silver": {"required_tokens": silver, "emoji": "🥈"},
            "gold": {"required_tokens": gold, "emoji": "🥇"}
        }
        self._config["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._save_config(self._config)

    def get_token_status(self, agent_name: str) -> Tuple[Optional[int], str, Dict[str, Tuple[str, Optional[int]]]]:
        """
        Get the beta tokens status and medal progress for an agent.

        Args:
            agent_name: The agent's codename

        Returns:
            Tuple of (current_tokens, task_name, medal_progress)
            where medal_progress maps tier names to (status_message, tokens_needed)
        """
        current_tokens = self.get_beta_tokens(agent_name)
        task_name = self._config.get("task_name", "Current Beta Task")

        if current_tokens is None:
            return None, task_name, {}

        medal_tiers = self.get_medal_tiers()
        medal_progress = {}

        for tier_name, tier in sorted(medal_tiers.items(), key=lambda x: x[1].required_tokens):
            if current_tokens >= tier.required_tokens:
                # Tier achieved
                status = f"{tier.emoji} {tier.name.capitalize()} achieved"
                tokens_needed = None
            else:
                # Tier not achieved
                tokens_needed = tier.required_tokens - current_tokens
                status = f"⏳ {tokens_needed} tokens needed for {tier.name}"

            medal_progress[tier_name] = (status, tokens_needed)

        return current_tokens, task_name, medal_progress

    def format_token_status_message(self, agent_name: str) -> str:
        """
        Format the token status as a user-friendly message.

        Args:
            agent_name: The agent's codename

        Returns:
            Formatted status message
        """
        current_tokens, task_name, medal_progress = self.get_token_status(agent_name)

        if current_tokens is None:
            return f"📊 *Beta Tokens Status for {agent_name}*\n\n❌ No beta tokens data found.\n\nSubmit your stats first or contact admin to manually add your data."

        task_name = self._config.get("task_name", "Current Beta Task")

        lines = [
            f"📊 *Beta Tokens Status for {agent_name}*",
            f"🎯 Task: {task_name}",
            f"💎 Current Tokens: *{current_tokens}*",
            ""
        ]

        # Add medal progress
        achieved_count = 0
        total_tiers = len(medal_progress)

        for tier_name, (status, tokens_needed) in medal_progress.items():
            lines.append(status)
            if tokens_needed is None:
                achieved_count += 1

        lines.append("")

        # Add summary
        if achieved_count == total_tiers:
            lines.append("🏆 *All medal tiers achieved! Congratulations!*")
        else:
            lines.append(f"📈 *Progress: {achieved_count}/{total_tiers} medal tiers achieved*")

        return "\n".join(lines)

    def set_task_name(self, task_name: str) -> None:
        """
        Update the current task name.

        Args:
            task_name: The name of the current beta task
        """
        self._config["task_name"] = task_name
        self._config["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._save_config(self._config)

    def get_config_summary(self) -> str:
        """
        Get a summary of the current configuration.

        Returns:
            Formatted configuration summary
        """
        task_name = self._config.get("task_name", "Current Beta Task")
        last_updated = self._config.get("last_updated", "Unknown")

        try:
            dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
            formatted_time = dt.strftime("%Y-%m-%d %H:%M")
        except:
            formatted_time = last_updated[:19] if len(last_updated) > 19 else last_updated

        lines = [
            "⚙️ *Beta Tokens Configuration*",
            "",
            f"🎯 Current Task: {task_name}",
            f"🕐 Last Updated: {formatted_time}",
            "",
            "🏅 *Medal Requirements*:"
        ]

        medal_tiers = self.get_medal_tiers()
        for tier_name, tier in sorted(medal_tiers.items(), key=lambda x: x[1].required_tokens):
            lines.append(f"  {tier.emoji} {tier.name.capitalize()}: {tier.required_tokens:,} tokens")

        return "\n".join(lines)


# Global instance for easy access
_beta_tokens_manager = None

def get_beta_tokens_manager() -> BetaTokensManager:
    """Get the global beta tokens manager instance."""
    global _beta_tokens_manager
    if _beta_tokens_manager is None:
        _beta_tokens_manager = BetaTokensManager()
    return _beta_tokens_manager


# Convenience functions for direct access
def get_beta_tokens(agent_name: str) -> Optional[int]:
    """Get beta tokens for an agent."""
    return get_beta_tokens_manager().get_beta_tokens(agent_name)


def set_beta_tokens(agent_name: str, tokens: int, updated_by: Optional[str] = None) -> None:
    """Set beta tokens for an agent."""
    get_beta_tokens_manager().set_beta_tokens(agent_name, tokens, updated_by)


def update_beta_tokens(agent_name: str, tokens: int, updated_by: Optional[str] = None) -> bool:
    """Update beta tokens for an agent."""
    return get_beta_tokens_manager().update_tokens(agent_name, tokens, updated_by)


def get_token_status_message(agent_name: str) -> str:
    """Get formatted token status message for an agent."""
    return get_beta_tokens_manager().format_token_status_message(agent_name)


def update_medal_requirements(bronze: int, silver: int, gold: int) -> None:
    """Update medal tier requirements."""
    get_beta_tokens_manager().set_medal_tier_requirements(bronze, silver, gold)


def update_task_name(task_name: str) -> None:
    """Update the current task name."""
    get_beta_tokens_manager().set_task_name(task_name)


def get_medal_config() -> str:
    """Get current medal configuration summary."""
    return get_beta_tokens_manager().get_config_summary()