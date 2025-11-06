import asyncio
import asyncio
import logging
import sqlite3
import re
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any
from itertools import combinations


from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from redis import Redis
from rq import Queue
import uvicorn
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from telegram import Update
from telegram.error import RetryAfter, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings, load_settings
from .dashboard import create_dashboard_app
from .database import build_engine, build_session_factory, init_models, session_scope
from .jobs.deletion import cleanup_expired_group_messages, schedule_message_deletion
from .jobs.backup import perform_backup, manual_backup_command
from .models import Agent, GroupMessage, GroupPrivacyMode, GroupSetting, PendingAction, Submission, WeeklyStat, Verification, VerificationStatus, UserSetting
from .services.leaderboard import get_leaderboard
from .utils.beta_tokens import get_token_status_message, update_medal_requirements, update_task_name, get_medal_config

logger = logging.getLogger(__name__)

CURRENT_CYCLE_FILE = Path(__file__).resolve().parent.parent / "current_cycle.txt"
AGENTS_DB_PATH = Path(__file__).resolve().parent / "agents.db"


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


async def get_agent_verification_status(session_factory, agent_id: int, chat_id: int | None = None, time_span: str | None = None) -> str | None:
    """Get the verification status of an agent."""
    async with session_scope(session_factory) as session:
        # Count approved submissions
        approved_result = await session.execute(
            select(func.count(Submission.id))
            .join(Verification, Verification.submission_id == Submission.id)
            .where(Submission.agent_id == agent_id)
            .where(Verification.status == VerificationStatus.approved.value)
        )
        approved_count = approved_result.scalar() or 0

        # Count pending submissions
        pending_result = await session.execute(
            select(func.count(Submission.id))
            .join(Verification, Verification.submission_id == Submission.id)
            .where(Submission.agent_id == agent_id)
            .where(Verification.status == VerificationStatus.pending.value)
        )
        pending_count = pending_result.scalar() or 0

        # Count total submissions
        total_result = await session.execute(
            select(func.count(Submission.id))
            .where(Submission.agent_id == agent_id)
        )
        total_count = total_result.scalar() or 0

        if approved_count > 0:
            return f"✅ {approved_count} verified"
        elif pending_count > 0:
            return f"⏳ {pending_count} pending verification"
        elif total_count > 0:
            return "❌ Unverified submissions"
        else:
            return None


async def get_agent_rank(session_factory, agent_id: int, time_span: str | None = None) -> int | None:
    """Get the current rank of an agent."""
    async with session_scope(session_factory) as session:
        # Create a subquery to count verified submissions for each agent
        verified_subquery = (
            select(
                Submission.agent_id,
                func.sum(case(
                    (Verification.status == VerificationStatus.approved.value, Submission.ap),
                    else_=0
                )).label("verified_ap"),
                func.sum(case(
                    (Verification.status == VerificationStatus.pending.value, Submission.ap),
                    else_=0
                )).label("pending_ap"),
            )
            .join(Verification, Verification.submission_id == Submission.id, isouter=True)
            .group_by(Submission.agent_id)
        ).subquery()

        # Main query to get all agents ranked by AP
        stmt = (
            select(
                Agent.id,
                func.sum(Submission.ap).label("total_ap"),
                func.coalesce(verified_subquery.c.verified_ap, 0).label("verified_ap"),
            )
            .join(Submission, Submission.agent_id == Agent.id)
            .join(verified_subquery, verified_subquery.c.agent_id == Agent.id, isouter=True)
        )

        if time_span is not None:
            stmt = stmt.where(Submission.time_span == time_span)

        stmt = (
            stmt.group_by(Agent.id)
            .order_by(
                func.coalesce(verified_subquery.c.verified_ap, 0).desc(),
                func.sum(Submission.ap).desc(),
                Agent.codename
            )
        )

        result = await session.execute(stmt)
        agents = result.all()

        # Find the rank of the specified agent
        for rank, (agent_id_result, _, _) in enumerate(agents, start=1):
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
        cursor = connection.execute(
            """
            SELECT 1
            FROM agents
            WHERE agent_name = ? AND date = ? AND time = ?
            LIMIT 1
            """,
            (
                parsed_data.get("agent_name"),
                parsed_data.get("date"),
                parsed_data.get("time"),
            ),
        )
        if cursor.fetchone():
            return False
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
    "+Beta Tokens",
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


def _parse_space_separated_dataset(lines: list[str]) -> dict[str, str]:
    header_line = lines[0]
    headers_tuple = SPACE_SEPARATED_HEADER_MAP.get(header_line)
    if not headers_tuple:
        raise ValueError("Unsupported header format")
    headers = list(headers_tuple)
    data_line = next((line for line in lines[1:] if line.strip()), None)
    if data_line is None:
        raise ValueError("Data must contain at least one data row")
    if not data_line.split():
        raise ValueError("Data row is empty")
    row_map = _parse_space_separated_row(data_line, headers)
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
    if cycle_value is None:
        return None
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
            raise ValueError("Unsupported header format")
        values = [part.strip() for part in lines[1].split('\t')]
        if len(values) != len(matched_columns):
            raise ValueError("Data row has unexpected number of columns")
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
    chat = getattr(update, "effective_chat", None)
    chat_type = getattr(chat, "type", None)
    if chat_type in {"group", "supergroup"}:
        bot_username = context.bot_data.get("bot_username")
        if not bot_username:
            me = await context.bot.get_me()
            bot_username = me.username or ""
            context.bot_data["bot_username"] = bot_username
        if not bot_username:
            return
        if f"@{bot_username.lower()}" not in text.lower():
            return
    parsed = parse_ingress_message(text)
    if not parsed:
        await message.reply_text("❌ Format incorrect. Use the standard format")
        return
    entries = [parsed] if isinstance(parsed, dict) else parsed
    saved = False
    for entry in entries:
        if isinstance(entry, dict):
            if not save_to_db(entry):
                await message.reply_text("⚠️ Duplicate entry ignored")
                return
            saved = True
    if not saved:
        await message.reply_text("❌ Format incorrect. Use the standard format")
        return
    await message.reply_text("✅ Data recorded")


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
            "• /register - Register your agent\n"
            "• /submit <data> - Submit your stats\n"
            "• /leaderboard - View rankings\n"
            "• /myrank - Check your rank\n"
            "• /verify - Submit screenshot proof\n\n"
            "📈 *LEADERBOARD OPTIONS:*\n"
            "• /leaderboard weekly - This week\n"
            "• /leaderboard hacks - By hacks\n"
            "• /leaderboard weekly hacks - Combined\n\n"
            "🎯 *OTHER USEFUL:*\n"
            "• /top ENL or /top RES - Faction tops\n"
            "• /top10 - Global top 10\n"
            "• /settings - Configure display\n"
            "• /help - Show this help\n\n"
            "💡 *EXAMPLES:*\n"
            "• /submit ap=1000000 hacks=5000\n"
            "• /myrank weekly\n"
            "• /leaderboard xm_collected"
        )
        await update.message.reply_text(help_text)
    else:
        # Simplified normal mode help (no complex markdown)
        help_text = (
            "🤖 *PrimeStatsBot Help* 🤖\n\n"
            "📊 *MAIN COMMANDS:*\n"
            "• /register - Register your agent\n"
            "• /submit <data> - Submit your stats\n"
            "• /leaderboard - View rankings\n"
            "• /myrank - Check your rank\n"
            "• /verify - Submit screenshot proof\n\n"
            "📈 *LEADERBOARD OPTIONS:*\n"
            "• /leaderboard weekly - This week\n"
            "• /leaderboard hacks - By hacks\n"
            "• /leaderboard weekly hacks - Combined\n\n"
            "🎯 *OTHER USEFUL:*\n"
            "• /top ENL or /top RES - Faction tops\n"
            "• /top10 - Global top 10\n"
            "• /settings - Configure display\n"
            "• /help - Show this help\n\n"
            "💡 *EXAMPLES:*\n"
            "• /submit ap=1000000 hacks=5000\n"
            "• /myrank weekly\n"
            "• /leaderboard xm_collected\n\n"
            "🔧 *ADMIN:* /privacy (groups) | /stats (admins)"
        )
        await update.message.reply_text(help_text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text("Welcome to the Ingress leaderboard bot. Use /register to begin.")


async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Disabled register command."""
    if update.message:
        await update.message.reply_text("This command has been disabled.")

    settings: Settings = context.application.bot_data["settings"]
    session_factory = context.application.bot_data["session_factory"]

    # Get agent's codename from database
    async with session_scope(session_factory) as session:
        result = await session.execute(
            select(Agent).where(Agent.telegram_id == update.effective_user.id)
        )
        agent = result.scalar_one_or_none()

    if agent is None:
        await update.message.reply_text(
            "❌ *Registration Required*\n\n"
            "You need to register first before checking your beta tokens status.\n\n"
            "Use /register to get started.",
            parse_mode="MarkdownV2"
        )
        return

    # Get beta tokens status message
    status_message = get_token_status_message(agent.codename)

    # Send the status message
    await update.message.reply_text(
        escape_markdown_v2(status_message),
        parse_mode="MarkdownV2"
    )


async def betatokens_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Disabled admin command."""
    if update.message:
        await update.message.reply_text("This command has been disabled.")

    settings: Settings = context.application.bot_data["settings"]

    # Check if user is admin
    if update.effective_user.id not in settings.admin_ids:
        await update.message.reply_text(
            "❌ *Access Denied*\n\nThis command is for administrators only\\.",
            parse_mode="MarkdownV2"
        )
        return

    args = context.args
    if not args:
        # Show current configuration
        config_message = get_medal_config()
        await update.message.reply_text(
            escape_markdown_v2(config_message),
            parse_mode="MarkdownV2"
        )
        return

    command = args[0].lower()

    if command == "requirements" and len(args) == 4:
        try:
            bronze = int(args[1])
            silver = int(args[2])
            gold = int(args[3])

            if bronze <= 0 or silver <= bronze or gold <= silver:
                raise ValueError("Invalid token requirements")

            update_medal_requirements(bronze, silver, gold)

            await update.message.reply_text(
                f"✅ *Beta Tokens Medal Requirements Updated*\n\n"
                f"🥉 Bronze: {bronze:,} tokens\n"
                f"🥈 Silver: {silver:,} tokens\n"
                f"🥇 Gold: {gold:,} tokens",
                parse_mode="MarkdownV2"
            )
        except ValueError:
            await update.message.reply_text(
                "❌ *Invalid Requirements*\n\n"
                "Usage: `/betatokens_admin requirements <bronze> <silver> <gold>`\n\n"
                "Requirements must be: 0 < bronze < silver < gold",
                parse_mode="MarkdownV2"
            )

    elif command == "task" and len(args) >= 2:
        task_name = " ".join(args[1:])
        update_task_name(task_name)

        await update.message.reply_text(
            f"✅ *Beta Tokens Task Updated*\n\n"
            f"🎯 New task name: {task_name}",
            parse_mode="MarkdownV2"
        )

    else:
        # Show help
        help_text = (
            "🛠️ *Beta Tokens Admin Commands*\n\n"
            "• `/betatokens_admin` \\- Show current configuration\n"
            "• `/betatokens_admin requirements <bronze> <silver> <gold>` \\- Set medal requirements\n"
            "• `/betatokens_admin task <task\\ name>` \\- Set current task name\n\n"
            "Example:\n"
            "`/betatokens_admin requirements 100 500 1000`"
        )
        await update.message.reply_text(
            escape_markdown_v2(help_text),
            parse_mode="MarkdownV2"
        )


async def last_week_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    settings: Settings = context.application.bot_data["settings"]
    since = datetime.now(timezone.utc) - timedelta(days=7)
    rows = await _fetch_cycle_leaderboard(10, since=since)
    await _send_cycle_leaderboard(update, settings, rows, "Top 10 agents — last 7 days")


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




async def verify_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the verification process by asking for submission data."""
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
        
        if not agent:
            await update.message.reply_text("Register first with /register.")
            return ConversationHandler.END
    
    await update.message.reply_text("Please send your submission data in one of these formats:\n\n"
                                   "1. Key-value format: ap=12345; metric=678\n"
                                   "2. Tab/space-separated data from Ingress Prime (copy and paste)")
    return VERIFY_SUBMIT


async def verify_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the submission data and ask for a screenshot."""
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    
    text = update.message.text or ""
    
    # Detect the format and parse accordingly
    try:
        # Check if the payload is in the new tab/space-separated format
        if ('\t' in text or 'Time Span' in text) and ('Agent Name' in text):
            # New tab/space-separated format
            ap, metrics, time_span = parse_tab_space_data(text)
        else:
            # Old key=value format
            ap, metrics = parse_submission(text)
            time_span = "ALL TIME"  # Default for old format
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return VERIFY_SUBMIT
    
    # Store the submission data in user context for later use
    context.user_data["verify_ap"] = ap
    context.user_data["verify_metrics"] = metrics
    context.user_data["verify_time_span"] = time_span
    
    await update.message.reply_text("Now please send a screenshot as proof of your score.")
    return VERIFY_SCREENSHOT


async def verify_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the screenshot and create a verification record."""
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    
    # Check if the message contains a photo
    if not update.message.photo:
        await update.message.reply_text("Please send a photo as a screenshot.")
        return VERIFY_SCREENSHOT
    
    # Get the submission data from user context
    ap = context.user_data.get("verify_ap")
    metrics = context.user_data.get("verify_metrics")
    time_span = context.user_data.get("verify_time_span", "ALL TIME")
    
    if not ap or not metrics:
        await update.message.reply_text("Submission data not found. Please start over with /verify.")
        return ConversationHandler.END
    
    # Get the highest resolution photo
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    
    # Generate a unique filename for the screenshot
    import uuid
    screenshot_filename = f"screenshots/{uuid.uuid4()}.jpg"
    
    # Download the screenshot
    import os
    os.makedirs("screenshots", exist_ok=True)
    await file.download_to_drive(screenshot_filename)
    
    # Get the agent
    session_factory = context.application.bot_data["session_factory"]
    chat = getattr(update, "effective_chat", None)
    is_group_chat = bool(chat and getattr(chat, "type", None) in {"group", "supergroup"})
    chat_id_value = chat.id if is_group_chat else None
    
    async with session_scope(session_factory) as session:
        # Check if the submission contains an agent name (new format)
        agent_name_from_data = metrics.get("agent_name")
        
        # If agent_name is provided in the data, try to find the agent by codename
        if agent_name_from_data:
            result = await session.execute(select(Agent).where(Agent.codename == agent_name_from_data))
            agent = result.scalar_one_or_none()
            
            # If agent found by codename, verify it belongs to the current user
            if agent and agent.telegram_id != update.effective_user.id:
                await update.message.reply_text(f"Agent '{agent_name_from_data}' is registered to a different Telegram account. Please use your own agent data.")
                return ConversationHandler.END
        
        # If no agent found by codename or no agent_name in data, try by Telegram ID
        if not agent:
            result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
            agent = result.scalar_one_or_none()
            
            if not agent:
                await update.message.reply_text("Register first with /register.")
                return ConversationHandler.END
        
        # Check if the user already has a submission for this chat
        result = await session.execute(
            select(Submission)
            .options(selectinload(Submission.verification))
            .where(Submission.agent_id == agent.id)
            .where(Submission.chat_id == chat_id_value)
            .order_by(Submission.submitted_at.desc())
            .limit(1)
        )
        existing_submission = result.scalar_one_or_none()
        
        if existing_submission:
            # Update the existing submission
            existing_submission.ap = ap
            existing_submission.metrics = convert_datetime_to_iso(metrics)
            existing_submission.time_span = time_span
            existing_submission.submitted_at = datetime.now(timezone.utc)
            
            # Update or create the verification record
            if existing_submission.verification:
                existing_submission.verification.screenshot_path = screenshot_filename
                existing_submission.verification.status = VerificationStatus.pending.value
                existing_submission.verification.admin_id = None
                existing_submission.verification.verified_at = None
                existing_submission.verification.rejection_reason = None
            else:
                verification = Verification(
                    submission_id=existing_submission.id,
                    screenshot_path=screenshot_filename,
                    status=VerificationStatus.pending.value
                )
                session.add(verification)
        else:
            # Create the submission
            submission = Submission(
                agent_id=agent.id,
                chat_id=chat_id_value,
                ap=ap,
                metrics=convert_datetime_to_iso(metrics),
                time_span=time_span
            )
            session.add(submission)
            await session.flush()  # Get the submission ID
            
            # Create the verification record
            verification = Verification(
                submission_id=submission.id,
                screenshot_path=screenshot_filename,
                status=VerificationStatus.pending.value
            )
            session.add(verification)
    
    # Clear user context
    context.user_data.clear()
    
    await update.message.reply_text("Your submission has been received and is pending verification. You will be notified once it's reviewed.")
    return ConversationHandler.END


async def verify_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the verification process."""
    if update.message:
        await update.message.reply_text("Verification process cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


async def proof_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the proof process by asking for a screenshot."""
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    
    # Get the optional database path from command arguments
    args = context.args
    db_path = args[0] if args else None
    
    # Store the database path in user context for later use
    if db_path:
        context.user_data["proof_db_path"] = db_path
        await update.message.reply_text(f"Please send a screenshot as proof for database path: {db_path}")
    else:
        context.user_data["proof_db_path"] = None
        await update.message.reply_text("Please send a screenshot as proof.")
    
    return PROOF_SCREENSHOT


async def proof_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the screenshot and save it with metadata."""
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    
    # Check if the message contains a photo
    if not update.message.photo:
        await update.message.reply_text("Please send a photo as a screenshot.")
        return PROOF_SCREENSHOT
    
    # Get the database path from user context
    db_path = context.user_data.get("proof_db_path")
    
    # Get the highest resolution photo
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    
    # Generate a unique filename for the screenshot
    import uuid
    import os
    screenshot_filename = f"proofs/{uuid.uuid4()}.jpg"
    
    # Create the proofs directory if it doesn't exist
    os.makedirs("proofs", exist_ok=True)
    
    # Download the screenshot
    await file.download_to_drive(screenshot_filename)
    
    # Get the agent
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
        
        if not agent:
            await update.message.reply_text("Register first with /register.")
            return ConversationHandler.END
        
        # Create a verification record for the proof
        verification = Verification(
            submission_id=None,  # No submission associated with proof
            screenshot_path=screenshot_filename,
            status=VerificationStatus.pending.value
        )
        session.add(verification)
        await session.flush()  # Get the verification ID
        
        # Create a pending action to track the proof with metadata
        pending_action = PendingAction(
            action=f"proof_{verification.id}",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            message_id=update.message.message_id,
            executed=False
        )
        session.add(pending_action)
    
    # Clear user context
    context.user_data.clear()
    
    # Format the response message
    if db_path:
        await update.message.reply_text(f"Your proof for database path '{db_path}' has been uploaded successfully (ID: {verification.id}). It is pending review.")
    else:
        await update.message.reply_text(f"Your proof has been uploaded successfully (ID: {verification.id}). It is pending review.")
    
    return ConversationHandler.END


async def pending_verifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Disabled command."""
    if update.message:
        await update.message.reply_text("This command has been disabled.")


async def reject_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Disabled command."""
    if not update.message or not update.effective_user:
        return
    
    settings: Settings = context.application.bot_data["settings"]
    
    # Check if the user is an admin
    if update.effective_user.id not in settings.admin_user_ids:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    # Get the verification ID and reason from command arguments
    args = context.args
    if not args or not args[0].isdigit() or len(args) < 2:
        await update.message.reply_text("Usage: /reject_verification <verification_id> <reason>")
        return
    
    verification_id = int(args[0])
    reason = " ".join(args[1:])
    
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        # Get the verification with submission and agent details
        result = await session.execute(
            select(Verification, Submission, Agent)
            .join(Submission, Verification.submission_id == Submission.id)
            .join(Agent, Submission.agent_id == Agent.id)
            .where(Verification.id == verification_id)
        )
        
        verification_data = result.one_or_none()
        
        if not verification_data:
            await update.message.reply_text(f"Verification request with ID {verification_id} not found.")
            return
        
        verification, submission, agent = verification_data
        
        # Update the verification status
        verification.status = VerificationStatus.rejected.value
        verification.admin_id = update.effective_user.id
        verification.verified_at = datetime.now(timezone.utc)
        verification.rejection_reason = reason
        
        # Notify the agent
        try:
            await context.bot.send_message(
                chat_id=agent.telegram_id,
                text=f"Your submission of {submission.ap} AP has been rejected. Reason: {reason}"
            )
        except Exception as e:
            logger.error(f"Failed to notify agent {agent.telegram_id} about rejected verification: {e}")
        
        await update.message.reply_text(
            f"Verification request ID {verification_id} for {agent.codename} [{agent.faction}] with {submission.ap} AP has been rejected."
        )


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
        
        # Get verification statistics
        pending_result = await session.execute(
            select(func.count(Verification.id))
            .where(Verification.status == VerificationStatus.pending.value)
        )
        pending_verifications = pending_result.scalar()
        
        approved_result = await session.execute(
            select(func.count(Verification.id))
            .where(Verification.status == VerificationStatus.approved.value)
        )
        approved_verifications = approved_result.scalar()
        
        rejected_result = await session.execute(
            select(func.count(Verification.id))
            .where(Verification.status == VerificationStatus.rejected.value)
        )
        rejected_verifications = rejected_result.scalar()
        
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
                "VERIFICATION STATISTICS\n"
                f"Pending verifications: {pending_verifications}\n"
                f"Approved verifications: {approved_verifications}\n"
                f"Rejected verifications: {rejected_verifications}\n\n"
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
                "✅ *VERIFICATION STATISTICS*\\n"
                f"⏳ Pending verifications: `{escape_markdown_v2(str(pending_verifications))}`\\n"
                f"✅ Approved verifications: `{escape_markdown_v2(str(approved_verifications))}`\\n"
                f"❌ Rejected verifications: `{escape_markdown_v2(str(rejected_verifications))}`\\n\\n"
                "👥 *GROUP STATISTICS*\\n"
                f"Total groups: `{escape_markdown_v2(str(total_groups))}`\\n\\n"
                "🏆 *MOST ACTIVE USERS*\\n"
            )
            
            for i, (codename, faction, count) in enumerate(active_users, start=1):
                stats_text += f"{escape_markdown_v2(str(i) + '.')}. {escape_markdown_v2(codename)} \\[{escape_markdown_v2(faction)}\\] — `{escape_markdown_v2(str(count))}` submissions\\n"
        
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


async def build_application() -> Application:
    load_dotenv()
    logging.basicConfig(level=logging.WARNING)
    settings = load_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    await init_models(engine)
    redis_conn = Redis.from_url(settings.redis_url)
    queue = Queue(connection=redis_conn)
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    application = ApplicationBuilder().token(settings.telegram_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["engine"] = engine
    application.bot_data["session_factory"] = session_factory
    application.bot_data["queue"] = queue
    application.bot_data["redis_connection"] = redis_conn
    application.bot_data["scheduler"] = scheduler
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
    application = await build_application()
    
    async with application:
        await application.start()
        await application.updater.start_polling()
        
        try:
            # Keep the bot running
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            await application.updater.stop()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
