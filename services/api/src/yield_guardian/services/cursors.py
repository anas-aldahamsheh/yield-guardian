"""Opaque pagination cursors: base64url of a JSON array `[kind, *position]`.

The position is the sort key of the last item on the page, so pages stay stable while new items
arrive. A cursor of another list, or one that does not decode, is an invalid argument.
"""

import base64
import binascii
import json

from yield_guardian.contracts.services import InvalidArgumentError

Position = list[str | int]


def encode(kind: str, *position: str | int) -> str:
    raw = json.dumps([kind, *position], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(kind: str, cursor: str, *types: type[str] | type[int]) -> Position:
    """The position in `cursor`, checked against the expected kind and element types."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(raw)
    except (binascii.Error, ValueError) as exc:
        raise InvalidArgumentError("The cursor is not valid.") from exc
    if (
        not isinstance(value, list)
        or len(value) != len(types) + 1
        or value[0] != kind
        or not all(type(item) is expected for item, expected in zip(value[1:], types, strict=True))
    ):
        raise InvalidArgumentError("The cursor is not valid for this list.")
    position: Position = value[1:]
    return position
