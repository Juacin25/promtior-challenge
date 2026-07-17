import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "gpt-4o-mini"
PROMPT_CACHE_KEY = "promtior-booking-agent-v1"
GMT_MINUS_3 = timezone(timedelta(hours=-3))


def build_llm() -> ChatOpenAI:
    """Build the deterministic, environment-configured chat model."""
    load_dotenv()
    return ChatOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("OPENAI_MODEL") or DEFAULT_MODEL,
        temperature=0,
        model_kwargs={"prompt_cache_key": PROMPT_CACHE_KEY},
    )


def build_system_prompt(current_dt: datetime, username: str) -> str:
    """Build the grounded booking prompt with deterministic per-turn context."""
    anchor = (
        current_dt.replace(tzinfo=GMT_MINUS_3)
        if current_dt.tzinfo is None
        else current_dt.astimezone(GMT_MINUS_3)
    )
    tomorrow = anchor.date() + timedelta(days=1)

    # Keep reusable instructions first; dynamic context belongs at the end for prefix caching.
    return f"""You are Cubo Itaú's meeting-room booking assistant. Your sole purpose is booking,
listing, inspecting, and cancelling bookings for rooms A-E. Politely refuse unrelated requests.

Ground every room or booking fact in tool output. Never invent or infer availability, capacity,
bookings, schedules, or other current state from memory. Any such claim must come from a tool call.
Tools receive absolute ISO datetimes. Convert relative user phrasing with the turn context below,
use 24-hour time, and include the GMT-3 (-03:00) offset.

Turn context:
- Logged-in username: {username}
- Current datetime: {anchor.isoformat(sep=" ", timespec="seconds")} (GMT-3)
- Today's date: {anchor.date().isoformat()}
- "Tomorrow" means: {tomorrow.isoformat()} (today + 1 day)
"""
