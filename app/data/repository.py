"""The only SQL boundary. Maps rows <-> domain Booking; parameterized queries only.

Persists/retrieves only — no business validation (rules stay pure and are fed the
lists this repository returns).
"""

import sqlite3
from datetime import datetime

from app.domain.models import Booking


def _to_booking(row: sqlite3.Row) -> Booking:
    return Booking(
        id=row[0],
        room_id=row[1],
        user=row[2],
        title=row[3],
        attendees=row[4],
        start=datetime.fromisoformat(row[5]),
        end=datetime.fromisoformat(row[6]),
    )


_COLUMNS = "id, room_id, user, title, attendees, start, end"


class BookingRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def save(self, booking: Booking) -> None:
        self._conn.execute(
            f"INSERT INTO bookings ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                booking.id,
                booking.room_id,
                booking.user,
                booking.title,
                booking.attendees,
                booking.start.isoformat(),
                booking.end.isoformat(),
            ),
        )
        self._conn.commit()

    def find_by_id(self, booking_id: str) -> Booking | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM bookings WHERE id = ?", (booking_id,)
        ).fetchone()
        return _to_booking(row) if row else None

    def find_by_room(self, room_id: str) -> list[Booking]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM bookings WHERE room_id = ?", (room_id,)
        ).fetchall()
        return [_to_booking(row) for row in rows]

    def find_by_user(self, user: str) -> list[Booking]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM bookings WHERE user = ?", (user,)
        ).fetchall()
        return [_to_booking(row) for row in rows]

    def delete(self, booking_id: str) -> None:
        self._conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        self._conn.commit()
