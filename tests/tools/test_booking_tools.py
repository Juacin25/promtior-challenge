import re
from datetime import datetime, timedelta, timezone

import pytest

from app.data.db import connect
from app.data.repository import BookingRepository
from app.domain.exceptions import (
    CapacityError,
    DurationError,
    OverlapError,
    SlotAlignmentError,
    TitleRequiredError,
)
from app.domain.models import Booking
from app.tools.booking_tools import build_booking_tools

GMT3 = timezone(timedelta(hours=-3))


@pytest.fixture
def repo(tmp_path):
    return BookingRepository(connect(tmp_path / "test.db"))


@pytest.fixture
def tools(repo):
    return build_booking_tools(repo)


@pytest.fixture
def create(tools):
    return tools[0]


@pytest.fixture
def cancel(tools):
    return tools[1]


@pytest.fixture
def list_rooms(tools):
    return tools[2]


@pytest.fixture
def schedule(tools):
    return tools[3]


def args(**overrides):
    base = {
        "room_id": "C",
        "start": "2026-07-18T09:00:00-03:00",
        "end": "2026-07-18T10:00:00-03:00",
        "title": "Standup",
        "attendees": 3,
        "user": "User1",
    }
    return base | overrides


# --- create_booking -------------------------------------------------------


def test_create_saves_booking_and_confirms(create, repo):
    result = create.invoke(args())

    saved = repo.find_by_room("C")
    assert len(saved) == 1
    booking = saved[0]
    assert booking.title == "Standup"
    assert booking.start == datetime(2026, 7, 18, 9, 0, tzinfo=GMT3)
    assert booking.end == datetime(2026, 7, 18, 10, 0, tzinfo=GMT3)
    # The confirmation must carry the id, so the user can cancel it later.
    assert booking.id in result
    assert "C" in result


def test_create_ties_booking_to_the_passed_user(create, repo):
    create.invoke(args(user="User2"))
    assert repo.find_by_user("User2")[0].user == "User2"
    assert repo.find_by_user("User1") == []


def test_create_generates_unique_ids(create, repo):
    create.invoke(args(start="2026-07-18T09:00:00-03:00", end="2026-07-18T09:30:00-03:00"))
    create.invoke(args(start="2026-07-18T11:00:00-03:00", end="2026-07-18T11:30:00-03:00"))
    ids = {b.id for b in repo.find_by_room("C")}
    assert len(ids) == 2


def test_create_accepts_naive_iso_as_gmt3(create, repo):
    # The LLM may drop the offset; GMT-3 is the app's only timezone.
    create.invoke(args(start="2026-07-18T09:00:00", end="2026-07-18T09:30:00"))
    assert repo.find_by_room("C")[0].start == datetime(2026, 7, 18, 9, 0, tzinfo=GMT3)


def test_create_rejects_non_iso_datetime_without_saving(create, repo):
    result = create.invoke(args(start="tomorrow at nine"))
    assert "ISO" in result
    assert repo.find_by_room("C") == []


def test_create_rejects_unknown_room_without_saving(create, repo):
    result = create.invoke(args(room_id="Z"))
    assert "Z" in result
    assert "A, B, C, D, E" in result


@pytest.mark.parametrize(
    "overrides, error",
    [
        ({"attendees": 5}, CapacityError),  # room C holds 4
        ({"start": "2026-07-18T09:10:00-03:00"}, SlotAlignmentError),
        ({"end": "2026-07-18T13:30:00-03:00"}, DurationError),  # 4h30 > 3h
        ({"title": "   "}, TitleRequiredError),
    ],
)
def test_create_propagates_rule_violations(create, repo, overrides, error):
    with pytest.raises(error):
        create.invoke(args(**overrides))
    assert repo.find_by_room("C") == []


def test_create_propagates_overlap_against_existing_booking(create, repo):
    create.invoke(args())
    with pytest.raises(OverlapError):
        create.invoke(args(start="2026-07-18T09:30:00-03:00", end="2026-07-18T10:30:00-03:00"))
    assert len(repo.find_by_room("C")) == 1


def test_create_allows_back_to_back_bookings(create, repo):
    create.invoke(args())
    create.invoke(args(start="2026-07-18T10:00:00-03:00", end="2026-07-18T10:30:00-03:00"))
    assert len(repo.find_by_room("C")) == 2


def test_create_overlap_is_scoped_to_the_room(create, repo):
    create.invoke(args(room_id="C"))
    create.invoke(args(room_id="D"))  # same time, different room
    assert len(repo.find_by_room("D")) == 1


# --- cancel_booking -------------------------------------------------------


def seed(repo, id="b1", user="User1"):
    repo.save(
        Booking(
            id=id,
            room_id="C",
            user=user,
            title="Standup",
            start=datetime(2026, 7, 18, 9, 0, tzinfo=GMT3),
            end=datetime(2026, 7, 18, 9, 30, tzinfo=GMT3),
        )
    )


def test_cancel_removes_own_booking(cancel, repo):
    seed(repo, user="User1")
    result = cancel.invoke({"booking_id": "b1", "user": "User1"})
    assert repo.find_by_id("b1") is None
    assert "b1" in result


def test_cancel_rejects_other_users_booking_without_deleting(cancel, repo):
    seed(repo, user="User2")
    result = cancel.invoke({"booking_id": "b1", "user": "User1"})
    assert repo.find_by_id("b1") is not None
    assert "couldn't cancel" in result.lower()
    assert "b1" not in result


def test_cancel_never_leaks_the_owner_identity(cancel, repo):
    seed(repo, user="User2")
    result = cancel.invoke({"booking_id": "b1", "user": "User1"})
    assert "User2" not in result
    # Nor may it leak booking details the caller is not entitled to see.
    assert "Standup" not in result
    assert "C" not in result


def test_cancel_unknown_id_returns_private_generic_message(cancel, repo):
    result = cancel.invoke({"booking_id": "nope", "user": "User1"})
    assert "couldn't cancel" in result.lower()
    assert "nope" not in result


def test_cancel_of_unknown_and_of_others_booking_are_indistinguishable_in_effect(cancel, repo):
    seed(repo, id="b1", user="User2")
    denied = cancel.invoke({"booking_id": "b1", "user": "User1"})
    missing = cancel.invoke({"booking_id": "b2", "user": "User1"})
    assert denied == missing
    assert "b1" not in denied
    assert "b2" not in missing
    assert repo.find_by_id("b1") is not None


# --- list_available_rooms -------------------------------------------------


def occupy(repo, room_id, start="2026-07-18T09:00:00-03:00", end="2026-07-18T10:00:00-03:00"):
    repo.save(
        Booking(
            id=f"occ-{room_id}",
            room_id=room_id,
            user="User1",
            title="Busy",
            start=datetime.fromisoformat(start),
            end=datetime.fromisoformat(end),
        )
    )


def rooms_in(result):
    return set(re.findall(r"\b[A-E]\b", result))


RANGE = {"start": "2026-07-18T09:00:00-03:00", "end": "2026-07-18T10:00:00-03:00"}


def test_list_no_attendees_returns_all_free_rooms_alphabetical(list_rooms, repo):
    result = list_rooms.invoke(dict(RANGE))
    assert rooms_in(result) == {"A", "B", "C", "D", "E"}
    # Deterministic A→E ordering.
    assert re.findall(r"\b[A-E]\b", result) == ["A", "B", "C", "D", "E"]


def test_list_excludes_occupied_rooms(list_rooms, repo):
    occupy(repo, "C")
    assert rooms_in(list_rooms.invoke(dict(RANGE))) == {"A", "B", "D", "E"}


def test_list_partial_overlap_still_excludes(list_rooms, repo):
    # A booking touching only part of the range makes the room not fully free.
    occupy(repo, "D", start="2026-07-18T09:30:00-03:00", end="2026-07-18T10:30:00-03:00")
    assert "D" not in rooms_in(list_rooms.invoke(dict(RANGE)))


def test_list_back_to_back_room_stays_free(list_rooms, repo):
    occupy(repo, "E", start="2026-07-18T10:00:00-03:00", end="2026-07-18T10:30:00-03:00")
    assert "E" in rooms_in(list_rooms.invoke(dict(RANGE)))


def test_list_with_attendees_2_includes_capacity_2_rooms(list_rooms, repo):
    assert rooms_in(list_rooms.invoke({**RANGE, "attendees": 2})) == {"A", "B", "C", "D", "E"}


def test_list_with_attendees_3_excludes_capacity_2_rooms(list_rooms, repo):
    assert rooms_in(list_rooms.invoke({**RANGE, "attendees": 3})) == {"C", "D", "E"}


def test_list_with_attendees_excludes_occupied_too(list_rooms, repo):
    occupy(repo, "C")
    assert rooms_in(list_rooms.invoke({**RANGE, "attendees": 3})) == {"D", "E"}


def test_list_no_free_rooms_message(list_rooms, repo):
    for room in "ABCDE":
        occupy(repo, room)
    result = list_rooms.invoke(dict(RANGE))
    assert rooms_in(result) == set()
    assert "no" in result.lower()


def test_list_rejects_non_iso(list_rooms, repo):
    assert "ISO" in list_rooms.invoke({"start": "soon", "end": "later"})


# --- get_room_schedule ----------------------------------------------------


def test_schedule_marks_free_and_occupied_slots(schedule, repo):
    occupy(repo, "C", start="2026-07-18T09:30:00-03:00", end="2026-07-18T10:00:00-03:00")
    result = schedule.invoke(
        {"room_id": "C", "start": "2026-07-18T09:00:00-03:00", "end": "2026-07-18T11:00:00-03:00"}
    )
    assert "09:00-09:30 free" in result
    assert "09:30-10:00 occupied" in result
    assert "10:00-10:30 free" in result
    assert "10:30-11:00 free" in result


def test_schedule_is_read_only(schedule, repo):
    occupy(repo, "C")
    before = len(repo.find_by_room("C"))
    schedule.invoke(
        {"room_id": "C", "start": "2026-07-18T09:00:00-03:00", "end": "2026-07-18T10:00:00-03:00"}
    )
    assert len(repo.find_by_room("C")) == before


def test_schedule_rejects_unknown_room(schedule, repo):
    result = schedule.invoke({"room_id": "Z", **RANGE})
    assert "Z" in result and "A, B, C, D, E" in result


def test_schedule_rejects_non_iso(schedule, repo):
    assert "ISO" in schedule.invoke({"room_id": "C", "start": "soon", "end": "later"})
