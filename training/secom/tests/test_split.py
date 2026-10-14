"""Chronological blocks, leakage checks and rolling-origin folds (SYNTHETIC inputs)."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd
import pytest

from yg_secom.split import (
    Blocks,
    LeakageError,
    SplitError,
    assert_no_leakage,
    chronological_blocks,
    epoch_us,
    rolling_origin_folds,
    time_order,
)


def _times(minutes: list[int]) -> pd.Series:
    base = pd.Timestamp("2008-07-19 00:00", tz="UTC")
    return pd.Series([base + pd.Timedelta(minutes=m) for m in minutes])


def _data(n: int = 500, seed: int = 0) -> tuple[pd.Series, npt.NDArray[np.int8]]:
    rng = np.random.default_rng(seed)
    steps = rng.integers(0, 5, size=n)  # many ties
    labels = (rng.random(n) < 0.12).astype(np.int8)
    return _times(list(np.cumsum(steps))), labels


def test_time_order_breaks_ties_by_unit_id() -> None:
    ts = _times([5, 1, 1, 0])
    assert time_order(ts).tolist() == [3, 1, 2, 0]


def test_blocks_are_strictly_ordered_and_cover_all_units() -> None:
    ts, y = _data()
    blocks = chronological_blocks(ts, y, test_fraction=0.2, warmup_fraction=0.3, min_failures=10)
    t = epoch_us(ts)
    assert t[blocks.train].max() < t[blocks.validation].min()
    assert t[blocks.validation].max() < t[blocks.test].min()
    everything = np.sort(np.concatenate([blocks.train, blocks.validation, blocks.test]))
    assert everything.tolist() == list(range(len(ts)))
    for ids in (blocks.train, blocks.validation, blocks.test):
        assert int(y[ids].sum()) >= 10
    assert blocks.development.tolist() == [*blocks.train.tolist(), *blocks.validation.tolist()]
    record = blocks.record
    assert record["boundaries"]["test_start_position"] == blocks.train.size + blocks.validation.size
    assert set(record["plain_60_20_20_for_comparison"]["failures"]) == {
        "train",
        "validation",
        "test",
    }


def test_tied_units_never_straddle_a_boundary() -> None:
    ts, y = _data(seed=3)
    blocks = chronological_blocks(ts, y, min_failures=10)
    labels = blocks.labels_per_unit(len(ts))
    for _, group in pd.Series(labels).groupby(epoch_us(ts)):
        assert group.nunique() == 1


def test_test_block_moves_earlier_until_it_has_enough_failures() -> None:
    n = 300
    y = np.zeros(n, dtype=np.int8)
    y[[10, 20, 30, 40, 50, 100, 110, 120, 130, 140, 200, 210, 220, 230, 235]] = 1
    ts = _times(list(range(n)))
    blocks = chronological_blocks(ts, y, test_fraction=0.2, warmup_fraction=0.3, min_failures=3)
    assert int(y[blocks.test].sum()) >= 3
    assert blocks.record["moves"][0]["boundary"] == "test start"


def test_impossible_split_is_an_error() -> None:
    ts = _times(list(range(100)))
    y = np.zeros(100, dtype=np.int8)
    y[:5] = 1
    with pytest.raises(SplitError):
        chronological_blocks(ts, y, min_failures=5)


def test_leakage_is_detected() -> None:
    ts = _times(list(range(10)))
    order = np.arange(10, dtype=np.int64)
    bad = Blocks(
        order=order,
        train=np.array([0, 1, 5], dtype=np.int64),
        validation=np.array([2, 3, 4], dtype=np.int64),
        test=np.array([6, 7, 8, 9], dtype=np.int64),
    )
    with pytest.raises(LeakageError):
        assert_no_leakage(bad, ts)
    missing = Blocks(
        order=order,
        train=np.array([0, 1], dtype=np.int64),
        validation=np.array([2, 3], dtype=np.int64),
        test=np.array([4, 5], dtype=np.int64),
    )
    with pytest.raises(LeakageError):
        assert_no_leakage(missing, ts)


def test_rolling_origin_folds_expand_and_never_look_ahead() -> None:
    ts, y = _data(seed=5)
    blocks = chronological_blocks(ts, y, min_failures=10)
    folds, record = rolling_origin_folds(
        blocks.development, int(blocks.train.size), ts, y, n_folds=4, min_failures=3
    )
    t = epoch_us(ts)
    covered = np.concatenate([f.valid for f in folds])
    assert np.array_equal(np.sort(covered), np.sort(blocks.validation))
    previous = 0
    for fold in folds:
        assert t[fold.train].max() < t[fold.valid].min()
        assert fold.train.size > previous
        previous = fold.train.size
        assert int(y[fold.valid].sum()) >= 3
        assert np.array_equal(fold.train, blocks.development[: fold.train.size])
    assert record["warmup_units"] == blocks.train.size


def test_slices_with_too_few_failures_are_merged() -> None:
    n = 200
    y = np.zeros(n, dtype=np.int8)
    y[[5, 10, 15, 20, 25, 30, 150, 160, 170, 180, 190, 199]] = 1
    ts = _times(list(range(n)))
    folds, record = rolling_origin_folds(
        np.arange(n, dtype=np.int64), 40, ts, y, n_folds=4, min_failures=2
    )
    assert record["merges"]
    assert all(int(y[f.valid].sum()) >= 2 for f in folds)
