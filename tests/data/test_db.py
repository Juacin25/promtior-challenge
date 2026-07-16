from app.data.db import ROOM_CAPACITIES, connect


def test_schema_creates_tables(tmp_path):
    conn = connect(tmp_path / "test.db")
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"rooms", "bookings"} <= tables


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
