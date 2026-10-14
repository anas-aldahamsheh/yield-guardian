"""RFC 6901 JSON Pointer resolution, used to find the value a report number cites."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_INDEX = re.compile(r"^(?:0|[1-9][0-9]*)$")
_MISSING = object()


class PointerError(ValueError):
    """The pointer is malformed or does not lead to a value."""


def _unescape(token: str) -> str:
    if re.search(r"~(?![01])", token):
        raise PointerError(f"invalid escape in {token!r}")
    return token.replace("~1", "/").replace("~0", "~")


def resolve(document: Any, pointer: str) -> Any:
    """The value at ``pointer`` ("" is the whole document); raises :class:`PointerError`."""
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise PointerError(f"a JSON Pointer starts with '/': {pointer!r}")
    current = document
    for raw in pointer[1:].split("/"):
        token = _unescape(raw)
        if isinstance(current, Mapping):
            current = current.get(token, _MISSING)
            if current is _MISSING:
                raise PointerError(f"no member {token!r} in {pointer!r}")
        elif isinstance(current, Sequence) and not isinstance(current, str | bytes):
            if not _INDEX.match(token):
                raise PointerError(f"{token!r} is not an array index in {pointer!r}")
            index = int(token)
            if index >= len(current):
                raise PointerError(f"index {index} is out of range in {pointer!r}")
            current = current[index]
        else:
            raise PointerError(f"{pointer!r} goes past a scalar value")
    return current
