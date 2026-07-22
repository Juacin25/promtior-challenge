from unittest.mock import Mock

from app.agent.conversation import execute_create_booking


def test_duration_prevalidation_names_limit_and_requested_duration():
    create_booking = Mock(name="create_booking")

    result = execute_create_booking(
        create_booking,
        "User1",
        room_id="E",
        start="2026-07-21T11:30:00-03:00",
        end="2026-07-21T15:00:00-03:00",
        title="Joaquin's birthday party",
        attendees=8,
    )

    assert result == (
        "A booking can last at most 3 hours; the requested range is "
        "3 hours 30 minutes. Please choose a shorter range."
    )
    create_booking.assert_not_called()


def test_end_before_start_has_its_own_actionable_message():
    create_booking = Mock(name="create_booking")

    result = execute_create_booking(
        create_booking,
        "User1",
        room_id="E",
        start="2026-07-21T15:00:00-03:00",
        end="2026-07-21T14:30:00-03:00",
        title="Review",
        attendees=8,
    )

    assert result == "The end time must be after the start time."
    create_booking.assert_not_called()
