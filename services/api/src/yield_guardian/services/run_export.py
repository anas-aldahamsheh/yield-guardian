"""What the "Your work" actions read out of a run or an investigation, all written by code from
the stored results: two runs side by side, a run's results as CSV, an investigation's report as
Markdown. Nothing here calls a model or adds a number the stored results do not hold."""

import csv
import io
from collections import Counter
from collections.abc import Iterable, Sequence

from yield_guardian.agent.run_results import stage_result
from yield_guardian.contracts.investigation import Investigation
from yield_guardian.contracts.runs import (
    ControlChartsResult,
    FinalTestResult,
    LotResult,
    Run,
    SensorRiskResult,
    WaferPatternResult,
)
from yield_guardian.contracts.workspace import RunComparison, RunSide, StageCompare

CSV_COLUMNS = (
    "record",
    "index",
    "item",
    "lot",
    "wafer",
    "risk",
    "risk_band",
    "risk_above_threshold",
    "risk_validity",
    "t2",
    "spe",
    "chart_level",
    "pattern",
    "pattern_probability",
    "pattern_auto_accepted",
    "unknown_pattern",
    "recorded_result",
    "alarm_id",
    "stage",
    "alarm_kind",
    "severity",
    "value",
    "limit",
    "title",
    "investigation_id",
)
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")

Cell = str | int | float | bool | None


def _cell(value: Cell) -> str:
    """A CSV cell. Text that a spreadsheet would run as a formula is quoted with a leading
    apostrophe (a unit ID from an uploaded file is the user's own text)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    text = str(value)
    return "'" + text if isinstance(value, str) and text.startswith(_FORMULA_START) else text


def _rows(run: Run) -> Iterable[dict[str, Cell]]:
    risk = stage_result(run, SensorRiskResult)
    charts = stage_result(run, ControlChartsResult)
    pattern = stage_result(run, WaferPatternResult)
    final = stage_result(run, FinalTestResult)
    by_chart = {u.index: u for u in charts.units} if charts else {}
    by_risk = {u.index: u for u in risk.units} if risk else {}
    unit_results = {u.index: u.result for u in final.units} if final else {}
    for index in sorted(set(by_chart) | set(by_risk)):
        scored, chart = by_risk.get(index), by_chart.get(index)
        yield {
            "record": "unit",
            "index": index,
            "item": scored.unit_id if scored else (chart.unit_id if chart else None),
            "risk": scored.risk if scored else None,
            "risk_band": scored.band if scored else None,
            "risk_above_threshold": scored.above_threshold if scored else None,
            "risk_validity": scored.validity if scored else None,
            "t2": chart.t2 if chart else None,
            "spe": chart.spe if chart else None,
            "chart_level": chart.level if chart else None,
            "recorded_result": unit_results.get(index),
        }
    for wafer in pattern.wafers if pattern else []:
        yield {
            "record": "wafer",
            "index": wafer.index,
            "item": wafer.source_wafer or f"{wafer.lot}-{wafer.wafer}",
            "lot": wafer.lot,
            "wafer": wafer.wafer,
            "pattern": wafer.top_label,
            "pattern_probability": wafer.top_probability,
            "pattern_auto_accepted": wafer.auto_accepted,
            "unknown_pattern": wafer.is_unknown,
            "recorded_result": wafer.recorded_label,
        }
    for alarm in run.alarms:
        position = alarm.unit_index if alarm.unit_index is not None else alarm.wafer_index
        yield {
            "record": "alarm",
            "index": position,
            "item": alarm.unit_id,
            "lot": alarm.lot,
            "alarm_id": alarm.alarm_id,
            "stage": alarm.stage,
            "alarm_kind": alarm.kind,
            "severity": alarm.severity,
            "value": alarm.value,
            "limit": alarm.limit,
            "title": alarm.title,
            "investigation_id": alarm.investigation_id,
        }


def results_csv(run: Run) -> bytes:
    """One row per sensor unit, per wafer and per alarm (the `record` column says which), with
    the run's computed values. UTF-8 with a byte-order mark, so Excel reads it as UTF-8."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in _rows(run):
        writer.writerow([_cell(row.get(c)) for c in CSV_COLUMNS])
    return ("﻿" + out.getvalue()).encode()


# -- comparing ---------------------------------------------------------------------------------


def turns_red(severity: str, kind: str) -> bool:
    """An alarm that turns its station red, which the alarms rail counts as an alarm; it counts
    every other listed alarm as a warning (the web's `turnsRed`)."""
    return severity == "alarm" and kind != "unknown_pattern"


def side(run: Run) -> RunSide:
    risk = stage_result(run, SensorRiskResult)
    charts = stage_result(run, ControlChartsResult)
    pattern = stage_result(run, WaferPatternResult)
    lots = stage_result(run, LotResult)
    final = stage_result(run, FinalTestResult)
    levels = Counter(u.level for u in charts.units) if charts else Counter()
    wafers = pattern.wafers if pattern else []
    red = sum(turns_red(a.severity, a.kind) for a in run.alarms)
    return RunSide(
        run_id=run.run_id,
        title=run.origin.title,
        created_at=run.created_at,
        status=run.status,
        units=run.units,
        wafers=run.wafers,
        alarms=red,
        warnings=len(run.alarms) - red,
        alarms_not_listed=run.alarms_not_listed,
        units_scored=len(risk.units) if risk else 0,
        units_flagged=sum(u.above_threshold for u in risk.units) if risk else 0,
        units_chart_alarm=levels["alarm"],
        units_chart_warning=levels["warning"],
        wafers_classified=len(wafers),
        wafers_auto_accepted=sum(w.auto_accepted for w in wafers),
        wafers_unknown=sum(w.is_unknown for w in wafers),
        patterns=dict(sorted(Counter(w.top_label for w in wafers).items())),
        lots=len(lots.lots) if lots else 0,
        lots_flagged=sum(lot.flagged for lot in lots.lots) if lots else 0,
        final_test=final.summary if final else None,
    )


def _change(what: str, a: int, b: int) -> str | None:
    if a == b:
        return None
    sign = "+" if b > a else "-"
    return f"{what}: {a:,} → {b:,} ({sign}{abs(b - a):,})."


def compare(a: Run, b: Run, *, same_input: bool) -> RunComparison:
    """Run `b` against run `a`: each stage's status, alarms and warnings, the flagged units and
    wafers, and what changed, in sentences (none when nothing did)."""
    left, right = side(a), side(b)

    def by_stage(run: Run, red: bool) -> Counter[str]:
        return Counter(x.stage for x in run.alarms if turns_red(x.severity, x.kind) is red)

    alarms_a, alarms_b = by_stage(a, True), by_stage(b, True)
    warnings_a, warnings_b = by_stage(a, False), by_stage(b, False)
    stages_b = {s.stage: s for s in b.stages}
    stages = [
        StageCompare(
            stage=s.stage,
            station=s.station,
            a_status=s.status,
            b_status=stages_b[s.stage].status,
            a_alarms=alarms_a[s.stage],
            b_alarms=alarms_b[s.stage],
            a_warnings=warnings_a[s.stage],
            b_warnings=warnings_b[s.stage],
        )
        for s in a.stages
        if s.stage in stages_b
    ]
    changes: list[str] = []
    for what, x, y in (
        ("Units", left.units, right.units),
        ("Wafers", left.wafers, right.wafers),
        ("Alarms", left.alarms, right.alarms),
        ("Warnings", left.warnings, right.warnings),
        ("Units above the risk threshold", left.units_flagged, right.units_flagged),
        ("Units at the T² or SPE alarm level", left.units_chart_alarm, right.units_chart_alarm),
        ("Units at the warning level", left.units_chart_warning, right.units_chart_warning),
        ("Wafers marked unknown", left.wafers_unknown, right.wafers_unknown),
        ("Wafers auto-classified", left.wafers_auto_accepted, right.wafers_auto_accepted),
        ("Lots flagged", left.lots_flagged, right.lots_flagged),
    ):
        if (found := _change(what, x, y)) is not None:
            changes.append(found)
    for stage in stages:
        name = stage.stage.replace("_", " ").capitalize()
        if stage.a_status != stage.b_status:
            changes.append(
                f"{name}: {stage.a_status} in the first, {stage.b_status} in the second."
            )
    for label in sorted(set(left.patterns) | set(right.patterns)):
        found = _change(
            f"Wafers predicted {label}", left.patterns.get(label, 0), right.patterns.get(label, 0)
        )
        if found is not None:
            changes.append(found)
    return RunComparison(a=left, b=right, same_input=same_input, stages=stages, changes=changes)


# -- an investigation's report -----------------------------------------------------------------


def _bullets(lines: Sequence[str]) -> list[str]:
    return [f"- {line}" for line in lines] or ["- None."]


def report_markdown(investigation: Investigation) -> str:
    """The investigation's report as Markdown: the summary, findings and actions with the
    evidence each cites, the hypotheses, the limitations, the checks and the decision."""
    report = investigation.report
    if report is None:
        raise ValueError("the investigation has no report")
    lines = [
        f"# {investigation.title}",
        "",
        f"Investigation {investigation.investigation_id}, started "
        f"{investigation.created_at:%Y-%m-%d %H:%M} UTC from {investigation.trigger.kind} "
        f"{investigation.trigger.ref}. Status: {investigation.status.replace('_', ' ')}.",
        "",
        "## Summary",
        "",
        report.summary,
        "",
        "## Findings",
        "",
        *_bullets(
            [
                f"{f.claim} ({f.strength}; evidence {', '.join(f.evidence_ids)})"
                for f in report.findings
            ]
        ),
        "",
        "## Actions",
        "",
        *_bullets(
            [
                f"{n}. {a.action} ({a.rationale}; evidence {', '.join(a.evidence_ids)})"
                for n, a in enumerate(report.actions, start=1)
            ]
        ),
    ]
    if report.hypotheses:
        lines += ["", "## Hypotheses", ""]
        for h in report.hypotheses:
            lines.append(f"- {h.hypothesis} ({h.assessment.replace('_', ' ')})")
            lines += [f"  - For, {e.evidence_id}: {e.observation}" for e in h.evidence_for]
            lines += [f"  - Against, {e.evidence_id}: {e.observation}" for e in h.evidence_against]
    lines += ["", "## Limitations", "", *_bullets(report.limitations)]
    if investigation.verification is not None:
        v = investigation.verification
        lines += [
            "",
            "## Checks",
            "",
            f"Numbers checked: {v.numbers_checked:,}, matched: {v.numbers_matched:,}. "
            f"Passed: {'yes' if v.passed else 'no'}.",
            *[f"- {i.severity}: {i.message} ({i.location})" for i in v.issues],
        ]
    lines += ["", "## Evidence", ""]
    lines += _bullets([f"{e.evidence_id}: {e.summary}" for e in investigation.evidence])
    if investigation.decision is not None:
        d = investigation.decision
        lines += [
            "",
            "## Decision",
            "",
            f"{d.verdict.capitalize()} by {d.decided_by} on {d.decided_at:%Y-%m-%d %H:%M} UTC."
            + (f" Work order {investigation.work_order_id}." if investigation.work_order_id else "")
            + (f" Note: {d.note}" if d.note else ""),
        ]
    return "\n".join(lines) + "\n"
