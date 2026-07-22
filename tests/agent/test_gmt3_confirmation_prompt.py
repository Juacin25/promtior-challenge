from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from app.agent.llm import build_system_prompt


def test_confirmation_prompt_requires_exact_gmt3_tool_time():
    llm = Mock(name="llm")
    booking_agent = Mock(name="booking_agent")

    prompt = " ".join(
        build_system_prompt(
            datetime(2026, 7, 20, 15, 0, tzinfo=timezone(timedelta(hours=-3))),
            "User1",
        ).split()
    )

    assert "copy the date and GMT-3 time range exactly as returned by create_booking" in prompt
    assert "Never convert, recalculate, or adjust tool-returned times" in prompt
    llm.assert_not_called()
    booking_agent.assert_not_called()
