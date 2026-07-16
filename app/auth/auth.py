"""Login for the two fixed users. bcrypt only — no JWT, sessions or roles.

The two users are defined in code (the brief fixes them as immutable), so they are
configuration, not mutable DB data. The shared password is hashed with bcrypt at
module load; the plaintext is never persisted or logged.
"""

import bcrypt

from app.domain.models import User

_PASSWORD = "TechnicalChallengePromtior"

# Hashed at import; the plaintext constant above is only used to derive these and
# is never stored. Case-sensitive usernames (dict keys).
_CREDENTIALS: dict[str, bytes] = {
    username: bcrypt.hashpw(_PASSWORD.encode(), bcrypt.gensalt())
    for username in ("User1", "User2")
}


class AuthError(Exception):
    """Raised on any failed login — generic to avoid user enumeration."""


def verify_password(password: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(password.encode(), hashed)


def authenticate(username: str, password: str) -> User:
    stored = _CREDENTIALS.get(username)
    # Same error whether the user is unknown or the password is wrong.
    if stored is None or not verify_password(password, stored):
        raise AuthError("Invalid username or password.")
    return User(username=username)
