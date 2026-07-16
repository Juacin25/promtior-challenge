"""Typed domain errors — one per business rule, flat under ``BookingError``.

Flat by design (no deeper hierarchy): Issue #14 catches ``BookingError`` to
surface messages to the user, while callers that care about a specific failure
can catch the exact subclass. No elaborate hierarchy (out of scope).
"""


class BookingError(Exception):
    """Base for all booking rule violations."""


class SlotAlignmentError(BookingError):
    pass


class DurationError(BookingError):
    pass


class CapacityError(BookingError):
    pass


class TitleRequiredError(BookingError):
    pass


class OverlapError(BookingError):
    pass
