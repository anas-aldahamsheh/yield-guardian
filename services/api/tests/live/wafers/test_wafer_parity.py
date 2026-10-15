"""Parity: the live wafer engine equals the bundle on the real demo wafers (PLAN_V2 §3.2).

- `pattern` on every demo wafer equals the bundle's load-time scores, bit for bit: both are
  `WaferModel.score` over the same maps in the same batches.
- `similar` equals the v1 similar-wafer search for every demo wafer.
- The join count reproduces the bundle's records: the statistic exactly, the permutation
  p-value within its Monte Carlo error (the bundle drew its permutations from one shared
  generator; the live test seeds each map from the map itself).
- `lots` reproduces demo/lots.json: the same counts and p-values wherever the live labels equal
  the stored ones, the same flags, the same stacked maps.
"""

import math
from collections.abc import Sequence

import numpy as np
import pytest

from tests.live.wafers.conftest import FULL_PARITY
from yield_guardian.bundles.wafermap import WafermapBundle
from yield_guardian.contracts.runs import LotItem, WaferInput, WaferPatternResult
from yield_guardian.live.wafers import ACCEPT_PRECISION_TARGET, LiveWafers, decode_map
from yield_guardian.science.wafermap.service import WaferInference

STRIDE = 1 if FULL_PARITY else 10  # join count: every demo wafer, or every 10th
SIMILAR_STRIDE = 1 if FULL_PARITY else 4
MC_SIGMAS = 6.0


def _stored_pattern(bundle: WafermapBundle) -> dict[str, str]:
    """The pattern each demo wafer was counted as in demo/lots.json."""
    return {
        w.wafer_id: "unknown" if w.unknown else w.predicted
        for lot in bundle.lots.values()
        for w in lot.wafers
    }


def _live_pattern(bundle: WafermapBundle, pattern: WaferPatternResult) -> list[str]:
    threshold = bundle.lot_reference.energy_threshold
    return [
        "unknown" if item.energy_score > threshold else item.top_label for item in pattern.wafers
    ]


def _lot_run(
    rows: Sequence[int], inputs: list[WaferInput], pattern: WaferPatternResult
) -> tuple[list[WaferInput], WaferPatternResult]:
    """The demo wafers at `rows` as a run of their own, with their live pattern items."""
    items = [pattern.wafers[r].model_copy(update={"index": k}) for k, r in enumerate(rows)]
    return [inputs[r] for r in rows], pattern.model_copy(update={"wafers": items})


# Pattern ----------------------------------------------------------------------------------------


async def test_live_pattern_equals_the_load_time_scores_on_every_demo_wafer(
    bundle: WafermapBundle, v1: WaferInference, demo_pattern: WaferPatternResult
) -> None:
    scores = bundle.scores
    assert len(demo_pattern.wafers) == len(bundle.wafers) == 10_253
    worst = 0.0
    for i, item in enumerate(demo_pattern.wafers):
        stored = await v1.get_prediction(bundle.wafers.wafer_id[i])
        assert [p.label for p in item.probabilities] == [p.label for p in stored.probabilities]
        for live, kept in zip(item.probabilities, stored.probabilities, strict=True):
            worst = max(worst, abs(live.probability - kept.probability))
        assert (
            item.top_label
            == stored.top_label
            == bundle.labels[int(scores.probabilities[i].argmax())]
        )
        assert item.top_probability == stored.top_probability
        assert item.unknown_score == stored.unknown.score == scores.mahalanobis[i]
        assert item.unknown_threshold == stored.unknown.threshold
        assert item.is_unknown == stored.unknown.is_unknown
        assert item.energy_score == stored.unknown.energy_score == scores.energy[i]
        assert item.map == v1._map(i)  # the map as processed is the bundle's map
        assert item.source_wafer == bundle.wafers.wafer_id[i]
        assert item.recorded_label == bundle.wafers.label[i]
        assert item.index == i
    assert worst == 0.0  # bit for bit: one scoring function, same batches
    assert demo_pattern.temperature == bundle.temperature


def test_auto_accept_uses_the_99_percent_precision_threshold(
    bundle: WafermapBundle, demo_pattern: WaferPatternResult
) -> None:
    (row,) = [
        a
        for a in bundle.metrics.auto_classification
        if a.precision_target == ACCEPT_PRECISION_TARGET
    ]
    assert demo_pattern.accept_threshold == row.confidence_threshold
    accepted = [item.auto_accepted for item in demo_pattern.wafers]
    assert accepted == [
        item.top_probability >= row.confidence_threshold for item in demo_pattern.wafers
    ]
    assert 0 < sum(accepted) < len(accepted)


def test_live_top_labels_agree_with_the_predictions_stored_at_build_time(
    bundle: WafermapBundle, demo_pattern: WaferPatternResult
) -> None:
    # The stored predictions come from the GPU under bf16 (bundles/wafermap.py `_parity`).
    stored = {w.wafer_id: w for lot in bundle.lots.values() for w in lot.wafers}
    top = [stored[wid].predicted for wid in bundle.wafers.wafer_id]
    agreement = np.mean(
        [item.top_label == t for item, t in zip(demo_pattern.wafers, top, strict=True)]
    )
    assert agreement == bundle.parity.top_label_agreement
    assert agreement >= 0.998


def test_the_score_of_a_wafer_barely_depends_on_its_batch(
    engine: LiveWafers, bundle: WafermapBundle
) -> None:
    # A run batches its own wafers: lot by lot, or one at a time, the float32 network gives the
    # same scores to about 1e-6 (metrics.json onnx_parity: batch of one, 2.4e-6 on the logits).
    rows = engine.lot_rows[engine.lot_names[0]] + [len(bundle.wafers) - 1]
    alone = [engine.score([bundle.wafers.grid(i)]) for i in rows[:3]]
    batch = engine.score([bundle.wafers.grid(i) for i in rows])
    for scores, picked in [(batch, rows), *zip(alone, ([i] for i in rows[:3]), strict=True)]:
        assert np.abs(scores.probabilities - bundle.scores.probabilities[picked]).max() < 1e-5
        assert np.abs(scores.embedding - bundle.scores.embedding[picked]).max() < 1e-5
        assert np.abs(scores.energy - bundle.scores.energy[picked]).max() < 1e-4
        assert np.abs(scores.mahalanobis - bundle.scores.mahalanobis[picked]).max() < 1e-2
        assert (
            scores.probabilities.argmax(1) == bundle.scores.probabilities[picked].argmax(1)
        ).all()


# Similar ----------------------------------------------------------------------------------------


async def test_similar_equals_the_v1_search_on_demo_wafers(
    engine: LiveWafers,
    v1: WaferInference,
    demo_inputs: list[WaferInput],
    demo_pattern: WaferPatternResult,
) -> None:
    rows = list(range(0, len(demo_inputs), SIMILAR_STRIDE))
    wafers, pattern = _lot_run(rows, demo_inputs, demo_pattern)
    result = engine.similar(wafers, pattern)
    assert result.searched == 10_253
    assert result.precision_at_10 == engine.bundle.metrics.similarity_precision_at_10
    for item, wafer in zip(result.wafers, wafers, strict=True):
        assert wafer.source_wafer is not None
        stored = await v1.get_similar(wafer.source_wafer, k=10)
        assert [s.wafer_id for s in item.similar] == [r.wafer.wafer_id for r in stored.results]
        assert [s.similarity for s in item.similar] == [r.similarity for r in stored.results]
        assert [s.predicted_label for s in item.similar] == [
            r.wafer.predicted_label for r in stored.results
        ]
        assert [s.recorded_label for s in item.similar] == [r.wafer.label for r in stored.results]
        assert [s.map for s in item.similar] == [r.map for r in stored.results]
        assert wafer.source_wafer not in {s.wafer_id for s in item.similar}


# Join count -------------------------------------------------------------------------------------


def test_join_count_on_demo_wafers_equals_the_bundles_records(
    engine: LiveWafers, bundle: WafermapBundle
) -> None:
    rows = list(range(0, len(bundle.wafers), STRIDE))
    live = engine.spatial([bundle.wafers.grid(i) for i in rows])
    stored = [bundle.join_count[i] for i in rows]
    permutations = bundle.permutations
    tested = agree = 0
    for j, s in zip(live, stored, strict=True):
        assert (j.bb, j.fails, j.dies) == (s.bb, s.fails, s.dies)
        assert (j.p is None) == (s.p is None)
        if j.p is None or s.p is None or j.expected is None or s.expected is None:
            continue
        tested += 1
        # Two independent estimates from `permutations` draws each: their difference has a
        # standard error of sqrt(2 p (1 - p) / (B + 1)) for the p-value, sd * sqrt(2 / B) for
        # the null mean; the 1 / (B + 1) floor is the p-value's resolution.
        p = (j.p + s.p) / 2
        assert abs(j.p - s.p) <= MC_SIGMAS * math.sqrt(2 * p * (1 - p) / (permutations + 1)) + 2 / (
            permutations + 1
        )
        assert j.sd is not None
        assert abs(j.expected - s.expected) <= MC_SIGMAS * j.sd * math.sqrt(2 / permutations) + 1e-9
        agree += (j.p < 0.05) == (s.p < 0.05)
    assert tested >= 0.99 * len(rows)
    assert agree / tested >= 0.97


def test_join_count_items_in_pattern_are_the_spatial_test(
    engine: LiveWafers, demo_inputs: list[WaferInput], bundle: WafermapBundle
) -> None:
    rows = engine.lot_rows[engine.lot_names[0]]
    result = engine.pattern([demo_inputs[i] for i in rows])
    for item, i in zip(result.wafers, rows, strict=True):
        record = bundle.join_count[i]
        if record.p is None:
            assert item.spatial is None
            continue
        assert item.spatial is not None
        assert item.spatial.statistic == record.bb
        assert item.spatial.permutations == bundle.permutations == 999
        assert item.spatial.clustered == (item.spatial.p_value < 0.05)


# Lots -------------------------------------------------------------------------------------------


def _check_against_lots_json(bundle: WafermapBundle, name: str, item: LotItem) -> None:
    record = bundle.lots[name]
    stored = {t.pattern: t for t in record.tests}
    assert item.lot == name
    assert item.wafers == len(record.wafers)
    for test in item.tests:
        kept = stored[test.label]
        assert (test.count, test.wafers, test.expected_rate) == (
            kept.count,
            kept.wafers,
            kept.expected_rate,
        )
        assert test.p_value == pytest.approx(kept.p, rel=1e-12, abs=1e-300)
        assert test.flagged == kept.flagged
    assert item.pattern_counts == {t.label: stored[t.label].count for t in item.tests}
    assert item.stacked == bundle.stacked[name]


def _hero_lot(bundle: WafermapBundle) -> str:
    """The flagged lot of the v1 home page: the defect-pattern test with the smallest q."""
    return min(
        (t.q, t.p, name)
        for name, lot in bundle.lots.items()
        for t in lot.tests
        if t.flagged and t.pattern != "unknown"
    )[2]


def _largest_unflagged_lot(bundle: WafermapBundle) -> str:
    """The unflagged lot with the most wafers (ties: lot name)."""
    return min((-len(lot.wafers), name) for name, lot in bundle.lots.items() if not lot.flagged)[1]


@pytest.mark.parametrize("rule", [_hero_lot, _largest_unflagged_lot])
def test_lots_reproduces_lots_json_on_a_real_lot(
    rule: object,
    engine: LiveWafers,
    bundle: WafermapBundle,
    demo_inputs: list[WaferInput],
    demo_pattern: WaferPatternResult,
) -> None:
    assert callable(rule)
    name = rule(bundle)
    rows = engine.lot_rows[name]
    wafers, pattern = _lot_run(rows, demo_inputs, demo_pattern)
    stored = _stored_pattern(bundle)
    live = _live_pattern(bundle, pattern)
    assert live == [stored[bundle.wafers.wafer_id[r]] for r in rows]
    result = engine.lots(wafers, pattern)
    (item,) = result.lots
    _check_against_lots_json(bundle, name, item)
    assert item.flagged == bundle.lots[name].flagged


def test_lots_over_every_demo_lot(
    engine: LiveWafers,
    bundle: WafermapBundle,
    demo_inputs: list[WaferInput],
    demo_pattern: WaferPatternResult,
) -> None:
    """One run per demo lot. p-values are compared wherever the live labels equal the stored
    ones (a label differs only where float32 and the build's bf16 disagree); a flag the bundle
    raised over its 14,472 tests is raised in a run of the lot alone too (a smaller family)."""
    stored = _stored_pattern(bundle)
    live = _live_pattern(bundle, demo_pattern)
    changed = {r for r in range(len(live)) if live[r] != stored[bundle.wafers.wafer_id[r]]}
    same = compared = flags_kept = 0
    lots = [n for n in engine.lot_names if len(engine.lot_rows[n]) >= 2]
    for name in lots:
        rows = engine.lot_rows[name]
        wafers, pattern = _lot_run(rows, demo_inputs, demo_pattern)
        (item,) = engine.lots(wafers, pattern).lots
        assert item.stacked == bundle.stacked[name]
        kept = {t.pattern: t for t in bundle.lots[name].tests}
        if changed & set(rows):
            continue
        same += 1
        for test in item.tests:
            assert test.count == kept[test.label].count
            assert test.p_value == pytest.approx(kept[test.label].p, rel=1e-12, abs=1e-300)
            compared += 1
            if kept[test.label].flagged:
                assert test.flagged
                flags_kept += 1
    assert len(lots) == 475
    assert len(changed) <= 0.005 * len(live)  # wafers near a class tie or the energy threshold
    assert same >= 0.9 * len(lots)
    assert compared == 8 * same
    assert flags_kept > 0


def test_the_lot_tests_use_the_bundles_reference(
    engine: LiveWafers, bundle: WafermapBundle
) -> None:
    ref = bundle.lot_reference
    assert ref.fdr_q == 0.05
    assert ref.lots == 1612
    assert ref.energy_threshold == pytest.approx(-2.6177380084991455)
    for lot in bundle.lots.values():
        for test in lot.tests:
            assert test.expected_rate == ref.rates[test.pattern]
    assert decode_map(engine.demo_maps[0]).shape == (
        bundle.wafers.height[0],
        bundle.wafers.width[0],
    )
