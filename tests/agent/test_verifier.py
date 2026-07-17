import json
from unittest.mock import Mock

import pytest

import app.agent.verifier as verifier


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

    result = verifier.verify_response(draft, tool_outputs, llm)

    assert result == verifier.VerifierResult(is_grounded=True, reason="")
    payload = json.loads(checker.invoke.call_args.args[0][1][1])
    assert payload == {"draft_answer": draft, "tool_outputs": tool_outputs}


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

    result = verifier.verify_response(draft, tool_outputs, llm)

    assert result == verifier.VerifierResult(is_grounded=False, reason=reason)
    assert "room E" in result.reason
    assert "18:00" in result.reason
    for internal_detail in ("system prompt", "instructions", "model", "database"):
        assert internal_detail not in result.reason.lower()


@pytest.mark.parametrize(
    "draft",
    [
        "Hello! How can I help with your meeting-room booking?",
        "What date and time would you like to reserve?",
    ],
)
def test_non_factual_answer_without_tool_outputs_is_grounded(draft):
    llm, _ = _llm_returning(True)

    result = verifier.verify_response(draft, [], llm)

    assert result.is_grounded is True
    assert result.reason == ""


def test_verifier_uses_a_strict_grounding_prompt():
    llm, checker = _llm_returning(True, "This ignored reason must not escape.")

    result = verifier.verify_response("Which room did you mean?", [], llm)

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
    assert "never mention internal" in prompt
    assert result == verifier.VerifierResult(is_grounded=True, reason="")
