from contextlib import closing
from datetime import datetime, timedelta, timezone

import app.agent.orchestrator as orchestrator
from app.agent.conversation import format_my_bookings
from app.data.db import connect
from app.data.repository import BookingRepository
from app.domain.models import Booking

GMT3 = timezone(timedelta(hours=-3))
BOOKING_ID = "greppable-booking-id"


def _booking(id, user, title, room, hour, attendees):
    return Booking(
        id=id,
        room_id=room,
        user=user,
        title=title,
        attendees=attendees,
        start=datetime(2026, 7, 21, hour, tzinfo=GMT3),
        end=datetime(2026, 7, 21, hour + 1, tzinfo=GMT3),
    )


def test_my_bookings_lists_four_fields_for_each_booking_without_ids():
    bookings = [
        _booking(BOOKING_ID, "User1", "Planning", "C", 9, 3),
        _booking("second-private-id", "User1", "Review", "D", 11, 6),
    ]

    result = format_my_bookings(bookings)

    assert result == """Your bookings:
Title: Planning
Date: 2026-07-21
Time: 09:00 - 10:00
Attendees: 3
Room: C

Title: Review
Date: 2026-07-21
Time: 11:00 - 12:00
Attendees: 6
Room: D"""
    assert BOOKING_ID not in result
    assert "second-private-id" not in result


def test_my_bookings_has_clear_empty_state():
    assert format_my_bookings([]) == "You have no bookings."


def test_my_bookings_rejects_other_users_data_defensively():
    bookings = [_booking("private-id", "User2", "Private", "E", 14, 2)]

    result = format_my_bookings(bookings, username="User1")

    assert result == "You have no bookings."
    assert "Private" not in result


def test_my_bookings_tool_uses_server_bound_authenticated_username(
    tmp_path, monkeypatch
):
    path = tmp_path / "bookings.db"
    with closing(connect(path)) as seed_connection:
        repo = BookingRepository(seed_connection)
        repo.save(_booking("own-id", "User1", "Mine", "C", 9, 3))
        repo.save(_booking("other-id", "User2", "Private", "D", 11, 4))
    monkeypatch.setattr(orchestrator, "BOOKINGS_DB_PATH", path)

    tools, connection = orchestrator._build_bound_tools("User1")
    try:
        listing = next(tool for tool in tools if tool.name == "list_my_bookings")
        result = listing.invoke({})
    finally:
        connection.close()

    assert "Mine" in result
    assert "Private" not in result
    assert "own-id" not in result
    assert "other-id" not in result
    assert "user" not in listing.args
