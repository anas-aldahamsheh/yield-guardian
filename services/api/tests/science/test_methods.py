"""The methods service on the committed bundles: provenance from data/manifest.json, model cards
read from the bundles, and a results table whose numbers are the bundles' own evaluations."""

import json
from pathlib import Path

import httpx
import pytest

from tests.science.bundle_factory import DATA, REPO
from yield_guardian.api.app import create_app
from yield_guardian.bootstrap import build_registry
from yield_guardian.core.settings import Settings
from yield_guardian.services.registry import ServiceRegistry

ARTIFACTS = REPO / "artifacts"


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(
        environment="test",
        log_json=False,
        database_url=None,
        artifacts_dir=ARTIFACTS,
        secom_data_dir=DATA,
    )


@pytest.fixture(scope="module")
def registry(settings: Settings) -> ServiceRegistry:
    return build_registry(settings)


async def _get(settings: Settings, registry: ServiceRegistry, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app(settings, registry))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_results_come_from_the_loaded_bundles(
    settings: Settings, registry: ServiceRegistry
) -> None:
    response = await _get(settings, registry, "/api/v1/results")
    assert response.status_code == 200
    rows = {r["id"]: r for r in response.json()["results"]}
    assert registry.secom is not None
    metrics = await registry.secom.get_metrics()
    main = next(m for m in metrics.models if m.main)
    pr_auc = next(v for v in main.metrics if v.metric == "pr_auc")
    assert rows["secom_pr_auc"]["estimate"]["value"] == pytest.approx(pr_auc.estimate.value)
    raw = json.loads((ARTIFACTS / "secom" / "v1" / "metrics.json").read_text())
    assert "lightgbm" in raw["models"]  # the bundle's own evaluation, not a copy
    for measured in ("secom_pr_auc_no_skill", "wafer_macro_f1_lot_grouped", "unknown_auroc_loco"):
        assert rows[measured]["estimate"] is not None, measured
    # Not measured yet: no number is shown.
    assert rows["points_per_investigation"]["estimate"] is None
    assert response.json()["updated_at"] is not None


async def test_methods_lists_both_datasets_and_model_cards(
    settings: Settings, registry: ServiceRegistry
) -> None:
    body = (await _get(settings, registry, "/api/v1/methods")).json()
    assert {d["name"] for d in body["datasets"]} == {"SECOM", "WM-811K"}
    assert {c["name"] for c in body["model_cards"]} == {"secom", "wafermap"}
    assert any(text.startswith("SECOM: ") for text in body["limitations"])
    card = await _get(settings, registry, "/api/v1/methods/model-cards/wafermap")
    assert card.status_code == 200
    assert card.json()["markdown"].strip()
    assert (await _get(settings, registry, "/api/v1/methods/model-cards/nope")).status_code in (
        404,
        422,
    )


async def test_without_bundles_methods_is_not_ready(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        log_json=False,
        database_url=None,
        artifacts_dir=tmp_path,
        secom_data_dir=DATA,
    )
    response = await _get(settings, build_registry(settings), "/api/v1/results")
    assert response.status_code == 503
