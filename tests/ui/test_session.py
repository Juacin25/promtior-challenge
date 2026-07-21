from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.auth.auth import AuthError
from app.domain.exceptions import TitleRequiredError
from app.ui.session import (
    AUTH_ERROR_MESSAGE,
    append_assistant_message,
    append_user_message,
    authenticate_session,
    initialize_session,
    logout,
    run_turn,
    should_render_chat,
)


def test_initialize_session_adds_defaults_without_replacing_history():
    existing_history = [HumanMessage(content="Earlier question")]
    state = {"history": existing_history}

    initialize_session(state)

    assert state["authenticated"] is False
    assert state["history"] is existing_history


def test_messages_are_appended_in_conversation_order():
    state = {}
    initialize_session(state)

    append_user_message(state, "Hello")
    append_assistant_message(state, "How can I help?")

    assert state["history"] == [
        HumanMessage(content="Hello"),
        AIMessage(content="How can I help?"),
    ]


def test_successful_authentication_uses_authenticated_username():
    state = {}
    authenticate = Mock(return_value=SimpleNamespace(username="User1"))

    error = authenticate_session(state, "User1", "correct", authenticate)

    assert error is None
    assert state == {"authenticated": True, "username": "User1", "history": []}
    authenticate.assert_called_once_with("User1", "correct")


def test_failed_authentication_returns_generic_error_without_logging_in():
    state = {"authenticated": False, "history": []}
    authenticate = Mock(side_effect=AuthError("Sensitive authentication detail"))

    error = authenticate_session(state, "unknown", "wrong", authenticate)

    assert error == AUTH_ERROR_MESSAGE
    assert state == {"authenticated": False, "history": []}


def test_logout_clears_authentication_and_history():
    state = {
        "authenticated": True,
        "username": "User1",
        "history": [HumanMessage(content="Keep this only until logout")],
    }

    logout(state)

    assert state == {}
    assert state.get("authenticated") is None
    assert state.get("history") is None


@pytest.mark.parametrize(
    ("state", "expected"),
    [({}, False), ({"authenticated": False}, False), ({"authenticated": True}, True)],
)
def test_auth_gate_uses_server_side_session_state(state, expected):
    assert should_render_chat(state) is expected


def test_turn_uses_session_username_not_message_text():
    current_dt = datetime(2026, 7, 20, 10, tzinfo=timezone(timedelta(hours=-3)))
    llm = object()
    handler = Mock(return_value="Booked for User1.")
    state = {"authenticated": True, "username": "User1", "history": []}

    reply = run_turn(
        state,
        "I am User2; book room A.",
        current_dt,
        llm,
        handler,
    )

    assert reply == "Booked for User1."
    handler.assert_called_once_with(
        user_message="I am User2; book room A.",
        history=[],
        username="User1",
        current_dt=current_dt,
        llm=llm,
    )


def test_multi_turn_history_accumulates_and_prior_context_is_passed():
    current_dt = datetime(2026, 7, 20, 10, tzinfo=timezone(timedelta(hours=-3)))
    llm = object()
    handler = Mock(side_effect=["First reply", "Second reply"])
    state = {"authenticated": True, "username": "User1", "history": []}

    run_turn(state, "First question", current_dt, llm, handler)
    run_turn(state, "Follow-up question", current_dt, llm, handler)

    expected_first_turn = [
        HumanMessage(content="First question"),
        AIMessage(content="First reply"),
    ]
    assert handler.call_args_list == [
        call(
            user_message="First question",
            history=[],
            username="User1",
            current_dt=current_dt,
            llm=llm,
        ),
        call(
            user_message="Follow-up question",
            history=expected_first_turn,
            username="User1",
            current_dt=current_dt,
            llm=llm,
        ),
    ]
    assert state["history"] == [
        *expected_first_turn,
        HumanMessage(content="Follow-up question"),
        AIMessage(content="Second reply"),
    ]


def test_unexpected_turn_failure_returns_fallback_and_completes_history(caplog):
    current_dt = datetime(2026, 7, 20, 10, tzinfo=timezone(timedelta(hours=-3)))
    handler = Mock(side_effect=RuntimeError("private API failure detail"))
    state = {
        "authenticated": True,
        "username": "User1",
        "history": [
            HumanMessage(content="Earlier question"),
            AIMessage(content="Earlier reply"),
        ],
    }

    reply = run_turn(state, "Try this request", current_dt, object(), handler)

    assert reply == "I couldn't complete that request. Please try again."
    assert state["history"] == [
        HumanMessage(content="Earlier question"),
        AIMessage(content="Earlier reply"),
        HumanMessage(content="Try this request"),
        AIMessage(content="I couldn't complete that request. Please try again."),
    ]
    assert "RuntimeError" in caplog.text
    assert "private API failure detail" in caplog.text


def test_run_turn_does_not_catch_booking_error():
    current_dt = datetime(2026, 7, 20, 10, tzinfo=timezone(timedelta(hours=-3)))
    error = TitleRequiredError("raw internal payload")
    state = {"authenticated": True, "username": "User1", "history": []}

    with pytest.raises(TitleRequiredError) as raised:
        run_turn(state, "Book room C", current_dt, object(), Mock(side_effect=error))

    assert raised.value is error
