import sqlite3

from app.data.db import ROOM_CAPACITIES, connect


def test_schema_creates_tables(tmp_path):
    conn = connect(tmp_path / "test.db")
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"rooms", "bookings"} <= tables


def test_bookings_schema_persists_attendee_count(tmp_path):
    conn = connect(tmp_path / "test.db")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(bookings)")}

    assert "attendees" in columns


def test_rooms_seeded_with_fixed_capacities(tmp_path):
    conn = connect(tmp_path / "test.db")
    rows = dict(conn.execute("SELECT id, capacity FROM rooms").fetchall())
    assert rows == {"A": 2, "B": 2, "C": 4, "D": 8, "E": 10}
    assert ROOM_CAPACITIES == {"A": 2, "B": 2, "C": 4, "D": 8, "E": 10}


def test_init_is_idempotent(tmp_path):
    path = tmp_path / "test.db"
    connect(path).close()
    conn = connect(path)  # second call must not error or duplicate rooms
    count = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    assert count == 5


def test_existing_database_gets_attendees_column(tmp_path):
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.execute(
        """CREATE TABLE bookings (
        id TEXT PRIMARY KEY, room_id TEXT, user TEXT, title TEXT, start TEXT, end TEXT
        )"""
    )
    legacy.execute(
        "INSERT INTO bookings VALUES ('b1', 'A', 'User1', 'Legacy', '2026-07-21', '2026-07-21')"
    )
    legacy.commit()
    legacy.close()

    migrated = connect(path)

    assert migrated.execute(
        "SELECT attendees FROM bookings WHERE id = 'b1'"
    ).fetchone()[0] == 1
