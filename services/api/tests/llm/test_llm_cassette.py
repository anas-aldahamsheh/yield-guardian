"""Cassettes: every fixture is hand-authored and loads; replay is strict; record needs a key."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tests.llm.helpers import FIXTURES, PLACEHOLDER_KEY, load_cassette
from yield_guardian.llm.cassette import (
    Cassette,
    CassetteMeta,
    CassettePlayer,
    RecordedResponse,
    RecordingTransport,
    cassette_mode,
)
from yield_guardian.llm.errors import CassetteError

ALL_FIXTURES = sorted(FIXTURES.glob("*.json"))


def test_the_fixture_folder_is_not_empty() -> None:
    assert len(ALL_FIXTURES) >= 13


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.name)
def test_every_fixture_is_a_valid_hand_authored_cassette(path: Path) -> None:
    cassette = Cassette.load(path)
    assert cassette.meta.hand_authored is True
    assert cassette.meta.recorded_at is None
    assert cassette.meta.source
    assert cassette.interactions
    readme = (FIXTURES / "README.md").read_text(encoding="utf-8")
    assert path.name in readme or path.name.startswith("investigation_")


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.name)
def test_no_fixture_contains_anything_like_a_real_key(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "Bearer " not in text
    assert '"authorization"' not in text.lower()


def request(method: str, path: str, body: object | None = None) -> httpx.Request:
    content = json.dumps(body).encode() if body is not None else b""
    return httpx.Request(method, f"https://fixture.invalid/v1{path}", content=content)


def test_player_serves_in_order_and_checks_method_path_and_pinned_fields() -> None:
    player = CassettePlayer(load_cassette("structured_fallback"))
    with pytest.raises(CassetteError, match="reasoning_effort"):
        player(request("POST", "/chat/completions", {"model": "Qwen3.8-Flash-Next"}))
    player = CassettePlayer(load_cassette("structured_fallback"))
    with pytest.raises(CassetteError, match="does not match"):
        player(request("GET", "/chat/completions"))
    player = CassettePlayer(load_cassette("catalog_and_usage"))
    assert player(request("GET", "/models")).status_code == 200
    assert player.remaining == 1
    with pytest.raises(CassetteError, match="not used"):
        player.assert_done()
    player(request("GET", "/usage"))
    with pytest.raises(CassetteError, match="cassette done"):
        player(request("GET", "/usage"))


def test_pinned_fields_need_a_json_body() -> None:
    player = CassettePlayer(load_cassette("ocr_mineru"))
    with pytest.raises(CassetteError, match="not JSON"):
        player(request("POST", "/ocr"))


def test_a_response_has_at_most_one_body() -> None:
    with pytest.raises(ValueError, match="at most one"):
        RecordedResponse(status=200, json_body={"a": 1}, text="a")
    sse = RecordedResponse(status=200, sse=["{}", "[DONE]"])
    assert sse.body_bytes() == b"data: {}\n\ndata: [DONE]\n\n"
    assert sse.content_type() == "text/event-stream"


@pytest.mark.parametrize(
    ("environ", "mode"),
    [({}, "replay"), ({"YG_LLM_CASSETTE_MODE": "replay"}, "replay"), ({"YG_LLM_CASSETTE_MODE": " "}, "replay")],
)  # fmt: skip
def test_replay_is_the_default(environ: dict[str, str], mode: str) -> None:
    assert cassette_mode(environ) == mode


def test_record_mode_needs_the_key_and_a_known_value() -> None:
    with pytest.raises(CassetteError, match="needs TOKEN_FACTORY_API_KEY"):
        cassette_mode({"YG_LLM_CASSETTE_MODE": "record"})
    with pytest.raises(CassetteError, match="must be"):
        cassette_mode({"YG_LLM_CASSETTE_MODE": "live"})
    assert (
        cassette_mode({"YG_LLM_CASSETTE_MODE": "record", "TOKEN_FACTORY_API_KEY": PLACEHOLDER_KEY})
        == "record"
    )


async def test_recording_transport_redacts_credentials_and_marks_the_cassette() -> None:
    def upstream(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == f"Bearer {PLACEHOLDER_KEY}"
        return httpx.Response(
            200,
            headers={"set-cookie": "session=secret", "x-ratelimit-remaining-requests": "5"},
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    cassette = Cassette(
        meta=CassetteMeta(hand_authored=True, description="test", source="test"), interactions=[]
    )
    transport = RecordingTransport(httpx.MockTransport(upstream), cassette)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.post(
            "https://fixture.invalid/v1/chat/completions",
            json={"model": "GLM-5.3-Flash", "messages": []},
            headers={"Authorization": f"Bearer {PLACEHOLDER_KEY}"},
        )
    assert response.json()["choices"][0]["message"]["content"] == "ok"
    (interaction,) = cassette.interactions
    assert interaction.request.match == {"model": "GLM-5.3-Flash"}
    assert "set-cookie" not in interaction.response.headers
    assert interaction.response.headers["x-ratelimit-remaining-requests"] == "5"
    assert interaction.response.json_body == {"choices": [{"message": {"content": "ok"}}]}
    assert cassette.meta.hand_authored is False
    assert cassette.meta.recorded_at is not None
    assert PLACEHOLDER_KEY not in cassette.model_dump_json()


async def test_recording_transport_keeps_stream_payloads() -> None:
    def upstream(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b'data: {"choices":[]}\n\ndata: [DONE]\n\n',
        )

    cassette = Cassette(
        meta=CassetteMeta(hand_authored=True, description="t", source="t"), interactions=[]
    )
    async with httpx.AsyncClient(
        transport=RecordingTransport(httpx.MockTransport(upstream), cassette)
    ) as client:
        await client.post("https://fixture.invalid/v1/chat/completions", json={"model": "m"})
    assert cassette.interactions[0].response.sse == ['{"choices":[]}', "[DONE]"]


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    original = load_cassette("error_shapes")
    target = tmp_path / "copy.json"
    original.save(target)
    assert Cassette.load(target) == original
