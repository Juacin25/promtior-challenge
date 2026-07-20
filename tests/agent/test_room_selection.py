from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.agent.llm import build_system_prompt
from app.agent.orchestrator import _run_booking_agent

RANGE_ARGS = {
    "start": "2026-07-21T14:30:00-03:00",
    "end": "2026-07-21T16:00:00-03:00",
    "attendees": 5,
}


def _tool(name, output):
    tool = Mock()
    tool.name = name
    tool.invoke.return_value = output
    return tool


@pytest.mark.parametrize(
    ("tool_output", "reply"),
    [
        (
            "Rooms free from 2026-07-21 14:30 to 16:00: D, E.",
            "Rooms D and E are available. Which room would you like?",
        ),
        (
            "Rooms free from 2026-07-21 14:30 to 16:00: E.",
            "Room E is available. Would you like to book room E?",
        ),
        (
            "No rooms are free for that range.",
            "No rooms match that attendee count and time range.",
        ),
    ],
    ids=["all_matches", "single_match", "zero_matches"],
)
def test_roomless_request_lists_matches_without_auto_selecting(tool_output, reply):
    create_booking = _tool("create_booking", "must not run")
    list_available_rooms = _tool("list_available_rooms", tool_output)
    booking_agent = Mock()
    booking_agent.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "list_available_rooms",
                    "args": RANGE_ARGS,
                    "id": "rooms-1",
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content=reply),
    ]
    llm = Mock()
    llm.bind_tools.return_value = booking_agent

    result, _ = _run_booking_agent(
        "Reserva para 5 personas de 14:30 a 16:00",
        [],
        build_system_prompt(__import__("datetime").datetime(2026, 7, 20, 10), "User1"),
        llm,
        [create_booking, list_available_rooms],
    )

    assert result == reply
    list_available_rooms.invoke.assert_called_once_with(RANGE_ARGS)
    create_booking.invoke.assert_not_called()
    returned = booking_agent.invoke.call_args_list[1].args[0][-1]
    assert isinstance(returned, ToolMessage)
    assert returned.content == tool_output


def test_prompt_forbids_room_auto_selection_and_invented_alternatives():
    prompt = build_system_prompt(
        __import__("datetime").datetime(2026, 7, 20, 10), "User1"
    )

    assert "present every matching room" in prompt.lower()
    assert "never select a room" in prompt.lower()
    assert "even when exactly one room matches" in prompt.lower()
    assert "do not invent alternative rooms or times" in prompt.lower()
