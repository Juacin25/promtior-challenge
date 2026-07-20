from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.data.db import connect
from app.data.repository import BookingRepository
from app.domain.models import Booking

GMT3 = timezone(timedelta(hours=-3))


def make_booking(id="b1", room_id="A", user="User1", title="Standup", attendees=3):
    start = datetime(2026, 7, 17, 9, 0, tzinfo=GMT3)
    end = datetime(2026, 7, 17, 9, 30, tzinfo=GMT3)
    return Booking(
        id=id,
        room_id=room_id,
        user=user,
        title=title,
        attendees=attendees,
        start=start,
        end=end,
    )


def repo(tmp_path, name="test.db"):
    return BookingRepository(connect(tmp_path / name))


def test_save_then_find_by_id(tmp_path):
    r = repo(tmp_path)
    b = make_booking()
    r.save(b)
    assert r.find_by_id("b1") == b


def test_find_by_id_absent_returns_none(tmp_path):
    r = repo(tmp_path)
    assert r.find_by_id("nope") is None


def test_find_by_room(tmp_path):
    r = repo(tmp_path)
    r.save(make_booking(id="b1", room_id="A"))
    r.save(make_booking(id="b2", room_id="B"))
    found = r.find_by_room("A")
    assert [b.id for b in found] == ["b1"]


def test_find_by_user(tmp_path):
    r = repo(tmp_path)
    r.save(make_booking(id="b1", user="User1"))
    r.save(make_booking(id="b2", user="User2"))
    found = r.find_by_user("User1")
    assert [b.id for b in found] == ["b1"]


def test_delete_removes_only_target(tmp_path):
    r = repo(tmp_path)
    r.save(make_booking(id="b1"))
    r.save(make_booking(id="b2"))
    r.delete("b1")
    assert r.find_by_id("b1") is None
    assert r.find_by_id("b2") is not None


def test_datetime_round_trips(tmp_path):
    r = repo(tmp_path)
    b = make_booking()
    r.save(b)
    got = r.find_by_id("b1")
    assert got.start == b.start
    assert got.end == b.end
    assert got.start.utcoffset() == timedelta(hours=-3)


def test_save_preserves_exact_gmt3_wall_time(tmp_path):
    connection = connect(tmp_path / "gmt3.db")
    r = BookingRepository(connection)
    booking = make_booking()

    r.save(booking)

    raw = connection.execute("SELECT start, end FROM bookings").fetchone()
    stored = r.find_by_id("b1")
    assert raw == ("2026-07-17T09:00:00-03:00", "2026-07-17T09:30:00-03:00")
    assert stored.start.isoformat() == "2026-07-17T09:00:00-03:00"
    assert stored.end.isoformat() == "2026-07-17T09:30:00-03:00"


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 7, 17, 9, 0), datetime(2026, 7, 17, 9, 30)),
        (
            datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
            datetime(2026, 7, 17, 12, 30, tzinfo=UTC),
        ),
    ],
    ids=["offsetless", "foreign_offset"],
)
def test_save_rejects_non_gmt3_datetime_representation(tmp_path, start, end):
    connection = connect(tmp_path / "invalid-timezone.db")
    r = BookingRepository(connection)
    booking = replace(
        make_booking(),
        start=start,
        end=end,
    )

    with pytest.raises(ValueError, match="GMT-3"):
        r.save(booking)

    assert connection.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 0


def test_attendee_count_round_trips(tmp_path):
    r = repo(tmp_path)
    r.save(make_booking(attendees=7))

    assert r.find_by_id("b1").attendees == 7


def test_persistence_across_fresh_connection(tmp_path):
    BookingRepository(connect(tmp_path / "persist.db")).save(make_booking())
    # Fresh connection to the same file — data must survive a "restart".
    reopened = BookingRepository(connect(tmp_path / "persist.db"))
    assert reopened.find_by_id("b1") == make_booking()
