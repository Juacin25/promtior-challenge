"""Testable session-state helpers for the thin Streamlit UI."""

import logging
from collections.abc import Callable, MutableMapping
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.orchestrator import handle_message
from app.auth.auth import AuthError, authenticate
from app.domain.exceptions import BookingError
from app.domain.models import User

AUTH_ERROR_MESSAGE = "Invalid username or password."
TURN_FAILURE_MESSAGE = "I couldn't complete that request. Please try again."
logger = logging.getLogger(__name__)


def initialize_session(state: MutableMapping[str, Any]) -> None:
    state.setdefault("authenticated", False)
    state.setdefault("history", [])


def authenticate_session(
    state: MutableMapping[str, Any],
    username: str,
    password: str,
    authenticator: Callable[[str, str], User] = authenticate,
) -> str | None:
    """Authenticate and establish server-side state, or return one generic error."""
    try:
        user = authenticator(username, password)
    except AuthError:
        return AUTH_ERROR_MESSAGE

    initialize_session(state)
    state["username"] = user.username
    state["authenticated"] = True
    return None


def should_render_chat(state: MutableMapping[str, Any]) -> bool:
    return bool(state.get("authenticated"))


def append_user_message(state: MutableMapping[str, Any], content: str) -> None:
    state["history"].append(HumanMessage(content=content))


def append_assistant_message(state: MutableMapping[str, Any], content: str) -> None:
    state["history"].append(AIMessage(content=content))


def run_turn(
    state: MutableMapping[str, Any],
    user_message: str,
    current_dt: datetime,
    llm,
    handler=handle_message,
) -> str:
    """Append one turn while passing only prior conversation context downstream."""
    initialize_session(state)
    prior_history = list(state["history"])
    append_user_message(state, user_message)
    try:
        reply = handler(
            user_message=user_message,
            history=prior_history,
            username=state["username"],
            current_dt=current_dt,
            llm=llm,
        )
    except BookingError:
        raise
    except Exception:
        logger.exception("Unexpected failure while handling chat turn")
        reply = TURN_FAILURE_MESSAGE
    append_assistant_message(state, reply)
    return reply


def logout(state: MutableMapping[str, Any]) -> None:
    state.clear()
