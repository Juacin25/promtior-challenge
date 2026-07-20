from unittest.mock import Mock

import app.agent.orchestrator as orchestrator
from app.agent.conversation import execute_create_booking, format_available_slots
from app.agent.llm import build_system_prompt

BOOKING_ID = "deadbeef"


def test_contiguous_free_time_is_rendered_as_exact_unmerged_slots():
    tool_output = """Schedule for room C:
11:30-12:00 free
12:00-12:30 free
12:30-13:00 free"""

    result = format_available_slots(tool_output)

    assert result == "11:30 - 12:00\n12:00 - 12:30\n12:30 - 13:00"


def test_creation_confirmation_has_required_fields_and_no_booking_id():
    create_booking = Mock(
        return_value=(
            "Booked room C for 'Planning' from 2026-07-21 09:00 to 10:00 "
            f"(3 attendees). Booking id: {BOOKING_ID}."
        )
    )

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
        "Booked 'Planning' in room C on 2026-07-21, 09:00 - 10:00, for 3 attendees."
    )
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


def test_system_prompt_pins_output_formats_and_forbids_booking_ids():
    prompt = " ".join(
        build_system_prompt(
            __import__("datetime").datetime(2026, 7, 20, 10), "User1"
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

    assert free == "11:30 - 12:00\n12:00 - 12:30\n12:30 - 13:00"
    assert "There is no room 'Z'" in invalid


def test_schedule_with_no_free_slots_has_clear_empty_state():
    assert format_available_slots("Schedule for room C:\n09:00-09:30 occupied") == (
        "No free 30-minute slots are available."
    )
