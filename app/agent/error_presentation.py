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
    SlotAlignmentError: "Please use start and end times on :00 or :30 boundaries.",
    DurationError: "A booking must end after it starts and last no more than 3 hours.",
    TitleRequiredError: "A meeting title is required and cannot be blank.",
    OverlapError: (
        "The room is already booked for part or all of that date and time range."
    ),
}
_CAPACITY_PATTERN = re.compile(r"room capacity \((\d+)\)")


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
    return _MESSAGES.get(type(error), GENERIC_BOOKING_ERROR)
