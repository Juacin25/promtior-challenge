"""Thin single-page Streamlit interface for login and booking chat."""

from datetime import datetime

import streamlit as st
from langchain_core.messages import HumanMessage

from app.agent.llm import GMT_MINUS_3, build_llm
from app.ui.session import (
    authenticate_session,
    initialize_session,
    logout,
    run_turn,
    should_render_chat,
)


@st.cache_resource
def _get_llm():
    return build_llm()


def render_login() -> None:
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.title("Meeting rooms")
        st.caption("Sign in to manage bookings at Cubo Itaú.")
        with st.form("login"):
            username = st.text_input("Username", autocomplete="username")
            password = st.text_input(
                "Password", type="password", autocomplete="current-password"
            )
            submitted = st.form_submit_button("Sign in", use_container_width=True)

        if submitted:
            error = authenticate_session(st.session_state, username, password)
            if error:
                st.error(error)
            else:
                st.rerun()


def render_chat() -> None:
    username = st.session_state["username"]
    st.title("Meeting-room assistant")
    st.caption(f"Signed in as {username}")

    with st.sidebar:
        st.subheader("Session")
        st.write(username)
        if st.button("Log out", use_container_width=True):
            logout(st.session_state)
            st.rerun()

    for message in st.session_state["history"]:
        role = "user" if isinstance(message, HumanMessage) else "assistant"
        with st.chat_message(role):
            st.markdown(str(message.content))

    if user_message := st.chat_input("Ask about a room or booking"):
        with st.chat_message("user"):
            st.markdown(user_message)
        with st.chat_message("assistant"):
            with st.spinner("Working on it…"):
                reply = run_turn(
                    st.session_state,
                    user_message,
                    datetime.now(GMT_MINUS_3),
                    _get_llm(),
                )
            st.markdown(reply)


def main() -> None:
    st.set_page_config(
        page_title="Promtior Meeting Rooms",
        page_icon="📅",
        layout="centered",
    )
    initialize_session(st.session_state)
    if should_render_chat(st.session_state):
        render_chat()
    else:
        render_login()


if __name__ == "__main__":
    main()
