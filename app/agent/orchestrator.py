"""Coordinate one guarded booking-agent turn; contain no booking rules."""

from datetime import datetime
from pathlib import Path
from sqlite3 import Connection

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from app.agent.guardrail import check_message
from app.agent.llm import build_system_prompt
from app.data.db import connect
from app.data.repository import BookingRepository
from app.domain.exceptions import BookingError
from app.tools.booking_tools import build_booking_tools

BOOKINGS_DB_PATH = Path("bookings.db")


def _bind_username(tools: list[BaseTool], username: str) -> list[BaseTool]:
    """Remove ``user`` from model-visible schemas and inject it at execution."""
    by_name = {tool.name: tool for tool in tools}

    def create_booking(
        room_id: str, start: str, end: str, title: str, attendees: int
    ) -> str:
        return by_name["create_booking"].invoke(
            {
                "room_id": room_id,
                "start": start,
                "end": end,
                "title": title,
                "attendees": attendees,
                "user": username,
            }
        )

    def cancel_booking(booking_id: str) -> str:
        return by_name["cancel_booking"].invoke(
            {"booking_id": booking_id, "user": username}
        )

    bound_create = StructuredTool.from_function(
        create_booking,
        name="create_booking",
        description=by_name["create_booking"].description,
    )
    bound_cancel = StructuredTool.from_function(
        cancel_booking,
        name="cancel_booking",
        description=by_name["cancel_booking"].description,
    )
    return [
        bound_create,
        bound_cancel,
        by_name["list_available_rooms"],
        by_name["get_room_schedule"],
    ]


def _build_bound_tools(username: str) -> tuple[list[BaseTool], Connection]:
    connection = connect(BOOKINGS_DB_PATH)
    tools = build_booking_tools(BookingRepository(connection))
    return _bind_username(tools, username), connection


def _run_booking_agent(
    user_message: str,
    history: list[BaseMessage],
    system_prompt: str,
    llm,
    tools: list[BaseTool],
) -> tuple[str, list[dict[str, str]]]:
    """Run model -> tool -> model until a final answer, retaining turn evidence."""
    model = llm.bind_tools(tools)
    tools_by_name = {tool.name: tool for tool in tools}
    messages = [
        SystemMessage(content=system_prompt),
        *history,
        HumanMessage(content=user_message),
    ]
    tool_outputs = []

    while True:
        response = model.invoke(messages)
        if not response.tool_calls:
            return str(response.content), tool_outputs

        tool_messages = []
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            try:
                output = str(tools_by_name[tool_name].invoke(tool_call["args"]))
            except BookingError as error:
                message = f"I couldn't complete that booking: {error}"
                tool_outputs.append({"tool": tool_name, "output": message})
                return message, tool_outputs

            tool_outputs.append({"tool": tool_name, "output": output})
            tool_messages.append(
                ToolMessage(
                    content=output,
                    name=tool_name,
                    tool_call_id=tool_call["id"],
                )
            )
        messages = [*messages, response, *tool_messages]


def handle_message(
    user_message: str,
    history: list[BaseMessage],
    username: str,
    current_dt: datetime,
    llm,
) -> str:
    """Coordinate one message without owning conversation state."""
    guardrail_result = check_message(user_message, llm)
    if not guardrail_result.is_safe:
        return guardrail_result.reason

    system_prompt = build_system_prompt(current_dt, username)
    tools, connection = _build_bound_tools(username)
    try:
        return _run_booking_agent(user_message, history, system_prompt, llm, tools)[0]
    finally:
        connection.close()
