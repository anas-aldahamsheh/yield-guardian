import pytest

from yield_guardian.contracts.services import InvalidArgumentError
from yield_guardian.services import cursors
from yield_guardian.services.passwords import PasswordHash, hash_password


def test_hash_round_trip_and_format() -> None:
    encoded = hash_password("a long synthetic test password")
    scheme, n, r, p, _salt, _digest = encoded.split("$")
    assert (scheme, n, r, p) == ("scrypt", "32768", "8", "1")
    parsed = PasswordHash.parse(encoded)
    assert parsed.verify("a long synthetic test password")
    assert not parsed.verify("a long synthetic test passwore")


def test_hashes_are_salted() -> None:
    assert hash_password("same") != hash_password("same")


@pytest.mark.parametrize(
    "encoded",
    [
        "",
        "bcrypt$1$2$3$c2FsdHNhbHQ$aGFzaGhhc2hoYXNoaGFzaA",
        "scrypt$32768$8$1$c2FsdHNhbHQ",
        "scrypt$1000$8$1$c2FsdHNhbHQ$aGFzaGhhc2hoYXNoaGFzaA",
        "scrypt$4194304$8$1$c2FsdHNhbHQ$aGFzaGhhc2hoYXNoaGFzaA",
        "scrypt$x$8$1$c2FsdHNhbHQ$aGFzaGhhc2hoYXNoaGFzaA",
        "scrypt$32768$8$1$YQ$aGFzaGhhc2hoYXNoaGFzaA",
    ],
)
def test_malformed_hashes_are_rejected(encoded: str) -> None:
    with pytest.raises(ValueError):
        PasswordHash.parse(encoded)


def test_cursor_round_trip() -> None:
    cursor = cursors.encode("inv", "2026-10-14T08:00:00+00:00", "inv_0123456789")
    assert cursors.decode("inv", cursor, str, str) == [
        "2026-10-14T08:00:00+00:00",
        "inv_0123456789",
    ]


@pytest.mark.parametrize(
    "cursor",
    ["", "!!!", cursors.encode("wo", "WO-000001"), cursors.encode("audit", "12"), "e30"],
)
def test_invalid_cursors(cursor: str) -> None:
    with pytest.raises(InvalidArgumentError):
        cursors.decode("audit", cursor, int)
