import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from langchain_core.messages import AIMessage

import app.agent.orchestrator as orchestrator
from app.agent.guardrail import GuardrailResult

USER_MESSAGE = (
    "Book room A for 2 attendees from 16:00 until 17:00. "
    'The meeting is called "Performance review - Tim".'
)
CLARIFICATION = (
    "What date should I book room A from 16:00 to 17:00 for "
    "Performance review - Tim?"
)


def test_no_tool_clarification_is_verified_against_user_supplied_details(monkeypatch):
    create_booking = Mock(name="create_booking")
    create_booking.name = "create_booking"
    connection = Mock()
    monkeypatch.setattr(
        orchestrator,
        "check_message",
        Mock(return_value=GuardrailResult(is_safe=True, reason="")),
    )
    monkeypatch.setattr(
        orchestrator,
        "_build_bound_tools",
        Mock(return_value=([create_booking], connection)),
    )
    booking_agent = Mock()
    booking_agent.invoke.return_value = AIMessage(content=CLARIFICATION)
    checker = Mock()
    checker.invoke.return_value = {"is_grounded": True, "reason": ""}
    llm = Mock()
    llm.bind_tools.return_value = booking_agent
    llm.with_structured_output.return_value = checker

    result = orchestrator.handle_message(
        USER_MESSAGE,
        [],
        "User1",
        datetime(2026, 7, 20, 15, 0, tzinfo=timezone(timedelta(hours=-3))),
        llm,
    )

    assert result == CLARIFICATION
    payload = json.loads(checker.invoke.call_args.args[0][1][1])
    assert payload == {
        "current_date": "2026-07-20",
        "draft_answer": CLARIFICATION,
        "tomorrow_date": "2026-07-21",
        "tool_outputs": [],
        "user_message": USER_MESSAGE,
    }
    prompt = checker.invoke.call_args.args[0][0][1].lower()
    assert "request details" in prompt
    assert "availability" in prompt
    create_booking.invoke.assert_not_called()
    connection.close.assert_called_once_with()
