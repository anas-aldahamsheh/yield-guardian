"""The smoke script refuses to run in CI, without --yes or without a key (no call is made)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import respx

from tests.llm.helpers import PLACEHOLDER_KEY

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "smoke_token_factory.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_token_factory", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("environ", "argv", "message"),
    [
        ({"CI": "true", "TOKEN_FACTORY_API_KEY": PLACEHOLDER_KEY}, ["--yes"], "refusing to run in CI"),
        ({"TOKEN_FACTORY_API_KEY": PLACEHOLDER_KEY}, [], "pass --yes"),
        ({}, ["--yes"], "TOKEN_FACTORY_API_KEY is not set"),
    ],
)  # fmt: skip
def test_the_script_refuses_without_every_condition(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    respx_mock: respx.Router,
    environ: dict[str, str],
    argv: list[str],
    message: str,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("TOKEN_FACTORY_API_KEY", raising=False)
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    assert load_script().main(argv) == 2
    assert message in capsys.readouterr().err
    assert not respx_mock.calls


def test_the_writer_schema_option_sends_the_writers_exact_response_format() -> None:
    from yield_guardian.agent.writer import REPORT_SCHEMA_NAME
    from yield_guardian.contracts.investigation import Report
    from yield_guardian.llm.messages import ResponseFormat
    from yield_guardian.llm.structured import strict_json_schema

    script = load_script()
    request = script.smoke_request("writer-schema", "none")
    assert request.response_format == ResponseFormat.strict_schema(
        REPORT_SCHEMA_NAME, strict_json_schema(Report)
    )
    assert request.max_tokens == 64
    assert "JSON" in request.messages[0].text()
    assert script.smoke_request("json_object", "low").response_format == (
        ResponseFormat.json_object()
    )
    assert script.smoke_request("none", None).response_format is None


async def test_a_refused_call_prints_the_error_body(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    respx_mock: respx.Router,
) -> None:
    import httpx

    from yield_guardian.core.settings import Settings

    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", PLACEHOLDER_KEY)
    route = respx_mock.post(url__regex=r".*/chat/completions$").mock(
        return_value=httpx.Response(
            400, json={"error": {"message": "bad", "param": "reasoning_effort"}}
        )
    )
    script = load_script()
    args = script.parse_args(
        ["--yes", "--model", "MiMo-V2.6-Flash", "--effort", "low", "--response-format",
         "writer-schema"]
    )  # fmt: skip
    assert await script.run(args, Settings()) == 2
    out = capsys.readouterr()
    assert "Upper bound for this call: 0.000" in out.out
    assert 'Error body: {"error":{"message":"bad","param":"reasoning_effort"}}' in out.out
    assert route.call_count == 1
