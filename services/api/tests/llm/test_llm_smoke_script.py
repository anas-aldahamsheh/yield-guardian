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
