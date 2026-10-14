"""Print an scrypt hash for ADMIN_PASSWORD_HASH.

Usage (from services/api): `uv run python scripts/hash_password.py`. The password is read without
echo and asked twice; when stdin is not a terminal, its first line is read instead. The output has
the format `scrypt$<n>$<r>$<p>$<salt>$<hash>` (unpadded base64url salt and hash). Use a long
random password: the product has no login attempt limits (PLAN D-009).
"""

import getpass
import sys

from yield_guardian.services.passwords import hash_password

MIN_LENGTH = 16


def read_password() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Admin password: ")
    if getpass.getpass("Again: ") != first:
        sys.exit("The passwords do not match.")
    return first


def main() -> None:
    password = read_password()
    if len(password) < MIN_LENGTH:
        sys.exit(f"Use at least {MIN_LENGTH} characters.")
    print(hash_password(password))


if __name__ == "__main__":
    main()
