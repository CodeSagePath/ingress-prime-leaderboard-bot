import sqlite3
from typing import Any, Dict

DB_PATH = "leaderboard.db"


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def ensure_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                cycle_name TEXT,
                cycle_points INTEGER,
                raw_line TEXT,
                date TEXT,
                time TEXT,
                agent_name TEXT,
                inserted_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
                UNIQUE(agent_name, date, time)
            )
            """
        )
        conn.commit()


def save_snapshot(conn: sqlite3.Connection, parsed: Dict[str, Any]) -> str:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO snapshots (
            cycle_name,
            cycle_points,
            raw_line,
            date,
            time,
            agent_name
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            parsed["cycle_name"],
            parsed["cycle_points"],
            parsed["raw_line"],
            parsed["date"],
            parsed["time"],
            parsed["agent_name"],
        ),
    )
    conn.commit()
    return "inserted" if cursor.rowcount == 1 else "skipped"
