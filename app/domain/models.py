"""Domain entities as frozen dataclasses. Data only — validation lives in rules.py.

Grouped in one file for cohesion: Room, User and Booking are the shared vocabulary
of the domain and always evolve together. Booking references its room by ``room_id``
(a str), not a ``Room`` instance, to avoid duplicating room state and to mirror the
SQLite persistence layer (foreign key by id).
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Room:
    id: str
    capacity: int


@dataclass(frozen=True)
class User:
    username: str


@dataclass(frozen=True)
class Booking:
    id: str
    room_id: str
    user: str
    title: str
    attendees: int
    start: datetime
    end: datetime
