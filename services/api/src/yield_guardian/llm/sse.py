"""Incremental Server-Sent Events parser (WHATWG HTML, "event stream interpretation").

Bytes arrive in arbitrary pieces: a line, a multi-byte UTF-8 character or a ``data:`` field
may be split across network reads, so the parser buffers and decodes incrementally. Lines
end with LF, CRLF or a lone CR; ``:`` starts a comment; consecutive ``data:`` lines join
with a newline; a blank line dispatches the event.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass, field

DONE_SENTINEL = "[DONE]"


@dataclass(frozen=True, slots=True)
class SseEvent:
    data: str
    event: str | None = None
    id: str | None = None


@dataclass(slots=True)
class SseParser:
    _decoder: codecs.IncrementalDecoder = field(
        default_factory=lambda: codecs.getincrementaldecoder("utf-8")(errors="strict")
    )
    _buffer: str = ""
    _data: list[str] = field(default_factory=list)
    _event: str | None = None
    _id: str | None = None
    _pending_cr: bool = False
    _first_line: bool = True

    def feed(self, chunk: bytes) -> list[SseEvent]:
        return self._feed_text(self._decoder.decode(chunk))

    def close(self) -> list[SseEvent]:
        """Flush at end of stream. A last event without its blank line is still dispatched
        (servers commonly omit the final blank line after ``data: [DONE]``)."""
        events = self._feed_text(self._decoder.decode(b"", final=True))
        if self._buffer:
            self._process_line(self._buffer, events)
            self._buffer = ""
        self._dispatch(events)
        return events

    def _feed_text(self, text: str) -> list[SseEvent]:
        events: list[SseEvent] = []
        if self._pending_cr and text.startswith("\n"):
            text = text[1:]
        self._pending_cr = False
        buffer = self._buffer + text
        start = 0
        index = 0
        length = len(buffer)
        while index < length:
            char = buffer[index]
            if char in "\r\n":
                self._process_line(buffer[start:index], events)
                if char == "\r":
                    if index + 1 < length:
                        if buffer[index + 1] == "\n":
                            index += 1
                    else:
                        self._pending_cr = True
                start = index + 1
            index += 1
        self._buffer = buffer[start:]
        return events

    def _process_line(self, line: str, events: list[SseEvent]) -> None:
        if self._first_line:
            self._first_line = False
            line = line.removeprefix("﻿")
        if line == "":
            self._dispatch(events)
            return
        if line.startswith(":"):
            return
        name, sep, value = line.partition(":")
        if sep:
            value = value.removeprefix(" ")
        if name == "data":
            self._data.append(value)
        elif name == "event":
            self._event = value
        elif name == "id" and "\x00" not in value:
            self._id = value

    def _dispatch(self, events: list[SseEvent]) -> None:
        if self._data:
            events.append(SseEvent(data="\n".join(self._data), event=self._event, id=self._id))
        self._data = []
        self._event = None
