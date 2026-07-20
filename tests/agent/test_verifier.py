import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

import app.agent.verifier as verifier

CURRENT_DT = datetime(2026, 7, 20, 19, 30, tzinfo=timezone(timedelta(hours=-3)))


def _llm_returning(is_grounded: bool, reason: str = "") -> tuple[Mock, Mock]:
    checker = Mock()
    checker.invoke.return_value = {"is_grounded": is_grounded, "reason": reason}
    llm = Mock()
    llm.with_structured_output.return_value = checker
    return llm, checker


def test_answer_supported_by_tool_outputs_is_grounded():
    draft = "Rooms A and C are free tomorrow from 14:00 to 15:00."
    tool_outputs = [
        {
            "tool": "list_available_rooms",
            "output": "Rooms free from 2026-07-18 14:00 to 15:00: A, C.",
        }
    ]
    llm, checker = _llm_returning(True)

    user_message = "Which rooms are free tomorrow from 14:00 to 15:00?"
    result = verifier.verify_response(
        draft, tool_outputs, llm, user_message=user_message, current_dt=CURRENT_DT
    )

    assert result == verifier.VerifierResult(is_grounded=True, reason="")
    payload = json.loads(checker.invoke.call_args.args[0][1][1])
    assert payload == {
        "current_date": "2026-07-20",
        "draft_answer": draft,
        "tomorrow_date": "2026-07-21",
        "tool_outputs": tool_outputs,
        "user_message": user_message,
    }


def test_unsupported_room_time_and_availability_are_reported():
    draft = "Room E is free today at 18:00."
    tool_outputs = [
        {
            "tool": "list_available_rooms",
            "output": "Rooms free from 2026-07-17 18:00 to 19:00: A, C.",
        }
    ]
    reason = "The claim that room E is free at 18:00 is unsupported."
    llm, _ = _llm_returning(False, reason)

    result = verifier.verify_response(
        draft,
        tool_outputs,
        llm,
        user_message="Is room E free today at 18:00?",
        current_dt=CURRENT_DT,
    )

    assert result == verifier.VerifierResult(is_grounded=False, reason=reason)
    assert "room E" in result.reason
    assert "18:00" in result.reason
    for internal_detail in ("system prompt", "instructions", "model", "database"):
        assert internal_detail not in result.reason.lower()


def test_rejection_reason_and_tool_evidence_are_logged_server_side(caplog):
    reason = "The booking attendee count is unsupported."
    tool_outputs = [
        {
            "tool": "create_booking",
            "output": "Booked room A. Booking id: hidden-id.",
        }
    ]
    llm, _ = _llm_returning(False, reason)

    with caplog.at_level(logging.WARNING, logger=verifier.__name__):
        verifier.verify_response(
            "Booked Planning in room A for 2 attendees.",
            tool_outputs,
            llm,
            user_message="Book room A for 2 attendees.",
            current_dt=CURRENT_DT,
        )

    assert reason in caplog.text
    assert json.dumps(tool_outputs, ensure_ascii=False, sort_keys=True) in caplog.text


@pytest.mark.parametrize(
    "draft",
    [
        "Hello! How can I help with your meeting-room booking?",
        "What date and time would you like to reserve?",
    ],
)
def test_non_factual_answer_without_tool_outputs_is_grounded(draft):
    llm, _ = _llm_returning(True)

    result = verifier.verify_response(
        draft,
        [],
        llm,
        user_message="I need to book a meeting room.",
        current_dt=CURRENT_DT,
    )

    assert result.is_grounded is True
    assert result.reason == ""


def test_verifier_uses_a_strict_grounding_prompt():
    llm, checker = _llm_returning(True, "This ignored reason must not escape.")

    result = verifier.verify_response(
        "Which room did you mean?",
        [],
        llm,
        user_message="Book tomorrow from 10:00 to 11:00.",
        current_dt=CURRENT_DT,
    )

    schema = llm.with_structured_output.call_args.args[0]
    assert schema.__annotations__ == {"is_grounded": bool, "reason": str}
    assert llm.with_structured_output.call_args.kwargs == {"strict": True}
    messages = checker.invoke.call_args.args[0]
    assert messages[0][0] == "system"
    prompt = messages[0][1].lower()
    assert "only" in prompt
    assert "tool outputs" in prompt
    assert "greetings" in prompt
    assert "clarification" in prompt
    assert "no tool outputs" in prompt
    assert "request details" in prompt
    assert "availability" in prompt
    assert "exactly match" in prompt
    assert "gmt-3" in prompt
    assert "today" in prompt
    assert "tomorrow" in prompt
    assert "never mention internal" in prompt
    assert result == verifier.VerifierResult(is_grounded=True, reason="")
