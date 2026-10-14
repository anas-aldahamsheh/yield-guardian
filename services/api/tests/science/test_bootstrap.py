"""Startup: the registry loads the newest verified bundle, or reports why it could not."""

from pathlib import Path

import httpx

from tests.science.bundle_factory import DATA
from yield_guardian.api.app import create_app
from yield_guardian.bootstrap import build_registry
from yield_guardian.core.settings import Settings


def _settings(artifacts: Path) -> Settings:
    return Settings(
        environment="test",
        log_json=False,
        database_url=None,
        artifacts_dir=artifacts,
        secom_data_dir=DATA,
    )


def test_the_newest_secom_bundle_is_loaded(bundle_dir: Path) -> None:
    registry = build_registry(_settings(bundle_dir.parents[1]))
    assert registry.line is not None
    assert registry.secom is not None
    assert [b.bundle.version for b in registry.bundles] == ["v1"]
    assert "secom_bundle" not in registry.problems


async def test_a_missing_bundle_is_reported_by_ready(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry = build_registry(settings)
    assert registry.line is None
    assert registry.secom is None
    assert "secom" in registry.problems["secom_bundle"]
    transport = httpx.ASGITransport(app=create_app(settings, registry))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        body = (await client.get("/api/v1/ready")).json()
    assert body["ready"] is False
    secom = next(c for c in body["checks"] if c["name"] == "secom_bundle")
    assert secom["ok"] is False
    assert secom["detail"] == registry.problems["secom_bundle"]
