CATEGORY_LAYOUT = (
    (
        "General",
        (
            ("Time Span", "time_span", None),
            ("Agent Name", "agent_name", None),
            ("Agent Faction", "agent_faction", None),
            ("Date (yyyy-mm-dd)", "date", None),
            ("Time (hh:mm:ss)", "time", None),
            ("Level", "level", None),
            ("Lifetime AP", "lifetime_ap", "AP"),
            ("Current AP", "current_ap", "AP"),
            ("Cycle Name", "cycle_name", None),
            ("Cycle Points", "cycle_points", None),
        ),
    ),
    (
        "Discovery",
        (
            ("Unique Portals Visited", "unique_portals_visited", None),
            ("Unique Portals Drone Visited", "unique_portals_drone_visited", None),
            ("Furthest Drone Distance", "furthest_drone_distance", "km"),
            ("Portals Discovered", "portals_discovered", None),
            ("Seer Points", "seer_points", None),
            ("XM Collected", "xm_collected", "XM"),
            ("OPR Agreements", "opr_agreements", None),
            ("Portal Scans Uploaded", "portal_scans_uploaded", None),
            ("Uniques Scout Controlled", "uniques_scout_controlled", None),
        ),
    ),
    (
        "Building",
        (
            ("Resonators Deployed", "resonators_deployed", None),
            ("Links Created", "links_created", None),
            ("Control Fields Created", "control_fields_created", None),
            ("Mind Units Captured", "mind_units_captured", "MUs"),
            ("Longest Link Ever Created", "longest_link_ever_created", "km"),
            ("Largest Control Field", "largest_control_field", "MUs"),
            ("XM Recharged", "xm_recharged", None),
            ("Portals Captured", "portals_captured", None),
            ("Unique Portals Captured", "unique_portals_captured", None),
            ("Mods Deployed", "mods_deployed", None),
            ("Links Active", "links_active", None),
            ("Portals Owned", "portals_owned", None),
            ("Control Fields Active", "control_fields_active", None),
            ("Mind Unit Control", "mind_unit_control", "MUs"),
        ),
    ),
    (
        "Resource Gathering",
        (
            ("Hacks", "hacks", None),
            ("Drone Hacks", "drone_hacks", None),
            ("Glyph Hack Points", "glyph_hack_points", None),
        ),
    ),
    (
        "Streaks",
        (
            ("Longest Hacking Streak", "longest_hacking_streak", "days"),
            ("Current Hacking Streak", "current_hacking_streak", "days"),
            ("Longest Sojourner Streak", "longest_sojourner_streak", "days"),
            ("Completed Hackstreaks", "completed_hackstreaks", None),
        ),
    ),
    (
        "Combat",
        (
            ("Resonators Destroyed", "resonators_destroyed", None),
            ("Portals Neutralized", "portals_neutralized", None),
            ("Enemy Links Destroyed", "enemy_links_destroyed", None),
            ("Enemy Fields Destroyed", "enemy_fields_destroyed", None),
            ("Battle Beacon Combatant", "battle_beacon_combatant", None),
            ("Drones Returned", "drones_returned", None),
            ("Machina Links Destroyed", "machina_links_destroyed", None),
            ("Machina Resonators Destroyed", "machina_resonators_destroyed", None),
            ("Machina Portals Neutralized", "machina_portals_neutralized", None),
            ("Machina Portals Reclaimed", "machina_portals_reclaimed", None),
        ),
    ),
    (
        "Defense",
        (
            ("Max Time Portal Held", "max_time_portal_held", "days"),
            ("Max Time Link Maintained", "max_time_link_maintained", "days"),
            ("Max Link Length x Days", "max_link_length_x_days", "km-days"),
            ("Max Time Field Held", "max_time_field_held", "days"),
            ("Largest Field MUs x Days", "largest_field_mus_x_days", "MU-days"),
            ("Forced Drone Recalls", "forced_drone_recalls", None),
        ),
    ),
    (
        "Health",
        (
            ("Distance Walked", "distance_walked", "km"),
            ("Kinetic Capsules Completed", "kinetic_capsules_completed", None),
        ),
    ),
    (
        "Missions",
        (
            ("Unique Missions Completed", "unique_missions_completed", None),
        ),
    ),
    (
        "Research",
        (
            ("Research Bounties Completed", "research_bounties_completed", None),
            ("Research Days Completed", "research_days_completed", None),
        ),
    ),
    (
        "Events",
        (
            ("Mission Day(s) Attended", "mission_days_attended", None),
            ("NL-1331 Meetup(s) Attended", "nl1331_meetups_attended", None),
            ("First Saturday Events", "first_saturday_events", None),
            ("Second Sunday Events", "second_sunday_events", None),
        ),
    ),
    (
        "Delta",
        (
            ("+Delta Tokens", "delta_tokens", None),
            ("+Delta Reso Points", "delta_reso_points", None),
            ("+Delta Field Points", "delta_field_points", None),
        ),
    ),
    (
        "Mentoring",
        (
            ("Agents Recruited", "agents_recruited", None),
        ),
    ),
    (
        "Recursion",
        (
            ("Recursions", "recursions", None),
        ),
    ),
    (
        "Subscription",
        (
            ("Months Subscribed", "months_subscribed", None),
        ),
    ),
)


def _format_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not value.is_integer():
            text = f"{value:,.2f}".rstrip("0").rstrip(".")
        else:
            text = f"{int(value):,}"
        return text
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        normalized = stripped.replace(",", "")
        if normalized.isdigit():
            return f"{int(normalized):,}"
        try:
            number = float(normalized)
        except ValueError:
            return stripped
        if number.is_integer():
            return f"{int(number):,}"
        return f"{number:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def format_primestats(parsed: dict) -> str:
    lines = []
    for category, entries in CATEGORY_LAYOUT:
        section = []
        for label, key, unit in entries:
            if key not in parsed:
                continue
            formatted = _format_value(parsed[key])
            if formatted is None:
                continue
            if unit:
                section.append(f"{label}: {formatted} {unit}")
            else:
                section.append(f"{label}: {formatted}")
        if section:
            lines.append(f"-- {category} --")
            lines.extend(section)
    return "\n".join(lines)


def format_primestats_efficient(parsed: dict) -> str:
    """
    Format stats showing only meaningful and interesting information.
    Uses efficient stat prioritization based on availability and ranking value.
    Filters out stats that are zero, missing, or not significant.
    """
    if not parsed:
        return "No stats available."

    lines = []

    # Core stats (always show if available) - prioritized for ranking efficiency
    core_stats = [
        ("Agent Name", "agent_name", None),
        ("Agent Faction", "agent_faction", None),
        ("Date", "date", None),
        ("Level", "level", None),
        ("Lifetime AP", "lifetime_ap", "AP"),      # Tier 1: Universal ranking standard
        ("Current AP", "current_ap", "AP"),
    ]

    core_section = []
    for label, key, unit in core_stats:
        if key in parsed and parsed[key] is not None:
            formatted = _format_value(parsed[key])
            if formatted and formatted not in ["0", "0.00"]:
                if unit:
                    core_section.append(f"{label}: {formatted} {unit}")
                else:
                    core_section.append(f"{label}: {formatted}")

    if core_section:
        lines.append("-- Agent Profile --")
        lines.extend(core_section)

    # Achievement-based stats (prioritized by efficiency and availability)
    # Tier 1: High-frequency activity stats (98%+ availability)
    achievement_stats = [
        ("Core Activity", [  # Highest priority - most available stats
            ("Hacks", "hacks", None),                    # Tier 1: 98% availability
            ("XM Collected", "xm_collected", "XM"),      # Tier 1: 95% availability
        ]),
        ("Strategic Building", [  # Tier 2: High value building stats
            ("Links Created", "links_created", None),          # Tier 2: 85% availability
            ("Control Fields Created", "control_fields_created", None),  # Tier 2: 75% availability
            ("Mind Units Captured", "mind_units_captured", "MUs"),
        ]),
        ("Discovery & Exploration", [
            ("Unique Portals Visited", "unique_portals_visited", None),
            ("Portals Discovered", "portals_discovered", None),
            ("Portal Scans Uploaded", "portal_scans_uploaded", None),
        ]),
        ("Combat Activity", [  # Tier 3: Combat-focused stats
            ("Portals Captured", "portals_captured", None),     # 80% availability
            ("Resonators Destroyed", "resonators_destroyed", None),  # 70% availability
            ("Portals Neutralized", "portals_neutralized", None),
            ("Enemy Links Destroyed", "enemy_links_destroyed", None),
        ]),
        ("Advanced Activities", [  # Tier 4: Specialized stats
            ("Glyph Hack Points", "glyph_hack_points", None),
            ("Distance Walked", "distance_walked", "km"),       # 80% availability
            ("Resonators Deployed", "resonators_deployed", None),
        ]),
        ("Achievements", [
            ("Longest Sojourner Streak", "longest_sojourner_streak", "days"),
            ("Recursions", "recursions", None),
        ]),
    ]

    for category_name, stats in achievement_stats:
        category_section = []
        for label, key, unit in stats:
            if key in parsed and parsed[key] is not None:
                value = parsed[key]
                # Only show if value > 0
                if isinstance(value, (int, float)) and value > 0:
                    formatted = _format_value(value)
                    if unit:
                        category_section.append(f"{label}: {formatted} {unit}")
                    else:
                        category_section.append(f"{label}: {formatted}")

        if category_section:
            lines.append(f"-- {category_name} --")
            lines.extend(category_section)

    # High-impact stats (prioritized by ranking value and availability)
    # Only show if they meet significance thresholds
    high_impact_stats = [
        ("Longest Link Ever Created", "longest_link_ever_created", "km", 10),      # Strategic achievement
        ("Largest Control Field", "largest_control_field", "MUs", 1000000),        # Major field achievement
        ("Max Time Portal Held", "max_time_portal_held", "days", 100),             # Long-term defense
        ("XM Collected", "xm_collected", "XM", 1000000),                          # Volume achievement
        ("Distance Walked", "distance_walked", "km", 100),                        # Physical achievement
        ("Max Link Length x Days", "max_link_length_x_days", "km-days", 5000),    # Sustained linking
        ("Largest Field MUs x Days", "largest_field_mus_x_days", "MU-days", 100000),  # Sustained control
    ]

    high_impact_section = []
    for label, key, unit, threshold in high_impact_stats:
        if key in parsed and parsed[key] is not None:
            value = parsed[key]
            if isinstance(value, (int, float)) and value >= threshold:
                formatted = _format_value(value)
                if unit:
                    high_impact_section.append(f"{label}: {formatted} {unit}")
                else:
                    high_impact_section.append(f"{label}: {formatted}")

    if high_impact_section:
        lines.append("-- Notable Achievements --")
        lines.extend(high_impact_section)

    # Cycle info (if available)
    if parsed.get("cycle_name") or parsed.get("cycle_points"):
        lines.append("-- Current Cycle --")
        if parsed.get("cycle_name"):
            lines.append(f"Cycle: {parsed['cycle_name']}")
        if parsed.get("cycle_points"):
            points_formatted = _format_value(parsed["cycle_points"])
            lines.append(f"Points: {points_formatted}")

    return "\n".join(lines) if lines else "No meaningful stats found."


def format_stats_for_ranking(parsed: dict) -> dict:
    """
    Extract and format stats specifically optimized for ranking calculations.
    Returns a dictionary with the most efficient ranking metrics.

    Args:
        parsed: Dictionary of parsed agent stats

    Returns:
        Dictionary containing only the most valuable ranking metrics
    """
    if not parsed:
        return {}

    # Core ranking metrics - prioritized by availability and ranking value
    ranking_metrics = {}

    # Tier 1: Universal metrics (always available)
    if parsed.get("lifetime_ap") is not None:
        ranking_metrics["ap"] = int(parsed["lifetime_ap"])
    if parsed.get("level") is not None:
        ranking_metrics["level"] = int(parsed["level"])

    # Tier 2: High-frequency activity metrics (95%+ availability)
    if parsed.get("hacks") is not None and parsed["hacks"] > 0:
        ranking_metrics["hacks"] = int(parsed["hacks"])
    if parsed.get("xm_collected") is not None and parsed["xm_collected"] > 0:
        ranking_metrics["xm_collected"] = int(parsed["xm_collected"])

    # Tier 3: Strategic building metrics (75%+ availability)
    if parsed.get("links_created") is not None and parsed["links_created"] > 0:
        ranking_metrics["links_created"] = int(parsed["links_created"])
    if parsed.get("control_fields_created") is not None and parsed["control_fields_created"] > 0:
        ranking_metrics["control_fields_created"] = int(parsed["control_fields_created"])

    # Tier 4: Combat metrics (70%+ availability)
    if parsed.get("portals_captured") is not None and parsed["portals_captured"] > 0:
        ranking_metrics["portals_captured"] = int(parsed["portals_captured"])
    if parsed.get("resonators_destroyed") is not None and parsed["resonators_destroyed"] > 0:
        ranking_metrics["resonators_destroyed"] = int(parsed["resonators_destroyed"])

    # Tier 5: Specialized metrics (only if significant)
    if parsed.get("distance_walked") is not None and parsed["distance_walked"] > 50:
        ranking_metrics["distance_walked"] = int(parsed["distance_walked"])
    if parsed.get("portal_scans_uploaded") is not None and parsed["portal_scans_uploaded"] > 100:
        ranking_metrics["portal_scans_uploaded"] = int(parsed["portal_scans_uploaded"])

    return ranking_metrics


def get_ranking_weight(parsed: dict) -> float:
    """
    Calculate a ranking weight based on the completeness and significance of stats.
    Higher weight = more complete/valuable agent profile for ranking.

    Args:
        parsed: Dictionary of parsed agent stats

    Returns:
        Float ranking weight (0.0 - 1.0)
    """
    if not parsed:
        return 0.0

    weight = 0.0
    max_weight = 1.0

    # Core stats (40% weight)
    if parsed.get("lifetime_ap") and parsed["lifetime_ap"] > 1000:
        weight += 0.15
    if parsed.get("level") and parsed["level"] >= 5:
        weight += 0.10
    if parsed.get("hacks") and parsed["hacks"] > 100:
        weight += 0.15

    # Activity stats (30% weight)
    if parsed.get("xm_collected") and parsed["xm_collected"] > 10000:
        weight += 0.10
    if parsed.get("unique_portals_visited") and parsed["unique_portals_visited"] > 100:
        weight += 0.10
    if parsed.get("portals_discovered") and parsed["portals_discovered"] > 10:
        weight += 0.10

    # Strategic stats (20% weight)
    if parsed.get("links_created") and parsed["links_created"] > 50:
        weight += 0.10
    if parsed.get("control_fields_created") and parsed["control_fields_created"] > 10:
        weight += 0.10

    # Advanced stats (10% weight)
    if parsed.get("resonators_destroyed") and parsed["resonators_destroyed"] > 100:
        weight += 0.05
    if parsed.get("distance_walked") and parsed["distance_walked"] > 50:
        weight += 0.05

    return min(weight, max_weight)
