from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from app.agent import verifier

CURRENT_DT = datetime(2026, 7, 20, 19, 30, tzinfo=timezone(timedelta(hours=-3)))


def test_duration_correction_is_grounded_without_tool_output():
    create_booking = Mock(name="create_booking")
    checker = Mock()
    checker.invoke.return_value = {"is_grounded": True, "reason": ""}
    llm = Mock()
    llm.with_structured_output.return_value = checker

    result = verifier.verify_response(
        "A meeting cannot be more than 3 hours long. Please provide a shorter range.",
        [],
        llm,
        user_message=(
            "Let's book room E, title Joaquin's birthday party, from 11:30 until "
            "15:00, 8 attendees."
        ),
        current_dt=CURRENT_DT,
    )

    prompt = checker.invoke.call_args.args[0][0][1]
    assert "server-defined conversational constraints" in prompt
    assert "no more than 3 hours" in prompt
    assert "grounded without tool output" in prompt
    assert result.is_grounded is True
    create_booking.assert_not_called()
