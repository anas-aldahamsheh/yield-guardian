import math
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from yield_guardian.contracts.base import Estimate, Problem
from yield_guardian.contracts.investigation import (
    Finding,
    InvestigationEvent,
    NumberRef,
    StatusEvent,
)
from yield_guardian.contracts.services import NotFoundError, NotReadyError, ServiceError
from yield_guardian.contracts.wafer import WaferSummary

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def test_estimate_rejects_nan_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Estimate(value=math.nan, ci_low=0.1, ci_high=0.2)
    with pytest.raises(ValidationError):
        Estimate.model_validate({"value": 0.4, "ci_low": 0.3, "ci_high": 0.5, "extra": 1})


def test_estimate_defaults_to_95_percent() -> None:
    assert Estimate(value=0.4, ci_low=0.3, ci_high=0.5).ci_level == 0.95


def test_contracts_are_immutable() -> None:
    e = Estimate(value=0.4, ci_low=0.3, ci_high=0.5)
    with pytest.raises(ValidationError):
        e.value = 0.9  # type: ignore[misc]


@pytest.mark.parametrize(
    ("wafer_id", "ok"),
    [("lot47542-12", True), ("lot1-1", True), ("lot1", False), ("lot 1-1", False), ("-1", False)],
)
def test_wafer_id_pattern(wafer_id: str, ok: bool) -> None:
    data = {
        "wafer_id": wafer_id,
        "lot": "lot1",
        "wafer_index": 1,
        "die_size": 533,
        "height": 26,
        "width": 26,
        "label": None,
        "official_split": None,
        "predicted_label": None,
        "unknown": None,
    }
    if ok:
        WaferSummary.model_validate(data)
    else:
        with pytest.raises(ValidationError):
            WaferSummary.model_validate(data)


def test_finding_needs_evidence() -> None:
    with pytest.raises(ValidationError):
        Finding(claim="S060 readings are higher in failed units.", evidence_ids=[], strength="weak")


@pytest.mark.parametrize(
    ("path", "ok"), [("/contributions/0/shap", True), ("", True), ("risk", False)]
)
def test_number_path_is_a_json_pointer(path: str, ok: bool) -> None:
    data = {"value": 12.5, "as_written": "12.5%", "unit": "%", "evidence_id": "E1", "path": path}
    if ok:
        NumberRef.model_validate(data)
    else:
        with pytest.raises(ValidationError):
            NumberRef.model_validate(data)


def test_investigation_event_discriminates_on_type() -> None:
    event = InvestigationEvent.model_validate(
        {"type": "status", "seq": 3, "at": NOW.isoformat(), "status": "running"}
    )
    assert isinstance(event.root, StatusEvent)
    with pytest.raises(ValidationError):
        InvestigationEvent.model_validate({"type": "unknown", "seq": 1, "at": NOW.isoformat()})


def test_service_errors_map_to_problems() -> None:
    problem = NotFoundError("Unit 99999 does not exist.").problem(instance="/api/v1/units/99999")
    assert problem == Problem(
        title="Not found",
        status=404,
        detail="Unit 99999 does not exist.",
        instance="/api/v1/units/99999",
        code="not_found",
    )
    assert NotReadyError("x").problem().status == 503
    assert issubclass(NotReadyError, ServiceError)
