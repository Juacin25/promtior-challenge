from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from app.agent.llm import build_system_prompt


def test_direct_read_only_queries_have_explicit_tool_routes():
    llm = Mock(name="llm")
    booking_agent = Mock(name="booking_agent")
    create_booking = Mock(name="create_booking")
    user_message = (
        "Show room A's schedule today and list rooms available from 17:00 to 18:00."
    )

    prompt = " ".join(
        build_system_prompt(
            datetime(2026, 7, 20, 15, 0, tzinfo=timezone(timedelta(hours=-3))),
            "User1",
        ).split()
    )

    assert "call get_room_schedule" in prompt
    assert "call list_available_rooms" in prompt
    assert "Do not require a meeting title or attendee count" in prompt
    assert user_message
    assert llm is not booking_agent

    create_booking.assert_not_called()
