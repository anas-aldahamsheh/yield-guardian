"""Checks on the real processed data and exported model; skipped where they are absent (CI)."""

from __future__ import annotations

import json

import pytest

from wm.common import RUNS
from wm.splits import SPLITS

pytestmark = pytest.mark.skipif(not SPLITS.exists(), reason="processed WM-811K data not present")


def test_real_splits_have_no_lot_in_two_parts() -> None:
    from wm.common import load_index

    index = load_index()
    for column in ("split_official", "split_lot"):
        labelled = index[index[column].notna()]
        assert (labelled.groupby("lot")[column].nunique() == 1).all(), column
    assert index.loc[index["label"].isna(), ["split_official", "split_lot"]].isna().all().all()


@pytest.mark.parametrize("path", sorted(RUNS.glob("*/parity.json")) if RUNS.exists() else [])
def test_onnx_parity(path) -> None:
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["max_abs_diff_logits"] < 1e-3
    assert result["argmax_agreement"] == 1.0
