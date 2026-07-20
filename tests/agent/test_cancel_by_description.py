from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.agent.conversation import execute_cancel_booking
from app.domain.models import Booking

GMT3 = timezone(timedelta(hours=-3))


def _booking(id, title="Standup", room="C", hour=9):
    return Booking(
        id=id,
        room_id=room,
        user="User1",
        title=title,
        attendees=3,
        start=datetime(2026, 7, 21, hour, tzinfo=GMT3),
        end=datetime(2026, 7, 21, hour + 1, tzinfo=GMT3),
    )


def test_unique_description_cancels_resolved_internal_id_without_exposing_it():
    cancel_booking = Mock(return_value="Cancelled booking 'secret-id'.")

    result = execute_cancel_booking(
        cancel_booking,
        [_booking("secret-id")],
        "User1",
        title="standup",
        date="2026-07-21",
    )

    assert result == "Cancelled 'Standup' in room C on 2026-07-21, 09:00 - 10:00."
    assert "secret-id" not in result
    cancel_booking.assert_called_once_with(
        {"booking_id": "secret-id", "user": "User1"}
    )


def test_ambiguous_description_lists_candidates_without_cancelling_or_ids():
    cancel_booking = Mock(name="cancel_booking")
    bookings = [_booking("id-one", hour=9), _booking("id-two", hour=11)]

    result = execute_cancel_booking(
        cancel_booking, bookings, "User1", title="Standup", date="2026-07-21"
    )

    assert result == """More than one booking matches. Which one should I cancel?
Title: Standup | Date: 2026-07-21 | Time: 09:00 - 10:00 | Room: C
Title: Standup | Date: 2026-07-21 | Time: 11:00 - 12:00 | Room: C"""
    assert "id-one" not in result
    assert "id-two" not in result
    cancel_booking.assert_not_called()


def test_unmatched_description_returns_clear_message_without_cancelling():
    cancel_booking = Mock(name="cancel_booking")

    result = execute_cancel_booking(
        cancel_booking, [_booking("id-one")], "User1", title="Retrospective"
    )

    assert result == "I couldn't find one of your bookings matching that description."
    cancel_booking.assert_not_called()


def test_other_users_booking_never_matches_description():
    cancel_booking = Mock(name="cancel_booking")
    other_booking = Booking(
        id="other-id",
        room_id="C",
        user="User2",
        title="Standup",
        attendees=3,
        start=datetime(2026, 7, 21, 9, tzinfo=GMT3),
        end=datetime(2026, 7, 21, 10, tzinfo=GMT3),
    )

    result = execute_cancel_booking(
        cancel_booking, [other_booking], "User1", title="Standup"
    )

    assert result == "I couldn't find one of your bookings matching that description."
    assert "other-id" not in result
    cancel_booking.assert_not_called()


def test_cancellation_requires_at_least_one_description_field():
    cancel_booking = Mock(name="cancel_booking")

    result = execute_cancel_booking(
        cancel_booking, [_booking("id-one")], "User1"
    )

    assert result == "Please describe the booking by its date, time, title, or room."
    cancel_booking.assert_not_called()


def test_unique_match_can_use_room_and_start_time():
    cancel_booking = Mock(return_value="Cancelled booking 'id-one'.")

    result = execute_cancel_booking(
        cancel_booking,
        [_booking("id-one")],
        "User1",
        room_id="c",
        start="09:00",
    )

    assert result.startswith("Cancelled 'Standup'")
    cancel_booking.assert_called_once()


def test_tool_level_cancel_failure_is_preserved_without_internal_id():
    cancel_booking = Mock(
        return_value="I couldn't cancel that booking. Please confirm it exists and belongs to you."
    )

    result = execute_cancel_booking(
        cancel_booking, [_booking("hidden-id")], "User1", title="Standup"
    )

    assert result == (
        "I couldn't cancel that booking. Please confirm it exists and belongs to you."
    )
    assert "hidden-id" not in result


@pytest.mark.parametrize(
    "description",
    [
        {"room_id": "D"},
        {"date": "2026-07-22"},
        {"start": "10:00"},
        {"title": "Review"},
    ],
    ids=["room", "date", "start", "title"],
)
def test_nonmatching_description_field_prevents_cancellation(description):
    cancel_booking = Mock(name="cancel_booking")
    booking = _booking("hidden-id")

    result = execute_cancel_booking(
        cancel_booking, [booking], "User1", **description
    )

    assert result.startswith("I couldn't find")
    cancel_booking.assert_not_called()
