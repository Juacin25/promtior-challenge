from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import app.agent.orchestrator as orchestrator
from app.agent.conversation import (
    execute_create_booking,
    format_room_schedule,
)
from app.agent.llm import build_system_prompt
from app.domain.models import Booking

BOOKING_ID = "deadbeef"


def test_creation_confirmation_has_required_fields_and_no_booking_id():
    persisted = Booking(
        id=BOOKING_ID,
        room_id="C",
        user="User1",
        title="Planning",
        attendees=3,
        start=datetime(2026, 7, 21, 9, tzinfo=timezone(timedelta(hours=-3))),
        end=datetime(2026, 7, 21, 10, tzinfo=timezone(timedelta(hours=-3))),
    )
    create_booking = Mock(return_value=persisted)

    result = execute_create_booking(
        create_booking,
        "User1",
        room_id="C",
        start="2026-07-21T09:00:00-03:00",
        end="2026-07-21T10:00:00-03:00",
        title="Planning",
        attendees=3,
    )

    assert result == (
        "Booked 'Planning' in room C on 2026-07-21, "
        "09:00 - 10:00 GMT-3, for 3 attendees."
    )
    returned_fields = (
        persisted.title,
        persisted.room_id,
        persisted.start.date().isoformat(),
        persisted.start.strftime("%H:%M"),
        persisted.end.strftime("%H:%M"),
        str(persisted.attendees),
    )
    for field in returned_fields:
        assert field in result
    assert BOOKING_ID not in result
    create_booking.assert_called_once_with(
        {
            "room_id": "C",
            "start": "2026-07-21T09:00:00-03:00",
            "end": "2026-07-21T10:00:00-03:00",
            "title": "Planning",
            "attendees": 3,
            "user": "User1",
        }
    )


def test_booking_path_stores_and_displays_exact_entered_gmt3_time(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "BOOKINGS_DB_PATH", tmp_path / "bookings.db")
    tools, connection = orchestrator._build_bound_tools("User1")
    try:
        create = next(tool for tool in tools if tool.name == "create_booking")
        result = create.invoke(
            {
                "room_id": "A",
                "start": "2026-07-20T17:00:00-03:00",
                "end": "2026-07-20T18:00:00-03:00",
                "title": "Performance Review - Tim",
                "attendees": 2,
            }
        )
        stored = connection.execute("SELECT start, end FROM bookings").fetchone()
    finally:
        connection.close()

    assert stored == ("2026-07-20T17:00:00-03:00", "2026-07-20T18:00:00-03:00")
    assert result == (
        "Booked 'Performance Review - Tim' in room A on 2026-07-20, "
        "17:00 - 18:00 GMT-3, for 2 attendees."
    )


def test_system_prompt_pins_output_formats_and_forbids_booking_ids():
    prompt = " ".join(
        build_system_prompt(
            datetime(2026, 7, 20, 10, tzinfo=timezone(timedelta(hours=-3))),
            "User1",
        ).split()
    )

    assert "HH:MM - HH:MM" in prompt
    assert "Never merge contiguous slots" in prompt
    assert "Never expose booking IDs" in prompt
    assert "title, room, date, time range, and attendee count" in prompt


def test_bound_schedule_formats_free_slots_and_preserves_input_errors(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(orchestrator, "BOOKINGS_DB_PATH", tmp_path / "bookings.db")
    tools, connection = orchestrator._build_bound_tools("User1")
    try:
        schedule = next(tool for tool in tools if tool.name == "get_room_schedule")
        free = schedule.invoke(
            {
                "room_id": "C",
                "start": "2026-07-21T11:30:00-03:00",
                "end": "2026-07-21T13:00:00-03:00",
            }
        )
        invalid = schedule.invoke(
            {
                "room_id": "Z",
                "start": "2026-07-21T11:30:00-03:00",
                "end": "2026-07-21T13:00:00-03:00",
            }
        )
    finally:
        connection.close()

    assert free == (
        "Schedule for room C on 2026-07-21 (GMT-3):\nAvailable:\n"
        "11:30 - 12:00\n12:00 - 12:30\n12:30 - 13:00\nOccupied:\nNone."
    )
    assert "There is no room 'Z'" in invalid


def test_room_schedule_with_no_available_slots_represents_both_states():
    result = format_room_schedule(
        "Schedule for room C:\n09:00-09:30 occupied",
        "C",
        "2026-07-21T09:00:00-03:00",
    )

    assert result == (
        "Schedule for room C on 2026-07-21 (GMT-3):\n"
        "Available:\nNone.\nOccupied:\n09:00 - 09:30"
    )
