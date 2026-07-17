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
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

from app.data.db import ROOM_CAPACITIES
from app.data.repository import BookingRepository
from app.domain import rules
from app.domain.models import Booking

GMT3 = timezone(timedelta(hours=-3))


def _parse(value: str) -> datetime:
    """Absolute ISO -> aware datetime. A missing offset means GMT-3, the app's
    only timezone; aware datetimes are required to compare against stored ones."""
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=GMT3)


def build_booking_tools(repo: BookingRepository) -> list:
    @tool
    def create_booking(
        room_id: str, start: str, end: str, title: str, attendees: int, user: str
    ) -> str:
        """Book a room for a time range. Times are absolute ISO datetimes (GMT-3)."""
        try:
            start_dt, end_dt = _parse(start), _parse(end)
        except ValueError:
            return f"'{start}' / '{end}' is not a valid ISO datetime. Use YYYY-MM-DDTHH:MM."

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
            start=start_dt,
            end=end_dt,
        )
        rules.check_overlap(booking, repo.find_by_room(room_id))
        repo.save(booking)
        return (
            f"Booked room {room_id} for '{title}' from {start_dt:%Y-%m-%d %H:%M} "
            f"to {end_dt:%H:%M} ({attendees} attendees). Booking id: {booking.id}."
        )

    @tool
    def cancel_booking(booking_id: str, user: str) -> str:
        """Cancel a booking the logged-in user made, by its booking id."""
        booking = repo.find_by_id(booking_id)
        if booking is None:
            return f"Booking '{booking_id}' was not found."
        if booking.user != user:
            # Deliberately says nothing about the booking or its owner.
            return f"You cannot cancel booking '{booking_id}'."
        repo.delete(booking_id)
        return f"Cancelled booking '{booking_id}'."

    return [create_booking, cancel_booking]
