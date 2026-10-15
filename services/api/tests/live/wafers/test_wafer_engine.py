"""The live wafer engine on new maps: a real wafer redrawn as a file, a drawing on a real die
layout, a map unlike any class, any size; and the real inputs it takes from the demo set.

Maps built here (the drawn ring, the checkerboard, the random maps) are test inputs and say so;
nothing computed from them is reported.
"""

import base64
import random
import time

import numpy as np
import numpy.typing as npt
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.live.wafers.test_wafer_file import csv_file, die_rows, xlsx_file
from yield_guardian.bundles.wafermap import WafermapBundle
from yield_guardian.contracts.runs import DrawLayoutItem, WaferInput
from yield_guardian.contracts.services import NotFoundError
from yield_guardian.contracts.wafer import WaferMap
from yield_guardian.live.protocols import NeedsInput
from yield_guardian.live.wafer_file import WaferDieFile
from yield_guardian.live.wafer_stats import benjamini_hochberg
from yield_guardian.live.wafers import (
    NEEDS_LOT,
    NEEDS_WAFERS,
    LiveWafers,
    MapError,
    decode_map,
    encode_map,
)


def _input(grid: np.ndarray, lot: str = "T1", wafer: int = 1) -> WaferInput:
    return WaferInput(lot=lot, wafer=wafer, map=encode_map(grid.astype(np.uint8)))


def _edge_ring_wafer(bundle: WafermapBundle) -> int:
    """Rule: the demo wafer recorded as Edge-Ring that the bundle scores as Edge-Ring with the
    highest probability (ties: demo order)."""
    c = bundle.labels.index("Edge-Ring")
    p = bundle.scores.probabilities
    rows = [
        i
        for i in range(len(bundle.wafers))
        if bundle.wafers.label[i] == "Edge-Ring" and p[i].argmax() == c
    ]
    return min(rows, key=lambda i: (-p[i, c], i))


# A real wafer, redrawn ------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["csv", "xlsx"])
def test_a_real_edge_ring_wafer_redrawn_as_die_rows_is_edge_ring(
    engine: LiveWafers, bundle: WafermapBundle, kind: str
) -> None:
    i = _edge_ring_wafer(bundle)
    rows = die_rows("T1", 1, bundle.wafers.grid(i))
    data = csv_file(rows) if kind == "csv" else xlsx_file(rows)
    parsed = WaferDieFile().parse(data, f"ring.{kind}")
    assert parsed.issues == []
    result = engine.pattern(parsed.items)
    (item,) = result.wafers
    assert item.top_label == "Edge-Ring"
    assert item.map == engine.demo_maps[i]
    assert item.source_wafer is None
    assert item.recorded_label is None
    live = {p.label: p.probability for p in item.probabilities}
    for c, label in enumerate(bundle.labels):
        # Scored alone, not in the bundle's batch of 64: float32 agrees to about 1e-6.
        assert live[label] == pytest.approx(bundle.scores.probabilities[i, c], abs=1e-5)
    assert item.unknown_score == pytest.approx(bundle.scores.mahalanobis[i], abs=1e-2)
    assert not item.is_unknown
    assert item.spatial is not None
    assert item.spatial.statistic == bundle.join_count[i].bb


def _outer_ring(die: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
    """The dies on the wafer's edge: a rook neighbour is a no-die cell or off the map."""
    padded = np.pad(die, 1, constant_values=False)
    core = padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    ring: npt.NDArray[np.bool_] = die & ~core
    return ring


def test_a_ring_drawn_on_each_real_layout_is_edge_ring(engine: LiveWafers) -> None:
    # Test-built drawings: on each real die layout offered for drawing, the user paints the
    # outermost ring of dies as failing.
    for layout in engine.draw_layouts():
        drawn = decode_map(layout.map).copy()
        drawn[_outer_ring(drawn > 0)] = 2
        (item,) = engine.pattern([_input(drawn)]).wafers
        assert item.top_label == "Edge-Ring", layout.layout_id
        assert not item.is_unknown, layout.layout_id
        assert item.auto_accepted, layout.layout_id
        assert item.spatial is not None
        assert item.spatial.clustered


def test_a_map_far_from_every_class_is_unknown(engine: LiveWafers) -> None:
    # Test-built map: a 40 x 40 square with no edge (no "no die" cell) and a checkerboard of
    # pass and fail dies, nothing like a wafer.
    yy, xx = np.mgrid[:40, :40]
    checker = np.where((yy + xx) % 2 == 0, 2, 1)
    (item,) = engine.pattern([_input(checker)]).wafers
    assert item.is_unknown
    assert item.unknown_score > item.unknown_threshold
    assert item.spatial is not None
    assert not item.spatial.clustered  # a checkerboard has no fail-fail neighbours at all
    assert item.spatial.statistic == 0


@pytest.mark.parametrize(
    ("h", "w"), [(3, 3), (3, 512), (512, 3), (64, 64), (65, 63), (211, 97), (512, 512)]
)
def test_any_size_from_3x3_to_512x512_scores(engine: LiveWafers, h: int, w: int) -> None:
    grid = np.random.default_rng(h * 1000 + w).integers(0, 3, size=(h, w))  # test-only map
    grid[0, 0] = 2
    (item,) = engine.pattern([_input(grid)]).wafers
    assert item.map.height == h
    assert item.map.width == w
    assert sum(p.probability for p in item.probabilities) == pytest.approx(1.0)
    assert item.spatial is not None


@settings(
    deadline=None, max_examples=25, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    h=st.integers(1, 90),
    w=st.integers(1, 90),
    seed=st.integers(0, 2**32 - 1),
    share=st.floats(0.0, 1.0),
)
def test_random_maps_of_any_shape_score(
    engine: LiveWafers, h: int, w: int, seed: int, share: float
) -> None:
    rng = np.random.default_rng(seed)  # test-only map
    die = rng.random((h, w)) < 0.8
    die[rng.integers(h), rng.integers(w)] = True
    grid = np.where(die, np.where(rng.random((h, w)) < share, 2, 1), 0)
    result = engine.pattern([_input(grid), _input(grid, wafer=2)])
    first, second = result.wafers
    assert first.probabilities == second.probabilities
    assert first.spatial == second.spatial  # the same map: the same permutations
    assert first.top_probability == first.probabilities[0].probability


def test_the_same_map_gets_the_same_spatial_test_in_any_run(
    engine: LiveWafers, demo_inputs: list[WaferInput]
) -> None:
    a = engine.pattern(demo_inputs[:3]).wafers[2].spatial
    b = engine.pattern([demo_inputs[7], demo_inputs[2]]).wafers[1].spatial
    assert a is not None
    assert a == b


# Inputs that cannot run ---------------------------------------------------------------------


def test_no_wafer_needs_input(engine: LiveWafers, demo_inputs: list[WaferInput]) -> None:
    empty = engine.pattern(demo_inputs[:1]).model_copy(update={"wafers": []})
    with pytest.raises(NeedsInput) as caught:
        engine.pattern([])
    assert caught.value.needs == NEEDS_WAFERS
    with pytest.raises(NeedsInput):
        engine.similar([], empty)


def test_maps_that_cannot_be_read() -> None:
    def bad(cells: bytes | str, h: int = 2, w: int = 2) -> str:
        text = cells if isinstance(cells, str) else base64.b64encode(cells).decode()
        with pytest.raises(MapError) as caught:
            decode_map(WaferMap(height=h, width=w, cells=text))
        return caught.value.message

    assert "not valid base64" in bad("not base64!")
    assert "has 3 cells; 2 x 2 needs 4" in bad(b"\x01\x01\x01")
    assert "0 (no die), 1 (pass) or 2 (fail)" in bad(b"\x01\x01\x01\x07")
    assert "has no die" in bad(b"\x00\x00\x00\x00")


def test_a_pattern_result_for_other_wafers_is_refused(
    engine: LiveWafers, demo_inputs: list[WaferInput]
) -> None:
    pattern = engine.pattern(demo_inputs[:2])
    with pytest.raises(ValueError, match="other wafers"):
        engine.similar(demo_inputs[1:3], pattern)
    with pytest.raises(ValueError, match="other wafers"):
        engine.lots(demo_inputs[:3], pattern)


# Similar ------------------------------------------------------------------------------------


def test_similar_on_a_new_map_and_its_causes(engine: LiveWafers, bundle: WafermapBundle) -> None:
    i = _edge_ring_wafer(bundle)
    redrawn = _input(bundle.wafers.grid(i))  # not marked as a demo wafer: it finds its source
    pattern = engine.pattern([redrawn])
    result = engine.similar([redrawn], pattern)
    (item,) = result.wafers
    assert len(item.similar) == 10
    assert item.similar[0].wafer_id == bundle.wafers.wafer_id[i]
    assert item.similar[0].similarity == pytest.approx(1.0, abs=1e-5)
    sims = [s.similarity for s in item.similar]
    assert sims == sorted(sims, reverse=True)
    assert {c.label for c in result.causes.causes} == {"Edge-Ring"}
    assert result.causes.sources


def test_causes_cover_every_predicted_pattern_but_none(
    engine: LiveWafers, demo_inputs: list[WaferInput]
) -> None:
    lot = engine.from_demo(lot=engine.lot_names[0])
    pattern = engine.pattern(lot)
    result = engine.similar(lot, pattern)
    predicted = {w.top_label for w in pattern.wafers} - {"none"}
    assert {c.label for c in result.causes.causes} == predicted & {
        c.label for c in engine.causes_source.causes(list(predicted)).causes
    }


# Lots ---------------------------------------------------------------------------------------


def test_a_lot_needs_two_wafers(engine: LiveWafers, demo_inputs: list[WaferInput]) -> None:
    single = [demo_inputs[0], demo_inputs[-1]]  # two wafers of two lots
    assert single[0].lot != single[1].lot
    with pytest.raises(NeedsInput) as caught:
        engine.lots(single, engine.pattern(single))
    assert caught.value.needs == NEEDS_LOT


def test_bh_runs_over_every_lot_of_the_run(engine: LiveWafers) -> None:
    wafers = engine.from_demo(lot=engine.lot_names[0]) + engine.from_demo(lot=engine.lot_names[1])
    wafers.append(engine.from_demo(lot=engine.lot_names[2])[0])  # a lot of one wafer: not tested
    result = engine.lots(wafers, engine.pattern(wafers))
    assert [item.lot for item in result.lots] == engine.lot_names[:2]
    tests = [t for item in result.lots for t in item.tests]
    assert len(tests) == 16
    q, flagged = benjamini_hochberg([t.p_value for t in tests], 0.05)
    assert [t.q_value for t in tests] == q
    assert [t.flagged for t in tests] == flagged
    for item in result.lots:
        assert item.flagged == any(t.flagged for t in item.tests)
        assert item.pattern_counts == {t.label: t.count for t in item.tests}
    assert "the run is the family" in result.method


def test_a_lot_of_mixed_sizes_has_no_stacked_map(engine: LiveWafers) -> None:
    a = np.ones((5, 5), dtype=np.uint8)  # test-only maps
    b = np.ones((5, 6), dtype=np.uint8)
    a[2, 2] = b[1, 1] = 2
    wafers = [_input(a, "T1", 1), _input(b, "T1", 2)]
    (item,) = engine.lots(wafers, engine.pattern(wafers)).lots
    assert item.stacked is None
    assert item.wafers == 2


# Real inputs --------------------------------------------------------------------------------


def test_from_demo_keeps_the_order_and_adds_the_lot(
    engine: LiveWafers, bundle: WafermapBundle
) -> None:
    lot = engine.lot_names[3]
    rows = engine.lot_rows[lot]
    ids = [bundle.wafers.wafer_id[rows[2]], "lot10291-1", bundle.wafers.wafer_id[rows[2]]]
    picked = engine.from_demo(ids, lot)
    assert [w.source_wafer for w in picked] == [
        ids[0],
        "lot10291-1",
        *[bundle.wafers.wafer_id[r] for r in rows if r != rows[2]],
    ]
    first = picked[0]
    assert first.label == bundle.wafers.label[rows[2]]
    assert first.lot == lot
    assert first.wafer == bundle.wafers.wafer_index[rows[2]]
    with pytest.raises(NotFoundError, match="lot1-999"):
        engine.from_demo(["lot1-999"])
    with pytest.raises(NotFoundError, match="nolot"):
        engine.from_demo(lot="nolot")


def test_a_sample_is_one_whole_real_lot(engine: LiveWafers, bundle: WafermapBundle) -> None:
    picked = engine.sample(random.Random(20261015))
    again = engine.sample(random.Random(20261015))
    assert picked == again
    lot = picked.items[0].lot
    assert {w.lot for w in picked.items} == {lot}
    assert [w.source_wafer for w in picked.items] == [
        bundle.wafers.wafer_id[r] for r in engine.lot_rows[lot]
    ]
    assert len(picked.items) >= 2
    assert f"lot {lot} ({len(picked.items)} wafers)" in picked.rule
    assert "uniformly at random from the 475 demo lots" in picked.rule
    lots = {engine.sample(random.Random(seed)).items[0].lot for seed in range(40)}
    assert len(lots) > 30


def test_draw_layouts_are_real_die_layouts_all_pass(
    engine: LiveWafers, bundle: WafermapBundle
) -> None:
    layouts = engine.draw_layouts()
    assert len(layouts) == 6
    assert layouts[0].layout_id == "25x27"
    sizes = [(bundle.wafers.height[i], bundle.wafers.width[i]) for i in range(len(bundle.wafers))]
    shapes = [d.layout_id.split("x") for d in layouts]
    counts = [sizes.count((int(h), int(w))) for h, w in shapes]
    assert counts == sorted(counts, reverse=True)
    for layout in layouts:
        item = DrawLayoutItem(
            layout_id=layout.layout_id,
            map=layout.map,
            source_wafer=layout.source_wafer,
            rule=layout.rule,
        )
        grid = decode_map(item.map)
        source = bundle.wafers.grid(bundle.wafers.index_of[layout.source_wafer])
        assert set(np.unique(grid).tolist()) == {0, 1}
        assert np.array_equal(grid, (source > 0).astype(np.uint8))
        assert layout.source_wafer in layout.rule


# Performance --------------------------------------------------------------------------------


def test_pattern_and_similar_for_200_wafers(
    engine: LiveWafers, demo_inputs: list[WaferInput], capsys: pytest.CaptureFixture[str]
) -> None:
    wafers = demo_inputs[::51][:200]  # spread over the demo set: its mix of map sizes
    start = time.perf_counter()
    pattern = engine.pattern(wafers)
    middle = time.perf_counter()
    similar = engine.similar(wafers, pattern)
    end = time.perf_counter()
    assert len(similar.wafers) == 200
    dies = sum(int((decode_map(w.map) > 0).sum()) for w in wafers)
    with capsys.disabled():
        print(
            f"\n200 wafers ({dies} dies): pattern {middle - start:.2f} s, "
            f"similar {end - middle:.2f} s"
        )
    assert end - start < 120  # a loose guard; the measured time is printed above
