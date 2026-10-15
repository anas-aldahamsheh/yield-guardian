"""Upload helpers: kind detection, the summary's size guards and issue cap, file names, and the
attribution read from the real ATTRIBUTION.md files."""

import base64

from tests.live.doubles import SECOM_DATA, WAFERMAP_DEMO, small_wafer
from yield_guardian.contracts.runs import MAX_DIES, UploadIssue, WaferInput
from yield_guardian.contracts.wafer import WaferMap
from yield_guardian.live.protocols import Parsed
from yield_guardian.live.uploads import (
    MAX_ISSUES,
    SENSOR_HEADER,
    WAFER_HEADER,
    Attribution,
    clean_filename,
    detect_kind,
    peek_header,
    summary_of,
    template,
)


def full_wafer(n: int) -> WaferInput:
    """A 512 x 512 map built in the test, every cell a passing die."""
    cells = base64.b64encode(b"\x01" * 512 * 512).decode()
    return WaferInput(lot="T1", wafer=n, map=WaferMap(height=512, width=512, cells=cells))


def test_the_kind_is_read_from_the_header() -> None:
    assert detect_kind(SENSOR_HEADER) == "sensors"
    assert detect_kind(["Unit_ID", "S001"]) == "sensors"
    assert detect_kind(WAFER_HEADER) == "wafers"
    assert detect_kind(["Lot", "Wafer", "X", "Y"]) == "wafers"
    assert detect_kind(["name", "colour"]) is None
    assert peek_header(template("sensors", "xlsx").content, "t.xlsx") == SENSOR_HEADER
    assert peek_header(b"\xef\xbb\xbflot;wafer;x;y;result\n", "t.csv") == WAFER_HEADER


def test_too_many_dies_is_an_upload_error() -> None:
    wafers = [full_wafer(n) for n in range(1, 9)]
    data, issues, runnable = summary_of("wafers", Parsed(items=wafers, issues=[]))
    assert len(data.wafers) == 8
    assert runnable is False
    assert issues[0].message == (
        f"This file has {8 * 512 * 512:,} dies; the limit is {MAX_DIES:,}. Split the file."
    )
    _, _, fine = summary_of("wafers", Parsed(items=wafers[:7], issues=[]))
    assert fine is True


def test_issues_are_capped_errors_first() -> None:
    warnings = [
        UploadIssue(severity="warning", row=i, column=None, message="w") for i in range(150)
    ]
    errors = [UploadIssue(severity="error", row=i, column="S001", message="e") for i in range(100)]
    _, issues, runnable = summary_of(
        "wafers", Parsed(items=[small_wafer("A", 1)], issues=[*warnings, *errors])
    )
    assert runnable is False
    assert len(issues) == MAX_ISSUES
    assert [i.severity for i in issues[:100]] == ["error"] * 100
    assert issues[-1].message.startswith("51 more problems are not listed")
    _, none, empty = summary_of("sensors", Parsed(items=[], issues=[]))
    assert empty is False
    assert none[0].message == "The file has no units to run."


def test_file_names_keep_only_the_name() -> None:
    assert clean_filename("C:\\Users\\me\\units.csv") == "units.csv"
    assert clean_filename("../../etc/units.csv") == "units.csv"
    assert clean_filename("a\x00b.csv") == "ab.csv"
    assert clean_filename(None) == "upload"
    assert len(clean_filename("x" * 400 + ".csv")) == 255


def test_attribution_comes_from_the_real_files() -> None:
    found = Attribution.load(
        SECOM_DATA / "ATTRIBUTION.md", (WAFERMAP_DEMO / "ATTRIBUTION.md").read_text()
    )
    assert found.secom is not None
    assert found.wafermap is not None
    assert found.secom.citation.startswith("McCann, M. and Johnston, A. (2008). SECOM [Dataset].")
    assert found.secom.doi == "https://doi.org/10.24432/C54305"
    assert found.secom.licence.startswith("Creative Commons Attribution 4.0")
    assert found.wafermap.doi == "https://doi.org/10.1109/TSM.2014.2364237"
    assert "CC0-1.0" in found.wafermap.licence
    assert Attribution.load(None, None) == Attribution(secom=None, wafermap=None)
