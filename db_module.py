import sqlite3
from datetime import datetime

def get_db_conn():
    conn = sqlite3.connect('stats.db')
    cursor = conn.cursor()
    
    # Check if snapshots table exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='snapshots'
    """)
    
    if not cursor.fetchone():
        # Create snapshots table if it doesn't exist
        cursor.execute("""
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT,
                agent_faction TEXT,
                date TEXT,
                time TEXT,
                level INTEGER,
                lifetime_ap INTEGER,
                current_ap INTEGER,
                cycle_name TEXT,
                cycle_points INTEGER,
                raw_line TEXT,
                inserted_at TEXT
            )
        """)
        conn.commit()
    
    return conn

def save_snapshot(conn, row):
    cursor = conn.cursor()
    
    # Check if snapshot already exists
    cursor.execute("""
        SELECT id FROM snapshots 
        WHERE agent_name = ? AND date = ? AND time = ?
    """, (row['agent_name'], row['date'], row['time']))
    
    if cursor.fetchone():
        conn.close()
        return "skipped"
    
    # Insert new snapshot
    cursor.execute("""
        INSERT INTO snapshots (
            agent_name, agent_faction, date, time,
            level, lifetime_ap, current_ap,
            cycle_name, cycle_points,
            raw_line, inserted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row['agent_name'],
        row['agent_faction'],
        row['date'],
        row['time'],
        row['level'],
        row['lifetime_ap'],
        row['current_ap'],
        row['cycle_name'],
        row['cycle_points'],
        row['raw_line'],
        datetime.now().isoformat()
    ))
    
    conn.commit()
    return "inserted"