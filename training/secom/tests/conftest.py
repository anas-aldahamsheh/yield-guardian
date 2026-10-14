"""Shared fixtures. Every dataset here is SYNTHETIC (see tests/synthetic.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from synthetic import SyntheticSecom, make_synthetic, write_secom_files


@pytest.fixture(scope="session")
def synthetic() -> SyntheticSecom:
    return make_synthetic()


@pytest.fixture(scope="session")
def synthetic_dir(tmp_path_factory: pytest.TempPathFactory, synthetic: SyntheticSecom) -> Path:
    return write_secom_files(tmp_path_factory.mktemp("synthetic_secom"), synthetic)
