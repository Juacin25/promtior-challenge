from unittest.mock import Mock

from langchain_core.messages import AIMessage

from app.agent.orchestrator import _run_booking_agent
from app.domain.exceptions import TitleRequiredError


def test_booking_error_still_uses_issue_14_translation():
    create_booking = Mock()
    create_booking.name = "create_booking"
    create_booking.invoke.side_effect = TitleRequiredError("raw internal payload")
    booking_agent = Mock()
    booking_agent.invoke.return_value = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "create_booking",
                "args": {},
                "id": "create-1",
                "type": "tool_call",
            }
        ],
    )
    llm = Mock()
    llm.bind_tools.return_value = booking_agent

    result, outputs = _run_booking_agent(
        "Book room C", [], "system prompt", llm, [create_booking]
    )

    assert result == "A meeting title is required and cannot be blank."
    assert outputs == [{"tool": "create_booking", "output": result}]
    create_booking.invoke.assert_called_once_with({})
