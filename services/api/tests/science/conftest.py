from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.science.bundle_factory import DATA, build_secom_bundle
from yield_guardian.bundles.manifest import verify_bundle
from yield_guardian.bundles.secom import SecomBundle, load_secom_bundle
from yield_guardian.replay.clock import ReplayClock
from yield_guardian.replay.line import LineReplay
from yield_guardian.science.secom.service import SecomInference

EPOCH = datetime.fromisoformat("2026-10-12T00:00:00+00:00")


@pytest.fixture(scope="session")
def bundle_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_secom_bundle(tmp_path_factory.mktemp("artifacts"))


@pytest.fixture(scope="session")
def secom_bundle(bundle_dir: Path) -> SecomBundle:
    return load_secom_bundle(verify_bundle(bundle_dir, "secom"), DATA)


class FakeNow:
    """A settable wall clock for the replay."""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def at_tick(self, tick: int, seconds: float = 6.0) -> None:
        self.at = EPOCH + timedelta(seconds=tick * seconds)


@pytest.fixture
def now() -> FakeNow:
    fake = FakeNow(EPOCH)
    fake.at_tick(1100)
    return fake


@pytest.fixture
def clock(secom_bundle: SecomBundle, now: Callable[[], datetime]) -> ReplayClock:
    return ReplayClock(
        epoch=EPOCH,
        seconds_per_unit=6.0,
        plant_times=secom_bundle.timeline.timestamp,
        final_test_lag_units=25,
        now=now,
    )


@pytest.fixture
def line(secom_bundle: SecomBundle, clock: ReplayClock) -> LineReplay:
    return LineReplay(secom_bundle, clock)


@pytest.fixture
def secom(secom_bundle: SecomBundle, line: LineReplay) -> SecomInference:
    return SecomInference(secom_bundle, line)
