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
