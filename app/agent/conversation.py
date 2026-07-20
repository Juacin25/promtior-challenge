"""Deterministic presentation and server-bound booking conversation helpers."""

import re
from collections.abc import Callable
from datetime import datetime, timedelta

from app.data.db import ROOM_CAPACITIES
from app.domain.models import Booking

MAX_DURATION = timedelta(hours=3)
_FREE_SLOT = re.compile(r"^(\d{2}:\d{2})-(\d{2}:\d{2}) free$")


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def execute_create_booking(
    invoke: Callable[[dict], str],
    username: str,
    *,
    room_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    title: str | None = None,
    attendees: int | None = None,
) -> str:
    """Pre-validate a complete request, then invoke and present the domain tool."""
    if not room_id or not room_id.strip():
        return "Please provide a room."
    if not start or not end:
        return "Please provide both a start and end time."
    start_dt, end_dt = _parse_datetime(start), _parse_datetime(end)
    if start_dt is None or end_dt is None:
        if re.fullmatch(r"\d{2}:\d{2}", start) and re.fullmatch(
            r"\d{2}:\d{2}", end
        ):
            return "Please provide the booking date."
        return "Please provide a valid date and time range."
    if title is None or not title.strip():
        return "Please provide a meeting title; it cannot be blank."
    if attendees is None:
        return "Please provide the attendee count."
    if start_dt.minute % 30 or end_dt.minute % 30:
        return "Please use start and end times on :00 or :30 boundaries."
    if end_dt <= start_dt or end_dt - start_dt > MAX_DURATION:
        return (
            "Please choose a range that ends after it starts and lasts no more than "
            "3 hours."
        )
    capacity = ROOM_CAPACITIES.get(room_id.upper())
    if attendees < 1:
        return "Please provide an attendee count of at least 1."
    if capacity is not None and attendees > capacity:
        return (
            f"Room {room_id.upper()} holds at most {capacity} attendees. "
            "Please provide a corrected attendee count."
        )

    output = str(
        invoke(
            {
                "room_id": room_id.upper(),
                "start": start,
                "end": end,
                "title": title.strip(),
                "attendees": attendees,
                "user": username,
            }
        )
    )
    if not output.startswith("Booked room "):
        return output
    return (
        f"Booked '{title.strip()}' in room {room_id.upper()} on {start_dt:%Y-%m-%d}, "
        f"{start_dt:%H:%M} - {end_dt:%H:%M}, for {attendees} attendees."
    )


def format_available_slots(tool_output: str) -> str:
    """Return free 30-minute slots using the pinned user-facing format."""
    slots = []
    for line in tool_output.splitlines():
        match = _FREE_SLOT.fullmatch(line.strip())
        if match:
            slots.append(f"{match.group(1)} - {match.group(2)}")
    return "\n".join(slots) or "No free 30-minute slots are available."


def format_my_bookings(
    bookings: list[Booking], username: str | None = None
) -> str:
    """Present bookings without their internal identifiers."""
    visible = [booking for booking in bookings if username in (None, booking.user)]
    if not visible:
        return "You have no bookings."
    entries = [
        "\n".join(
            [
                f"Title: {booking.title}",
                f"Date: {booking.start:%Y-%m-%d}",
                f"Time: {booking.start:%H:%M} - {booking.end:%H:%M}",
                f"Attendees: {booking.attendees}",
                f"Room: {booking.room_id}",
            ]
        )
        for booking in sorted(visible, key=lambda booking: booking.start)
    ]
    return "Your bookings:\n" + "\n\n".join(entries)


def _matches(
    booking: Booking,
    *,
    room_id: str | None,
    date: str | None,
    start: str | None,
    title: str | None,
) -> bool:
    return (
        (room_id is None or booking.room_id.casefold() == room_id.strip().casefold())
        and (date is None or booking.start.date().isoformat() == date.strip())
        and (start is None or booking.start.strftime("%H:%M") == start.strip())
        and (title is None or booking.title.casefold() == title.strip().casefold())
    )


def execute_cancel_booking(
    invoke: Callable[[dict], str],
    bookings: list[Booking],
    username: str,
    *,
    room_id: str | None = None,
    date: str | None = None,
    start: str | None = None,
    title: str | None = None,
) -> str:
    """Resolve an owned booking description, then invoke cancel with its hidden ID."""
    if not any((room_id, date, start, title)):
        return "Please describe the booking by its date, time, title, or room."
    matches = [
        booking
        for booking in bookings
        if booking.user == username
        and _matches(
            booking, room_id=room_id, date=date, start=start, title=title
        )
    ]
    if not matches:
        return "I couldn't find one of your bookings matching that description."
    if len(matches) > 1:
        candidates = [
            (
                f"Title: {booking.title} | Date: {booking.start:%Y-%m-%d} | "
                f"Time: {booking.start:%H:%M} - {booking.end:%H:%M} | "
                f"Room: {booking.room_id}"
            )
            for booking in sorted(matches, key=lambda booking: booking.start)
        ]
        return "More than one booking matches. Which one should I cancel?\n" + "\n".join(
            candidates
        )

    booking = matches[0]
    output = str(invoke({"booking_id": booking.id, "user": username}))
    if not output.startswith("Cancelled booking "):
        return output
    return (
        f"Cancelled '{booking.title}' in room {booking.room_id} on "
        f"{booking.start:%Y-%m-%d}, {booking.start:%H:%M} - {booking.end:%H:%M}."
    )
