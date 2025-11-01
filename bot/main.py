import asyncio
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from redis import Redis
from rq import Queue
import uvicorn
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
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
from .jobs.deletion import cleanup_expired_group_messages
from .jobs.backup import perform_backup, manual_backup_command
from .models import Agent, GroupMessage, GroupPrivacyMode, GroupSetting, PendingAction, Submission, WeeklyStat, Verification, VerificationStatus
from .services.leaderboard import get_leaderboard

logger = logging.getLogger(__name__)

CURRENT_CYCLE_FILE = Path(__file__).resolve().parent.parent / "current_cycle.txt"

# Constants for time span aliases
TIME_SPAN_ALIASES = {
    "ALL": "ALL TIME",
    "ALL TIME": "ALL TIME",
    "WEEKLY": "WEEKLY",
    "WEEK": "WEEKLY",
    "MONTHLY": "MONTHLY",
    "MONTH": "MONTHLY",
}

SPACE_SEPARATED_COLUMNS = [
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
    "Mission Day(s) Attended",
    "NL-1331 Meetup(s) Attended",
    "First Saturday Events",
    "Second Sunday Events",
    "+Delta Tokens",
    "+Delta Reso Points",
    "+Delta Field Points",
    "Agents Recruited",
    "Recursions",
    "Months Subscribed",
]

SPACE_SEPARATED_IGNORED_COLUMNS = {
    "+Delta Tokens",
    "+Delta Reso Points",
    "+Delta Field Points",
}

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

CODENAME, FACTION = range(2)
VERIFY_SUBMIT, VERIFY_SCREENSHOT = range(2)


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
    if header_line != " ".join(SPACE_SEPARATED_COLUMNS):
        raise ValueError("Unsupported header format")
    data_line = next((line for line in lines[1:] if line.strip()), None)
    if data_line is None:
        raise ValueError("Data must contain at least one data row")
    tokens = data_line.split()
    if not tokens:
        raise ValueError("Data row is empty")
    time_span = None
    position = 0
    max_span_tokens = min(len(tokens), 4)
    for end in range(1, max_span_tokens + 1):
        candidate = " ".join(tokens[:end])
        upper_candidate = candidate.upper()
        if upper_candidate in TIME_SPAN_ALIASES:
            time_span = TIME_SPAN_ALIASES[upper_candidate]
            position = end
            break
    if time_span is None:
        raise ValueError("Invalid time span value")
    name_tokens: list[str] = []
    while position < len(tokens) and tokens[position].upper() not in FACTION_ALIASES:
        name_tokens.append(tokens[position])
        position += 1
    if not name_tokens or position >= len(tokens):
        raise ValueError("Missing agent faction")
    agent_name = " ".join(name_tokens)
    faction_token = tokens[position]
    position += 1
    if faction_token.upper() not in FACTION_ALIASES:
        raise ValueError(f"Unknown faction: {faction_token}")
    if len(tokens) - position < 3:
        raise ValueError("Missing date or time values")
    date_token = tokens[position]
    position += 1
    time_token = tokens[position]
    position += 1
    level_token = tokens[position]
    position += 1
    remaining_tokens = tokens[position:]
    expected_remaining = len(SPACE_SEPARATED_COLUMNS) - 6
    if len(remaining_tokens) != expected_remaining:
        raise ValueError("Data row has unexpected number of columns")
    data_dict: dict[str, str] = {
        "Time Span": time_span,
        "Agent Name": agent_name,
        "Agent Faction": faction_token,
        "Date (yyyy-mm-dd)": date_token,
        "Time (hh:mm:ss)": time_token,
        "Level": level_token,
    }
    for column, value in zip(SPACE_SEPARATED_COLUMNS[6:], remaining_tokens):
        if column in SPACE_SEPARATED_IGNORED_COLUMNS:
            continue
        data_dict[column] = value
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
    for end in range(1, max_span_tokens + 1):
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
        if header_line != " ".join(SPACE_SEPARATED_COLUMNS):
            return None
        headers = list(SPACE_SEPARATED_COLUMNS)
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
    results: list[dict[str, Any]] = []
    for data_line in lines[1:]:
        if not data_line:
            continue
        if use_tabs:
            values = [part.strip() for part in data_line.split("\t")]
            if len(values) != len(headers):
                return None
            row_map = dict(zip(headers, values))
        else:
            row_map = _parse_space_separated_row(data_line, headers)
            if row_map is None:
                return None
        normalized = _normalize_row(row_map, headers, cycle_index, cycle_header)
        if normalized is None:
            return None
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
    if '\t' not in lines[0]:
        data_dict = _parse_space_separated_dataset(lines)
    else:
        headers = [part.strip() for part in lines[0].split('\t')]
        filtered_headers = []
        header_indices = []
        for index, header in enumerate(headers):
            if "+Delta" in header:
                continue
            filtered_headers.append(header)
            header_indices.append(index)
        values = [part.strip() for part in lines[1].split('\t')]
        if len(values) != len(headers):
            raise ValueError("Data row has unexpected number of columns")
        filtered_values = [values[index] for index in header_indices]
        data_dict = dict(zip(filtered_headers, filtered_values))
    for column in SPACE_SEPARATED_IGNORED_COLUMNS:
        data_dict.pop(column, None)
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
    metrics = {
        "agent_name": data_dict["Agent Name"],
        "faction": faction,
    }
    if "Date (yyyy-mm-dd)" in data_dict and "Time (hh:mm:ss)" in data_dict:
        from datetime import datetime
        date_str = data_dict["Date (yyyy-mm-dd)"]
        time_str = data_dict["Time (hh:mm:ss)"]
        try:
            metrics["timestamp"] = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError(f"Invalid date/time format: {date_str} {time_str}") from exc
    for header, value in data_dict.items():
        if header in {
            "Agent Name",
            "Agent Faction",
            "Lifetime AP",
            "Time Span",
            "Date (yyyy-mm-dd)",
            "Time (hh:mm:ss)",
        }:
            continue
        key = header.lower().replace(" ", "_")
        cleaned_value = value.replace(",", "")
        try:
            metrics[key] = int(cleaned_value)
            continue
        except ValueError:
            pass
        try:
            metrics[key] = float(cleaned_value)
            continue
        except ValueError:
            pass
        metrics[key] = value
    return ap, metrics, time_span


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text("Welcome to the Ingress leaderboard bot. Use /register to begin.")


async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
    if agent:
        await update.message.reply_text(f"You are already registered as {agent.codename} ({agent.faction}).")
        return ConversationHandler.END
    await update.message.reply_text("Please send your agent codename.")
    return CODENAME


async def register_codename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return ConversationHandler.END
    codename = update.message.text.strip()
    if not codename:
        await update.message.reply_text("Codename cannot be empty. Send your codename.")
        return CODENAME
    context.user_data["codename"] = codename
    await update.message.reply_text("Send your faction (ENL or RES).")
    return FACTION


async def register_faction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    faction = update.message.text.strip().upper()
    if faction not in {"ENL", "RES"}:
        await update.message.reply_text("Faction must be ENL or RES. Send your faction.")
        return FACTION
    codename = context.user_data.get("codename")
    if not codename:
        await update.message.reply_text("Codename missing. Restart with /register.")
        return ConversationHandler.END
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
        if agent:
            agent.codename = codename
            agent.faction = faction
        else:
            session.add(Agent(telegram_id=update.effective_user.id, codename=codename, faction=faction))
    await update.message.reply_text(f"Registered {codename} ({faction}).")
    context.user_data.clear()
    return ConversationHandler.END


async def register_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("Registration cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


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


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings: Settings = context.application.bot_data["settings"]
    text = update.message.text or ""
    _, _, payload = text.partition(" ")
    payload = payload.strip()
    if not payload:
        await update.message.reply_text("Usage: /submit ap=12345; metric=678 or paste tab/space-separated data from Ingress Prime")
        return
    
    # Detect the format and parse accordingly
    try:
        # Check if the payload is in the new tab/space-separated format
        if ('\t' in payload or 'Time Span' in payload) and ('Agent Name' in payload):
            # New tab/space-separated format
            ap, metrics, time_span = parse_tab_space_data(payload)
        else:
            # Old key=value format
            ap, metrics = parse_submission(payload)
            time_span = "ALL TIME"  # Default for old format
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return
    chat = getattr(update, "effective_chat", None)
    is_group_chat = bool(chat and getattr(chat, "type", None) in {"group", "supergroup"})
    chat_id_value = chat.id if is_group_chat else None
    session_factory = context.application.bot_data["session_factory"]
    agent = None
    
    # Check if the submission contains an agent name (new format)
    agent_name_from_data = metrics.get("agent_name")
    
    async with session_scope(session_factory) as session:
        # If agent_name is provided in the data, try to find the agent by codename
        if agent_name_from_data:
            result = await session.execute(select(Agent).where(Agent.codename == agent_name_from_data))
            agent = result.scalar_one_or_none()
            
            # If agent found by codename, verify it belongs to the current user
            if agent and agent.telegram_id != update.effective_user.id:
                await update.message.reply_text(f"Agent '{agent_name_from_data}' is registered to a different Telegram account. Please use your own agent data.")
                return
        
        # If no agent found by codename or no agent_name in data, try by Telegram ID
        if not agent:
            result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
            agent = result.scalar_one_or_none()
            if not agent:
                await update.message.reply_text("Register first with /register.")
                return
        
        # Check if the user already has a submission for this chat
        result = await session.execute(
            select(Submission)
            .where(Submission.agent_id == agent.id)
            .where(Submission.chat_id == chat_id_value)
            .order_by(Submission.submitted_at.desc())
            .limit(1)
        )
        existing_submission = result.scalar_one_or_none()
        
        if existing_submission:
            # Update the existing submission
            existing_submission.ap = ap
            existing_submission.metrics = metrics
            existing_submission.time_span = time_span
            existing_submission.submitted_at = datetime.now(timezone.utc)
            submission = existing_submission
            
            # If the submission has a verification, reset it to pending
            if existing_submission.verification:
                existing_submission.verification.status = VerificationStatus.pending.value
                existing_submission.verification.admin_id = None
                existing_submission.verification.verified_at = None
                existing_submission.verification.rejection_reason = None
        else:
            # Create a new submission
            submission = Submission(
                agent_id=agent.id,
                chat_id=chat_id_value,
                ap=ap,
                metrics=metrics,
                time_span=time_span
            )
            session.add(submission)
            await session.flush()  # Get the submission ID
            
            # Create a verification record for the new submission
            verification = Verification(
                submission_id=submission.id,
                screenshot_path="",  # Empty path for now, will be updated if user sends screenshot
                status=VerificationStatus.pending.value
            )
            session.add(verification)
            
        # Get agent name and faction for the response message
        agent_name = metrics.get("agent_name", agent.codename)
        faction = metrics.get("faction", agent.faction)
        
        if is_group_chat:
            setting = await _get_or_create_group_setting(
                session,
                chat.id,
                settings.group_message_retention_minutes,
            )
            # Store the messages for later deletion by the scheduled job
            if setting.privacy_mode != GroupPrivacyMode.public.value:
                if settings.text_only_mode:
                    # Text-only mode for better performance on old Android devices
                    reply = await update.message.reply_text(f"Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")
                else:
                    # Normal mode with emojis
                    reply = await update.message.reply_text(f"✅ Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")
                original_message_id = getattr(update.message, "message_id", None)
                confirmation_message_id = getattr(reply, "message_id", None)
                
                if original_message_id is not None:
                    session.add(
                        GroupMessage(
                            chat_id=chat.id,
                            message_id=original_message_id,
                            received_at=update.message.date or datetime.now(timezone.utc),
                        )
                    )
                
                if confirmation_message_id is not None and setting.privacy_mode == GroupPrivacyMode.soft.value:
                    session.add(
                        GroupMessage(
                            chat_id=chat.id,
                            message_id=confirmation_message_id,
                            received_at=datetime.now(timezone.utc),
                        )
                    )
            else:
                if settings.text_only_mode:
                    # Text-only mode for better performance on old Android devices
                    await update.message.reply_text(f"Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")
                else:
                    # Normal mode with emojis
                    await update.message.reply_text(f"✅ Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")
        else:
            if settings.text_only_mode:
                # Text-only mode for better performance on old Android devices
                await update.message.reply_text(f"Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")
            else:
                # Normal mode with emojis
                await update.message.reply_text(f"✅ Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")


async def submit_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle submission of tab/space-separated data from Ingress Prime leaderboard."""
    if not update.message or not update.effective_user:
        return
    
    settings: Settings = context.application.bot_data["settings"]
    text = update.message.text or ""
    _, _, payload = text.partition(" ")
    payload = payload.strip()
    
    if not payload:
        await update.message.reply_text("Usage: /submit_data <tab/space-separated data>")
        return
    
    try:
        ap, metrics, time_span = parse_tab_space_data(payload)
    except ValueError as exc:
        await update.message.reply_text(f"Error parsing data: {str(exc)}")
        return
    
    chat = getattr(update, "effective_chat", None)
    is_group_chat = bool(chat and getattr(chat, "type", None) in {"group", "supergroup"})
    chat_id_value = chat.id if is_group_chat else None
    session_factory = context.application.bot_data["session_factory"]
    
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
                return
        
        # If no agent found by codename or no agent_name in data, try by Telegram ID
        if not agent:
            result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
            agent = result.scalar_one_or_none()
            
            if not agent:
                await update.message.reply_text("Register first with /register.")
                return
        
        # Check if the user already has a submission for this chat
        result = await session.execute(
            select(Submission)
            .where(Submission.agent_id == agent.id)
            .where(Submission.chat_id == chat_id_value)
            .order_by(Submission.submitted_at.desc())
            .limit(1)
        )
        existing_submission = result.scalar_one_or_none()
        
        if existing_submission:
            # Update the existing submission
            existing_submission.ap = ap
            existing_submission.metrics = metrics
            existing_submission.time_span = time_span
            existing_submission.submitted_at = datetime.now(timezone.utc)
            submission = existing_submission
            
            # If the submission has a verification, reset it to pending
            if existing_submission.verification:
                existing_submission.verification.status = VerificationStatus.pending.value
                existing_submission.verification.admin_id = None
                existing_submission.verification.verified_at = None
                existing_submission.verification.rejection_reason = None
        else:
            # Create a new submission
            submission = Submission(
                agent_id=agent.id,
                chat_id=chat_id_value,
                ap=ap,
                metrics=metrics,
                time_span=time_span
            )
            session.add(submission)
            await session.flush()  # Get the submission ID
            
            # Create a verification record for the new submission
            verification = Verification(
                submission_id=submission.id,
                screenshot_path="",  # Empty path for now, will be updated if user sends screenshot
                status=VerificationStatus.pending.value
            )
            session.add(verification)
        
        # Format the response message
        agent_name = metrics.get("agent_name", agent.codename)
        faction = metrics.get("faction", agent.faction)
        
        if is_group_chat:
            setting = await _get_or_create_group_setting(
                session,
                chat.id,
                settings.group_message_retention_minutes,
            )
            # Store the messages for later deletion by the scheduled job
            if setting.privacy_mode != GroupPrivacyMode.public.value:
                if settings.text_only_mode:
                    # Text-only mode for better performance on old Android devices
                    reply = await update.message.reply_text(f"Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")
                else:
                    # Normal mode with emojis
                    reply = await update.message.reply_text(f"✅ Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")
                original_message_id = getattr(update.message, "message_id", None)
                confirmation_message_id = getattr(reply, "message_id", None)
                
                if original_message_id is not None:
                    session.add(
                        GroupMessage(
                            chat_id=chat.id,
                            message_id=original_message_id,
                            received_at=update.message.date or datetime.now(timezone.utc),
                        )
                    )
                
                if confirmation_message_id is not None and setting.privacy_mode == GroupPrivacyMode.soft.value:
                    session.add(
                        GroupMessage(
                            chat_id=chat.id,
                            message_id=confirmation_message_id,
                            received_at=datetime.now(timezone.utc),
                        )
                    )
            else:
                if settings.text_only_mode:
                    # Text-only mode for better performance on old Android devices
                    await update.message.reply_text(f"Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")
                else:
                    # Normal mode with emojis
                    await update.message.reply_text(f"✅ Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")
        else:
            if settings.text_only_mode:
                # Text-only mode for better performance on old Android devices
                await update.message.reply_text(f"Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")
            else:
                # Normal mode with emojis
                await update.message.reply_text(f"✅ Recorded {ap} AP for {agent_name} [{faction}] ({time_span}). Use /verify to submit a screenshot for verification.")


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    settings: Settings = context.application.bot_data["settings"]
    session_factory = context.application.bot_data["session_factory"]
    chat = getattr(update, "effective_chat", None)
    is_group_chat = bool(chat and getattr(chat, "type", None) in {"group", "supergroup"})
    chat_id_value = chat.id if is_group_chat else None
    privacy_mode = GroupPrivacyMode.public
    
    # Parse command arguments for time_span and metric
    args = context.args
    time_span = None
    metric = "ap"  # Default metric
    
    # Check if time_span is specified
    if args and args[0].upper() in TIME_SPAN_ALIASES:
        time_span = TIME_SPAN_ALIASES[args[0].upper()]
        # If there's a second argument, use it as the metric
        if len(args) > 1:
            metric = args[1].lower()
    # If no time_span but there's an argument, use it as the metric
    elif args:
        metric = args[0].lower()
    
    async with session_scope(session_factory) as session:
        if is_group_chat:
            setting = await _get_or_create_group_setting(
                session,
                chat.id,
                settings.group_message_retention_minutes,
            )
            privacy_mode = GroupPrivacyMode(setting.privacy_mode)
        
        # Get leaderboard with optional filters
        rows = await get_leaderboard(
            session,
            settings.leaderboard_size,
            chat_id_value,
            time_span=time_span,
            metric=metric
        )
    
    if not rows:
        await update.message.reply_text("No submissions yet.")
        return
    
    # Get verification status for each agent
    async with session_scope(session_factory) as session:
        agent_verification_status = {}
        for codename, faction, metric_value, metrics_dict in rows:
            result = await session.execute(
                select(Agent.id)
                .where(Agent.codename == codename)
                .where(Agent.faction == faction)
            )
            agent = result.scalar_one_or_none()
            
            if agent:
                # Check if the agent has any approved submissions
                result = await session.execute(
                    select(func.count(Submission.id))
                    .join(Verification, Verification.submission_id == Submission.id)
                    .where(Submission.agent_id == agent.id)
                    .where(Verification.status == VerificationStatus.approved.value)
                )
                approved_count = result.scalar() or 0
                
                # Check if the agent has any pending submissions
                result = await session.execute(
                    select(func.count(Submission.id))
                    .join(Verification, Verification.submission_id == Submission.id)
                    .where(Submission.agent_id == agent.id)
                    .where(Verification.status == VerificationStatus.pending.value)
                )
                pending_count = result.scalar() or 0
                
                # Determine verification status
                if approved_count > 0:
                    agent_verification_status[codename] = "✅"
                elif pending_count > 0:
                    agent_verification_status[codename] = "⏳"
                else:
                    agent_verification_status[codename] = "❌"
    
    # Format the leaderboard header
    header_parts = ["Leaderboard"]
    if time_span:
        header_parts.append(f"({time_span})")
    if metric != "ap":
        header_parts.append(f"by {metric.upper()}")
    
    header = " ".join(header_parts)
    
    if settings.text_only_mode:
        # Text-only mode for better performance on old Android devices
        lines = [header]
        for index, (codename, faction, metric_value, metrics_dict) in enumerate(rows, start=1):
            status = agent_verification_status.get(codename, "")
            if metric == "ap":
                lines.append(f"{index}. {codename} [{faction}] {status} - {metric_value:,} AP")
            else:
                lines.append(f"{index}. {codename} [{faction}] {status} - {metric_value:,} {metric.upper()}")
        reply = await update.message.reply_text("\n".join(lines))
    else:
        # Normal mode with emojis and markdown
        lines = [f"🏆 *{header}* 🏆"]
        for index, (codename, faction, metric_value, metrics_dict) in enumerate(rows, start=1):
            status = agent_verification_status.get(codename, "")
            if metric == "ap":
                lines.append(f"{index}. {codename} [{faction}] {status} — {metric_value:,} AP")
            else:
                lines.append(f"{index}. {codename} [{faction}] {status} — {metric_value:,} {metric.upper()}")
        reply = await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")
    
    # In strict mode, store messages for immediate deletion and clear submissions
    if is_group_chat and privacy_mode is GroupPrivacyMode.strict:
        confirmation_message_id = getattr(reply, "message_id", None)
        original_message_id = getattr(update.message, "message_id", None)
        
        async with session_scope(session_factory) as session:
            # Store messages for deletion
            if original_message_id is not None:
                session.add(
                    GroupMessage(
                        chat_id=chat.id,
                        message_id=original_message_id,
                        received_at=update.message.date or datetime.now(timezone.utc),
                    )
                )
            
            if confirmation_message_id is not None:
                session.add(
                    GroupMessage(
                        chat_id=chat.id,
                        message_id=confirmation_message_id,
                        received_at=datetime.now(timezone.utc),
                    )
                )
            
            # Clear submissions and other data for this group
            await session.execute(delete(Submission).where(Submission.chat_id == chat_id_value))
            await session.execute(delete(GroupMessage).where(GroupMessage.chat_id == chat_id_value))
            await session.execute(delete(PendingAction).where(PendingAction.chat_id == chat_id_value))


async def myrank_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    settings: Settings = context.application.bot_data["settings"]
    session_factory = context.application.bot_data["session_factory"]
    chat = getattr(update, "effective_chat", None)
    is_group_chat = bool(chat and getattr(chat, "type", None) in {"group", "supergroup"})
    chat_id_value = chat.id if is_group_chat else None
    
    # Parse command arguments for time_span and metric
    args = context.args
    time_span = None
    metric = "ap"  # Default metric
    
    # Check if time_span is specified
    if args and args[0].upper() in TIME_SPAN_ALIASES:
        time_span = TIME_SPAN_ALIASES[args[0].upper()]
        # If there's a second argument, use it as the metric
        if len(args) > 1:
            metric = args[1].lower()
    # If no time_span but there's an argument, use it as the metric
    elif args:
        metric = args[0].lower()
    
    # Get the agent
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
        
        if not agent:
            await update.message.reply_text("Register first with /register.")
            return
        
        # Determine which metric field to use for ranking
        if metric == "ap":
            metric_field = Submission.ap
        else:
            # For custom metrics, we need to extract them from the JSON metrics field
            metric_field = func.coalesce(Submission.metrics[metric].astext.cast(Integer), 0)
        
        # Get the agent's metric value
        agent_metric_result = await session.execute(
            select(func.sum(metric_field))
            .where(Submission.agent_id == agent.id)
            .where(Submission.chat_id == chat_id_value if is_group_chat else True)
        )
        if time_span:
            agent_metric_result = await session.execute(
                select(func.sum(metric_field))
                .where(Submission.agent_id == agent.id)
                .where(Submission.chat_id == chat_id_value if is_group_chat else True)
                .where(Submission.time_span == time_span)
            )
        
        agent_metric_value = agent_metric_result.scalar() or 0
        
        # Get all agents ranked by the selected metric (for the same chat_id if in group)
        stmt = (
            select(Agent.id, Agent.codename, Agent.faction, func.sum(metric_field).label("metric_value"))
            .join(Submission, Submission.agent_id == Agent.id)
        )
        if is_group_chat:
            stmt = stmt.where(Submission.chat_id == chat_id_value)
        if time_span:
            stmt = stmt.where(Submission.time_span == time_span)
        stmt = stmt.group_by(Agent.id).order_by(func.sum(metric_field).desc())
        
        result = await session.execute(stmt)
        all_agents = result.all()
        
        # Find the user's rank
        rank = None
        for i, (agent_id, codename, faction, metric_value) in enumerate(all_agents, start=1):
            if agent_id == agent.id:
                rank = i
                break
        
        if rank is None:
            await update.message.reply_text("You don't have any submissions yet.")
            return
        
        # Format the response
        context_parts = ["Your rank"]
        if is_group_chat:
            context_parts.append("in this group")
        else:
            context_parts.append("globally")
        
        if time_span:
            context_parts.append(f"for {time_span}")
        
        if metric != "ap":
            context_parts.append(f"by {metric.upper()}")
        
        context_text = " ".join(context_parts)
        
        if settings.text_only_mode:
            # Text-only mode for better performance on old Android devices
            response = f"{context_text} is #{rank}\n"
            if metric == "ap":
                response += f"{agent.codename} [{agent.faction}] - {int(agent_metric_value):,} AP"
            else:
                response += f"{agent.codename} [{agent.faction}] - {int(agent_metric_value):,} {metric.upper()}"
        else:
            # Normal mode with emojis and markdown
            response = f"{context_text} is *#{rank}*\n"
            if metric == "ap":
                response += f"{agent.codename} [{agent.faction}] — {int(agent_metric_value):,} AP"
            else:
                response += f"{agent.codename} [{agent.faction}] — {int(agent_metric_value):,} {metric.upper()}"
        
        await update.message.reply_text(response, parse_mode="MarkdownV2")


async def store_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or message.chat_id is None:
        return
    timestamp = message.date or datetime.now(timezone.utc)
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        setting = await _get_or_create_group_setting(session, message.chat_id)
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
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        setting = await _get_or_create_group_setting(session, chat.id)
        setting.privacy_mode = mode.value
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
            .where(Submission.agent_id == agent.id)
            .where(Submission.chat_id == chat_id_value)
            .order_by(Submission.submitted_at.desc())
            .limit(1)
        )
        existing_submission = result.scalar_one_or_none()
        
        if existing_submission:
            # Update the existing submission
            existing_submission.ap = ap
            existing_submission.metrics = metrics
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
                metrics=metrics,
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


async def pending_verifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all pending verification requests (admin only)."""
    if not update.message or not update.effective_user:
        return
    
    settings: Settings = context.application.bot_data["settings"]
    
    # Check if the user is an admin
    if update.effective_user.id not in settings.admin_user_ids:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        # Get all pending verifications with submission and agent details
        result = await session.execute(
            select(Verification, Submission, Agent)
            .join(Submission, Verification.submission_id == Submission.id)
            .join(Agent, Submission.agent_id == Agent.id)
            .where(Verification.status == VerificationStatus.pending.value)
            .order_by(Verification.created_at.asc())
        )
        
        pending_verifications = result.all()
        
        if not pending_verifications:
            await update.message.reply_text("No pending verification requests.")
            return
        
        # Format the response
        lines = ["*Pending Verification Requests:*\n"]
        for verification, submission, agent in pending_verifications:
            lines.append(
                f"ID: {verification.id}\n"
                f"Agent: {agent.codename} [{agent.faction}]\n"
                f"AP: {submission.ap}\n"
                f"Submitted: {submission.submitted_at.strftime('%Y-%m-%d %H:%M')}\n"
            )
        
        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")


async def approve_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve a verification request (admin only)."""
    if not update.message or not update.effective_user:
        return
    
    settings: Settings = context.application.bot_data["settings"]
    
    # Check if the user is an admin
    if update.effective_user.id not in settings.admin_user_ids:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    # Get the verification ID from command arguments
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: /approve_verification <verification_id>")
        return
    
    verification_id = int(args[0])
    
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
        verification.status = VerificationStatus.approved.value
        verification.admin_id = update.effective_user.id
        verification.verified_at = datetime.now(timezone.utc)
        
        # Notify the agent
        try:
            await context.bot.send_message(
                chat_id=agent.telegram_id,
                text=f"Your submission of {submission.ap} AP has been approved and verified!"
            )
        except Exception as e:
            logger.error(f"Failed to notify agent {agent.telegram_id} about approved verification: {e}")
        
        await update.message.reply_text(
            f"Verification request ID {verification_id} for {agent.codename} [{agent.faction}] with {submission.ap} AP has been approved."
        )


async def reject_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject a verification request (admin only)."""
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
                    # Normal mode with emojis and markdown
                    announcement = "🏆 *Weekly Competition Results* 🏆\n\n"
                    
                    # Add ENL winners
                    if enl_agents:
                        announcement += "*🟢 Enlightened (ENL) Top Performers:*\n"
                        for i, (codename, ap) in enumerate(enl_agents[:3], start=1):
                            announcement += f"{i}. {codename} - {ap:,} AP\n"
                        announcement += "\n"
                    else:
                        announcement += "*🟢 Enlightened (ENL):* No submissions this week\n\n"
                    
                    # Add RES winners
                    if res_agents:
                        announcement += "*🔵 Resistance (RES) Top Performers:*\n"
                        for i, (codename, ap) in enumerate(res_agents[:3], start=1):
                            announcement += f"{i}. {codename} - {ap:,} AP\n"
                        announcement += "\n"
                    else:
                        announcement += "*🔵 Resistance (RES):* No submissions this week\n\n"
                    
                    # Add footer
                    announcement += "Scores have been reset for the new week. Good luck! 🍀"
                
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
                                # Normal mode with markdown
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


def configure_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    register_handler = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            CODENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_codename)],
            FACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_faction)],
        },
        fallbacks=[CommandHandler("cancel", register_cancel)],
    )
    application.add_handler(register_handler)
    
    verify_handler = ConversationHandler(
        entry_points=[CommandHandler("verify", verify_start)],
        states={
            VERIFY_SUBMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_submit)],
            VERIFY_SCREENSHOT: [MessageHandler(filters.PHOTO, verify_screenshot)],
        },
        fallbacks=[CommandHandler("cancel", verify_cancel)],
    )
    application.add_handler(verify_handler)
    
    application.add_handler(CommandHandler("submit", submit))
    application.add_handler(CommandHandler("submit_data", submit_data))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("myrank", myrank_command))
    application.add_handler(CommandHandler("privacy", set_group_privacy))
    application.add_handler(CommandHandler("pending_verifications", pending_verifications))
    application.add_handler(CommandHandler("approve_verification", approve_verification))
    application.add_handler(CommandHandler("reject_verification", reject_verification))
    application.add_handler(CommandHandler("backup", manual_backup_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, store_group_message))


async def run() -> None:
    load_dotenv()
    # Reduce logging verbosity for better performance on old Android devices
    logging.basicConfig(level=logging.WARNING)
    settings = load_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    await init_models(engine)
    redis_conn = Redis.from_url(settings.redis_url)
    queue = Queue(connection=redis_conn)
    dashboard_server: uvicorn.Server | None = None
    dashboard_task: asyncio.Task | None = None
    if settings.dashboard_enabled:
        dashboard_app = create_dashboard_app(settings, session_factory)
        config = uvicorn.Config(
            dashboard_app,
            host=settings.dashboard_host,
            port=settings.dashboard_port,
            log_level="info",
            loop="asyncio",
        )
        dashboard_server = uvicorn.Server(config)
        dashboard_task = asyncio.create_task(dashboard_server.serve())
    application = ApplicationBuilder().token(settings.telegram_token).build()
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
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
        minutes=10,
        args=(application, session_factory),
        max_instances=1,
        misfire_grace_time=60,
        coalesce=True,
    )
    # Add backup job if enabled
    if settings.backup_enabled:
        # Determine trigger based on schedule
        if settings.backup_schedule.lower() == "daily":
            trigger = "cron"
            trigger_args = {"hour": 2, "minute": 0}  # Run at 2 AM UTC daily
        elif settings.backup_schedule.lower() == "weekly":
            trigger = "cron"
            trigger_args = {"day_of_week": "sun", "hour": 2, "minute": 0}  # Run at 2 AM UTC on Sundays
        else:
            # Default to daily if schedule is not recognized
            logger.warning(f"Unknown backup schedule '{settings.backup_schedule}', defaulting to daily")
            trigger = "cron"
            trigger_args = {"hour": 2, "minute": 0}
        
        scheduler.add_job(
            perform_backup,
            trigger=trigger,
            args=(settings, application),
            max_instances=1,
            misfire_grace_time=3600,  # 1 hour grace time
            coalesce=True,
            **trigger_args
        )
        logger.info(f"Backup job scheduled to run {settings.backup_schedule} at 2 AM UTC")
    
    scheduler.start()
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    try:
        await application.updater.idle()
    finally:
        if dashboard_server is not None:
            dashboard_server.should_exit = True
        scheduler.shutdown(wait=False)
        await application.stop()
        await application.shutdown()
        if dashboard_task is not None:
            await dashboard_task
        await engine.dispose()
        redis_conn.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
