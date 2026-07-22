"""Deterministic user-facing presentation of domain booking errors."""

import re
from collections.abc import Mapping
from datetime import datetime, timedelta

from app.domain.exceptions import (
    BookingError,
    CapacityError,
    DurationError,
    OverlapError,
    SlotAlignmentError,
    TitleRequiredError,
)

GENERIC_BOOKING_ERROR = (
    "I couldn't complete that booking. Please review the details and try again."
)
_MESSAGES = {
    SlotAlignmentError: (
        "Start and end times must use 30-minute boundaries (:00 or :30)."
    ),
    TitleRequiredError: "A meeting title is required and cannot be blank.",
    OverlapError: (
        "The room is already booked for part or all of that date and time range. "
        "Choose another time or another room."
    ),
}
_CAPACITY_PATTERN = re.compile(r"room capacity \((\d+)\)")
_DURATION_MESSAGES = {
    "End time must be after start time.": "The end time must be after the start time.",
    "A booking may last at most 3 hours.": "A booking can last at most 3 hours.",
}


def _datetime(request: Mapping[str, object], name: str) -> datetime | None:
    value = request.get(name)
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _time_range(request: Mapping[str, object]) -> tuple[datetime, datetime] | None:
    start, end = _datetime(request, "start"), _datetime(request, "end")
    return (start, end) if start is not None and end is not None else None


def _alignment_message(request: Mapping[str, object]) -> str:
    corrections = []
    for label in ("start", "end"):
        value = _datetime(request, label)
        if value is None or value.minute % 30 == 0:
            continue
        earlier = value.replace(minute=value.minute // 30 * 30, second=0, microsecond=0)
        later = earlier + timedelta(minutes=30)
        corrections.append(
            f"{label} time {value:%H:%M} (nearest valid times: "
            f"{earlier:%H:%M} or {later:%H:%M})"
        )
    if not corrections:
        return _MESSAGES[SlotAlignmentError]
    return (
        f"The requested {'; '.join(corrections)} is not valid. Booking times must "
        "fall on :00 or :30. Please choose one of the nearest valid times."
    )


def _duration_message(error: BookingError, request: Mapping[str, object]) -> str:
    requested = _time_range(request)
    if requested is None:
        return _DURATION_MESSAGES.get(str(error), GENERIC_BOOKING_ERROR)
    start, end = requested
    if str(error) == "End time must be after start time.":
        return (
            f"The requested time range {start:%H:%M} - {end:%H:%M} is invalid: "
            "the end time must be after the start time. Choose a later end time."
        )
    if str(error) == "A booking may last at most 3 hours.":
        minutes = int((end - start).total_seconds() // 60)
        hours, minutes = divmod(minutes, 60)
        return (
            f"The requested {hours} hours {minutes} minutes exceeds the 3-hour "
            "maximum. Choose a shorter time range."
        )
    return GENERIC_BOOKING_ERROR


def present_booking_error(
    error: BookingError, request: Mapping[str, object] | None = None
) -> str:
    """Map a domain error to fixed guidance without exposing its raw payload."""
    request = request or {}
    if type(error) is SlotAlignmentError:
        return _alignment_message(request)
    if type(error) is CapacityError:
        match = _CAPACITY_PATTERN.search(str(error))
        if not match:
            return GENERIC_BOOKING_ERROR
        attendees, room = request.get("attendees"), request.get("room_id")
        if isinstance(attendees, int) and isinstance(room, str):
            return (
                f"You requested {attendees} attendees for room {room.upper()}, but "
                f"that room's capacity is {match.group(1)}. Choose an attendee count "
                f"from 1 to {match.group(1)}."
            )
        return (
            "The attendee count must be at least 1 and within the room's capacity of "
            f"{match.group(1)}."
        )
    if type(error) is DurationError:
        return _duration_message(error, request)
    if type(error) is TitleRequiredError and request.get("title") is not None:
        return (
            "The meeting title you provided is blank. A title is required and cannot "
            "be blank. Provide a meeting title."
        )
    if type(error) is OverlapError:
        requested = _time_range(request)
        room = request.get("room_id")
        if requested is not None and isinstance(room, str):
            return (
                f"Room {room.upper()} is already taken for part of your requested "
                f"{requested[0]:%H:%M} - {requested[1]:%H:%M} range. Choose another "
                "time or another room."
            )
    return _MESSAGES.get(type(error), GENERIC_BOOKING_ERROR)
