def save_snapshot(conn, parsed_dict):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM snapshots WHERE agent_name = ? AND date = ? AND time = ?",
        (parsed_dict['agent_name'], parsed_dict['date'], parsed_dict['time'])
    )
    if cursor.fetchone():
        cursor.close()
        return 'skipped'
    cursor.execute(
        "INSERT INTO snapshots (agent_name, date, time, cycle_name, cycle_points, raw_row) VALUES (?, ?, ?, ?, ?, ?)",
        (
            parsed_dict['agent_name'],
            parsed_dict['date'],
            parsed_dict['time'],
            parsed_dict.get('cycle_name'),
            parsed_dict.get('cycle_points'),
            parsed_dict.get('raw_row')
        )
    )
    conn.commit()
    cursor.close()
    return 'inserted'
