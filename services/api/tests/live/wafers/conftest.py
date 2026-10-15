"""The real wafer-map bundle and the live engine built on it, once per test session.

Everything here is real: the committed WM-811K bundle (artifacts/wafermap) and the curated
literature table (docs/knowledge). Test-built maps live in the test modules and say so.
"""

import os
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from yield_guardian.bundles.manifest import latest_version, verify_bundle
from yield_guardian.bundles.wafermap import WafermapBundle, load_wafermap_bundle
from yield_guardian.contracts.runs import WaferInput, WaferPatternResult
from yield_guardian.live.causes import LiteratureCauses
from yield_guardian.live.wafer_stats import JoinCount
from yield_guardian.live.wafers import LiveWafers
from yield_guardian.science.wafermap.service import WaferInference

REPO = Path(__file__).resolve().parents[5]
ARTIFACTS = REPO / "artifacts"
KNOWLEDGE = REPO / "docs" / "knowledge"

FULL_PARITY = os.environ.get("YG_FULL_PARITY") == "1"
"""Run the join-count and similar-wafer parity on every demo wafer (about 4 minutes on 4 cores)
instead of a fixed tenth and quarter of them."""

NOT_TESTED = JoinCount(bb=0, fails=0, dies=0, expected=None, sd=None, z=None, p=None)


class WithoutSpatial(LiveWafers):
    """The live engine with the join-count step left out, so `pattern` can run on all 10,253
    demo wafers in a test; the join count is checked on its own (test_wafer_parity.py)."""

    def spatial(self, grids: Sequence[npt.NDArray[np.uint8]]) -> list[JoinCount]:
        return [NOT_TESTED] * len(grids)


@pytest.fixture(scope="session")
def bundle() -> WafermapBundle:
    return load_wafermap_bundle(verify_bundle(latest_version(ARTIFACTS, "wafermap"), "wafermap"))


@pytest.fixture(scope="session")
def causes() -> LiteratureCauses:
    return LiteratureCauses.from_directory(KNOWLEDGE)


@pytest.fixture(scope="session")
def engine(bundle: WafermapBundle, causes: LiteratureCauses) -> LiveWafers:
    return LiveWafers(bundle, causes)


@pytest.fixture(scope="session")
def v1(bundle: WafermapBundle) -> WaferInference:
    """The v1 wafer service: what the bundle serves from its load-time scores."""
    return WaferInference(bundle)


@pytest.fixture(scope="session")
def demo_inputs(engine: LiveWafers, bundle: WafermapBundle) -> list[WaferInput]:
    return engine.from_demo(bundle.wafers.wafer_id)


@pytest.fixture(scope="session")
def demo_pattern(
    bundle: WafermapBundle, causes: LiteratureCauses, demo_inputs: list[WaferInput]
) -> WaferPatternResult:
    """Live `pattern` on every demo wafer, in one call, in bundle order."""
    return WithoutSpatial(bundle, causes).pattern(demo_inputs)
