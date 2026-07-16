"""SQLite connection + schema. Idempotent init, seeds the 5 fixed rooms.

Datetimes are stored as ISO strings (see repository), keeping the store simple
and human-readable; the app works in GMT-3 (-03:00).
"""

import sqlite3
from pathlib import Path

# Fixed room capacities from the brief — the only place they are defined.
ROOM_CAPACITIES = {"A": 2, "B": 2, "C": 4, "D": 8, "E": 10}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY,
    capacity INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    user TEXT NOT NULL,
    title TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a connection and ensure schema + seeded rooms exist (idempotent)."""
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.executemany(
        "INSERT OR IGNORE INTO rooms (id, capacity) VALUES (?, ?)",
        ROOM_CAPACITIES.items(),
    )
    conn.commit()
    return conn
