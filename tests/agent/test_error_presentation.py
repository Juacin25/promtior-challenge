from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from app.agent.error_presentation import present_booking_error
from app.data.db import connect
from app.data.repository import BookingRepository
from app.domain.exceptions import (
    BookingError,
    CapacityError,
    DurationError,
    OverlapError,
    SlotAlignmentError,
    TitleRequiredError,
)
from app.domain.models import Booking
from app.tools.booking_tools import build_booking_tools

BOOKING_ID = "booking-id-9f8e7d"
OWNER = "GreppableOwnerUsername"


@pytest.fixture
def presented_messages():
    return {
        SlotAlignmentError: present_booking_error(SlotAlignmentError(BOOKING_ID)),
        DurationError: present_booking_error(
            DurationError("A booking may last at most 3 hours.")
        ),
        CapacityError: present_booking_error(
            CapacityError(
                f"Attendees must be between 1 and the room capacity (4). {BOOKING_ID}"
            )
        ),
        TitleRequiredError: present_booking_error(TitleRequiredError(BOOKING_ID)),
        OverlapError: present_booking_error(
            OverlapError(f"Conflict owned by {OWNER}; id={BOOKING_ID}")
        ),
    }


def test_each_domain_error_has_a_distinct_human_readable_message(presented_messages):
    messages = list(presented_messages.values())

    assert all(message.strip() for message in messages)
    assert len(set(messages)) == len(messages)


def test_messages_explain_the_valid_expected_values(presented_messages):
    slot = presented_messages[SlotAlignmentError]
    duration = presented_messages[DurationError]
    capacity = presented_messages[CapacityError]
    title = presented_messages[TitleRequiredError]
    overlap = presented_messages[OverlapError]

    assert ":00" in slot and ":30" in slot
    assert "3 hours" in duration
    assert "at least 1" in capacity and "capacity of 4" in capacity
    assert "title" in title.lower() and "blank" in title.lower()
    assert "already booked" in overlap.lower() and "part or all" in overlap.lower()


def test_constraint_messages_state_exact_expected_values(presented_messages):
    assert presented_messages[SlotAlignmentError] == (
        "Start and end times must use 30-minute boundaries (:00 or :30)."
    )
    assert presented_messages[DurationError] == "A booking can last at most 3 hours."
    assert presented_messages[CapacityError] == (
        "The attendee count must be at least 1 and within the room's capacity of 4."
    )
    assert presented_messages[TitleRequiredError] == (
        "A meeting title is required and cannot be blank."
    )
    assert presented_messages[OverlapError] == (
        "The room is already booked for part or all of that date and time range."
    )


def test_end_before_start_has_a_distinct_translated_message():
    assert present_booking_error(DurationError("End time must be after start time.")) == (
        "The end time must be after the start time."
    )


def test_overlap_message_leaks_neither_owner_nor_booking_id(presented_messages):
    message = presented_messages[OverlapError]

    assert OWNER not in message
    assert BOOKING_ID not in message


def test_no_domain_error_message_leaks_ids_class_names_or_technical_terms(
    presented_messages,
):
    forbidden_terms = {
        "exception",
        "traceback",
        "database",
        "sql",
        *(error_type.__name__.lower() for error_type in presented_messages),
    }

    for message in presented_messages.values():
        assert BOOKING_ID not in message
        assert all(term not in message.lower() for term in forbidden_terms)


def test_unknown_booking_error_uses_safe_generic_fallback():
    class UnexpectedBookingError(BookingError):
        pass

    message = present_booking_error(
        UnexpectedBookingError(f"database traceback for {BOOKING_ID}")
    )

    assert message == "I couldn't complete that booking. Please review the details and try again."
    assert BOOKING_ID not in message
    assert "UnexpectedBookingError" not in message
    assert "database" not in message.lower()


def test_capacity_error_without_safe_capacity_uses_generic_fallback():
    message = present_booking_error(
        CapacityError(f"untrusted capacity payload {BOOKING_ID}")
    )

    assert message == "I couldn't complete that booking. Please review the details and try again."
    assert BOOKING_ID not in message


def test_cancel_denial_and_missing_booking_are_indistinguishable_and_private(tmp_path):
    with closing(connect(tmp_path / "bookings.db")) as connection:
        repo = BookingRepository(connection)
        repo.save(
            Booking(
                id="private-booking-id",
                room_id="C",
                user=OWNER,
                title="Private meeting",
                attendees=2,
                start=datetime(2026, 7, 21, 9, tzinfo=timezone(timedelta(hours=-3))),
                end=datetime(2026, 7, 21, 10, tzinfo=timezone(timedelta(hours=-3))),
            )
        )
        cancel = build_booking_tools(repo)[1]

        denied = cancel.invoke(
            {"booking_id": "private-booking-id", "user": "User1"}
        )
        missing = cancel.invoke({"booking_id": "missing-booking-id", "user": "User1"})

    assert denied == missing
    assert OWNER not in denied
    assert "private-booking-id" not in denied
    assert "missing-booking-id" not in missing
