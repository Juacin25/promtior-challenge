from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.agent.conversation import execute_create_booking
from app.agent.llm import build_system_prompt

VALID_REQUEST = {
    "room_id": "D",
    "start": "2026-07-21T14:30:00-03:00",
    "end": "2026-07-21T16:00:00-03:00",
    "title": "Planning",
    "attendees": 5,
}


@pytest.mark.parametrize(
    ("overrides", "missing_field"),
    [
        ({"room_id": None}, "room"),
        ({"room_id": "   "}, "room"),
        ({"start": "14:30", "end": "16:00"}, "date"),
        ({"start": None, "end": None}, "time range"),
        ({"end": None}, "time range"),
        ({"title": None}, "meeting title"),
        ({"attendees": None}, "attendee count"),
    ],
    ids=[
        "room",
        "blank_room",
        "date",
        "time_range",
        "missing_end",
        "title",
        "attendees",
    ],
)
def test_each_missing_required_field_is_requested_without_calling_create(
    overrides, missing_field
):
    create_booking = Mock(name="create_booking")

    result = execute_create_booking(
        create_booking, "User1", **(VALID_REQUEST | overrides)
    )

    assert missing_field in result.lower()
    assert "I understood" in result
    create_booking.assert_not_called()


@pytest.mark.parametrize("title", ["", "   "], ids=["empty", "whitespace"])
def test_blank_title_is_requested_without_calling_create(title):
    create_booking = Mock(name="create_booking")

    result = execute_create_booking(
        create_booking, "User1", **(VALID_REQUEST | {"title": title})
    )

    assert "meeting title" in result.lower()
    assert "required and cannot be blank" in result.lower()
    assert "I understood" in result
    assert "Planning" not in result
    create_booking.assert_not_called()


def test_multiple_missing_fields_are_requested_together_without_calling_create():
    create_booking = Mock(name="create_booking")

    result = execute_create_booking(
        create_booking,
        "User1",
        room_id=None,
        start="2026-07-21T14:30:00-03:00",
        end="2026-07-21T16:00:00-03:00",
        title=None,
        attendees=5,
    )

    assert "room" in result.lower()
    assert "meeting title" in result.lower()
    assert "date 2026-07-21" in result
    assert "time range 14:30 - 16:00" in result
    assert "attendee count 5" in result
    create_booking.assert_not_called()


def test_all_missing_fields_are_named_with_brief_guidance():
    create_booking = Mock(name="create_booking")

    result = execute_create_booking(create_booking, "User1")

    for field in ("room", "date", "time range", "meeting title", "attendee count"):
        assert field in result.lower()
    assert "check the room fits" in result.lower()
    assert "booking-id-greppable" not in result
    assert "BookingError" not in result
    create_booking.assert_not_called()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {"start": "2026-07-21T14:15:00-03:00"},
            "Please use start and end times on :00 or :30 boundaries.",
        ),
        (
            {"end": "2026-07-21T15:15:00-03:00"},
            "Please use start and end times on :00 or :30 boundaries.",
        ),
        (
            {"end": "2026-07-21T18:00:00-03:00"},
            "A booking can last at most 3 hours; the requested range is "
            "3 hours 30 minutes. Please choose a shorter range.",
        ),
        (
            {"attendees": 9},
            "Room D holds at most 8 attendees. Please provide a corrected attendee count.",
        ),
        (
            {"start": "not-a-date"},
            "Please provide a valid date and time range.",
        ),
        (
            {"attendees": 0},
            "Please provide an attendee count of at least 1.",
        ),
    ],
    ids=["start_alignment", "end_alignment", "duration", "capacity", "date", "minimum"],
)
def test_invalid_supplied_value_is_corrected_without_calling_create(
    overrides, expected
):
    create_booking = Mock(name="create_booking")

    result = execute_create_booking(
        create_booking, "User1", **(VALID_REQUEST | overrides)
    )

    assert result == expected
    create_booking.assert_not_called()


def test_unknown_room_is_left_to_the_authoritative_tool():
    create_booking = Mock(return_value="There is no room 'Z'. The rooms are: A, B, C, D, E.")

    result = execute_create_booking(
        create_booking, "User1", **(VALID_REQUEST | {"room_id": "Z"})
    )

    assert result == "There is no room 'Z'. The rooms are: A, B, C, D, E."
    create_booking.assert_called_once()


def test_system_prompt_requires_all_five_fields_without_defaults():
    prompt = " ".join(
        build_system_prompt(
            datetime(2026, 7, 20, 10, tzinfo=timezone(timedelta(hours=-3))),
            "User1",
        ).lower().split()
    )

    for field in ("room", "date", "start and end", "meeting title", "attendee count"):
        assert field in prompt
    assert "never invent, assume, or default" in prompt
    assert "cannot be created without" in prompt
    assert "30-minute" in prompt
    assert "3 hours" in prompt
    assert "room capacity" in prompt
