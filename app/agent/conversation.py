"""Deterministic presentation and server-bound booking conversation helpers."""

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import cast

from app.data.db import ROOM_CAPACITIES
from app.domain.models import Booking

MAX_DURATION = timedelta(hours=3)
_SCHEDULE_SLOT = re.compile(
    r"^(\d{2}:\d{2})-(\d{2}:\d{2}) (free|occupied)$"
)


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _missing_booking_message(
    room_id: str | None,
    start: str | None,
    end: str | None,
    title: str | None,
    attendees: int | None,
) -> str | None:
    missing = []
    if not room_id or not room_id.strip():
        missing.append("room (so I know which room to reserve)")
    if all(
        not value or re.fullmatch(r"\d{2}:\d{2}", value)
        for value in (start, end)
    ):
        missing.append("date (so I know which day to reserve)")
    if not start or not end:
        missing.append("time range (start and end time)")
    if title is None or not title.strip():
        missing.append("meeting title (required and cannot be blank)")
    if attendees is None:
        missing.append("attendee count (needed to check the room fits)")
    if not missing:
        return None

    understood = []
    if room_id and room_id.strip():
        understood.append(f"room {room_id.strip().upper()}")
    parsed = next(
        filter(None, (_parse_datetime(value) for value in (start, end) if value)),
        None,
    )
    if parsed is not None:
        understood.append(f"date {parsed:%Y-%m-%d}")
    if start and end:
        start_dt, end_dt = _parse_datetime(start), _parse_datetime(end)
        start_time = start_dt.strftime("%H:%M") if start_dt else start
        end_time = end_dt.strftime("%H:%M") if end_dt else end
        understood.append(f"time range {start_time} - {end_time}")
    if title and title.strip():
        understood.append(f'meeting title "{title.strip()}"')
    if attendees is not None:
        understood.append(f"attendee count {attendees}")

    prefix = f"I understood {', '.join(understood)}. " if understood else ""
    return f"{prefix}To create the booking, please provide: {'; '.join(missing)}."


def execute_create_booking(
    invoke: Callable[[dict], Booking | str],
    username: str,
    *,
    room_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    title: str | None = None,
    attendees: int | None = None,
) -> str:
    """Pre-validate a complete request, then invoke and present the domain tool."""
    missing_message = _missing_booking_message(
        room_id, start, end, title, attendees
    )
    if missing_message:
        return missing_message
    room_id, start, end = cast(str, room_id), cast(str, start), cast(str, end)
    title, attendees = cast(str, title), cast(int, attendees)
    start_dt, end_dt = _parse_datetime(start), _parse_datetime(end)
    if start_dt is None or end_dt is None:
        return "Please provide a valid date and time range."
    if start_dt.minute % 30 or end_dt.minute % 30:
        return "Please use start and end times on :00 or :30 boundaries."
    if end_dt <= start_dt:
        return "The end time must be after the start time."
    if end_dt - start_dt > MAX_DURATION:
        hours, minutes = divmod(int((end_dt - start_dt).total_seconds() // 60), 60)
        return (
            "A booking can last at most 3 hours; the requested range is "
            f"{hours} hours {minutes} minutes. Please choose a shorter range."
        )
    capacity = ROOM_CAPACITIES.get(room_id.upper())
    if attendees < 1:
        return "Please provide an attendee count of at least 1."
    if capacity is not None and attendees > capacity:
        return (
            f"Room {room_id.upper()} holds at most {capacity} attendees. "
            "Please provide a corrected attendee count."
        )

    output = invoke(
        {
            "room_id": room_id.upper(),
            "start": start,
            "end": end,
            "title": title.strip(),
            "attendees": attendees,
            "user": username,
        }
    )
    if not isinstance(output, Booking):
        return str(output)
    return (
        f"Booked '{output.title}' in room {output.room_id} on {output.start:%Y-%m-%d}, "
        f"{output.start:%H:%M} - {output.end:%H:%M} GMT-3, "
        f"for {output.attendees} attendees."
    )


def format_room_schedule(tool_output: str, room_id: str, start: str) -> str:
    """Present every schedule slot by state without exposing booking details."""
    local_start = datetime.fromisoformat(start)
    slots = {"free": [], "occupied": []}
    for line in tool_output.splitlines():
        match = _SCHEDULE_SLOT.fullmatch(line.strip())
        if match:
            slots[match.group(3)].append(f"{match.group(1)} - {match.group(2)}")
    available = "\n".join(slots["free"]) or "None."
    occupied = "\n".join(slots["occupied"]) or "None."
    return (
        f"Schedule for room {room_id.upper()} on {local_start:%Y-%m-%d} (GMT-3):\n"
        f"Available:\n{available}\nOccupied:\n{occupied}"
    )


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
    end: str | None,
    title: str | None,
) -> bool:
    return (
        (room_id is None or booking.room_id.casefold() == room_id.strip().casefold())
        and (date is None or booking.start.date().isoformat() == date.strip())
        and (start is None or booking.start.strftime("%H:%M") == start.strip())
        and (end is None or booking.end.strftime("%H:%M") == end.strip())
        and (title is None or booking.title.casefold() == title.strip().casefold())
    )


def execute_cancel_booking(
    invoke: Callable[[dict], Booking | str],
    bookings: list[Booking],
    username: str,
    *,
    room_id: str | None = None,
    date: str | None = None,
    start: str | None = None,
    end: str | None = None,
    title: str | None = None,
    default_date: str | None = None,
) -> str:
    """Resolve an owned booking description, then invoke cancel with its hidden ID."""
    if not any((room_id, date, start, end, title)):
        return "Please describe the booking by its date, time, title, or room."
    date_was_omitted = date is None
    match_date = date or default_date
    matches = [
        booking
        for booking in bookings
        if booking.user == username
        and _matches(
            booking,
            room_id=room_id,
            date=match_date,
            start=start,
            end=end,
            title=title,
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
    if date_was_omitted:
        return (
            f"I found this booking for today: Title: {booking.title} | "
            f"Room: {booking.room_id} | Date: {booking.start:%Y-%m-%d} | "
            f"Time: {booking.start:%H:%M} - {booking.end:%H:%M}. "
            "Should I cancel it?"
        )
    output = invoke({"booking_id": booking.id, "user": username})
    if not isinstance(output, Booking):
        return str(output)
    return (
        f"Cancelled '{output.title}' in room {output.room_id} on "
        f"{output.start:%Y-%m-%d}, {output.start:%H:%M} - {output.end:%H:%M}."
    )
