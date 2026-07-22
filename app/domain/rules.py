"""Pure business validation. No I/O, no DB — the repository supplies any lists.

Each rule is single-responsibility: returns None on success, raises its specific
:mod:`app.domain.exceptions` error on failure.
"""

from datetime import datetime, timedelta

from app.domain.exceptions import (
    CapacityError,
    DurationError,
    OverlapError,
    SlotAlignmentError,
    TitleRequiredError,
)
from app.domain.models import Booking

MAX_DURATION = timedelta(hours=3)


def check_slot_alignment(start: datetime, end: datetime) -> None:
    if start.minute % 30 != 0 or end.minute % 30 != 0:
        raise SlotAlignmentError(
            "Bookings must start and end on 30-minute boundaries (:00 or :30)."
        )


def check_duration(start: datetime, end: datetime) -> None:
    if end <= start:
        raise DurationError("End time must be after start time.")
    if end - start > MAX_DURATION:
        raise DurationError("A booking may last at most 3 hours.")


def check_capacity(attendees: int, capacity: int) -> None:
    if attendees < 1 or attendees > capacity:
        raise CapacityError(f"Attendees must be between 1 and the room capacity ({capacity}).")


def check_title(title: str) -> None:
    if not title.strip():
        raise TitleRequiredError("A booking requires a non-empty title.")


def check_overlap(candidate: Booking, existing: list[Booking]) -> None:
    for other in existing:
        # Back-to-back (touching endpoints) is allowed; only true overlap fails.
        if candidate.start < other.end and other.start < candidate.end:
            raise OverlapError("The room is already booked for part of that time range.")
