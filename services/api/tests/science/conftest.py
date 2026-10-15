from pathlib import Path

import pytest

from tests.science.bundle_factory import DATA, REPO, build_secom_bundle
from yield_guardian.bundles.manifest import latest_version, verify_bundle
from yield_guardian.bundles.secom import SecomBundle, load_secom_bundle
from yield_guardian.bundles.wafermap import WafermapBundle, load_wafermap_bundle
from yield_guardian.science.secom.alarms import SecomAlarms
from yield_guardian.science.secom.service import SecomInference
from yield_guardian.science.wafermap.service import WaferInference

ARTIFACTS = REPO / "artifacts"


@pytest.fixture(scope="session")
def bundle_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_secom_bundle(tmp_path_factory.mktemp("artifacts"))


@pytest.fixture(scope="session")
def secom_bundle(bundle_dir: Path) -> SecomBundle:
    return load_secom_bundle(verify_bundle(bundle_dir, "secom"), DATA)


@pytest.fixture
def alarms(secom_bundle: SecomBundle) -> SecomAlarms:
    return SecomAlarms(secom_bundle)


@pytest.fixture
def secom(secom_bundle: SecomBundle, alarms: SecomAlarms) -> SecomInference:
    return SecomInference(secom_bundle, alarms)


@pytest.fixture(scope="session")
def wafermap_dir() -> Path:
    """The real wafer-map bundle committed under artifacts/ (no synthetic data)."""
    return latest_version(ARTIFACTS, "wafermap")


@pytest.fixture(scope="session")
def wafermap_bundle(wafermap_dir: Path) -> WafermapBundle:
    return load_wafermap_bundle(verify_bundle(wafermap_dir, "wafermap"))


@pytest.fixture(scope="session")
def wafers(wafermap_bundle: WafermapBundle) -> WaferInference:
    return WaferInference(wafermap_bundle)
