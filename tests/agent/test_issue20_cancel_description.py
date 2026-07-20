from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import app.agent.orchestrator as orchestrator
from app.agent.conversation import execute_cancel_booking
from app.domain.models import Booking

GMT3 = timezone(timedelta(hours=-3))


def _booking(booking_id: str, *, date: int = 21) -> Booking:
    return Booking(
        id=booking_id,
        room_id="C",
        user="User1",
        title="Planning",
        attendees=3,
        start=datetime(2026, 7, date, 14, 30, tzinfo=GMT3),
        end=datetime(2026, 7, date, 16, 0, tzinfo=GMT3),
    )


def test_undated_description_uses_today_and_requires_confirmation():
    cancel_booking = Mock(name="cancel_booking")

    result = execute_cancel_booking(
        cancel_booking,
        [_booking("hidden-id"), _booking("tomorrow-id", date=22)],
        "User1",
        room_id="C",
        start="14:30",
        end="16:00",
        default_date="2026-07-21",
    )

    assert result == (
        "I found this booking for today: Title: Planning | Room: C | "
        "Date: 2026-07-21 | Time: 14:30 - 16:00. Should I cancel it?"
    )
    assert "hidden-id" not in result
    assert "tomorrow-id" not in result
    cancel_booking.assert_not_called()


def test_full_description_cancels_the_resolved_internal_id():
    cancel_booking = Mock(return_value=_booking("correct-id"))

    result = execute_cancel_booking(
        cancel_booking,
        [_booking("correct-id"), _booking("tomorrow-id", date=22)],
        "User1",
        room_id="C",
        date="2026-07-21",
        start="14:30",
        end="16:00",
    )

    assert result == "Cancelled 'Planning' in room C on 2026-07-21, 14:30 - 16:00."
    cancel_booking.assert_called_once_with(
        {"booking_id": "correct-id", "user": "User1"}
    )


def test_model_visible_cancel_schema_accepts_end_but_not_identity_or_id(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(orchestrator, "BOOKINGS_DB_PATH", tmp_path / "bookings.db")
    tools, connection = orchestrator._build_bound_tools("User1", "2026-07-21")
    try:
        cancel_booking = next(tool for tool in tools if tool.name == "cancel_booking")
    finally:
        connection.close()

    assert "end" in cancel_booking.args
    assert "user" not in cancel_booking.args
    assert "booking_id" not in cancel_booking.args
    assert "default_date" not in cancel_booking.args
