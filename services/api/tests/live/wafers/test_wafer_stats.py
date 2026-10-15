"""The live wafer statistics against reference implementations (scipy, the training code).

Maps built here are test inputs (said where they are); nothing computed from them is reported.
"""

from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from yield_guardian.bundles.wafermap import WafermapBundle
from yield_guardian.live import wafer_stats
from yield_guardian.live.wafer_stats import (
    benjamini_hochberg,
    binomial_tail,
    join_count,
    map_seed,
    stacked_failure_map,
)

scipy_stats = pytest.importorskip("scipy.stats")


def reference_join_count(
    grid: npt.NDArray[np.uint8], rng: np.random.Generator, permutations: int
) -> dict[str, Any]:
    """training/wafermap/wm/lots.py `join_count`, copied as is (PERMUTATIONS as a parameter;
    the list of pair blocks renamed for the type checker)."""
    die = grid > 0
    position = -np.ones(grid.shape, dtype=np.int64)
    position[die] = np.arange(die.sum())
    blocks = []
    for a, b in ((position[:, :-1], position[:, 1:]), (position[:-1, :], position[1:, :])):
        ok = (a >= 0) & (b >= 0)
        blocks.append(np.stack([a[ok], b[ok]], 1))
    pairs = np.concatenate(blocks)
    fail = (grid[die] == 2).astype(np.int8)
    observed = int((fail[pairs[:, 0]] & fail[pairs[:, 1]]).sum())
    if fail.sum() < 2 or len(pairs) == 0:
        return {"bb": observed, "fails": int(fail.sum()), "dies": int(die.sum()), "p": None}
    perms = rng.permuted(np.tile(fail, (permutations, 1)), axis=1)
    null = (perms[:, pairs[:, 0]] & perms[:, pairs[:, 1]]).sum(1)
    sd = null.std(ddof=1)
    return {
        "bb": observed,
        "fails": int(fail.sum()),
        "dies": int(die.sum()),
        "expected": float(null.mean()),
        "z": float((observed - null.mean()) / sd) if sd > 0 else None,
        "p": float((1 + (null >= observed).sum()) / (1 + permutations)),
    }


@pytest.mark.parametrize(
    ("k", "n", "p"),
    [
        (0, 25, 0.03),
        (1, 25, 0.03),
        (5, 22, 0.034),
        (25, 25, 0.048),
        (3, 2, 0.5),
        (2, 500, 0.0007),
        (40, 500, 0.0482),
        (499, 500, 0.97),
        (1, 1, 0.0),
        (0, 1, 1.0),
        (1, 1, 1.0),
    ],
)
def test_binomial_tail_matches_scipy(k: int, n: int, p: float) -> None:
    assert binomial_tail(k, n, p) == pytest.approx(
        float(scipy_stats.binom.sf(k - 1, n, p)), rel=1e-11, abs=1e-300
    )


def test_binomial_tail_reproduces_every_p_value_in_lots_json(bundle: WafermapBundle) -> None:
    worst = 0.0
    for lot in bundle.lots.values():
        for t in lot.tests:
            live = binomial_tail(t.count, t.wafers, t.expected_rate)
            worst = max(worst, abs(live - t.p) / max(t.p, 1e-300))
    assert worst < 1e-12


def test_benjamini_hochberg_matches_scipy() -> None:
    rng = np.random.default_rng(5)  # test-only p-values
    p = np.concatenate([rng.uniform(size=200), rng.uniform(0, 1e-3, size=20), [0.5, 0.5, 1.0]])
    q, reject = benjamini_hochberg(p.tolist(), 0.05)
    np.testing.assert_allclose(q, scipy_stats.false_discovery_control(p, method="bh"), rtol=1e-12)
    assert reject == [v <= 0.05 for v in q]
    assert any(reject)
    assert not all(reject)
    assert benjamini_hochberg([], 0.05) == ([], [])


def test_benjamini_hochberg_steps_up() -> None:
    # p_(2) fails its own bound but p_(3) passes: step-up rejects all three.
    q, reject = benjamini_hochberg([0.01, 0.03, 0.035, 0.9], 0.05)
    assert reject == [True, True, True, False]
    assert q == pytest.approx([0.04, 0.035 * 4 / 3, 0.035 * 4 / 3, 0.9])


def _test_grid(seed: int, h: int, w: int, fail_share: float) -> npt.NDArray[np.uint8]:
    """Test-only map: a disc of dies with random fails."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:h, :w]
    die = (yy - (h - 1) / 2) ** 2 / (h / 2) ** 2 + (xx - (w - 1) / 2) ** 2 / (w / 2) ** 2 <= 1
    return np.where(die, np.where(rng.random((h, w)) < fail_share, 2, 1), 0).astype(np.uint8)


@pytest.mark.parametrize(
    ("seed", "h", "w", "share"), [(1, 25, 27, 0.2), (2, 40, 31, 0.6), (3, 9, 70, 0.05)]
)
def test_join_count_is_the_training_code(seed: int, h: int, w: int, share: float) -> None:
    grid = _test_grid(seed, h, w, share)
    live = join_count(grid, 999, np.random.default_rng(11))
    reference = reference_join_count(grid, np.random.default_rng(11), 999)
    assert (live.bb, live.fails, live.dies, live.p) == (
        reference["bb"],
        reference["fails"],
        reference["dies"],
        reference["p"],
    )
    assert live.expected == reference["expected"]
    assert live.z == pytest.approx(reference["z"], rel=1e-12)


def test_permutations_drawn_in_blocks_equal_one_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    grid = _test_grid(4, 60, 60, 0.3)
    whole = join_count(grid, 999)
    monkeypatch.setattr(wafer_stats, "BLOCK_CELLS", 50_000)  # blocks of a few permutations
    assert join_count(grid, 999) == whole


def test_the_same_map_always_gets_the_same_p_value(bundle: WafermapBundle) -> None:
    grid = bundle.wafers.grid(1234)
    first = join_count(grid, 999)
    assert join_count(grid.copy(), 999) == first
    assert map_seed(grid) == map_seed(np.ascontiguousarray(grid.copy()))
    other = grid.copy()
    other[other == 1] = 2  # any change of cells changes the seed
    assert map_seed(other) != map_seed(grid)
    assert map_seed(grid.T) != map_seed(grid)  # and so does the shape


def test_nothing_to_test_with_fewer_than_two_fails() -> None:
    grid = np.ones((5, 5), dtype=np.uint8)  # test-only map
    grid[2, 2] = 2
    jc = join_count(grid, 999)
    assert (jc.bb, jc.fails, jc.dies, jc.p, jc.expected) == (0, 1, 25, None, None)
    single = join_count(np.full((1, 1), 2, dtype=np.uint8), 999)
    assert single.p is None
    assert single.dies == 1


def test_stacked_failure_map_is_the_share_of_wafers_failing_at_each_die() -> None:
    a = np.array([[0, 1, 2], [1, 2, 2]], dtype=np.uint8)  # test-only maps
    b = np.array([[0, 2, 2], [0, 1, 2]], dtype=np.uint8)
    c = np.array([[0, 1, 1], [1, 1, 2]], dtype=np.uint8)
    stacked = stacked_failure_map([a, b, c])
    assert stacked is not None
    assert (stacked.height, stacked.width, stacked.wafers) == (2, 3, 3)
    assert stacked.frequencies == [None, 0.3333, 0.6667, 0.0, 0.3333, 1.0]
    assert stacked_failure_map([a, np.zeros((3, 2), dtype=np.uint8)]) is None
    assert stacked_failure_map([]) is None
