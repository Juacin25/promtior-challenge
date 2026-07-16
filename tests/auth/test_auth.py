import pytest

from app.auth.auth import _CREDENTIALS, AuthError, authenticate, verify_password
from app.domain.models import User

PASSWORD = "TechnicalChallengePromtior"


@pytest.mark.parametrize("username", ["User1", "User2"])
def test_correct_credentials_return_user(username):
    result = authenticate(username, PASSWORD)
    assert result == User(username=username)


def test_wrong_password_raises_auth_error():
    with pytest.raises(AuthError):
        authenticate("User1", "wrong")


def test_unknown_username_raises_auth_error():
    with pytest.raises(AuthError):
        authenticate("Nobody", PASSWORD)


def test_same_generic_error_for_unknown_user_and_wrong_password():
    with pytest.raises(AuthError) as wrong_pw:
        authenticate("User1", "wrong")
    with pytest.raises(AuthError) as unknown:
        authenticate("Nobody", PASSWORD)
    assert str(wrong_pw.value) == str(unknown.value)


def test_username_is_case_sensitive():
    with pytest.raises(AuthError):
        authenticate("user1", PASSWORD)
    assert authenticate("User1", PASSWORD) == User(username="User1")


def test_stored_credential_is_bcrypt_hash_not_plaintext():
    for stored in _CREDENTIALS.values():
        assert PASSWORD.encode() != stored
        assert PASSWORD not in stored.decode()
        assert stored.startswith(b"$2")  # bcrypt hash prefix


def test_verify_password_helper():
    assert verify_password(PASSWORD, _CREDENTIALS["User1"]) is True
    assert verify_password("wrong", _CREDENTIALS["User1"]) is False
