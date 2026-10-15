"""The wafer-map statistics of the live engine, as the bundle's build computed them.

Each function reimplements one step of training/wafermap/wm/lots.py without its training-only
dependencies (scipy, statsmodels), so the API computes the same numbers at request time:

- `join_count`: the Cliff and Ord (1981) join-count test of whether fail dies cluster, the
  number of rook-adjacent fail-fail die pairs against random permutations of the fail labels
  over the wafer's dies (lots.py `join_count`, line for line). The bundle drew its permutations
  from one generator shared by all demo wafers; here each map seeds its own (`map_seed`), so the
  same map always gets the same p-value, whatever run, lot or position it comes in.
- `binomial_tail`: P(X >= k) for X ~ Binomial(n, p), the one-sided lot test (scipy
  `binom.sf(k - 1, n, p)`).
- `benjamini_hochberg`: q-values and rejections at level alpha (statsmodels
  `multipletests(method="fdr_bh")`).
- `stacked_failure_map`: per die position, the share of a lot's wafers in which it failed
  (lots.py `stacked`, rounded to 4 decimals as stored).
"""

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

Grid = npt.NDArray[np.uint8]

SEED_DOMAIN = b"yield-guardian/join-count/v1"
# Permutations are drawn in blocks so a large map never holds every permutation at once; a block
# of rows from rng.permuted consumes the generator exactly as one call over all rows would.
BLOCK_CELLS = 4_000_000
STACK_DECIMALS = 4


@dataclass(frozen=True, slots=True)
class JoinCount:
    """One wafer's join-count test; `expected`, `sd`, `z` and `p` are None when fewer than two
    dies fail or no two dies touch (nothing to test)."""

    bb: int
    fails: int
    dies: int
    expected: float | None
    sd: float | None
    z: float | None
    p: float | None


def map_seed(grid: Grid) -> int:
    """The permutation seed of a map: the first 8 bytes (big-endian) of SHA-256 over a fixed
    domain tag, the height and width (2 bytes each, big-endian) and the cells, row-major."""
    height, width = grid.shape
    digest = hashlib.sha256(
        SEED_DOMAIN
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + np.ascontiguousarray(grid, dtype=np.uint8).tobytes()
    ).digest()
    return int.from_bytes(digest[:8], "big")


def _rook_pairs(die: npt.NDArray[np.bool_]) -> npt.NDArray[np.int64]:
    """Index pairs (into the dies, row-major) of horizontally or vertically adjacent dies."""
    position = -np.ones(die.shape, dtype=np.int64)
    position[die] = np.arange(int(die.sum()))
    pairs = []
    for a, b in ((position[:, :-1], position[:, 1:]), (position[:-1, :], position[1:, :])):
        ok = (a >= 0) & (b >= 0)
        pairs.append(np.stack([a[ok], b[ok]], 1))
    return np.concatenate(pairs)


def join_count(grid: Grid, permutations: int, rng: np.random.Generator | None = None) -> JoinCount:
    """Rook-adjacent fail-fail joins among die cells, with a permutation p-value.

    p = (1 + #{null >= observed}) / (1 + permutations); expected is the mean of the null and
    z = (observed - expected) / sd(null, ddof=1). `rng` defaults to the map's own generator.
    """
    die = grid > 0
    pairs = _rook_pairs(die)
    fail = (grid[die] == 2).astype(np.int8)
    observed = int((fail[pairs[:, 0]] & fail[pairs[:, 1]]).sum())
    fails, dies = int(fail.sum()), int(die.sum())
    if fails < 2 or len(pairs) == 0:
        return JoinCount(observed, fails, dies, None, None, None, None)
    generator = rng if rng is not None else np.random.default_rng(map_seed(grid))
    block = max(1, BLOCK_CELLS // max(len(pairs), len(fail)))
    null_blocks = []
    for start in range(0, permutations, block):
        rows = min(block, permutations - start)
        perms = generator.permuted(np.tile(fail, (rows, 1)), axis=1)
        null_blocks.append((perms[:, pairs[:, 0]] & perms[:, pairs[:, 1]]).sum(1))
    null = np.concatenate(null_blocks)
    expected = float(null.mean())
    sd = float(null.std(ddof=1)) if permutations > 1 else 0.0
    return JoinCount(
        bb=observed,
        fails=fails,
        dies=dies,
        expected=expected,
        sd=sd,
        z=(observed - expected) / sd if sd > 0 else None,
        p=float((1 + int((null >= observed).sum())) / (1 + permutations)),
    )


def binomial_tail(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), summed exactly in log space (n is at most a run's
    wafers, so the sum has at most a few hundred terms)."""
    if k <= 0:
        return 1.0
    if k > n or p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    log_p, log_q = math.log(p), math.log1p(-p)
    log_n = math.lgamma(n + 1)
    terms = [
        log_n - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * log_p + (n - j) * log_q
        for j in range(k, n + 1)
    ]
    top = max(terms)
    return min(1.0, math.exp(top) * math.fsum(math.exp(t - top) for t in terms))


def benjamini_hochberg(p_values: Sequence[float], alpha: float) -> tuple[list[float], list[bool]]:
    """Benjamini-Hochberg q-values and step-up rejections at level alpha, in input order."""
    p = np.asarray(p_values, dtype=np.float64)
    m = len(p)
    if m == 0:
        return [], []
    order = np.argsort(p, kind="stable")
    ranked = p[order]
    factor = np.arange(1, m + 1) / m
    reject_ranked = ranked <= factor * alpha
    if reject_ranked.any():
        reject_ranked[: int(np.nonzero(reject_ranked)[0].max()) + 1] = True
    q_ranked = np.minimum(np.minimum.accumulate((ranked / factor)[::-1])[::-1], 1.0)
    q = np.empty(m)
    q[order] = q_ranked
    reject = np.empty(m, dtype=np.bool_)
    reject[order] = reject_ranked
    return [float(v) for v in q], [bool(v) for v in reject]


@dataclass(frozen=True, slots=True)
class Stacked:
    height: int
    width: int
    wafers: int
    frequencies: list[float | None]  # row-major; None where no wafer has a die


def stacked_failure_map(grids: Sequence[Grid]) -> Stacked | None:
    """The share of wafers whose die failed at each position; None when the shapes differ."""
    if not grids or len({g.shape for g in grids}) != 1:
        return None
    die = np.stack([g > 0 for g in grids]).sum(0)
    fail = np.stack([g == 2 for g in grids]).sum(0)
    share = np.round(np.where(die > 0, fail / np.maximum(die, 1), -1.0), STACK_DECIMALS)
    height, width = grids[0].shape
    return Stacked(
        height=int(height),
        width=int(width),
        wafers=len(grids),
        frequencies=[
            float(s) if d > 0 else None
            for s, d in zip(share.ravel().tolist(), die.ravel().tolist(), strict=True)
        ],
    )
