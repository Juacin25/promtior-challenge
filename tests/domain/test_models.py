from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from app.domain.models import Booking, Room, User


def test_room_construction_and_types():
    room = Room(id="A", capacity=10)
    assert room.id == "A"
    assert room.capacity == 10


def test_user_construction():
    user = User(username="User1")
    assert user.username == "User1"


def test_booking_construction_references_room_by_id():
    start = datetime(2026, 7, 17, 9, 0)
    end = datetime(2026, 7, 17, 9, 30)
    booking = Booking(
        id="b1",
        room_id="A",
        user="User1",
        title="Standup",
        attendees=3,
        start=start,
        end=end,
    )
    assert booking.id == "b1"
    assert booking.room_id == "A"
    assert booking.user == "User1"
    assert booking.title == "Standup"
    assert booking.attendees == 3
    assert booking.start == start
    assert booking.end == end


def test_value_equality():
    assert Room(id="B", capacity=4) == Room(id="B", capacity=4)
    assert User(username="User2") == User(username="User2")
    start, end = datetime(2026, 7, 17, 9, 0), datetime(2026, 7, 17, 9, 30)
    assert Booking("b1", "A", "User1", "T", 3, start, end) == Booking(
        "b1", "A", "User1", "T", 3, start, end
    )
    assert Room(id="A", capacity=1) != Room(id="A", capacity=2)


@pytest.mark.parametrize(
    "entity",
    [
        Room(id="A", capacity=10),
        User(username="User1"),
        Booking(
            "b1",
            "A",
            "User1",
            "T",
            3,
            datetime(2026, 7, 17, 9, 0),
            datetime(2026, 7, 17, 9, 30),
        ),
    ],
)
def test_immutable(entity):
    with pytest.raises(FrozenInstanceError):
        entity.__setattr__("id", "mutated")
