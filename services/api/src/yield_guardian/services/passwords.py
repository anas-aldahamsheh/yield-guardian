"""scrypt password hashes for the admin account.

Format: `scrypt$<n>$<r>$<p>$<salt>$<hash>`, with salt (16 bytes) and hash (32 bytes) in unpadded
base64url. Produce one with `uv run python scripts/hash_password.py`.
"""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

N = 2**15
R = 8
P = 1
SALT_BYTES = 16
HASH_BYTES = 32
MAX_N = 2**20


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, dklen=length, maxmem=256 * n * r + 2**20
    )


@dataclass(frozen=True, slots=True)
class PasswordHash:
    n: int
    r: int
    p: int
    salt: bytes
    digest: bytes

    @classmethod
    def parse(cls, encoded: str) -> "PasswordHash":
        """Parse a stored hash; ValueError when it is not in the documented format."""
        parts = encoded.strip().split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            raise ValueError("Expected scrypt$<n>$<r>$<p>$<salt>$<hash>.")
        try:
            n, r, p = (int(x) for x in parts[1:4])
            salt, digest = _unb64(parts[4]), _unb64(parts[5])
        except ValueError as exc:
            raise ValueError("The scrypt parameters or base64 fields are malformed.") from exc
        if n < 2 or n > MAX_N or n & (n - 1) or not 1 <= r <= 32 or not 1 <= p <= 16:
            raise ValueError("The scrypt parameters are out of range.")
        if len(salt) < 8 or len(digest) < 16:
            raise ValueError("The salt or hash is too short.")
        return cls(n=n, r=r, p=p, salt=salt, digest=digest)

    def verify(self, password: str) -> bool:
        """Constant-time comparison of the password's scrypt digest with the stored one."""
        candidate = _scrypt(password, self.salt, self.n, self.r, self.p, len(self.digest))
        return hmac.compare_digest(candidate, self.digest)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, N, R, P, HASH_BYTES)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"
