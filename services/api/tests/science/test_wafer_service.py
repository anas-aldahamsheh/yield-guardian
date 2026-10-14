"""WaferService on the real wafer-map bundle: maps, predictions, the Mahalanobis unknown score,
similar wafers, lots, metrics, the hero wafer and 404s."""

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest

from yield_guardian.api.app import create_app
from yield_guardian.bundles.wafermap import WafermapBundle
from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError
from yield_guardian.core.settings import Settings
from yield_guardian.science.wafermap.service import HERO_RULE, WaferInference
from yield_guardian.services.registry import ServiceRegistry


def _json(directory: Path, name: str) -> Any:
    return json.loads((directory / name).read_text(encoding="utf-8"))


# Wafers and predictions -----------------------------------------------------------------------


async def test_a_wafer_has_its_real_map_and_attribution(
    wafers: WaferInference, wafermap_bundle: WafermapBundle
) -> None:
    detail = await wafers.get_wafer("lot534-1")
    w = detail.wafer
    assert (w.lot, w.wafer_index, w.height, w.width) == ("lot534", 1, 37, 55)
    assert w.label == "Edge-Loc"
    assert w.official_split == "training"
    cells = base64.b64decode(detail.map.cells)
    assert cells == wafermap_bundle.wafers.maps[wafermap_bundle.wafers.index_of["lot534-1"]]
    assert len(cells) == 37 * 55
    assert set(cells) <= {0, 1, 2}
    assert "WM-811K" in detail.attribution
    assert "Wu" in detail.attribution


async def test_predictions_are_calibrated_and_sorted(
    wafers: WaferInference, wafermap_bundle: WafermapBundle, wafermap_dir: Path
) -> None:
    prediction = await wafers.get_prediction("lot534-1")
    probabilities = [p.probability for p in prediction.probabilities]
    assert probabilities == sorted(probabilities, reverse=True)
    assert sum(probabilities) == pytest.approx(1.0)
    assert prediction.top_label == prediction.probabilities[0].label
    assert prediction.temperature == _json(wafermap_dir, "calibration.json")["temperature"]
    assert prediction.model == wafermap_bundle.bundle.info.bundle


async def test_the_unknown_score_is_mahalanobis_with_the_validation_threshold(
    wafers: WaferInference, wafermap_bundle: WafermapBundle, wafermap_dir: Path
) -> None:
    ood = _json(wafermap_dir, "ood.json")["mahalanobis"]
    with np.load(wafermap_dir / "ood_mahalanobis.npz") as params:
        means, precision = params["class_means"], params["precision"]
    scores = wafermap_bundle.scores
    for wafer_id in ("lot534-1", "lot534-3", wafermap_bundle.wafers.wafer_id[-1]):
        i = wafermap_bundle.wafers.index_of[wafer_id]
        z = scores.embedding[i].astype(np.float64)
        expected = min(float((z - mu) @ precision @ (z - mu)) for mu in means)
        unknown = (await wafers.get_prediction(wafer_id)).unknown
        assert unknown.method == "mahalanobis"
        assert unknown.threshold_set_on == "validation"
        assert unknown.threshold == ood["threshold"]
        assert unknown.in_distribution_recall == ood["in_distribution_recall_validation"]
        assert unknown.score == pytest.approx(expected, rel=1e-6)
        assert unknown.is_unknown == (unknown.score > ood["threshold"])
        assert unknown.energy_score is not None
    flags = scores.mahalanobis > ood["threshold"]
    assert np.array_equal(scores.is_unknown, flags)
    assert 0 < flags.sum() < len(flags)


async def test_wafer_lists_filter_and_page(
    wafers: WaferInference, wafermap_bundle: WafermapBundle
) -> None:
    seen: list[str] = []
    cursor = None
    while True:
        page = await wafers.list_wafers(cursor=cursor, limit=4000)
        seen += [w.wafer_id for w in page.items]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == wafermap_bundle.wafers.wafer_id
    assert page.total == len(seen) == len(set(seen))

    lot = await wafers.list_wafers(lot="lot534")
    assert lot.total == len(lot.items) > 0
    assert all(w.lot == "lot534" for w in lot.items)
    assert [w.wafer_index for w in lot.items] == sorted(w.wafer_index for w in lot.items)
    scratch = await wafers.list_wafers(label="Scratch", limit=500)
    assert scratch.total == sum(lab == "Scratch" for lab in wafermap_bundle.wafers.label)
    unknown = await wafers.list_wafers(unknown=True, limit=500)
    assert unknown.total == int(wafermap_bundle.scores.is_unknown.sum())
    assert all(w.unknown for w in unknown.items)
    assert (await wafers.list_wafers(lot="lot0")).total == 0
    with pytest.raises(InvalidArgumentError):
        await wafers.list_wafers(cursor="not-a-cursor")


# Similar wafers -------------------------------------------------------------------------------


async def test_similar_wafers_exclude_the_query_and_rank_by_cosine(
    wafers: WaferInference, wafermap_bundle: WafermapBundle
) -> None:
    query = "lot534-1"
    result = await wafers.get_similar(query, k=10)
    ids = [r.wafer.wafer_id for r in result.results]
    assert query not in ids
    assert len(ids) == result.k == 10
    similarities = [r.similarity for r in result.results]
    assert similarities == sorted(similarities, reverse=True)

    embedding = wafermap_bundle.scores.embedding.astype(np.float64)
    i = wafermap_bundle.wafers.index_of[query]
    cosine = (
        embedding @ embedding[i] / np.linalg.norm(embedding, axis=1) / np.linalg.norm(embedding[i])
    )
    cosine[i] = -np.inf
    expected = [wafermap_bundle.wafers.wafer_id[j] for j in np.argsort(-cosine, kind="stable")[:10]]
    assert ids == expected
    for r in result.results:
        j = wafermap_bundle.wafers.index_of[r.wafer.wafer_id]
        assert r.similarity == pytest.approx(cosine[j], abs=1e-5)
    assert "query wafer is excluded" in result.method
    assert result.precision_at_10 == (await wafers.get_metrics()).similarity_precision_at_10


async def test_the_query_is_excluded_for_any_k(wafers: WaferInference) -> None:
    result = await wafers.get_similar("lot534-2", k=50)
    ids = [r.wafer.wafer_id for r in result.results]
    assert "lot534-2" not in ids
    assert len(ids) == len(set(ids)) == 50
    with pytest.raises(InvalidArgumentError):
        await wafers.get_similar("lot534-2", k=0)


# Lots -----------------------------------------------------------------------------------------


async def test_a_lot_has_its_tests_and_stacked_map(
    wafers: WaferInference, wafermap_dir: Path
) -> None:
    raw = _json(wafermap_dir, "demo/lots.json")
    name = "lot10291"
    lot = await wafers.get_lot(name)
    record = raw[name]
    assert [w.wafer_id for w in lot.wafers] == [w["wafer_id"] for w in record["wafers"]]
    defect = [t for t in record["tests"] if t["pattern"] != "unknown"]
    assert [(t.label, t.count, t.p_value, t.q_value, t.flagged) for t in lot.tests] == [
        (t["pattern"], t["count"], t["p"], t["q"], t["flagged"]) for t in defect
    ]
    assert lot.stacked is not None
    stacked = record["stacked_failure_map"]
    assert (lot.stacked.height, lot.stacked.width, lot.stacked.wafers) == (
        stacked["height"],
        stacked["width"],
        len(record["wafers"]),
    )
    assert lot.stacked.frequencies == [None if f == -1 else f for f in stacked["fail_frequency"]]
    assert None in lot.stacked.frequencies
    assert "Mahalanobis" in lot.method
    assert "energy" in lot.method


async def test_lots_with_wafers_of_different_shapes_have_no_stacked_map(
    wafers: WaferInference, wafermap_dir: Path
) -> None:
    raw = _json(wafermap_dir, "demo/lots.json")
    mixed = [n for n, v in raw.items() if v["stacked_failure_map"]["height"] is None]
    assert mixed
    for name in mixed:
        assert (await wafers.get_lot(name)).stacked is None


async def test_lot_lists_report_the_defect_pattern_flags(
    wafers: WaferInference, wafermap_dir: Path
) -> None:
    raw = _json(wafermap_dir, "demo/lots.json")
    everything = await wafers.list_lots(limit=1000)
    assert everything.total == len(raw) == len(everything.items)
    assert [lot.lot for lot in everything.items] == sorted(raw)
    flagged = {
        n
        for n, v in raw.items()
        if any(t["flagged"] and t["pattern"] != "unknown" for t in v["tests"])
    }
    page = await wafers.list_lots(flagged_only=True, limit=1000)
    assert {lot.lot for lot in page.items} == flagged
    assert all(lot.flagged_labels for lot in page.items)
    first = await wafers.list_lots(limit=100)
    second = await wafers.list_lots(limit=100, cursor=first.next_cursor)
    assert first.items[-1].lot < second.items[0].lot
    summary = next(lot for lot in everything.items if lot.lot == "lot10291")
    assert summary.wafers == 22
    assert summary.labelled == sum(isinstance(w["label"], str) for w in raw["lot10291"]["wafers"])
    assert summary.flagged_labels == ["Center"]


# Metrics --------------------------------------------------------------------------------------


async def test_metrics_are_the_measured_values(
    wafers: WaferInference, wafermap_dir: Path, wafermap_bundle: WafermapBundle
) -> None:
    raw = _json(wafermap_dir, "metrics.json")
    metrics = await wafers.get_metrics()
    assert metrics.bundle == wafermap_bundle.bundle.info.bundle
    lot = next(s for s in metrics.splits if s.split == "lot_grouped")
    deployed = raw["lot_split"]["seeds"]["1"]["test"]
    assert raw["deployed_model"] == "lot-seed1"
    assert lot.macro_f1.value == deployed["macro_f1"]["value"]
    assert (lot.macro_f1.ci_low, lot.macro_f1.ci_high) == (
        deployed["macro_f1"]["ci_low"],
        deployed["macro_f1"]["ci_high"],
    )
    assert lot.seed_mean == raw["lot_split"]["across_seeds"]["macro_f1"]["mean"]
    assert [s.seed for s in lot.seeds] == [0, 1, 2]
    assert lot.lots_in_both == 0
    center = next(c for c in lot.per_class if c.label == "Center")
    assert center.support == 643
    assert center.f1.value == deployed["per_class"]["Center"]["f1"]["value"]
    assert lot.confusion.counts == deployed["confusion_matrix"]["rows_true_cols_pred"]

    official = next(s for s in metrics.splits if s.split == "official")
    assert official.test_wafers == raw["official_split"]["test_wafers"]
    assert all(b.seeds == [] and b.seed_mean is None for b in metrics.baseline)
    assert {b.split for b in metrics.baseline} == {"lot_grouped", "official"}

    ood = metrics.ood
    assert ood.method == "mahalanobis"
    assert ood.threshold == _json(wafermap_dir, "ood.json")["mahalanobis"]["threshold"]
    assert ood.threshold_set_on == "validation"
    assert ood.mean_auroc is not None
    assert ood.energy_mean_auroc is not None
    assert ood.mean_auroc.value == raw["leave_one_class_out"]["mean_auroc_mahalanobis"]
    assert ood.energy_mean_auroc.value == raw["leave_one_class_out"]["mean_auroc_energy"]
    assert ood.mean_auroc.ci_low is None
    assert ood.mean_auroc.note
    assert len(ood.leave_one_class_out) == 8
    donut = next(x for x in ood.leave_one_class_out if x.held_out == "Donut")
    assert (
        donut.auroc.value
        == raw["leave_one_class_out"]["classes"]["Donut"]["mahalanobis"]["auroc"]["value"]
    )

    assert metrics.calibration.ece_before.ci_low is None
    assert [a.precision_target for a in metrics.auto_classification] == [0.95, 0.99]
    sim = raw["similarity"]["lot"]["seeds"]["1"]["all_neighbours"]["macro_precision_at_10"]
    assert metrics.similarity_precision_at_10.value == sim["value"]
    assert metrics.published == []
    assert any("label noise" in item for item in metrics.limitations)


# Hero -----------------------------------------------------------------------------------------


async def test_the_hero_is_a_real_wafer_chosen_by_a_fixed_rule(wafers: WaferInference) -> None:
    hero = await wafers.get_hero()
    assert hero.selection == HERO_RULE
    assert (await wafers.get_hero()) == hero
    assert hero.prediction is not None
    assert not hero.prediction.unknown.is_unknown
    pattern = hero.prediction.top_label
    lot = await wafers.get_lot(hero.wafer.lot)
    test = next(t for t in lot.tests if t.label == pattern)
    assert test.flagged
    every = [t for n in wafers.lot_names for t in wafers.tests[n] if t.flagged]
    assert test.q_value == min(t.q_value for t in every)
    assert WaferInference(wafers.bundle).hero_row == wafers.hero_row


# Not found ------------------------------------------------------------------------------------


async def test_unknown_ids_are_not_found(wafers: WaferInference) -> None:
    for call in (
        wafers.get_wafer("lot0-1"),
        wafers.get_prediction("lot534-99"),
        wafers.get_similar("lot0-1"),
        wafers.get_lot("lot0"),
    ):
        with pytest.raises(NotFoundError):
            await call


async def test_the_routes_answer_404_and_200(wafers: WaferInference) -> None:
    settings = Settings(environment="test", log_json=False)
    app = create_app(settings, ServiceRegistry(settings=settings, wafer=wafers))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/api/v1/wafers/lot0-1", "/api/v1/wafers/lot0-1/similar", "/api/v1/lots/lot0"):
            response = await client.get(path)
            assert response.status_code == 404, path
            assert response.headers["content-type"] == "application/problem+json"
        ok = await client.get("/api/v1/wafers/lot534-1/prediction")
        assert ok.status_code == 200
        assert ok.json()["unknown"]["method"] == "mahalanobis"
        assert (await client.get("/api/v1/wafers/hero")).status_code == 200
        assert (await client.get("/api/v1/methods/wafermap")).status_code == 200
