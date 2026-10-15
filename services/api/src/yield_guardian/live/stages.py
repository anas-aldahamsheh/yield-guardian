"""The two stages the orchestrator computes itself: intake (what came in) and final test (were the
warnings right?). Both read only the run input and the earlier stage results."""

import itertools
from collections.abc import Sequence

from yield_guardian.contracts.base import SensorId
from yield_guardian.contracts.runs import (
    N_SENSORS,
    FinalTestResult,
    FinalTestUnit,
    FinalTestWafer,
    IntakeResult,
    SensorRiskResult,
    SensorUnitInput,
    WaferInput,
    WaferPatternResult,
)


def in_time_order(units: Sequence[SensorUnitInput]) -> bool:
    """Every unit has a timestamp and none goes back (equal times are in order). The file order
    is kept as given: the orchestrator never re-sorts."""
    times = [u.timestamp for u in units if u.timestamp is not None]
    if not units or len(times) != len(units):
        return False
    return all(a <= b for a, b in itertools.pairwise(times))


def intake(
    units: Sequence[SensorUnitInput],
    wafers: Sequence[WaferInput],
    unmonitored: Sequence[SensorId],
) -> IntakeResult:
    missing = sum(r is None for u in units for r in u.readings)
    readings = len(units) * N_SENSORS
    times = [u.timestamp for u in units if u.timestamp is not None]
    return IntakeResult(
        units=len(units),
        wafers=len(wafers),
        lots=len({w.lot for w in wafers}),
        sensors=N_SENSORS if units else 0,
        missing_readings=missing,
        missing_share=missing / readings if readings else 0.0,
        first_timestamp=min(times) if times else None,
        last_timestamp=max(times) if times else None,
        in_time_order=in_time_order(units),
        two_sources=bool(units) and bool(wafers),
        unmonitored_sensors=list(unmonitored) if units else [],
    )


def has_results(units: Sequence[SensorUnitInput], wafers: Sequence[WaferInput]) -> bool:
    """The input carries something final test can compare with."""
    return any(u.result is not None for u in units) or any(w.label is not None for w in wafers)


def _count(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def final_test(
    units: Sequence[SensorUnitInput],
    wafers: Sequence[WaferInput],
    risk: SensorRiskResult | None,
    pattern: WaferPatternResult | None,
) -> FinalTestResult:
    """Compare the warnings with the recorded results: units only when the risk stage finished,
    wafers only when the pattern stage finished."""
    unit_rows: list[FinalTestUnit] = []
    if risk is not None:
        flagged = {u.index: u.above_threshold for u in risk.units}
        unit_rows = [
            FinalTestUnit(
                index=i, unit_id=u.unit_id, result=u.result, flagged=flagged.get(i, False)
            )
            for i, u in enumerate(units)
            if u.result is not None
        ]
    wafer_rows: list[FinalTestWafer] = []
    if pattern is not None:
        predicted = {w.index: w.top_label for w in pattern.wafers}
        wafer_rows = [
            FinalTestWafer(
                index=i,
                recorded_label=w.label,
                predicted_label=predicted[i],
                agrees=predicted[i] == w.label,
            )
            for i, w in enumerate(wafers)
            if w.label is not None and i in predicted
        ]
    failed = [u for u in unit_rows if u.result == "fail"]
    failed_flagged = sum(u.flagged for u in failed)
    passed_flagged = sum(u.flagged for u in unit_rows if u.result == "pass")
    agreeing = sum(w.agrees for w in wafer_rows)
    parts: list[str] = []
    if unit_rows:
        parts.append(
            f"Of {_count(len(unit_rows), 'unit')} with a recorded result, {len(failed):,} "
            f"failed; the risk was above the threshold for {failed_flagged:,} of them and for "
            f"{_count(passed_flagged, 'unit')} that passed."
        )
    if wafer_rows:
        parts.append(
            f"The predicted pattern matches the recorded WM-811K label on {agreeing:,} of "
            f"{_count(len(wafer_rows), 'wafer')}."
        )
    return FinalTestResult(
        units=unit_rows,
        wafers=wafer_rows,
        units_with_result=len(unit_rows),
        failed_units=len(failed),
        failed_flagged=failed_flagged,
        passed_flagged=passed_flagged,
        wafers_with_label=len(wafer_rows),
        wafers_agreeing=agreeing,
        summary=" ".join(parts) or "Nothing in the input could be compared.",
    )
