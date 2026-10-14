"""Incremental SSE parsing: line endings, comments, multi-line data, splits anywhere."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from yield_guardian.llm.sse import SseEvent, SseParser


def parse_all(*chunks: bytes) -> list[SseEvent]:
    parser = SseParser()
    events: list[SseEvent] = []
    for chunk in chunks:
        events.extend(parser.feed(chunk))
    events.extend(parser.close())
    return events


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"])
def test_each_line_ending_dispatches_events(newline: bytes) -> None:
    raw = b"data: one" + newline + newline + b"data: two" + newline + newline
    assert [e.data for e in parse_all(raw)] == ["one", "two"]


def test_comments_fields_and_multiline_data() -> None:
    raw = (
        b": keep-alive comment\n"
        b"event: update\n"
        b"id: 42\n"
        b"data: first line\n"
        b"data:second line\n"
        b"unknown: ignored\n"
        b"\n"
    )
    (event,) = parse_all(raw)
    assert event == SseEvent(data="first line\nsecond line", event="update", id="42")


def test_event_type_resets_but_last_id_persists() -> None:
    events = parse_all(b"event: a\nid: 1\ndata: x\n\ndata: y\n\n")
    assert [(e.event, e.id) for e in events] == [("a", "1"), (None, "1")]


def test_blank_lines_without_data_dispatch_nothing() -> None:
    assert parse_all(b"\n\n: only a comment\n\n") == []


def test_a_bare_data_field_is_an_empty_event() -> None:
    assert [e.data for e in parse_all(b"data\n\n")] == [""]


def test_leading_byte_order_mark_is_ignored() -> None:
    assert [e.data for e in parse_all("﻿data: x\n\n".encode())] == ["x"]


def test_close_dispatches_a_final_event_without_blank_line() -> None:
    assert [e.data for e in parse_all(b"data: [DONE]")] == ["[DONE]"]
    assert [e.data for e in parse_all(b"data: [DONE]\n")] == ["[DONE]"]


def test_crlf_split_between_reads_is_one_line_ending() -> None:
    events = parse_all(b"data: a\r", b"\n\r", b"\ndata: b\r\n\r\n")
    assert [e.data for e in events] == ["a", "b"]


def test_multibyte_character_split_across_reads() -> None:
    raw = "data: T² ≥ limit\n\n".encode()
    cut = raw.index("²".encode()) + 1  # inside the two-byte character
    assert [e.data for e in parse_all(raw[:cut], raw[cut:])] == ["T² ≥ limit"]


def test_invalid_utf8_is_an_error_not_silently_replaced() -> None:
    with pytest.raises(UnicodeDecodeError):
        parse_all(b"data: \xff\xfe\n\n")


_payloads = st.lists(
    st.text(
        alphabet=st.characters(codec="utf-8", exclude_characters="\r\n"),
        max_size=30,
    ),
    min_size=1,
    max_size=6,
)


@settings(max_examples=200, deadline=None)
@given(
    payloads=_payloads,
    newline=st.sampled_from(["\n", "\r\n", "\r"]),
    cuts=st.lists(st.integers(min_value=0, max_value=400), max_size=12),
)
def test_splitting_the_byte_stream_anywhere_gives_the_same_events(
    payloads: list[str], newline: str, cuts: list[int]
) -> None:
    raw = "".join(f"data: {p}{newline}{newline}" for p in payloads).encode()
    points = sorted({min(c, len(raw)) for c in cuts})
    pieces = [raw[a:b] for a, b in zip([0, *points], [*points, len(raw)], strict=True)]
    whole = parse_all(raw)
    assert [e.data for e in parse_all(*pieces)] == [e.data for e in whole]
    # Only the one space after "data:" is removed; the payload is otherwise kept as sent.
    assert [e.data for e in whole] == payloads
