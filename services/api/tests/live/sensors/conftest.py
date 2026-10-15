"""The real SECOM bundle (artifacts/secom) and source files (data/secom), loaded once.

These tests use no synthetic data: every input is a real SECOM unit, or a real unit changed in
a stated way inside a test.
"""

from pathlib import Path

import pytest

from yield_guardian.bundles.manifest import latest_version, verify_bundle
from yield_guardian.bundles.secom import SecomBundle, load_secom_bundle
from yield_guardian.contracts.runs import SensorUnitInput
from yield_guardian.live.sensors import SecomSensorEngine

REPO = Path(__file__).resolve().parents[5]
ARTIFACTS = REPO / "artifacts"
DATA = REPO / "data" / "secom"


@pytest.fixture(scope="session")
def real_bundle() -> SecomBundle:
    return load_secom_bundle(verify_bundle(latest_version(ARTIFACTS, "secom"), "secom"), DATA)


@pytest.fixture(scope="session")
def engine(real_bundle: SecomBundle) -> SecomSensorEngine:
    return SecomSensorEngine(real_bundle)


@pytest.fixture(scope="session")
def all_units(engine: SecomSensorEngine, real_bundle: SecomBundle) -> list[SensorUnitInput]:
    """Every SECOM unit, in time order (the timeline's order)."""
    return engine.from_secom(range(len(real_bundle.timeline)))
