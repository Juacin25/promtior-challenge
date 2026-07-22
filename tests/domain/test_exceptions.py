from app.domain.exceptions import (
    BookingError,
    CapacityError,
    DurationError,
    OverlapError,
    SlotAlignmentError,
    TitleRequiredError,
)


def test_all_inherit_directly_from_booking_error():
    for exc in (
        SlotAlignmentError,
        DurationError,
        CapacityError,
        TitleRequiredError,
        OverlapError,
    ):
        assert issubclass(exc, BookingError)
        # Flat hierarchy: BookingError is the immediate base, nothing deeper.
        assert exc.__bases__ == (BookingError,)


def test_booking_error_is_exception():
    assert issubclass(BookingError, Exception)
