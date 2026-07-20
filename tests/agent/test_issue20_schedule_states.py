from datetime import datetime, timedelta, timezone

import app.agent.orchestrator as orchestrator
from app.data.repository import BookingRepository
from app.domain.models import Booking

GMT3 = timezone(timedelta(hours=-3))
BOOKING_ID = "private-schedule-id"
OWNER = "PrivateOwner"


def test_specific_room_schedule_shows_exact_available_and_occupied_slots(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(orchestrator, "BOOKINGS_DB_PATH", tmp_path / "bookings.db")
    tools, connection = orchestrator._build_bound_tools("User1")
    try:
        BookingRepository(connection).save(
            Booking(
                id=BOOKING_ID,
                room_id="C",
                user=OWNER,
                title="Private meeting",
                attendees=2,
                start=datetime(2026, 7, 21, 9, 30, tzinfo=GMT3),
                end=datetime(2026, 7, 21, 10, 0, tzinfo=GMT3),
            )
        )
        schedule = next(tool for tool in tools if tool.name == "get_room_schedule")
        result = schedule.invoke(
            {
                "room_id": "C",
                "start": "2026-07-21T09:00:00-03:00",
                "end": "2026-07-21T10:30:00-03:00",
            }
        )
    finally:
        connection.close()

    assert result == """Schedule for room C on 2026-07-21 (GMT-3):
Available:
09:00 - 09:30
10:00 - 10:30
Occupied:
09:30 - 10:00"""
    assert OWNER not in result
    assert BOOKING_ID not in result
    assert "Private meeting" not in result
