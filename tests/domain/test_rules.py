from datetime import datetime

import pytest

from app.domain.exceptions import (
    CapacityError,
    DurationError,
    OverlapError,
    SlotAlignmentError,
    TitleRequiredError,
)
from app.domain.models import Booking
from app.domain.rules import (
    check_capacity,
    check_duration,
    check_overlap,
    check_slot_alignment,
    check_title,
)


def dt(h, m):
    return datetime(2026, 7, 17, h, m)


def booking(start, end, room_id="A", id="c"):
    return Booking(
        id=id,
        room_id=room_id,
        user="User1",
        title="T",
        attendees=1,
        start=start,
        end=end,
    )


# --- slot alignment ---

@pytest.mark.parametrize("minute", [0, 30])
def test_slot_alignment_ok(minute):
    assert check_slot_alignment(dt(9, minute), dt(10, minute)) is None


def test_slot_alignment_bad_minute_raises():
    with pytest.raises(SlotAlignmentError):
        check_slot_alignment(dt(9, 15), dt(9, 45))


def test_slot_alignment_bad_end_raises():
    with pytest.raises(SlotAlignmentError):
        check_slot_alignment(dt(9, 0), dt(9, 45))


# --- duration ---

def test_duration_30min_ok():
    assert check_duration(dt(9, 0), dt(9, 30)) is None


def test_duration_exactly_3h_ok():
    assert check_duration(dt(9, 0), dt(12, 0)) is None


def test_duration_3h30_raises():
    with pytest.raises(DurationError):
        check_duration(dt(9, 0), dt(12, 30))


def test_duration_end_equals_start_raises():
    with pytest.raises(DurationError):
        check_duration(dt(9, 0), dt(9, 0))


def test_duration_end_before_start_raises():
    with pytest.raises(DurationError):
        check_duration(dt(9, 30), dt(9, 0))


# --- capacity ---

def test_capacity_one_ok():
    assert check_capacity(1, 10) is None


def test_capacity_equal_ok():
    assert check_capacity(10, 10) is None


def test_capacity_over_raises():
    with pytest.raises(CapacityError):
        check_capacity(11, 10)


def test_capacity_zero_raises():
    with pytest.raises(CapacityError):
        check_capacity(0, 10)


# --- title ---

def test_title_ok():
    assert check_title("x") is None


@pytest.mark.parametrize("title", ["", "   "])
def test_title_empty_raises(title):
    with pytest.raises(TitleRequiredError):
        check_title(title)


# --- overlap ---

def test_overlap_none_ok():
    existing = [booking(dt(8, 0), dt(9, 0))]
    assert check_overlap(booking(dt(10, 0), dt(10, 30)), existing) is None


def test_overlap_empty_list_ok():
    assert check_overlap(booking(dt(9, 0), dt(9, 30)), []) is None


def test_overlap_back_to_back_ok():
    existing = [booking(dt(9, 0), dt(9, 30))]
    assert check_overlap(booking(dt(9, 30), dt(10, 0)), existing) is None
    assert check_overlap(booking(dt(8, 30), dt(9, 0)), existing) is None


def test_overlap_partial_raises():
    existing = [booking(dt(9, 0), dt(10, 0))]
    with pytest.raises(OverlapError):
        check_overlap(booking(dt(9, 30), dt(10, 30)), existing)


def test_overlap_identical_raises():
    existing = [booking(dt(9, 0), dt(10, 0))]
    with pytest.raises(OverlapError):
        check_overlap(booking(dt(9, 0), dt(10, 0)), existing)


def test_overlap_contained_raises():
    existing = [booking(dt(9, 0), dt(12, 0))]
    with pytest.raises(OverlapError):
        check_overlap(booking(dt(10, 0), dt(10, 30)), existing)


def test_overlap_message_does_not_leak_user():
    existing = [Booking("x", "A", "SecretUser", "T", 1, dt(9, 0), dt(10, 0))]
    with pytest.raises(OverlapError) as exc:
        check_overlap(booking(dt(9, 0), dt(10, 0)), existing)
    assert "SecretUser" not in str(exc.value)
