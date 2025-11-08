import asyncio
import logging
from sqlalchemy import text
import sqlite3
import re
from datetime import datetime, timedelta, timezone
import sys
from typing import Any
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from redis import Redis
from rq import Queue
import uvicorn
from sqlalchemy import delete, select, func, case
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import Update
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings, load_settings, validate_settings, print_environment_summary
from .dashboard import create_dashboard_app
from .database import build_engine, build_session_factory, init_models, session_scope
from .health import get_health_checker, create_health_check_response
from .jobs.deletion import cleanup_expired_group_messages, schedule_message_deletion
from .jobs.backup import perform_backup, manual_backup_command
from .models import Agent, GroupMessage, GroupPrivacyMode, GroupSetting, PendingAction, Submission, WeeklyStat, UserSetting
from .services.leaderboard import get_leaderboard
from .utils.beta_tokens import get_token_status_message, update_medal_requirements, update_task_name, get_medal_config

logger = logging.getLogger(__name__)

CURRENT_CYCLE_FILE = Path(__file__).resolve().parent.parent / "current_cycle.txt"
AGENTS_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "agents.db"


def _ensure_agents_table() -> None:
    with sqlite3.connect(AGENTS_DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY,
                time_span TEXT,
                agent_name TEXT,
                agent_faction TEXT,
                date TEXT,
                time TEXT,
                cycle_name TEXT,
                cycle_points INTEGER
            )
            """
        )
        connection.commit()


def escape_markdown_v2(text: str) -> str:
    """
    Escape special characters for Telegram's MarkdownV2 format.
    
    In MarkdownV2, the following characters must be escaped with a preceding backslash:
    _ * [ ] ( ) ~ ` > # + - = | { } . !
    
    Args:
        text: The input text to escape
        
    Returns:
        The text with all special characters properly escaped
    """
    # List of characters that need to be escaped in MarkdownV2
    special_chars = r'_*[]()~`>#+-=|{}.,!'
    
    # Escape each special character by adding a backslash before it
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


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


_ensure_agents_table()




async def get_agent_rank(session_factory, agent_id: int, time_span: str | None = None) -> int | None:
    """Get the current rank of an agent."""
    async with session_scope(session_factory) as session:
        # Main query to get all agents ranked by AP
        stmt = (
            select(
                Agent.id,
                func.sum(Submission.ap).label("total_ap"),
            )
            .join(Submission, Submission.agent_id == Agent.id)
        )

        if time_span is not None:
            stmt = stmt.where(Submission.time_span == time_span)

        stmt = (
            stmt.group_by(Agent.id)
            .order_by(
                func.sum(Submission.ap).desc(),
                Agent.codename
            )
        )

        result = await session.execute(stmt)
        agents = result.all()

        # Find the rank of the specified agent
        for rank, (agent_id_result, _) in enumerate(agents, start=1):
            if agent_id_result == agent_id:
                return rank

        return None


def save_to_db(parsed_data: dict) -> bool:
    cycle_points = parsed_data.get("cycle_points")
    if cycle_points is not None:
        try:
            cycle_points = int(cycle_points)
        except (TypeError, ValueError):
            cycle_points = None
    with sqlite3.connect(AGENTS_DB_PATH) as connection:
        # Remove duplicate check - allow agents to submit updated stats anytime
        # Players should be able to update their data multiple times
        connection.execute(
            """
            INSERT INTO agents (
                time_span,
                agent_name,
                agent_faction,
                date,
                time,
                cycle_name,
                cycle_points
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parsed_data.get("time_span"),
                parsed_data.get("agent_name"),
                parsed_data.get("agent_faction"),
                parsed_data.get("date"),
                parsed_data.get("time"),
                parsed_data.get("cycle_name"),
                cycle_points,
            ),
        )
        connection.commit()
    return True


async def save_submission_to_main_db(session, entry: dict, message) -> None:
    """Save submission data to the main SQLAlchemy database."""
    from datetime import datetime

    # Get or create agent
    telegram_id = message.from_user.id if message.from_user else None
    agent_name = entry.get('agent_name')
    faction = entry.get('agent_faction', '').upper()

    # Check if agent already exists
    from sqlalchemy import select
    result = await session.execute(
        select(Agent).where(Agent.telegram_id == telegram_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        # Create new agent
        agent = Agent(
            telegram_id=telegram_id,
            codename=agent_name,
            faction=faction,
            created_at=datetime.now(timezone.utc)
        )
        session.add(agent)
        await session.flush()

    # Create submission record (allow multiple submissions for updates)
    try:
        ap = int(str(entry.get('ap', entry.get('lifetime_ap', 0))).replace(',', ''))
    except (ValueError, TypeError):
        ap = 0

    submission = Submission(
        agent_id=agent.id,
        chat_id=message.chat_id if message.chat_id else None,
        time_span=entry.get('time_span', 'ALL TIME'),
        ap=ap,
        metrics=entry,  # Store all metrics as JSON
        submitted_at=datetime.now(timezone.utc)
    )

    session.add(submission)
    logger.info(f"Saved submission for agent {agent_name} ({faction}) with AP {ap}")


async def _get_latest_cycle_name_async() -> str | None:
    def _query() -> str | None:
        with sqlite3.connect(AGENTS_DB_PATH) as connection:
            row = connection.execute(
                """
                SELECT cycle_name
                FROM agents
                WHERE cycle_name IS NOT NULL AND cycle_name != ''
                ORDER BY rowid DESC
                LIMIT 1
                """
            ).fetchone()
            return row[0] if row else None
    return await asyncio.to_thread(_query)


async def _fetch_cycle_leaderboard(
    limit: int,
    *,
    faction: str | None = None,
    cycle_name: str | None = None,
    since: datetime | None = None,
) -> list[tuple[str, str, int]]:
    since_value = since.strftime("%Y-%m-%d %H:%M:%S") if since else None

    def _query() -> list[tuple[str, str, int]]:
        with sqlite3.connect(AGENTS_DB_PATH) as connection:
            connection.row_factory = sqlite3.Row
            sql = [
                "SELECT agent_name, agent_faction, SUM(cycle_points) AS total_points",
                "FROM agents",
                "WHERE cycle_points IS NOT NULL",
            ]
            params: list[Any] = []
            if faction:
                sql.append("AND agent_faction = ?")
                params.append(faction)
            if cycle_name:
                sql.append("AND cycle_name = ?")
                params.append(cycle_name)
            if since_value:
                sql.append("AND date IS NOT NULL AND date != ''")
                sql.append("AND time IS NOT NULL AND time != ''")
                sql.append("AND datetime(date || ' ' || time) >= ?")
                params.append(since_value)
            sql.append("GROUP BY agent_name, agent_faction")
            sql.append("ORDER BY total_points DESC, agent_name ASC")
            sql.append("LIMIT ?")
            params.append(limit)
            query = " ".join(sql)
            rows = connection.execute(query, params).fetchall()
        results: list[tuple[str, str, int]] = []
        for row in rows:
            total_points = row["total_points"]
            if total_points is None:
                continue
            results.append(
                (
                    row["agent_name"],
                    row["agent_faction"],
                    int(total_points),
                )
            )
        return results

    return await asyncio.to_thread(_query)


def _format_cycle_leaderboard(
    rows: list[tuple[str, str, int]],
    header: str,
    text_only_mode: bool,
) -> tuple[str, dict[str, Any]]:
    if text_only_mode:
        lines = [header]
        for index, (name, faction, points) in enumerate(rows, start=1):
            lines.append(f"{index}. {name} [{faction}] - {points:,} cycle points")
        return "\n".join(lines), {}
    lines = [f"🏅 {header} 🏅"]
    for index, (name, faction, points) in enumerate(rows, start=1):
        lines.append(f"{index}. {name} [{faction}] — {points:,} cycle points")
    return "\n".join(lines), {}


async def _send_cycle_leaderboard(
    update: Update,
    settings: Settings,
    rows: list[tuple[str, str, int]],
    header: str,
) -> None:
    if not rows:
        await update.message.reply_text("No data available.")
        return
    text, kwargs = _format_cycle_leaderboard(rows, header, settings.text_only_mode)
    await update.message.reply_text(text, **kwargs)


# Constants for time span aliases
TIME_SPAN_ALIASES = {
    "ALL": "ALL TIME",
    "ALL TIME": "ALL TIME",
    "WEEKLY": "WEEKLY",
    "WEEK": "WEEKLY",
    "MONTHLY": "MONTHLY",
    "MONTH": "MONTHLY",
}

SPACE_SEPARATED_COLUMN_SETS: tuple[tuple[str, ...], ...] = (
    (
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
        "Overclock Hack Points",
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
        "First Saturday Events",
        "Second Sunday Events",
        "OPR Live Events",
        "+Delta Tokens",
        "+Delta Reso Points",
        "+Delta Field Points",
        "Recursions",
        "Months Subscribed",
    ),
    (
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
        "NL-1331 Meetup(s) Attended",
        "First Saturday Events",
        "Second Sunday Events",
        "OPR Live Events",
        "+Beta Tokens",
        "Recursions",
    ),
    (
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
        "NL-1331 Meetup(s) Attended",
        "First Saturday Events",
        "Second Sunday Events",
        "OPR Live Events",
        "+Beta Tokens",
        "Recursions",
        "Months Subscribed",
    ),
)

SPACE_SEPARATED_COLUMNS = SPACE_SEPARATED_COLUMN_SETS[0]

SPACE_SEPARATED_IGNORED_COLUMNS: set[str] = {
    "+Delta Tokens",
    "+Delta Reso Points",
    "+Delta Field Points",
}

SPACE_SEPARATED_HEADER_LINE = " ".join(SPACE_SEPARATED_COLUMNS)
SPACE_SEPARATED_HEADER_MAP = {" ".join(columns): columns for columns in SPACE_SEPARATED_COLUMN_SETS}

TIME_SPAN_VALUES = {
    "ALL TIME",
    "LAST 7 DAYS",
    "LAST 30 DAYS",
    "PAST 7 DAYS",
    "PAST 30 DAYS",
    "THIS WEEK",
    "THIS MONTH",
    "LAST WEEK",
    "LAST MONTH",
    "WEEKLY",
    "MONTHLY",
    "DAILY",
}

TIME_SPAN_ALIASES = {value.upper(): value for value in TIME_SPAN_VALUES}

FACTION_ALIASES = {
    "ENLIGHTENED": "ENL",
    "RESISTANCE": "RES",
    "ENL": "ENL",
    "RES": "RES",
    "MACHINA": "MACHINA",
}

FACTION_DISPLAY_NAMES = {
    "ENL": "Enlightened",
    "RES": "Resistance",
}

SETTINGS_MENU, SETTINGS_SELECT, SETTINGS_VALUE = range(3)
BROADCAST_MESSAGE, BROADCAST_CONFIRM = range(2)


def parse_submission(payload: str) -> tuple[int, dict[str, Any]]:
    parts = [segment.strip() for segment in re.split(r"[;\n]+|\s{2,}", payload) if segment.strip()]
    data: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            raise ValueError("Entries must be provided as key=value pairs")
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key or not value:
            raise ValueError("Invalid entry")
        data[key] = value
    if "ap" not in data:
        raise ValueError("Missing ap value")
    try:
        ap = int(data.pop("ap"))
    except ValueError as exc:
        raise ValueError("ap must be an integer") from exc
    metrics: dict[str, Any] = {}
    for key, value in data.items():
        try:
            metrics[key] = int(value)
            continue
        except ValueError:
            pass
        try:
            metrics[key] = float(value)
            continue
        except ValueError:
            pass
        metrics[key] = value
    return ap, metrics


def _create_flexible_header_map(header_line: str) -> tuple[str, ...]:
    """
    Create a flexible header mapping that can handle varying column configurations.

    This function tries to match the provided header line against known column sets,
    but also handles cases where columns are missing, in different order, or have slight variations.
    """
    # First try exact match with existing header maps
    headers_tuple = SPACE_SEPARATED_HEADER_MAP.get(header_line)
    if headers_tuple:
        return headers_tuple

    # If no exact match, try to parse flexible headers
    # The challenge is that column names can be multi-word but are separated by spaces
    # We need to intelligently reconstruct the column boundaries

    # Start with known column sets and try to match what we can
    template_columns = list(SPACE_SEPARATED_COLUMN_SETS[0])

    # Define essential columns that must be present
    essential_columns = ["Time Span", "Agent Name", "Agent Faction"]

    # Try to match essential columns in the header line
    found_essential = []
    remaining_header = header_line

    for essential in essential_columns:
        if essential in remaining_header:
            found_essential.append(essential)
            remaining_header = remaining_header.replace(essential, "", 1).strip()

    if len(found_essential) < 3:
        # Try case-insensitive matching
        remaining_header_lower = header_line.lower()
        for essential in essential_columns:
            if essential.lower() in remaining_header_lower:
                found_essential.append(essential)
                remaining_header_lower = remaining_header_lower.replace(essential.lower(), "", 1).strip()

        if len(found_essential) < 3:
            raise ValueError(f"Missing essential columns. Could not find: Time Span, Agent Name, and Agent Faction")

    # Now try to match other known columns
    final_headers = found_essential.copy()
    remaining_tokens = remaining_header.split()

    # Try to match remaining tokens against known column patterns
    i = 0
    while i < len(remaining_tokens):
        token = remaining_tokens[i]
        best_match = None
        max_match_length = 0

        # Look for the longest possible match starting at this position
        for template_col in template_columns:
            if template_col in found_essential or template_col in final_headers:
                continue

            # Check if this column starts with the current token
            if template_col.startswith(token):
                # Look ahead to see if we can match more tokens
                words_needed = len(template_col.split())
                if i + words_needed <= len(remaining_tokens):
                    candidate_tokens = remaining_tokens[i:i + words_needed]
                    candidate = " ".join(candidate_tokens)
                    if candidate == template_col:
                        if len(candidate) > max_match_length:
                            best_match = candidate
                            max_match_length = len(candidate)

        if best_match:
            final_headers.append(best_match)
            i += len(best_match.split())
        else:
            # Unknown column - add it as is
            final_headers.append(token)
            i += 1

    return tuple(final_headers)


def _parse_space_separated_dataset(lines: list[str]) -> dict[str, str]:
    header_line = lines[0]

    # Try to get exact match first
    headers_tuple = SPACE_SEPARATED_HEADER_MAP.get(header_line)

    # If no exact match, try flexible mapping
    if not headers_tuple:
        try:
            headers_tuple = _create_flexible_header_map(header_line)
        except ValueError as e:
            raise ValueError(f"Unsupported header format: {e}")

    headers = list(headers_tuple)
    data_line = next((line for line in lines[1:] if line.strip()), None)
    if data_line is None:
        raise ValueError("Data must contain at least one data row")
    if not data_line.split():
        raise ValueError("Data row is empty")

    # Try to parse with the exact headers first
    row_map = _parse_space_separated_row(data_line, headers)
    if row_map is None:
        # If that fails, try flexible parsing
        row_map = _parse_space_separated_row_flexible(data_line, headers)
        if row_map is None:
            raise ValueError("Data row has unexpected number of columns")

    data_dict: dict[str, str] = {}
    for column in headers:
        if column in SPACE_SEPARATED_IGNORED_COLUMNS:
            continue
        if column in row_map:
            data_dict[column] = row_map[column]
    return data_dict


def _normalize_header(header: str) -> str:
    header = header.strip()
    header = header.replace("(", "").replace(")", "")
    header = header.replace("/", " ")
    header = header.replace("-", " ")
    header = re.sub(r"[^A-Za-z0-9]+", " ", header)
    normalized = re.sub(r"\s+", "_", header.strip().lower())
    if normalized == "date_yyyy_mm_dd":
        return "date"
    if normalized == "time_hh_mm_ss":
        return "time"
    return normalized


def _convert_numeric_value(value: str) -> Any:
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        return value
    if cleaned.isdigit():
        return int(cleaned)
    try:
        return float(cleaned)
    except ValueError:
        return value


def _convert_cycle_points(value: str) -> int | None:
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return None


def _parse_space_separated_row(row: str, headers: list[str]) -> dict[str, str] | None:
    tokens = row.split()
    if not tokens:
        return None
    time_span = None
    position = 0
    max_span_tokens = min(len(tokens), 4)
    for end in range(max_span_tokens, 0, -1):
        candidate = " ".join(tokens[:end])
        upper_candidate = candidate.upper()
        if upper_candidate in TIME_SPAN_ALIASES:
            time_span = TIME_SPAN_ALIASES[upper_candidate]
            position = end
            break
    if time_span is None:
        return None
    name_tokens: list[str] = []
    while position < len(tokens) and tokens[position].upper() not in FACTION_ALIASES:
        name_tokens.append(tokens[position])
        position += 1
    if not name_tokens or position >= len(tokens):
        return None
    faction_token = tokens[position]
    position += 1
    if faction_token.upper() not in FACTION_ALIASES:
        return None
    agent_name = " ".join(name_tokens)
    if len(tokens) - position < 3:
        return None
    date_token = tokens[position]
    position += 1
    time_token = tokens[position]
    position += 1
    level_token = tokens[position]
    position += 1
    remaining_tokens = tokens[position:]
    if len(remaining_tokens) != len(headers) - 6:
        return None
    data: dict[str, str] = {
        headers[0]: time_span,
        headers[1]: agent_name,
        headers[2]: faction_token,
        headers[3]: date_token,
        headers[4]: time_token,
        headers[5]: level_token,
    }
    for column, value in zip(headers[6:], remaining_tokens):
        data[column] = value
    return data


def _parse_space_separated_row_flexible(row: str, headers: list[str]) -> dict[str, str] | None:
    """
    Flexible row parsing that can handle varying numbers of columns.

    This function tries to map the data row to the available headers, allowing for
    missing columns or columns in different order.
    """
    tokens = row.split()
    if not tokens:
        return None

    # Find time span
    time_span = None
    position = 0
    max_span_tokens = min(len(tokens), 4)
    for end in range(max_span_tokens, 0, -1):
        candidate = " ".join(tokens[:end])
        upper_candidate = candidate.upper()
        if upper_candidate in TIME_SPAN_ALIASES:
            time_span = TIME_SPAN_ALIASES[upper_candidate]
            position = end
            break
    if time_span is None:
        return None

    # Find agent name and faction
    name_tokens: list[str] = []
    while position < len(tokens) and tokens[position].upper() not in FACTION_ALIASES:
        name_tokens.append(tokens[position])
        position += 1
    if not name_tokens or position >= len(tokens):
        return None

    faction_token = tokens[position]
    position += 1
    if faction_token.upper() not in FACTION_ALIASES:
        return None

    agent_name = " ".join(name_tokens)

    # Find date, time, and level
    if len(tokens) - position < 3:
        return None

    date_token = tokens[position]
    position += 1
    time_token = tokens[position]
    position += 1
    level_token = tokens[position]
    position += 1

    remaining_tokens = tokens[position:]
    data: dict[str, str] = {
        "Time Span": time_span,
        "Agent Name": agent_name,
        "Agent Faction": faction_token,
        "Date (yyyy-mm-dd)": date_token,
        "Time (hh:mm:ss)": time_token,
        "Level": level_token,
    }

    # Map remaining tokens to headers, allowing for flexibility
    expected_remaining_headers = [h for h in headers if h not in data]

    if len(remaining_tokens) != len(expected_remaining_headers):
        # If the numbers don't match exactly, try to map as many as possible
        for i, (header, value) in enumerate(zip(expected_remaining_headers, remaining_tokens)):
            data[header] = value
        # Add any extra tokens as "Unknown Column X"
        for i, extra_token in enumerate(remaining_tokens[len(expected_remaining_headers):], 1):
            data[f"Unknown Column {i}"] = extra_token
    else:
        # Perfect match - map one-to-one
        for header, value in zip(expected_remaining_headers, remaining_tokens):
            data[header] = value

    return data


def _process_field_value(key: str, value: str) -> Any:
    if key == "time_span":
        upper_value = value.upper()
        return TIME_SPAN_ALIASES.get(upper_value, value)
    if key == "agent_faction":
        upper_value = value.upper()
        return FACTION_ALIASES.get(upper_value, upper_value)
    if key == "time":
        if ":" in value and len(value) >= 5:
            return value[:5]
        return value
    if key == "date":
        return value
    return _convert_numeric_value(value)


def _normalize_row(row_map: dict[str, str], headers: list[str], cycle_index: int, cycle_header: str) -> dict[str, Any] | None:
    normalized: dict[str, Any] = {"original_header": cycle_header, "cycle_name": cycle_header}
    cycle_value = _convert_cycle_points(row_map.get(cycle_header, ""))
    # Handle missing cycle points gracefully - set to 0 instead of rejecting the entire entry
    if cycle_value is None:
        cycle_value = 0
    normalized["cycle_points"] = cycle_value
    for index, header in enumerate(headers):
        if index == cycle_index:
            continue
        key = _normalize_header(header)
        normalized[key] = _process_field_value(key, row_map.get(header, ""))
    return normalized


def parse_ingress_message(text: str) -> dict[str, Any] | list[dict[str, Any]] | None:
    if not text or not text.strip():
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    header_line = lines[0]
    use_tabs = "\t" in header_line
    if use_tabs:
        headers = [part.strip() for part in header_line.split("\t")]
    else:
        headers_tuple = SPACE_SEPARATED_HEADER_MAP.get(header_line)
        if not headers_tuple:
            # Try flexible mapping for non-tabular data
            try:
                headers_tuple = _create_flexible_header_map(header_line)
            except ValueError:
                return None
    headers = [column for column in headers_tuple if column not in SPACE_SEPARATED_IGNORED_COLUMNS]
    cycle_indices = [index for index, header in enumerate(headers) if header.startswith("+")]
    if not cycle_indices:
        return None
    cycle_index = cycle_indices[0]
    cycle_header = headers[cycle_index]
    stored_cycle = ""
    try:
        stored_cycle = CURRENT_CYCLE_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        pass
    except OSError:
        stored_cycle = ""
    if stored_cycle != cycle_header:
        try:
            CURRENT_CYCLE_FILE.write_text(cycle_header, encoding="utf-8")
        except OSError:
            logger.warning("Failed to update current cycle file")
    normalized_headers = {header: _normalize_header(header) for header in headers}
    date_headers = [header for header, normalized in normalized_headers.items() if normalized == "date"]
    time_headers = [header for header, normalized in normalized_headers.items() if normalized == "time"]
    results: list[dict[str, Any]] = []
    for data_line in lines[1:]:
        if not data_line:
            continue
        if use_tabs:
            values = [part.strip() for part in data_line.split("\t")]
            if len(values) != len(headers):
                continue
            row_map = dict(zip(headers, values))
        else:
            row_map = _parse_space_separated_row(data_line, headers)
            if row_map is None:
                # Try flexible parsing if exact parsing fails
                row_map = _parse_space_separated_row_flexible(data_line, headers)
                if row_map is None:
                    continue
        date_value = ""
        for header in date_headers:
            if header in row_map:
                date_value = (row_map.get(header) or "").strip()
                if date_value:
                    break
        time_value_raw = ""
        for header in time_headers:
            if header in row_map:
                time_value_raw = (row_map.get(header) or "").strip()
                if time_value_raw:
                    break
        if not date_value or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
            continue
        time_candidate = time_value_raw[:5] if time_value_raw else ""
        if not time_candidate or not re.fullmatch(r"\d{2}:\d{2}", time_candidate):
            continue
        normalized = _normalize_row(row_map, headers, cycle_index, cycle_header)
        if normalized is None:
            continue
        results.append(normalized)
    if not results:
        return None
    if len(results) == 1:
        return results[0]
    return results


def parse_tab_space_data(data: str) -> tuple[int, dict[str, Any], str]:
    """
    Parse tab/space-separated data from Ingress Prime leaderboard.
    
    Args:
        data: The raw data string containing header and data rows
        
    Returns:
        A tuple containing:
        - ap: The AP value as an integer
        - metrics: A dictionary of all other metrics
        - time_span: The time span value (e.g., "ALL TIME", "WEEKLY")
        
    Raises:
        ValueError: If the data format is invalid or required fields are missing
    """
    lines = [line.strip() for line in data.strip().split('\n') if line.strip()]
    if len(lines) < 2:
        raise ValueError("Data must contain at least a header and one data row")
    header_line = lines[0]
    data_dict: dict[str, str]
    if '\t' in header_line:
        headers = tuple(part.strip() for part in header_line.split('\t'))
        matched_columns = next((columns for columns in SPACE_SEPARATED_COLUMN_SETS if columns == headers), None)
        if matched_columns is None:
            # Try flexible mapping for tab-separated data
            try:
                matched_columns = _create_flexible_header_map(header_line)
            except ValueError as e:
                raise ValueError(f"Unsupported header format: {e}")
        values = [part.strip() for part in lines[1].split('\t')]
        if len(values) != len(matched_columns):
            # Try flexible parsing if the counts don't match exactly
            data_dict = {}
            for i, (header, value) in enumerate(zip(matched_columns, values)):
                data_dict[header] = value
            # Add any extra values as unknown columns
            for i, extra_value in enumerate(values[len(matched_columns):], 1):
                data_dict[f"Unknown Column {i}"] = extra_value
        else:
            data_dict = {column: value for column, value in zip(matched_columns, values) if column not in SPACE_SEPARATED_IGNORED_COLUMNS}
    else:
        data_dict = _parse_space_separated_dataset(lines)
    if "Agent Name" not in data_dict:
        raise ValueError("Missing required field: Agent Name")
    if "Agent Faction" not in data_dict:
        raise ValueError("Missing required field: Agent Faction")
    if "Lifetime AP" not in data_dict:
        raise ValueError("Missing required field: Lifetime AP")
    faction_token = data_dict["Agent Faction"]
    faction_key = faction_token.upper()
    if faction_key not in FACTION_ALIASES:
        raise ValueError(f"Unknown faction: {faction_token}")
    faction = FACTION_ALIASES[faction_key]
    try:
        ap = int(data_dict["Lifetime AP"].replace(",", ""))
    except ValueError as exc:
        raise ValueError(f"Invalid AP value: {data_dict['Lifetime AP']}") from exc
    time_span = data_dict.get("Time Span", "ALL TIME")
    metrics: dict[str, Any] = {
        "agent_name": data_dict["Agent Name"],
        "agent_faction": faction,
        "faction": faction,
        "time_span": time_span,
    }
    if "Date (yyyy-mm-dd)" in data_dict and "Time (hh:mm:ss)" in data_dict:
        from datetime import datetime
        date_str = data_dict["Date (yyyy-mm-dd)"]
        time_str = data_dict["Time (hh:mm:ss)"]
        try:
            metrics["timestamp"] = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError(f"Invalid date/time format: {date_str} {time_str}") from exc
    skip_headers = {
        "Agent Name",
        "Agent Faction",
        "Lifetime AP",
        "Time Span",
        "Date (yyyy-mm-dd)",
        "Time (hh:mm:ss)",
    }
    for header, value in data_dict.items():
        if header in skip_headers:
            continue
        key = _normalize_header(header)
        normalized_value = _convert_numeric_value(value)
        metrics[key] = normalized_value
        if key == "current_ap":
            metrics["ap"] = normalized_value
    return ap, metrics, time_span


async def handle_ingress_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return
    text = message.text or message.caption or ""
    if not text.strip():
        return

    # Check if this is a reply to a submit instruction (improved user experience)
    is_reply_to_submit = False
    if message.reply_to_message and message.reply_to_message.text:
        reply_text = message.reply_to_message.text.lower()
        if "stats submission" in reply_text or "ingress prime export data" in reply_text:
            is_reply_to_submit = True

    chat = getattr(update, "effective_chat", None)
    chat_type = getattr(chat, "type", None)

    # For groups, require bot mention unless it's a reply to submit instructions
    if chat_type in {"group", "supergroup"} and not is_reply_to_submit:
        bot_username = context.bot_data.get("bot_username")
        if not bot_username:
            me = await context.bot.get_me()
            bot_username = me.username or ""
            context.bot_data["bot_username"] = bot_username
        if not bot_username:
            return
        if f"@{bot_username.lower()}" not in text.lower():
            return

    # Check if this looks like Ingress Prime data (has common patterns)
    is_ingress_data = (
        "time span" in text.lower() and
        "agent name" in text.lower() and
        ("lifetime ap" in text.lower() or "all time" in text.lower())
    )

    if not is_ingress_data and not is_reply_to_submit:
        # Only provide helpful error if it's clearly not ingress data
        return

    parsed = parse_ingress_message(text)
    if not parsed:
        # Provide more helpful error messages
        if is_ingress_data:
            error_msg = (
                "❌ *Data format issue detected*\n\n"
                "Please make sure you're pasting the complete data from Ingress Prime:\n"
                "• Include both the header line (Time Span Agent Name...)\n"
                "• Include your data line (ALL TIME YourName...)\n"
                "• Copy exactly as shown in the app\n\n"
                "💡 *Use /submit to see the format example*"
            )
            await message.reply_text(error_msg, parse_mode="Markdown")
        else:
            await message.reply_text("❌ Please use /submit first, then paste your Ingress Prime data as a reply.")

        # Auto-delete user's invalid submission message after error response
        try:
            await message.delete()
            logger.info(f"Auto-deleted invalid submission message from user {message.from_user.id}")
        except Exception as e:
            logger.warning(f"Failed to auto-delete invalid submission message: {e}")

        return

    entries = [parsed] if isinstance(parsed, dict) else parsed
    saved = False
    successful_entries = []

    for entry in entries:
        if isinstance(entry, dict):
            if not save_to_db(entry):
                await message.reply_text("❌ Failed to save submission. Please try again.")

                # Auto-delete user's submission message after error response
                try:
                    await message.delete()
                    logger.info(f"Auto-deleted failed submission message from user {message.from_user.id}")
                except Exception as e:
                    logger.warning(f"Failed to auto-delete submission message: {e}")

                return

            # Also save to main database using SQLAlchemy models
            try:
                session_factory = context.application.bot_data["session_factory"]
                async with session_scope(session_factory) as session:
                    await save_submission_to_main_db(session, entry, message)
            except Exception as e:
                logger.error(f"Failed to save submission to main database: {e}")
                # Continue even if main DB save fails

            saved = True
            successful_entries.append(entry)

    if not saved:
        await message.reply_text("❌ No valid data found. Please check your format.")

        # Auto-delete user's invalid submission message after error response
        try:
            await message.delete()
            logger.info(f"Auto-deleted invalid submission message from user {message.from_user.id}")
        except Exception as e:
            logger.warning(f"Failed to auto-delete invalid submission message: {e}")

        return

    # Success message with details
    if len(successful_entries) == 1:
        entry = successful_entries[0]
        agent_name = entry.get('agent_name', 'Unknown')
        lifetime_ap = entry.get('lifetime_ap', 'Unknown')
        cycle_points = entry.get('cycle_points', 'N/A')

        success_msg = (
            f"✅ *Stats recorded successfully!*\n\n"
            f"👤 *Agent:* {agent_name}\n"
            f"⚡ *Lifetime AP:* {lifetime_ap:,}\n"
            f"🏆 *Cycle Points:* {cycle_points}"
        )
    else:
        success_msg = f"✅ *{len(successful_entries)} entries recorded successfully!*"

    # Send success message
    await message.reply_text(success_msg, parse_mode="Markdown")

    # Auto-delete user's data submission message after processing
    try:
        await message.delete()
        logger.info(f"Auto-deleted submission message from user {message.from_user.id}")
    except Exception as e:
        logger.warning(f"Failed to auto-delete submission message: {e}")
        # Continue even if deletion fails (might not have permissions)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display help message with all available commands."""
    if not update.message:
        return
    
    settings: Settings = context.application.bot_data["settings"]
    
    if settings.text_only_mode:
        # Simplified text-only help
        help_text = (
            "🤖 *PrimeStatsBot Help* 🤖\n\n"
            "📊 *MAIN COMMANDS:*\n"
              "• /submit - Submit your Ingress Prime stats\n"
            "• /leaderboard - View rankings\n"
            "• /myrank - Check your rank\n"
            ""
            "📈 *LEADERBOARD OPTIONS:*\n"
            "• /leaderboard - All time AP (default)\n"
            "• /leaderboard weekly - Weekly AP\n"
            "• /leaderboard hacks - Top hackers\n"
            "• /leaderboard weekly hacks - Weekly hackers\n"
            "• /leaderboard xm - Top XM collectors\n"
            "• /leaderboard portals - Top portal capturers\n"
            "• /leaderboard links - Top link creators\n"
            "• /leaderboard fields - Top field creators\n"
            "• /leaderboard distance - Top distance walkers\n\n"
            "🎯 *OTHER USEFUL:*\n"
            "• /top ENL or /top RES - Faction tops\n"
            "• /top10 - Global top 10\n"
            "• /settings - Configure display\n"
            "• /help - Show this help\n\n"
            "📋 *SUBMIT FORMAT:*\n"
            "Copy your data from Ingress Prime app and paste it:\n\n"
            "Time Span Agent Name Agent Faction Date (yyyy-mm-dd) Time (hh:mm:ss) Level Lifetime AP ...\n"
            "ALL TIME YourName Enlightened 2025-11-07 04:40:52 13 55000000 ...\n\n"
            "💡 *Simply use /submit and reply with your data*"
        )
        await update.message.reply_text(help_text)
    else:
        # Enhanced normal mode help
        help_text = (
            "🤖 **PrimeStatsBot Help** 🤖\n\n"
            "📊 **MAIN COMMANDS:**\n"
              "• /submit - Submit your Ingress Prime stats\n"
            "• /leaderboard - View rankings\n"
            "• /myrank - Check your rank\n"
            ""
            "📈 **LEADERBOARD OPTIONS:**\n"
            "• /leaderboard - All time AP (default)\n"
            "• /leaderboard weekly - Weekly AP\n"
            "• /leaderboard hacks - Top hackers\n"
            "• /leaderboard weekly hacks - Weekly hackers\n"
            "• /leaderboard xm - Top XM collectors\n"
            "• /leaderboard portals - Top portal capturers\n"
            "• /leaderboard links - Top link creators\n"
            "• /leaderboard fields - Top field creators\n"
            "• /leaderboard distance - Top distance walkers\n\n"
            "🎯 **OTHER USEFUL:**\n"
            "• /top ENL or /top RES - Faction tops\n"
            "• /top10 - Global top 10\n"
            "• /settings - Configure display\n"
            "• /help - Show this help\n\n"
            "📋 **SUBMIT FORMAT:**\n"
            "Copy your data from Ingress Prime app and paste it:\n\n"
            "```\n"
            "Time Span Agent Name Agent Faction Date (yyyy-mm-dd) Time (hh:mm:ss) Level Lifetime AP ...\n"
            "ALL TIME YourName Enlightened 2025-11-07 04:40:52 13 55000000 ...\n"
            "```\n\n"
            "💡 **Simply use /submit and reply with your data**\n\n"
            "🔧 **ADMIN:** /privacy (groups) | /stats (admins)"
        )
        await update.message.reply_text(help_text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text("Welcome to the Ingress leaderboard bot. Use /submit to submit your stats.")




async def last_week_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    settings: Settings = context.application.bot_data["settings"]
    since = datetime.now(timezone.utc) - timedelta(days=7)
    rows = await _fetch_cycle_leaderboard(10, since=since)
    await _send_cycle_leaderboard(update, settings, rows, "Top 10 agents — last 7 days")


async def last_cycle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    settings: Settings = context.application.bot_data["settings"]

    # Get the latest cycle name
    cycle_name = await _get_latest_cycle_name_async()
    if not cycle_name:
        await update.message.reply_text("No cycle data available.")
        return

    # Get leaderboard for the current cycle
    rows = await _fetch_cycle_leaderboard(10, cycle_name=cycle_name)
    cycle_header = f"Top 10 agents — {cycle_name}"
    await _send_cycle_leaderboard(update, settings, rows, cycle_header)


async def _get_or_create_group_setting(
    session: AsyncSession,
    chat_id: int,
    default_retention_minutes: int,
) -> GroupSetting:
    result = await session.execute(select(GroupSetting).where(GroupSetting.chat_id == chat_id))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = GroupSetting(
            chat_id=chat_id,
            privacy_mode=GroupPrivacyMode.public.value,
            retention_minutes=max(default_retention_minutes, 0),
        )
        session.add(setting)
        await session.flush()
    return setting


async def store_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or message.chat_id is None:
        return
    timestamp = message.date or datetime.now(timezone.utc)
    session_factory = context.application.bot_data["session_factory"]
    settings: Settings = context.application.bot_data["settings"]
    async with session_scope(session_factory) as session:
        setting = await _get_or_create_group_setting(
            session,
            message.chat_id,
            settings.group_message_retention_minutes,
        )
        mode = GroupPrivacyMode(setting.privacy_mode)
        if mode is GroupPrivacyMode.public:
            return
        exists = await session.execute(
            select(GroupMessage.id).where(
                GroupMessage.chat_id == message.chat_id,
                GroupMessage.message_id == message.message_id,
            )
        )
        if exists.scalar_one_or_none() is not None:
            return
        session.add(
            GroupMessage(
                chat_id=message.chat_id,
                message_id=message.message_id,
                received_at=timestamp,
            )
        )


async def set_group_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    chat = getattr(update, "effective_chat", None)
    if not chat or getattr(chat, "type", None) not in {"group", "supergroup"}:
        await update.message.reply_text("This command can only be used in groups.")
        return
    args = getattr(context, "args", [])
    if not args:
        await update.message.reply_text("Usage: /privacy <public|soft|strict>.")
        return
    value = args[0].lower()
    try:
        mode = GroupPrivacyMode(value)
    except ValueError:
        options = ", ".join(sorted(mode_option.value for mode_option in GroupPrivacyMode))
        await update.message.reply_text(f"Invalid mode. Choose from {options}.")
        return
    settings: Settings = context.application.bot_data["settings"]
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        setting = await _get_or_create_group_setting(
            session,
            chat.id,
            settings.group_message_retention_minutes,
        )
        setting.privacy_mode = mode.value
        setting.last_updated_by = update.effective_user.id if update.effective_user else setting.last_updated_by
    await update.message.reply_text(f"Privacy mode set to {mode.value}.")




















async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display usage statistics (admin only)."""
    if not update.message or not update.effective_user:
        return
    
    settings: Settings = context.application.bot_data["settings"]
    
    # Check if the user is an admin
    if update.effective_user.id not in settings.admin_user_ids:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    session_factory = context.application.bot_data["session_factory"]
    
    async with session_scope(session_factory) as session:
        # Get total number of registered users
        agents_result = await session.execute(select(func.count(Agent.id)))
        total_agents = agents_result.scalar()
        
        # Get total number of submissions
        submissions_result = await session.execute(select(func.count(Submission.id)))
        total_submissions = submissions_result.scalar()
        
        # Get submissions by time period
        now = datetime.now(timezone.utc)
        
        # Daily submissions
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_result = await session.execute(
            select(func.count(Submission.id)).where(Submission.submitted_at >= day_start)
        )
        daily_submissions = daily_result.scalar()
        
        # Weekly submissions
        week_start = day_start - timedelta(days=now.weekday())
        weekly_result = await session.execute(
            select(func.count(Submission.id)).where(Submission.submitted_at >= week_start)
        )
        weekly_submissions = weekly_result.scalar()
        
        # Monthly submissions
        month_start = day_start.replace(day=1)
        monthly_result = await session.execute(
            select(func.count(Submission.id)).where(Submission.submitted_at >= month_start)
        )
        monthly_submissions = monthly_result.scalar()
        
        # Get most active users (by submission count)
        active_users_result = await session.execute(
            select(Agent.codename, Agent.faction, func.count(Submission.id).label("submission_count"))
            .join(Submission, Agent.id == Submission.agent_id)
            .group_by(Agent.id)
            .order_by(func.count(Submission.id).desc())
            .limit(5)
        )
        active_users = active_users_result.all()

        # Get faction distribution
        enl_result = await session.execute(
            select(func.count(Agent.id)).where(Agent.faction == "ENL")
        )
        enl_count = enl_result.scalar()
        
        res_result = await session.execute(
            select(func.count(Agent.id)).where(Agent.faction == "RES")
        )
        res_count = res_result.scalar()
        
        # Get group statistics
        groups_result = await session.execute(select(func.count(GroupSetting.id)))
        total_groups = groups_result.scalar()
        
        # Format the statistics message
        if settings.text_only_mode:
            # Text-only mode for better performance on old Android devices
            stats_text = (
                "BOT USAGE STATISTICS\n\n"
                "USER STATISTICS\n"
                f"Total registered users: {total_agents}\n"
                f"ENL agents: {enl_count}\n"
                f"RES agents: {res_count}\n\n"
                "SUBMISSION STATISTICS\n"
                f"Total submissions: {total_submissions}\n"
                f"Daily submissions: {daily_submissions}\n"
                f"Weekly submissions: {weekly_submissions}\n"
                f"Monthly submissions: {monthly_submissions}\n\n"
                "GROUP STATISTICS\n"
                f"Total groups: {total_groups}\n\n"
                "MOST ACTIVE USERS\n"
            )
            
            for i, (codename, faction, count) in enumerate(active_users, start=1):
                stats_text += f"{i}. {codename} [{faction}] - {count} submissions\n"
        else:
            # Normal mode with emojis and markdown - using escape_markdown_v2 for proper escaping
            stats_text = (
                "📊 *BOT USAGE STATISTICS* 📊\\n\\n"
                "👥 *USER STATISTICS*\\n"
                f"Total registered users: `{escape_markdown_v2(str(total_agents))}`\\n"
                f"🟢 ENL agents: `{escape_markdown_v2(str(enl_count))}`\\n"
                f"🔵 RES agents: `{escape_markdown_v2(str(res_count))}`\\n\\n"
                "📝 *SUBMISSION STATISTICS*\\n"
                f"Total submissions: `{escape_markdown_v2(str(total_submissions))}`\\n"
                f"Daily submissions: `{escape_markdown_v2(str(daily_submissions))}`\\n"
                f"Weekly submissions: `{escape_markdown_v2(str(weekly_submissions))}`\\n"
                f"Monthly submissions: `{escape_markdown_v2(str(monthly_submissions))}`\\n\\n"
                "👥 *GROUP STATISTICS*\\n"
                f"Total groups: `{escape_markdown_v2(str(total_groups))}`\\n\\n"
                "🏆 *MOST ACTIVE USERS*\\n"
            )
            
            for i, (codename, faction, count) in enumerate(active_users, start=1):
                stats_text += f"{escape_markdown_v2(str(i) + '.')}. {escape_markdown_v2(codename)} \\[{escape_markdown_v2(faction)}\\] \\— `{escape_markdown_v2(str(count))}` submissions\\n"
        
        await update.message.reply_text(stats_text, parse_mode="MarkdownV2" if not settings.text_only_mode else None)


async def _get_or_create_user_setting(session: AsyncSession, telegram_id: int) -> UserSetting:
    """Get existing user settings or create new ones if they don't exist."""
    result = await session.execute(select(UserSetting).where(UserSetting.telegram_id == telegram_id))
    setting = result.scalar_one_or_none()
    
    if setting is None:
        setting = UserSetting(telegram_id=telegram_id)
        session.add(setting)
        await session.flush()
    
    return setting


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the settings configuration conversation."""
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        user_setting = await _get_or_create_user_setting(session, update.effective_user.id)
        
        # Format current settings for display
        date_format_preview = datetime.now().strftime(user_setting.date_format)
        
        settings_text = (
            f"⚙️ *Your Current Settings*\\n\\n"
            f"1\\. Date Format: `{escape_markdown_v2(user_setting.date_format)}` \\(Example: {escape_markdown_v2(date_format_preview)}\\)\\n"
            f"2\\. Number Format: `{escape_markdown_v2(user_setting.number_format)}` \\(Example: 1,000\\)\\n"
            f"3\\. Leaderboard Size: `{escape_markdown_v2(str(user_setting.leaderboard_size))}` \\(entries\\)\\n"
            f"4\\. Show Emojis: `{escape_markdown_v2('Yes' if user_setting.show_emojis else 'No')}`\\n\\n"
            f"Select a setting to change or type /cancel to exit\\."
        )
        
        await update.message.reply_text(settings_text, parse_mode="MarkdownV2")
        return SETTINGS_MENU


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle selection of a setting to change."""
    if not update.message:
        return ConversationHandler.END
    
    text = update.message.text.strip()
    
    # Check if the user wants to cancel
    if text.lower() == "/cancel":
        await update.message.reply_text("Settings configuration cancelled.")
        return ConversationHandler.END
    
    # Map user input to setting options
    setting_options = {
        "1": "date_format",
        "2": "number_format",
        "3": "leaderboard_size",
        "4": "show_emojis"
    }
    
    if text not in setting_options:
        await update.message.reply_text("Please select a valid option (1-4) or type /cancel to exit.")
        return SETTINGS_MENU
    
    # Store the selected setting in user context
    context.user_data["selected_setting"] = setting_options[text]
    
    # Provide guidance for the selected setting
    if text == "1":  # Date format
        await update.message.reply_text(
            "Enter your preferred date format.\n"
            "Common formats:\n"
            "- `%Y-%m-%d` (2023-12-31)\n"
            "- `%d/%m/%Y` (31/12/2023)\n"
            "- `%m/%d/%Y` (12/31/2023)\n"
            "- `%b %d, %Y` (Dec 31, 2023)\n\n"
            "Use Python strftime codes for custom formats."
        )
    elif text == "2":  # Number format
        await update.message.reply_text(
            "Enter your preferred number format:\n"
            "- `comma` (1,000)\n"
            "- `dot` (1.000)\n"
            "- `space` (1 000)"
        )
    elif text == "3":  # Leaderboard size
        await update.message.reply_text(
            "Enter leaderboard size (1-50):"
        )
    elif text == "4":  # Show emojis
        await update.message.reply_text(
            "Enter whether to show emojis:\n"
            "- `yes` or `true` to enable\n"
            "- `no` or `false` to disable"
        )
    
    return SETTINGS_VALUE


async def settings_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the new value for the selected setting."""
    if not update.message:
        return ConversationHandler.END
    
    selected_setting = context.user_data.get("selected_setting")
    if not selected_setting:
        await update.message.reply_text("Error: No setting selected. Please start over with /settings.")
        return ConversationHandler.END
    
    new_value = update.message.text.strip()
    session_factory = context.application.bot_data["session_factory"]
    
    async with session_scope(session_factory) as session:
        user_setting = await _get_or_create_user_setting(session, update.effective_user.id)
        
        try:
            if selected_setting == "date_format":
                # Validate date format by trying to format current date
                try:
                    datetime.now().strftime(new_value)
                    user_setting.date_format = new_value
                    date_format_preview = datetime.now().strftime(new_value)
                    response = f"✅ Date format updated to: `{new_value}` (Example: {date_format_preview})"
                except (ValueError, TypeError):
                    await update.message.reply_text("Invalid date format. Please try again or type /cancel to exit.")
                    return SETTINGS_VALUE
            
            elif selected_setting == "number_format":
                # Validate number format
                if new_value not in ["comma", "dot", "space"]:
                    await update.message.reply_text("Invalid number format. Please use 'comma', 'dot', or 'space' or type /cancel to exit.")
                    return SETTINGS_VALUE
                user_setting.number_format = new_value
                response = f"✅ Number format updated to: `{new_value}`"
            
            elif selected_setting == "leaderboard_size":
                # Validate leaderboard size
                try:
                    size = int(new_value)
                    if not (1 <= size <= 50):
                        await update.message.reply_text("Leaderboard size must be between 1 and 50. Please try again or type /cancel to exit.")
                        return SETTINGS_VALUE
                    user_setting.leaderboard_size = size
                    response = f"✅ Leaderboard size updated to: `{size}` entries"
                except ValueError:
                    await update.message.reply_text("Invalid number. Please enter a number between 1 and 50 or type /cancel to exit.")
                    return SETTINGS_VALUE
            
            elif selected_setting == "show_emojis":
                # Parse boolean value
                if new_value.lower() in ["yes", "true", "1", "on"]:
                    user_setting.show_emojis = True
                    response = "✅ Emojis enabled"
                elif new_value.lower() in ["no", "false", "0", "off"]:
                    user_setting.show_emojis = False
                    response = "✅ Emojis disabled"
                else:
                    await update.message.reply_text("Invalid value. Please use 'yes', 'no', 'true', or 'false' or type /cancel to exit.")
                    return SETTINGS_VALUE
            
            # Update the timestamp
            user_setting.updated_at = datetime.now(timezone.utc)
            
            # Send confirmation
            await update.message.reply_text(response + "\n\nType /settings to configure more settings or /cancel to exit.")
            
        except Exception as e:
            logger.error(f"Error updating user settings: {e}")
            await update.message.reply_text("An error occurred while updating your settings. Please try again.")
    
    # Clear user context and end conversation
    context.user_data.clear()
    return ConversationHandler.END


async def settings_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the settings configuration process."""
    if update.message:
        await update.message.reply_text("Settings configuration cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


async def announce_weekly_winners(application: Application, session_factory: async_sessionmaker, week_start: datetime, week_end: datetime) -> None:
    """Announce the weekly winners in all active group chats."""
    # Reduced logging for better performance on old Android devices
    logger.info("Starting weekly winners announcement")
    
    try:
        # Enhanced database connection error handling
        try:
            async with session_scope(session_factory) as session:
                # Get top performers for each faction from WeeklyStat
                try:
                    result = await session.execute(
                        select(
                            WeeklyStat.agent_id,
                            WeeklyStat.value,
                            WeeklyStat.faction,
                            Agent.codename,
                        )
                        .join(Agent, Agent.id == WeeklyStat.agent_id)
                        .where(WeeklyStat.week_start == week_start)
                        .where(WeeklyStat.week_end == week_end)
                        .where(WeeklyStat.category == "ap")
                        .order_by(WeeklyStat.value.desc())
                    )
                except Exception as db_error:
                    logger.error(f"Database error while fetching weekly stats: {db_error}")
                    raise
                
                # Separate by faction with validation
                enl_agents = []
                res_agents = []
                
                for agent_id, value, faction, codename in result.all():
                    # Validate WeeklyStat data
                    if not agent_id or not faction or not codename:
                        logger.warning(f"Invalid WeeklyStat data: agent_id={agent_id}, faction={faction}, codename={codename}")
                        continue
                    
                    if value is None or value <= 0:
                        logger.warning(f"Invalid AP value for agent {codename}: {value}")
                        continue
                    
                    if faction == "ENL":
                        enl_agents.append((codename, value))
                    elif faction == "RES":
                        res_agents.append((codename, value))
                    else:
                        logger.warning(f"Unknown faction {faction} for agent {codename}")
                
                # Get all active group chats
                try:
                    group_settings_result = await session.execute(select(GroupSetting))
                    group_settings = group_settings_result.scalars().all()
                except Exception as db_error:
                    logger.error(f"Database error while fetching group settings: {db_error}")
                    raise
                
                if not group_settings:
                    logger.info("No group chats found for announcing weekly winners")
                    return
                
                # Get settings from application bot_data
                settings = application.bot_data["settings"]
                
                # Format the announcement message
                if settings.text_only_mode:
                    # Text-only mode for better performance on old Android devices
                    announcement = "Weekly Competition Results\n\n"
                    
                    # Add ENL winners
                    if enl_agents:
                        announcement += "Enlightened (ENL) Top Performers:\n"
                        for i, (codename, ap) in enumerate(enl_agents[:3], start=1):
                            announcement += f"{i}. {codename} - {ap:,} AP\n"
                        announcement += "\n"
                    else:
                        announcement += "Enlightened (ENL): No submissions this week\n\n"
                    
                    # Add RES winners
                    if res_agents:
                        announcement += "Resistance (RES) Top Performers:\n"
                        for i, (codename, ap) in enumerate(res_agents[:3], start=1):
                            announcement += f"{i}. {codename} - {ap:,} AP\n"
                        announcement += "\n"
                    else:
                        announcement += "Resistance (RES): No submissions this week\n\n"
                    
                    # Add footer
                    announcement += "Scores have been reset for the new week. Good luck!"
                else:
                    # Normal mode with emojis and markdown - using escape_markdown_v2 for proper escaping
                    announcement = "🏆 *Weekly Competition Results* 🏆\\n\\n"
                    
                    # Add ENL winners
                    if enl_agents:
                        announcement += "*🟢 Enlightened \\(ENL\\) Top Performers:*\\n"
                        for i, (codename, ap) in enumerate(enl_agents[:3], start=1):
                            announcement += f"{escape_markdown_v2(str(i) + '.')}. {escape_markdown_v2(codename)} - {escape_markdown_v2(f'{ap:,}')} AP\\n"
                        announcement += "\\n"
                    else:
                        announcement += "*🟢 Enlightened \\(ENL\\):* No submissions this week\\n\\n"
                    
                    # Add RES winners
                    if res_agents:
                        announcement += "*🔵 Resistance \\(RES\\) Top Performers:*\\n"
                        for i, (codename, ap) in enumerate(res_agents[:3], start=1):
                            announcement += f"{escape_markdown_v2(str(i) + '.')}. {escape_markdown_v2(codename)} - {escape_markdown_v2(f'{ap:,}')} AP\\n"
                        announcement += "\\n"
                    else:
                        announcement += "*🔵 Resistance \\(RES\\):* No submissions this week\\n\\n"
                    
                    # Add footer
                    announcement += "Scores have been reset for the new week\\. Good luck! 🍀"
                
                # Send announcement to all group chats with enhanced error handling
                successful_sends = 0
                failed_sends = 0
                
                for setting in group_settings:
                    try:
                        # Verify if the group chat is active before sending
                        try:
                            chat = await application.bot.get_chat(setting.chat_id)
                            if chat.type not in ["group", "supergroup"]:
                                logger.warning(f"Chat {setting.chat_id} is not a group/supergroup, skipping")
                                continue
                            
                            if settings.text_only_mode:
                                # Text-only mode for better performance on old Android devices
                                await application.bot.send_message(
                                    chat_id=setting.chat_id,
                                    text=announcement
                                )
                            else:
                                # Normal mode with markdown - using escape_markdown_v2 for proper escaping
                                # Since announcement is already formatted with proper escaping in the code above,
                                # we don't need to escape it again here
                                await application.bot.send_message(
                                    chat_id=setting.chat_id,
                                    text=announcement,
                                    parse_mode="MarkdownV2"
                                )
                            successful_sends += 1
                        except RetryAfter as e:
                            await asyncio.sleep(e.retry_after)
                            # Retry once after waiting
                            try:
                                if settings.text_only_mode:
                                    # Text-only mode for better performance on old Android devices
                                    await application.bot.send_message(
                                        chat_id=setting.chat_id,
                                        text=announcement
                                    )
                                else:
                                    # Normal mode with markdown
                                    await application.bot.send_message(
                                        chat_id=setting.chat_id,
                                        text=announcement,
                                        parse_mode="MarkdownV2"
                                    )
                                successful_sends += 1
                            except TelegramError as retry_error:
                                failed_sends += 1
                                logger.error(f"Failed to send weekly winners announcement to group {setting.chat_id} after retry: {retry_error}")
                        except Forbidden as e:
                            failed_sends += 1
                            logger.error(f"Forbidden error for group {setting.chat_id}: {e}. Bot may have been blocked or removed from the group.")
                        except TelegramError as e:
                            failed_sends += 1
                            logger.error(f"Failed to send weekly winners announcement to group {setting.chat_id}: {e}")
                    except Exception as e:
                        failed_sends += 1
                        logger.error(f"Unexpected error sending to group {setting.chat_id}: {e}")
                
                logger.info(f"Weekly winners announcement completed: {successful_sends} successful, {failed_sends} failed")
        except Exception as db_error:
            logger.error(f"Database connection error in announce_weekly_winners: {db_error}")
            raise
                    
    except Exception as e:
        logger.error(f"Error in announce_weekly_winners: {e}", exc_info=True)


async def reset_weekly_scores(application: Application, session_factory: async_sessionmaker) -> None:
    """Reset weekly scores and store them in WeeklyStat table."""
    logger.info("Starting weekly score reset process")
    
    # Improved timezone handling - ensure we're using UTC consistently
    now = datetime.now(timezone.utc)
    week_end = now
    week_start = week_end - timedelta(days=7)
    
    try:
        # Use a transaction to prevent race conditions during score reset
        async with session_scope(session_factory) as session:
            try:
                # Get all submissions grouped by agent and faction
                result = await session.execute(
                    select(Submission.agent_id, func.sum(Submission.ap), Agent.faction)
                    .join(Agent, Agent.id == Submission.agent_id)
                    .group_by(Submission.agent_id, Agent.faction)
                )
                
                # Process each agent's weekly stats
                stats_created = 0
                for agent_id, total_ap, faction in result.all():
                    # Validate data before processing
                    if not agent_id or not faction:
                        logger.warning(f"Invalid data: agent_id={agent_id}, faction={faction}")
                        continue
                    
                    total_value = int(total_ap or 0)
                    if total_value <= 0:
                        continue
                    
                    # Create WeeklyStat record
                    try:
                        session.add(
                            WeeklyStat(
                                agent_id=agent_id,
                                category="ap",
                                faction=faction,
                                value=total_value,
                                week_start=week_start,
                                week_end=week_end,
                            )
                        )
                        stats_created += 1
                    except Exception as e:
                        logger.error(f"Error creating weekly stat for agent {agent_id}: {e}")
                
                # Delete all submissions - this is done after creating stats to prevent data loss
                try:
                    delete_result = await session.execute(delete(Submission))
                    deleted_count = delete_result.rowcount
                    logger.info(f"Deleted {deleted_count} submission records")
                except Exception as e:
                    logger.error(f"Error deleting submissions: {e}")
                    raise
                
                # Commit the transaction
                await session.commit()
                
            except Exception as db_error:
                logger.error(f"Database error during weekly score reset: {db_error}")
                await session.rollback()
                raise
        
        # Announce weekly winners after reset is complete and transaction is committed
        await announce_weekly_winners(application, session_factory, week_start, week_end)
        logger.info("Weekly score reset process completed successfully")
        
    except Exception as e:
        logger.error(f"Error in reset_weekly_scores: {e}", exc_info=True)
        raise


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the broadcast conversation (admin only)."""
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    
    settings: Settings = context.application.bot_data["settings"]
    
    # Check if the user is an admin
    if update.effective_user.id not in settings.admin_user_ids:
        await update.message.reply_text("You don't have permission to use this command.")
        return ConversationHandler.END
    
    await update.message.reply_text("Please send the message you want to broadcast to all users.")
    return BROADCAST_MESSAGE


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the broadcast message and ask for confirmation."""
    if not update.message:
        return ConversationHandler.END
    
    # Store the broadcast message in user context
    context.user_data["broadcast_message"] = update.message.text or update.message.caption or ""
    
    if not context.user_data["broadcast_message"].strip():
        await update.message.reply_text("Message cannot be empty. Please send a valid message.")
        return BROADCAST_MESSAGE
    
    # Show preview and ask for confirmation
    preview = context.user_data["broadcast_message"]
    await update.message.reply_text(
        f"Broadcast message preview:\n\n{preview}\n\n"
        "Send this message to all registered users? (yes/no)"
    )
    return BROADCAST_CONFIRM


async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm and send the broadcast message to all users."""
    if not update.message:
        return ConversationHandler.END
    
    response = update.message.text.strip().lower()
    
    if response not in ["yes", "y"]:
        await update.message.reply_text("Broadcast cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
    
    message = context.user_data.get("broadcast_message", "")
    if not message:
        await update.message.reply_text("Error: No message found. Please start over with /broadcast.")
        context.user_data.clear()
        return ConversationHandler.END
    
    # Send the broadcast to all users
    success_count, failure_count = await send_broadcast_to_all(update, context, message)
    
    # Clear user context
    context.user_data.clear()
    
    # Send confirmation to admin
    await update.message.reply_text(
        f"Broadcast completed.\n"
        f"Successfully sent to: {success_count} users\n"
        f"Failed to send to: {failure_count} users"
    )
    
    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the broadcast conversation."""
    if update.message:
        await update.message.reply_text("Broadcast cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


async def send_broadcast_to_all(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> tuple[int, int]:
    """Send a broadcast message to all registered users."""
    if not update.effective_user:
        return 0, 0
    
    session_factory = context.application.bot_data["session_factory"]
    success_count = 0
    failure_count = 0
    
    async with session_scope(session_factory) as session:
        # Get all registered users
        result = await session.execute(select(Agent.telegram_id))
        user_ids = result.scalars().all()
        
        if not user_ids:
            await update.message.reply_text("No registered users found.")
            return 0, 0
        
        # Send message to each user
        for user_id in user_ids:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📢 *Broadcast Message* 📢\\n\\n{escape_markdown_v2(message)}",
                    parse_mode="MarkdownV2"
                )
                success_count += 1
                
                # Add a small delay to avoid hitting rate limits
                await asyncio.sleep(0.05)
                
            except Exception as e:
                logger.error(f"Failed to send broadcast to user {user_id}: {e}")
                failure_count += 1
    
    return success_count, failure_count


def configure_handlers(application: Application) -> None:
    # Add error handling for all commands
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log errors and notify users."""
        logger.error(f"Exception while handling an update: {context.error}")

        # Try to notify the user about the error
        if update and hasattr(update, 'message') and update.message:
            try:
                await update.message.reply_text(
                    "❌ Sorry, something went wrong while processing your command. "
                    "Please try again or contact an admin if the problem persists."
                )
            except Exception:
                pass  # Ignore errors in error handling

    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
        
    settings_handler = ConversationHandler(
        entry_points=[CommandHandler("settings", settings_command)],
        states={
            SETTINGS_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_menu)],
            SETTINGS_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_value)],
        },
        fallbacks=[CommandHandler("cancel", settings_cancel)],
    )
    application.add_handler(settings_handler)
    
    broadcast_handler = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_command)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)],
            BROADCAST_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_confirm)],
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    application.add_handler(broadcast_handler)
    
    application.add_handler(CommandHandler("submit", submit))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("top10", top10_command))
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CommandHandler("lastcycle", last_cycle_command))
    application.add_handler(CommandHandler("lastweek", last_week_command))
    application.add_handler(CommandHandler("myrank", myrank_command))
    application.add_handler(CommandHandler("betatokens", betatokens_command))
    application.add_handler(CommandHandler("privacy", set_group_privacy))
    application.add_handler(CommandHandler("backup", manual_backup_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) & (filters.ChatType.PRIVATE | filters.ChatType.GROUPS), handle_ingress_message))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, store_group_message))


# Placeholder functions for missing core commands
async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /submit command - improved submission flow."""
    if not update.message:
        return

    settings: Settings = context.application.bot_data["settings"]

    # Send submission instructions
    if settings.text_only_mode:
        submit_text = (
            "📊 *STATS SUBMISSION*\n\n"
            "Please paste your Ingress Prime export data.\n\n"
            "📋 *FORMAT EXAMPLE:*\n"
            "Copy your data from Ingress Prime app and paste it exactly as shown:\n\n"
            "Time Span Agent Name Agent Faction Date (yyyy-mm-dd) Time (hh:mm:ss) Level Lifetime AP Current AP ...\n"
            "ALL TIME YourName Enlightened 2025-11-07 04:40:52 13 55000000 15000000 ...\n\n"
            "✅ *Simply reply to this message with your data*\n"
            "💡 *Make sure to include both the header line and your data line*"
        )
    else:
        submit_text = (
            "📊 **STATS SUBMISSION** 📊\n\n"
            "Please paste your Ingress Prime export data.\n\n"
            "📋 **FORMAT EXAMPLE:**\n"
            "Copy your data from Ingress Prime app and paste it exactly as shown:\n\n"
            "```\n"
            "Time Span Agent Name Agent Faction Date (yyyy-mm-dd) Time (hh:mm:ss) Level Lifetime AP Current AP ...\n"
            "ALL TIME YourName Enlightened 2025-11-07 04:40:52 13 55000000 15000000 ...\n"
            "```\n\n"
            "✅ **Simply reply to this message with your data**\n"
            "💡 **Make sure to include both the header line and your data line**"
        )

    await update.message.reply_text(submit_text, parse_mode="Markdown" if not settings.text_only_mode else None)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /leaderboard command with support for multiple metrics."""
    if not update.message:
        return

    settings: Settings = context.application.bot_data["settings"]
    session_factory = context.application.bot_data["session_factory"]

    # Parse command arguments
    args = context.args if context.args else []
    time_span = None
    metric = "ap"  # default metric
    limit = 10

    # Parse arguments
    for arg in args:
        arg_lower = arg.lower()
        if arg_lower in ["all", "all time", "lifetime"]:
            time_span = "ALL TIME"
        elif arg_lower in ["weekly", "week"]:
            time_span = "WEEKLY"
        elif arg_lower in ["monthly", "month"]:
            time_span = "MONTHLY"
        elif arg_lower in ["daily", "day"]:
            time_span = "DAILY"
        elif arg_lower in ["hacks", "hack"]:
            metric = "hacks"
        elif arg_lower in ["xm", "xm_collected", "xm collected"]:
            metric = "xm_collected"
        elif arg_lower in ["portals", "portals_captured", "portals captured"]:
            metric = "portals_captured"
        elif arg_lower in ["resonators", "resonators_deployed", "resonators deployed"]:
            metric = "resonators_deployed"
        elif arg_lower in ["links", "links_created", "links created"]:
            metric = "links_created"
        elif arg_lower in ["fields", "fields_created", "fields created"]:
            metric = "fields_created"
        elif arg_lower in ["mods", "mods_deployed", "mods deployed"]:
            metric = "mods_deployed"
        elif arg_lower in ["destroyed", "resonators_destroyed", "resonators destroyed"]:
            metric = "resonators_destroyed"
        elif arg_lower in ["neutralized", "portals_neutralized", "portals neutralized"]:
            metric = "portals_neutralized"
        elif arg_lower in ["distance", "distance_walked", "distance walked", "km"]:
            metric = "distance_walked"
        elif arg_lower.isdigit():
            limit = min(int(arg_lower), 50)  # Max 50 entries
        elif arg_lower == "top":
            continue  # Skip 'top' keyword
        else:
            # Try to handle combined format like "weekly hacks"
            if arg_lower in ["weekly", "week"]:
                time_span = "WEEKLY"
            elif arg_lower in ["monthly", "month"]:
                time_span = "MONTHLY"
            elif arg_lower in ["all", "all time", "lifetime"]:
                time_span = "ALL TIME"

    # Default to weekly if no time span specified for certain metrics
    if time_span is None and metric != "ap":
        time_span = "WEEKLY"

    # Get the appropriate title
    time_span_text = time_span if time_span else "ALL TIME"
    metric_text = metric.replace("_", " ").title() if metric != "ap" else "AP"

    if metric == "ap":
        title = f"Top {limit} agents - {time_span_text}"
    else:
        title = f"Top {limit} agents - {metric_text} ({time_span_text})"

    try:
        # Use the comprehensive leaderboard service
        from .services.leaderboard import get_leaderboard

        chat_id = update.effective_chat.id if update.effective_chat else None

        async with session_scope(session_factory) as session:
            rows = await get_leaderboard(
                session=session,
                limit=limit,
                chat_id=chat_id,
                time_span=time_span,
                metric=metric
            )

        if not rows:
            await update.message.reply_text("No data available for the specified criteria.")
            return

        # Format the leaderboard
        if settings.text_only_mode:
            lines = [f"🏆 {title} 🏆"]
            for index, (codename, faction, metric_value, metrics_dict) in enumerate(rows, start=1):
                metric_display = f"{metric_value:,}" if isinstance(metric_value, int) else str(metric_value)
                lines.append(f"{index}. {codename} [{faction}] - {metric_display}")
            leaderboard_text = "\n".join(lines)
        else:
            lines = [f"🏆 *{escape_markdown_v2(title)}* 🏆"]
            for index, (codename, faction, metric_value, metrics_dict) in enumerate(rows, start=1):
                metric_display = f"{metric_value:,}" if isinstance(metric_value, int) else str(metric_value)
                lines.append(f"{index}. {escape_markdown_v2(codename)} \\[{faction}\\] \\— {metric_display}")
            leaderboard_text = "\n".join(lines)

        await update.message.reply_text(
            leaderboard_text,
            parse_mode="MarkdownV2" if not settings.text_only_mode else None
        )

    except Exception as e:
        logger.error(f"Error fetching leaderboard: {e}")
        await update.message.reply_text("❌ Error fetching leaderboard data. Please try again later.")

async def top10_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /top10 command."""
    await leaderboard(update, context)

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /top command - basic implementation."""
    if not update.message or not context.args:
        await update.message.reply_text("Usage: /top ENL or /top RES")
        return

    faction = context.args[0].upper()
    if faction not in ["ENL", "RES"]:
        await update.message.reply_text("Faction must be ENL or RES")
        return

    settings: Settings = context.application.bot_data["settings"]
    session_factory = context.application.bot_data["session_factory"]

    # Get faction-specific leaderboard
    rows = await _fetch_cycle_leaderboard(10, faction=faction)
    await _send_cycle_leaderboard(update, settings, rows, f"Top 10 {faction} agents")

async def myrank_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /myrank command - basic implementation."""
    if not update.message or not update.effective_user:
        return

    session_factory = context.application.bot_data["session_factory"]

    # Get agent's rank
    async with session_scope(session_factory) as session:
        result = await session.execute(
            select(Agent).where(Agent.telegram_id == update.effective_user.id)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            await update.message.reply_text("You haven't submitted any stats yet. Use /submit to get started.")
            return

        rank = await get_agent_rank(session_factory, agent.id)
        if rank:
            await update.message.reply_text(f"Your current rank: #{rank}")
        else:
            await update.message.reply_text("You haven't submitted any stats yet. Use /submit to get started.")

async def betatokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /betatokens command - basic implementation."""
    if not update.message or not update.effective_user:
        return

    session_factory = context.application.bot_data["session_factory"]

    # Get agent's codename
    async with session_scope(session_factory) as session:
        result = await session.execute(
            select(Agent).where(Agent.telegram_id == update.effective_user.id)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            await update.message.reply_text("You haven't submitted any stats yet. Use /submit to get started.")
            return

        # Get beta tokens status
        status_message = get_token_status_message(agent.codename)
        await update.message.reply_text(status_message)


async def build_application() -> Application:
    load_dotenv()

    # Load and validate settings
    settings = load_settings()

    # Print environment summary in development mode
    if settings.environment == "development":
        print_environment_summary(settings)

    # Validate configuration
    validation_errors = validate_settings(settings)
    if validation_errors:
        logger.error("Configuration validation failed:")
        for error in validation_errors:
            logger.error(f"  - {error}")
        print(f"\n❌ Configuration validation failed:\n{chr(10).join(f'  - {error}' for error in validation_errors)}")
        print("\nPlease fix these issues before starting the bot.")
        sys.exit(1)

    # Set up logging
    log_level = getattr(logging, settings.server.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Add file logging if enabled
    if settings.monitoring.log_to_file:
        try:
            from logging.handlers import RotatingFileHandler
            log_file = Path(settings.monitoring.log_file_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=int(settings.monitoring.log_max_size.replace('MB', '')) * 1024 * 1024,
                backupCount=settings.monitoring.log_backup_count
            )
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            )

            root_logger = logging.getLogger()
            root_logger.addHandler(file_handler)

        except Exception as e:
            logger.warning(f"Failed to set up file logging: {e}")

    logger.info(f"Starting {settings.bot_name} in {settings.environment} mode")

    # Initialize database
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    await init_models(engine)

    # Initialize Redis
    redis_conn = Redis.from_url(
        settings.redis.url,
        socket_timeout=settings.redis.socket_timeout,
        socket_connect_timeout=settings.redis.socket_connect_timeout,
        retry_on_timeout=settings.redis.retry_on_timeout
    )
    queue = Queue(connection=redis_conn)

    # Test connections
    try:
        # Test database connection
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        logger.info("Database connection successful")

        # Test Redis connection
        redis_conn.ping()
        logger.info("Redis connection successful")

    except Exception as e:
        logger.error(f"Failed to connect to database/Redis: {e}")
        print(f"\n❌ Connection failed: {e}")
        print("Please check your configuration and ensure all services are running.")
        sys.exit(1)

    # Initialize scheduler
    scheduler = AsyncIOScheduler(timezone=timezone.utc)

    # Initialize health checker
    health_checker = get_health_checker(settings)

    # Build Telegram application
    application = ApplicationBuilder().token(settings.telegram_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["engine"] = engine
    application.bot_data["session_factory"] = session_factory
    application.bot_data["queue"] = queue
    application.bot_data["redis_connection"] = redis_conn
    application.bot_data["scheduler"] = scheduler
    application.bot_data["health_checker"] = health_checker

    configure_handlers(application)
    scheduler.add_job(
        cleanup_expired_group_messages,
        trigger="interval",
        minutes=7,
        args=(application, session_factory),
        max_instances=1,
        misfire_grace_time=60,
        coalesce=True,
    )
    if settings.backup_enabled:
        if settings.backup_schedule.lower() == "daily":
            trigger = "cron"
            trigger_args = {"hour": 2, "minute": 0}
        elif settings.backup_schedule.lower() == "weekly":
            trigger = "cron"
            trigger_args = {"day_of_week": "sun", "hour": 2, "minute": 0}
        else:
            logger.warning(f"Unknown backup schedule '{settings.backup_schedule}', defaulting to daily")
            trigger = "cron"
            trigger_args = {"hour": 2, "minute": 0}
        scheduler.add_job(
            perform_backup,
            trigger=trigger,
            args=(settings, application),
            max_instances=1,
            misfire_grace_time=3600,
            coalesce=True,
            **trigger_args,
        )
    async def on_start(app: Application) -> None:
        scheduler.start()
        if settings.dashboard_enabled:
            dashboard_app = create_dashboard_app(settings, session_factory)
            config = uvicorn.Config(
                dashboard_app,
                host=settings.dashboard_host,
                port=settings.dashboard_port,
                log_level="info",
                loop="asyncio",
            )
            server = uvicorn.Server(config)
            task = app.create_task(server.serve())
            app.bot_data["dashboard_server"] = server
            app.bot_data["dashboard_task"] = task
    async def on_stop(app: Application) -> None:
        server = app.bot_data.pop("dashboard_server", None)
        if server is not None:
            server.should_exit = True
        task = app.bot_data.pop("dashboard_task", None)
        scheduler.shutdown(wait=False)
        if task is not None:
            await task
        await engine.dispose()
        redis_conn.close()
    if application.post_init is None:
        application.post_init = []
    if application.post_stop is None:
        application.post_stop = []
    application.post_init.append(on_start)
    application.post_stop.append(on_stop)
    return application


async def async_main() -> None:
    print("🤖 Starting Ingress Prime Leaderboard Bot...")

    try:
        application = await build_application()
        settings = application.bot_data["settings"]
        health_checker = application.bot_data["health_checker"]

        # Perform startup health check
        print("🔍 Performing startup health check...")
        health_status = await health_checker.comprehensive_health_check()

        if health_status["status"] == "unhealthy":
            print("❌ Startup health check failed:")
            for check_name, check_result in health_status["checks"].items():
                if check_result["status"] == "unhealthy":
                    print(f"  - {check_name}: {check_result.get('message', 'Unknown error')}")
            print("\nPlease resolve these issues before starting the bot.")
            sys.exit(1)
        elif health_status["status"] == "warning":
            print("⚠️  Startup health check completed with warnings:")
            for check_name, check_result in health_status["checks"].items():
                if check_result["status"] == "warning":
                    print(f"  - {check_name}: {check_result.get('message', 'Warning')}")

        print(f"✅ Health check passed - Bot starting in {settings.environment} mode")

        # Start the bot
        async with application:
            await application.start()
            await application.updater.start_polling()

            print(f"🚀 {settings.bot_name} is now running!")
            print(f"📊 Environment: {settings.environment}")
            print(f"🔗 Dashboard: {'Enabled on port ' + str(settings.dashboard_port) if settings.dashboard_enabled else 'Disabled'}")

            # Add periodic health check job
            scheduler = application.bot_data["scheduler"]
            if settings.monitoring.health_check_enabled:
                scheduler.add_job(
                    lambda: asyncio.create_task(health_checker.comprehensive_health_check()),
                    trigger="interval",
                    minutes=5,
                    max_instances=1,
                    misfire_grace_time=60,
                    coalesce=True,
                )
                print("💓 Health monitoring enabled (every 5 minutes)")

            scheduler.start()

            try:
                # Keep the bot running
                await asyncio.Event().wait()
            except KeyboardInterrupt:
                print("\n🛑 Shutting down bot...")
            finally:
                print("🔄 Stopping components...")
                await application.updater.stop()
                print("✅ Bot stopped successfully")

    except KeyboardInterrupt:
        print("\n🛑 Bot interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        logger.error(f"Fatal error during startup: {e}", exc_info=True)
        sys.exit(1)


def main() -> None:
    """Main entry point with proper error handling."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
