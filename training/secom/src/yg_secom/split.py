"""Chronological blocks and rolling-origin cross-validation folds.

Units are ordered by timestamp; units with the same timestamp keep their file order (the
unit id breaks ties). Block and fold boundaries are only ever placed between two
different timestamps, so tied units always share a block and a fold, and every unit of an
earlier block is strictly older than every unit of a later block. ``assert_no_leakage``
checks this and is also run by the test suite.

Protocol (every boundary is recorded in ``metrics.json``):

- **test**: the last ``test_fraction`` of units in time order, untouched until the single
  final evaluation. If it holds fewer than ``min_failures`` failures, its start moves
  earlier one timestamp at a time until it does.
- **development period**: every unit before the test block. The final models are fitted
  on all of it.
- **train**: the first ``warmup_fraction`` of the development period. It is the
  rolling-origin warm-up: only ever used for fitting, so its units get no out-of-sample
  risk.
- **validation**: the rest of the development period, cut into consecutive
  rolling-origin evaluation slices. Each slice is predicted by a model fitted on every
  unit before it. These out-of-fold predictions choose the hyperparameters, fit the
  calibrator and set the alarm thresholds.

A plain 60/20/20 split is computed for the record: on SECOM its validation block holds too
few failures to tune or calibrate on, which is why validation is done by rolling origin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

IdArray = npt.NDArray[np.int64]


class LeakageError(AssertionError):
    """A later block contains a unit that is not strictly later than an earlier block."""


class SplitError(ValueError):
    """The requested split cannot be built from these data."""


def epoch_us(timestamps: pd.Series) -> npt.NDArray[np.int64]:
    """Timestamps as integer microseconds since 1970-01-01 UTC."""
    naive = timestamps.dt.tz_convert("UTC").dt.tz_localize(None)
    return np.asarray(naive.to_numpy().astype("datetime64[us]").astype(np.int64), dtype=np.int64)


def time_order(timestamps: pd.Series) -> IdArray:
    """Unit ids sorted by timestamp, ties broken by unit id."""
    t = epoch_us(timestamps)
    return np.asarray(np.lexsort((np.arange(t.size), t)), dtype=np.int64)


def _snap(t_sorted: npt.NDArray[np.int64], position: int) -> int:
    """Move a cut position back to the start of its timestamp tie group."""
    if position <= 0:
        return 0
    if position >= t_sorted.size:
        return int(t_sorted.size)
    return int(np.searchsorted(t_sorted, t_sorted[position], side="left"))


def _next_cut(t_sorted: npt.NDArray[np.int64], position: int) -> int:
    """The next cut position after ``position`` (start of the next timestamp)."""
    if position >= t_sorted.size:
        return int(t_sorted.size)
    return int(np.searchsorted(t_sorted, t_sorted[position], side="right"))


def iso(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Blocks:
    """Train (warm-up), validation and test unit ids, each in time order."""

    order: IdArray
    train: IdArray
    validation: IdArray
    test: IdArray
    record: dict[str, Any] = field(default_factory=dict)

    @property
    def development(self) -> IdArray:
        """Every unit before the test block (train then validation), in time order."""
        return np.concatenate([self.train, self.validation])

    def labels_per_unit(self, n_units: int) -> npt.NDArray[np.str_]:
        names = np.empty(n_units, dtype="<U10")
        names[self.train] = "train"
        names[self.validation] = "validation"
        names[self.test] = "test"
        return names


def _block_summary(
    name: str, ids: IdArray, timestamps: pd.Series, labels: npt.NDArray[np.int8]
) -> dict[str, Any]:
    ts = timestamps.iloc[ids]
    failures = int(labels[ids].sum())
    return {
        "block": name,
        "units": int(ids.size),
        "failures": failures,
        "passes": int(ids.size - failures),
        "failure_rate": failures / ids.size,
        "first": iso(ts.min()),
        "last": iso(ts.max()),
    }


def chronological_blocks(
    timestamps: pd.Series,
    labels: npt.NDArray[np.int8],
    test_fraction: float = 0.2,
    warmup_fraction: float = 0.3,
    min_failures: int = 15,
) -> Blocks:
    """Train (warm-up), validation and test blocks in time order (see module docstring)."""
    if not 0 < test_fraction < 1 or not 0 < warmup_fraction < 1:
        raise SplitError("test_fraction and warmup_fraction must lie in (0, 1)")
    order = time_order(timestamps)
    t = epoch_us(timestamps)[order]
    y = labels[order].astype(np.int64)
    n = int(order.size)
    before = np.concatenate([[0], np.cumsum(y)])

    def failures(a: int, b: int) -> int:
        return int(before[b] - before[a])

    moves: list[dict[str, Any]] = []
    start_test = _snap(t, round((1.0 - test_fraction) * n))
    origin = start_test
    while failures(start_test, n) < min_failures:
        if start_test <= 0:
            raise SplitError("the test block cannot reach the minimum number of failures")
        start_test = _snap(t, start_test - 1)
    if start_test != origin:
        moves.append(
            {
                "boundary": "test start",
                "from_position": origin,
                "to_position": start_test,
                "units_moved": origin - start_test,
                "reason": f"test block needed at least {min_failures} failures",
            }
        )

    warmup_end = _snap(t, round(warmup_fraction * start_test))
    origin = warmup_end
    while failures(0, warmup_end) < min_failures:
        if warmup_end >= start_test:
            raise SplitError("the train block cannot reach the minimum number of failures")
        warmup_end = _next_cut(t, warmup_end)
    while failures(warmup_end, start_test) < min_failures:
        candidate = _snap(t, warmup_end - 1)
        if candidate <= 0 or failures(0, candidate) < min_failures:
            raise SplitError(
                "the validation block cannot reach the minimum number of failures while the "
                "train block keeps its own minimum"
            )
        warmup_end = candidate
    if warmup_end != origin:
        moves.append(
            {
                "boundary": "validation start",
                "from_position": origin,
                "to_position": warmup_end,
                "units_moved": warmup_end - origin,
                "reason": f"train and validation blocks need at least {min_failures} failures each",
            }
        )
    if min(warmup_end, start_test - warmup_end, n - start_test) <= 0:
        raise SplitError("a block would be empty")

    train, validation, test = order[:warmup_end], order[warmup_end:start_test], order[start_test:]
    plain_val = _snap(t, round(0.6 * n))
    plain_test = _snap(t, round(0.8 * n))
    record = {
        "rule": (
            "units sorted by timestamp (unit id breaks ties), cuts only between different "
            f"timestamps; test = last {test_fraction:.0%} of units; development period = "
            f"everything before it; train = first {warmup_fraction:.0%} of the development "
            "period (rolling-origin warm-up, fitting only); validation = the rest of the "
            "development period (rolling-origin evaluation slices); a block start moves one "
            f"timestamp at a time until every block holds at least {min_failures} failures"
        ),
        "test_fraction": test_fraction,
        "warmup_fraction": warmup_fraction,
        "min_failures_per_block": min_failures,
        "moves": moves,
        "boundaries": {
            "validation_start_position": warmup_end,
            "validation_start": iso(timestamps.iloc[order[warmup_end]]),
            "test_start_position": start_test,
            "test_start": iso(timestamps.iloc[order[start_test]]),
            "positions": "0-based positions in time order; a block starts at its position",
        },
        "blocks": [
            _block_summary("train", train, timestamps, labels),
            _block_summary("validation", validation, timestamps, labels),
            _block_summary("test", test, timestamps, labels),
        ],
        "development": {
            "units": int(start_test),
            "failures": failures(0, start_test),
            "first": iso(timestamps.iloc[order[0]]),
            "last": iso(timestamps.iloc[order[start_test - 1]]),
        },
        "plain_60_20_20_for_comparison": {
            "units": {
                "train": plain_val,
                "validation": plain_test - plain_val,
                "test": n - plain_test,
            },
            "failures": {
                "train": failures(0, plain_val),
                "validation": failures(plain_val, plain_test),
                "test": failures(plain_test, n),
            },
            "why_not_used": (
                "a single validation block this small holds too few failures to tune "
                "hyperparameters or fit a calibrator on; rolling-origin validation over the "
                "whole development period uses every failure after the warm-up instead"
            ),
        },
    }
    blocks = Blocks(order=order, train=train, validation=validation, test=test, record=record)
    assert_no_leakage(blocks, timestamps)
    return blocks


def assert_no_leakage(blocks: Blocks, timestamps: pd.Series) -> None:
    """Raise ``LeakageError`` unless train < validation < test strictly in time.

    Also checks that every unit is in exactly one block.
    """
    t = epoch_us(timestamps)
    parts = {"train": blocks.train, "validation": blocks.validation, "test": blocks.test}
    for name, ids in parts.items():
        if ids.size == 0:
            raise LeakageError(f"{name} block is empty")
        if np.unique(ids).size != ids.size:
            raise LeakageError(f"{name} block lists a unit twice")
    all_ids = np.concatenate(list(parts.values()))
    if np.unique(all_ids).size != all_ids.size:
        raise LeakageError("a unit appears in two blocks")
    if all_ids.size != t.size or not np.array_equal(np.sort(all_ids), np.arange(t.size)):
        raise LeakageError("the blocks do not cover every unit exactly once")
    if not t[blocks.train].max() < t[blocks.validation].min():
        raise LeakageError("a train unit is not strictly earlier than every validation unit")
    if not t[blocks.validation].max() < t[blocks.test].min():
        raise LeakageError("a validation unit is not strictly earlier than every test unit")


@dataclass(frozen=True)
class Fold:
    """One rolling-origin fold: an expanding fitting window and the next time slice."""

    index: int
    train: IdArray
    valid: IdArray


def rolling_origin_folds(
    development_ids: IdArray,
    warmup_units: int,
    timestamps: pd.Series,
    labels: npt.NDArray[np.int8],
    n_folds: int = 5,
    min_failures: int = 5,
) -> tuple[list[Fold], dict[str, Any]]:
    """Expanding-window folds over the development period.

    The first ``warmup_units`` units (the train block) are only ever used for fitting. The
    rest (the validation block) is cut into ``n_folds`` consecutive slices of about equal
    size. Fold ``k`` fits on every unit before slice ``k`` and is evaluated on slice ``k``.
    A slice with fewer than ``min_failures`` failures is merged into the next slice (the
    last one into the previous), so every evaluation slice can measure average precision.
    """
    ids = np.asarray(development_ids, dtype=np.int64)
    t_all = epoch_us(timestamps)
    t = t_all[ids]
    if np.any(np.diff(t) < 0):
        raise SplitError("development_ids must be in time order")
    y = labels[ids].astype(np.int64)
    m = int(ids.size)
    warmup_end = int(warmup_units)
    if not 0 < warmup_end < m or _snap(t, warmup_end) != warmup_end:
        raise SplitError("the warm-up must end between two different timestamps")
    if y[:warmup_end].sum() == 0:
        raise SplitError("the warm-up window must contain at least one failure")
    raw_edges = [warmup_end]
    for k in range(1, n_folds):
        raw_edges.append(_snap(t, round(warmup_end + k * (m - warmup_end) / n_folds)))
    raw_edges.append(m)
    edges = sorted(set(raw_edges))
    merges: list[str] = []
    changed = True
    while changed and len(edges) > 2:
        changed = False
        for i in range(len(edges) - 1):
            count = int(y[edges[i] : edges[i + 1]].sum())
            if count < min_failures:
                drop = i + 1 if i + 1 < len(edges) - 1 else i
                merges.append(
                    f"slice {i + 1} had {count} failures (< {min_failures}); "
                    "merged with a neighbour"
                )
                del edges[drop]
                changed = True
                break
    if int(y[edges[0] : edges[1]].sum()) < min_failures and len(edges) == 2:
        raise SplitError("not enough failures after the warm-up window for one fold")
    folds: list[Fold] = []
    slices = []
    for k in range(len(edges) - 1):
        train_part = ids[: edges[k]]
        valid_part = ids[edges[k] : edges[k + 1]]
        if not t_all[train_part].max() < t_all[valid_part].min():
            raise LeakageError(f"fold {k}: training window overlaps the evaluation slice in time")
        folds.append(Fold(index=k, train=train_part, valid=valid_part))
        slices.append(
            {
                "fold": k,
                "train_units": int(train_part.size),
                "train_failures": int(y[: edges[k]].sum()),
                "valid_units": int(valid_part.size),
                "valid_failures": int(y[edges[k] : edges[k + 1]].sum()),
                "valid_start_position": int(edges[k]),
                "valid_first": iso(timestamps.iloc[valid_part].min()),
                "valid_last": iso(timestamps.iloc[valid_part].max()),
            }
        )
    record = {
        "rule": (
            "expanding window over the development period; the train block (warm-up) is "
            f"only fitted on; the validation block is cut into {n_folds} consecutive slices "
            "of about equal size, each predicted by a model fitted on every earlier unit; "
            f"slices with fewer than {min_failures} failures are merged with a neighbour"
        ),
        "warmup_units": warmup_end,
        "warmup_failures": int(y[:warmup_end].sum()),
        "merges": merges,
        "folds": slices,
    }
    return folds, record
