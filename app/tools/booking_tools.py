"""LangChain tools — thin adapters between the LLM and the domain.

No business logic lives here: every rule is a call into :mod:`app.domain.rules`,
every read/write a parameterized call into the repository.

Two failure channels, deliberately:

* **Rule violations propagate** as ``BookingError`` subclasses. Translating them
  to user-facing text happens centrally (#14), so the tools stay thin and every
  tool behaves the same way.
* **Malformed or unresolvable input returns a message string.** A bad datetime or
  an unknown room is not a rule violation — it is the LLM getting the arguments
  wrong, and a string it can read lets it retry with corrected arguments.

The repository is closed over by :func:`build_booking_tools` rather than being a
tool argument, so it never reaches the LLM's tool schema.
"""

import uuid
from datetime import datetime, timedelta

from langchain_core.tools import tool

from app.data.db import ROOM_CAPACITIES
from app.data.repository import BookingRepository
from app.domain import rules
from app.domain.exceptions import OverlapError
from app.domain.models import Booking

SLOT = timedelta(minutes=30)
_ROOM_LIST = ", ".join(sorted(ROOM_CAPACITIES))  # "A, B, C, D, E"
_CANCEL_FAILURE = (
    "I couldn't cancel that booking. Please confirm it exists and belongs to you."
)


def _parse(value: str) -> datetime:
    """Parse the app's sole datetime representation without converting it."""
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != timedelta(hours=-3):
        raise ValueError("Datetime must use the GMT-3 (-03:00) offset.")
    return parsed


def _datetime_error(start: str, end: str) -> str:
    return (
        f"'{start}' / '{end}' is not a valid GMT-3 ISO datetime. "
        "Use YYYY-MM-DDTHH:MM-03:00."
    )


def _is_free(start: datetime, end: datetime, existing: list[Booking]) -> bool:
    """Predicate form of the domain overlap rule (single source of truth) —
    a range is free iff a probe booking for it overlaps nothing existing."""
    probe = Booking(
        id="", room_id="", user="", title="", attendees=1, start=start, end=end
    )
    try:
        rules.check_overlap(probe, existing)
        return True
    except OverlapError:
        return False


def build_booking_tools(repo: BookingRepository) -> list:
    @tool
    def create_booking(
        room_id: str, start: str, end: str, title: str, attendees: int, user: str
    ) -> Booking | str:
        """Book a room for a time range. Times are absolute ISO datetimes (GMT-3)."""
        try:
            start_dt, end_dt = _parse(start), _parse(end)
        except ValueError:
            return _datetime_error(start, end)

        capacity = ROOM_CAPACITIES.get(room_id)
        if capacity is None:
            return f"There is no room '{room_id}'. The rooms are: A, B, C, D, E."

        rules.check_title(title)
        rules.check_slot_alignment(start_dt, end_dt)
        rules.check_duration(start_dt, end_dt)
        rules.check_capacity(attendees, capacity)

        booking = Booking(
            # ponytail: 8 hex chars — short enough to say in chat, and the id
            # column is a PK so a collision fails loudly. Widen if it ever does.
            id=uuid.uuid4().hex[:8],
            room_id=room_id,
            user=user,
            title=title,
            attendees=attendees,
            start=start_dt,
            end=end_dt,
        )
        rules.check_overlap(booking, repo.find_by_room(room_id))
        repo.save(booking)
        return booking

    @tool
    def cancel_booking(booking_id: str, user: str) -> Booking | str:
        """Cancel a booking the logged-in user made, by its booking id."""
        booking = repo.find_by_id(booking_id)
        if booking is None or booking.user != user:
            return _CANCEL_FAILURE
        repo.delete(booking_id)
        return booking

    @tool
    def list_available_rooms(start: str, end: str, attendees: int | None = None) -> str:
        """List rooms fully free for a time range (GMT-3 ISO datetimes).

        With ``attendees`` set, only rooms that also fit the group are returned.
        """
        try:
            start_dt, end_dt = _parse(start), _parse(end)
        except ValueError:
            return _datetime_error(start, end)

        free = [
            room
            for room, capacity in sorted(ROOM_CAPACITIES.items())
            if (attendees is None or capacity >= attendees)
            and _is_free(start_dt, end_dt, repo.find_by_room(room))
        ]
        if not free:
            return "No rooms are free for that range."
        return f"Rooms free from {start_dt:%Y-%m-%d %H:%M} to {end_dt:%H:%M}: {', '.join(free)}."

    @tool
    def get_room_schedule(room_id: str, start: str, end: str) -> str:
        """Show a room's 30-minute slots as free or occupied for a range (GMT-3)."""
        if room_id not in ROOM_CAPACITIES:
            return f"There is no room '{room_id}'. The rooms are: {_ROOM_LIST}."
        try:
            start_dt, end_dt = _parse(start), _parse(end)
        except ValueError:
            return _datetime_error(start, end)

        rules.check_slot_alignment(start_dt, end_dt)
        existing = repo.find_by_room(room_id)
        lines = []
        slot_start = start_dt
        while slot_start < end_dt:
            slot_end = slot_start + SLOT
            status = "free" if _is_free(slot_start, slot_end, existing) else "occupied"
            lines.append(f"{slot_start:%H:%M}-{slot_end:%H:%M} {status}")
            slot_start = slot_end
        return f"Schedule for room {room_id}:\n" + "\n".join(lines)

    return [create_booking, cancel_booking, list_available_rooms, get_room_schedule]
