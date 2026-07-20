"""Deterministic user-facing presentation of domain booking errors."""

import re

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
        "The room is already booked for part or all of that date and time range."
    ),
}
_CAPACITY_PATTERN = re.compile(r"room capacity \((\d+)\)")
_DURATION_MESSAGES = {
    "End time must be after start time.": "The end time must be after the start time.",
    "A booking may last at most 3 hours.": "A booking can last at most 3 hours.",
}


def present_booking_error(error: BookingError) -> str:
    """Map a domain error to fixed guidance without exposing its raw payload."""
    if type(error) is CapacityError:
        match = _CAPACITY_PATTERN.search(str(error))
        if not match:
            return GENERIC_BOOKING_ERROR
        return (
            "The attendee count must be at least 1 and within the room's capacity of "
            f"{match.group(1)}."
        )
    if type(error) is DurationError:
        return _DURATION_MESSAGES.get(str(error), GENERIC_BOOKING_ERROR)
    return _MESSAGES.get(type(error), GENERIC_BOOKING_ERROR)
