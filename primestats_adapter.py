import os
import re
from typing import Dict, List, Optional, Tuple

DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
TIME_PATTERN = re.compile(r"\b\d{2}:\d{2}(?::\d{2})?\b")
NUMERIC_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")
TIME_SPAN_WORDS = {
    "ALL",
    "TIME",
    "THIS",
    "WEEK",
    "WEEKS",
    "LAST",
    "DAY",
    "DAYS",
    "CYCLE",
    "CURRENT",
    "PREVIOUS",
    "PAST",
    "MONTH",
    "MONTHS",
    "YEAR",
    "YEARS",
    "SINCE",
    "INCEPTION",
}
METRIC_KEYS = [
    "level",
    "lifetime_ap",
    "current_ap",
    "unique_portals_visited",
    "unique_portals_drone_visited",
    "furthest_drone_distance",
    "portals_discovered",
    "xm_collected",
    "opr_agreements",
    "portal_scans_uploaded",
    "uniques_scout_controlled",
    "resonators_deployed",
    "links_created",
    "control_fields_created",
    "mind_units_captured",
    "longest_link_ever_created",
    "largest_control_field",
    "xm_recharged",
    "portals_captured",
    "unique_portals_captured",
    "mods_deployed",
    "hacks",
    "drone_hacks",
    "glyph_hack_points_completed",
    "hackstreaks",
    "longest_sojourner_streak",
    "resonators_destroyed",
    "portals_neutralized",
    "enemy_links_destroyed",
    "enemy_fields_destroyed",
    "battle_beacon_combatant",
    "drones_returned",
    "machina_links_destroyed",
    "machina_resonators_destroyed",
    "machina_portals_neutralized",
    "machina_portals_reclaimed",
    "max_time_portal_held",
    "max_time_link_maintained",
    "max_link_length_x_days",
    "max_time_field_held",
    "largest_field_mus_x_days",
    "forced_drone_recalls",
    "distance_walked",
    "kinetic_capsules_completed",
    "unique_missions_completed",
    "research_bounties_completed",
    "research_days_completed",
    "nl1331_meetups_attended",
    "first_saturday_events",
    "second_sunday_events",
    "opr_live_events",
    "beta_tokens",
    "recursions",
]

def _tokenize(line: str) -> List[str]:
    return re.findall(r"\S+", line)


def _normalize_time(value: str) -> str:
    if value.count(":") == 1:
        return f"{value}:00"
    return value


def _normalize_faction(value: str) -> Optional[str]:
    if not value:
        return None
    text = value.strip().lower()
    if text in {"enl", "enlightened"}:
        return "ENL"
    if text in {"res", "resistance"}:
        return "RES"
    return None


def _is_numeric(token: str) -> bool:
    if token is None:
        return False
    normalized = token.replace(",", "")
    if normalized in {"-", "--", "—"}:
        return False
    return bool(NUMERIC_PATTERN.fullmatch(normalized))


def _coerce_value(token: str):
    normalized = token.replace(",", "")
    if normalized in {"", "-", "--", "—"}:
        return None
    if NUMERIC_PATTERN.fullmatch(normalized):
        if "." in normalized:
            number = float(normalized)
            if number.is_integer():
                return int(number)
            return number
        return int(normalized)
    return token


def _extract_cycle_info(parts: List[str]) -> Tuple[Optional[str], Optional[int]]:
    for index in range(len(parts) - 1, -1, -1):
        token = parts[index]
        if token.startswith("+") and len(token) > 1:
            name = token[1:].strip()
            points = None
            if index + 1 < len(parts) and _is_numeric(parts[index + 1]):
                value = _coerce_value(parts[index + 1])
                if isinstance(value, float) and value.is_integer():
                    value = int(value)
                if isinstance(value, int):
                    points = value
                else:
                    points = None
                del parts[index + 1]
            del parts[index]
            return name or None, points
    return None, None


def _read_current_cycle() -> Optional[str]:
    if not os.path.exists("current_cycle.txt"):
        return None
    with open("current_cycle.txt", "r", encoding="utf-8") as handle:
        value = handle.read().strip()
    return value or None


def _write_current_cycle(cycle_name: str) -> None:
    if not cycle_name:
        return
    with open("current_cycle.txt", "w", encoding="utf-8") as handle:
        handle.write(cycle_name)


def _parse_stat_line(line: str, current_cycle: Optional[str]) -> Optional[Dict[str, object]]:
    if not line:
        return None
    tokens = _tokenize(line)
    if not tokens:
        return None
    date_index = next((i for i, token in enumerate(tokens) if DATE_PATTERN.fullmatch(token)), None)
    if date_index is None:
        return None
    time_index = None
    for idx in range(date_index + 1, len(tokens)):
        if TIME_PATTERN.fullmatch(tokens[idx]):
            time_index = idx
            break
    if time_index is None:
        return None
    head_tokens = tokens[:date_index]
    if not head_tokens:
        return None
    faction_index = None
    faction_value = None
    for idx in range(len(head_tokens) - 1, -1, -1):
        normalized = _normalize_faction(head_tokens[idx])
        if normalized:
            faction_index = idx
            faction_value = normalized
            break
    if faction_index is None or faction_value is None:
        return None
    span_tokens: List[str] = []
    split_index = 0
    while split_index < faction_index:
        token = head_tokens[split_index]
        upper = token.upper()
        if upper in TIME_SPAN_WORDS or upper.isdigit() or re.fullmatch(r"\d+[A-Z]+", upper):
            span_tokens.append(token)
            split_index += 1
        else:
            break
    agent_tokens = head_tokens[split_index:faction_index]
    if not agent_tokens and faction_index > 0:
        agent_tokens = [head_tokens[faction_index - 1]]
        span_tokens = head_tokens[:faction_index - 1]
    agent_name = " ".join(agent_tokens).strip()
    if not agent_name:
        return None
    metrics_tokens = tokens[time_index + 1:]
    cycle_name, cycle_points = _extract_cycle_info(metrics_tokens)
    record: Dict[str, object] = {
        "time_span": " ".join(span_tokens).strip() or None,
        "agent_name": agent_name,
        "agent_faction": faction_value,
        "date": tokens[date_index],
        "time": _normalize_time(tokens[time_index]),
        "cycle_name": cycle_name or current_cycle,
        "cycle_points": cycle_points,
        "raw_line": line,
        "cycle_detected": cycle_name is not None,
    }
    for key in METRIC_KEYS:
        if not metrics_tokens:
            break
        record[key] = _coerce_value(metrics_tokens.pop(0))
    level_value = record.get("level")
    if not isinstance(level_value, int):
        return None
    if record.get("cycle_points") is not None and isinstance(record["cycle_points"], float):
        points_value = record["cycle_points"]
        if isinstance(points_value, float) and points_value.is_integer():
            record["cycle_points"] = int(points_value)
    return record


def parse_pasted_stats(text: str) -> List[dict]:
    if not text or not text.strip():
        return []
    results: List[dict] = []
    active_cycle = _read_current_cycle()
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        parsed = _parse_stat_line(stripped, active_cycle)
        if not parsed:
            continue
        if parsed.get("cycle_detected") and parsed.get("cycle_name"):
            active_cycle = parsed["cycle_name"]
            _write_current_cycle(active_cycle)
        elif not parsed.get("cycle_name") and active_cycle:
            parsed["cycle_name"] = active_cycle
        parsed.pop("cycle_detected", None)
        results.append(parsed)
    return results
