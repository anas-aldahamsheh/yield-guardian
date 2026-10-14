# ruff: noqa: S106  (synthetic CSRF tokens in fixtures, not secrets)
"""Write synthetic example responses for development and tests.

Every value here is made up to exercise the interface. None of it is a SECOM or WM-811K result,
and none of it may be shown to users. Each fixture is built from the API's Pydantic models, so it
always matches the contract. Model profiles in get_model_catalog.json come from
docs/vendor/token-factory.md and are the only documented facts here.

Run from services/api:  uv run python ../../packages/contracts/scripts/make_fixtures.py
"""

import base64
import hashlib
import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from yield_guardian.contracts.base import BundleRef, Estimate
from yield_guardian.contracts.chat import (
    ChatCitationEvent,
    ChatDoneEvent,
    ChatEvent,
    ChatRouteEvent,
    ChatTokenEvent,
    ChatToolEvent,
)
from yield_guardian.contracts.investigation import (
    Action,
    ClaimVerdict,
    Decision,
    EndEvent,
    Evidence,
    EvidenceEvent,
    Finding,
    Investigation,
    InvestigationEvent,
    InvestigationPage,
    InvestigationStep,
    InvestigationSummary,
    InvestigationTrigger,
    NumberRef,
    Report,
    ReportEvent,
    RoleModel,
    StatusEvent,
    StepEvent,
    Verification,
    VerificationEvent,
    VerificationIssue,
)
from yield_guardian.contracts.knowledge import (
    KnowledgeHit,
    KnowledgeSearchResult,
    KnowledgeSource,
    PatternCause,
    PatternCauses,
    SourceQuote,
)
from yield_guardian.contracts.line import (
    Alarm,
    AlarmPage,
    LineAlarmMessage,
    LineCycle,
    LineEvent,
    LineFinalTestMessage,
    LineHeartbeat,
    LineHello,
    LineKpis,
    LineState,
    LineUnitMessage,
    OperatingPointRef,
    PlantClock,
    UnitSummary,
)
from yield_guardian.contracts.meta import Features, Meta
from yield_guardian.contracts.methods import (
    BundleInfo,
    DatasetCard,
    DatasetFile,
    MeasuredResult,
    MeasuredResults,
    MethodsOverview,
    ModelCard,
    ModelCardRef,
)
from yield_guardian.contracts.models import (
    CallUsage,
    CatalogModel,
    EvaluationResult,
    Evaluations,
    LlmCall,
    ModelUsage,
    Pricing,
    Quota,
    RoleAssignment,
    RoleUsage,
    Usage,
    UsageReport,
)
from yield_guardian.contracts.secom import (
    BlockInfo,
    Calibration,
    CurvePoint,
    CvFold,
    Explanation,
    FdcContribution,
    FdcContributions,
    FdcLimits,
    FdcPoint,
    FdcSeries,
    FdcValidation,
    GroupContribution,
    GroupingMethod,
    HealthCounts,
    HealthWindow,
    MetricValue,
    MissingnessTest,
    ModelResult,
    OperatingPoint,
    OperatingPoints,
    PairedComparison,
    ReferencePeriod,
    ReliabilityBin,
    SecomMetrics,
    SensorGroup,
    SensorGroups,
    SensorHealth,
    SensorHealthReport,
    SensorPoint,
    SensorReference,
    SensorSeries,
    ShapContribution,
    Tuning,
    UnitDetail,
    UnitPage,
    UnitRisk,
    UnivariateTest,
)
from yield_guardian.contracts.session import SessionInfo
from yield_guardian.contracts.wafer import (
    AutoClassification,
    ClassMetrics,
    ClassProbability,
    ConfusionMatrix,
    LeaveOneClassOut,
    LotDetail,
    LotPage,
    LotSummary,
    OodMetrics,
    PatternTest,
    PublishedResult,
    SeedResult,
    SimilarWafer,
    SimilarWafers,
    SpatialTest,
    SplitResult,
    StackedMap,
    UnknownScore,
    WaferCalibration,
    WaferDetail,
    WaferHero,
    WaferLabel,
    WaferMap,
    WaferMetrics,
    WaferPage,
    WaferPrediction,
    WaferSummary,
)
from yield_guardian.contracts.workorders import AuditEntry, AuditPage, WorkOrder, WorkOrderPage

OUT = Path(__file__).resolve().parents[1] / "fixtures"
DATA = Path(__file__).resolve().parents[3] / "data" / "secom"
SYNTHETIC = "Placeholder model output for interface development; replaced by the real bundle."
rng = np.random.default_rng(20261014)


def load_secom() -> tuple[np.ndarray, list[datetime], np.ndarray]:
    """Real SECOM rows: readings [units, 590] with NaN, timestamps (UTC) and labels (1 = fail)."""
    readings = np.loadtxt(DATA / "secom.data")
    stamps: list[datetime] = []
    labels: list[int] = []
    for line in (DATA / "secom_labels.data").read_text(encoding="ascii").splitlines():
        label, stamp = line.split(" ", 1)
        labels.append(int(label))
        stamps.append(datetime.strptime(stamp.strip('"'), "%d/%m/%Y %H:%M:%S").replace(tzinfo=UTC))
    return readings, stamps, np.array(labels)


READINGS, ROW_TIMES, ROW_LABELS = load_secom()
ORDER = np.array(sorted(range(len(ROW_TIMES)), key=lambda r: (ROW_TIMES[r], r)))
N_UNITS = len(ORDER)
POSITION = 1100
SECONDS_PER_UNIT = 6.0
LAG = 25
CYCLE = 22
EPOCH = datetime(2026, 10, 12, tzinfo=UTC)
NOW = EPOCH + timedelta(seconds=(CYCLE * N_UNITS + POSITION) * SECONDS_PER_UNIT)
T0 = datetime(2008, 7, 19, 11, 55, tzinfo=UTC)
COMMIT = "0000000000000000000000000000000000000000"
SECOM_BUNDLE = BundleRef(name="secom", version="v1", created_at=NOW, git_commit=COMMIT)
WAFER_BUNDLE = BundleRef(name="wafermap", version="v1", created_at=NOW, git_commit=COMMIT)
LIMITS = FdcLimits(t2_99=26.2, t2_999=32.9, spe_99=41.0, spe_999=55.3)
OP = OperatingPointRef(id="fpr_0.05", label="5% false-alarm rate", threshold=0.15)
FOCUS_SEQ = max(s for s in range(POSITION - LAG - 10) if ROW_LABELS[ORDER[s]] == 1)
TRAIN_END = round(0.6 * N_UNITS)  # provisional 60/20/20 by time; worker 2 sets the real blocks
VAL_END = round(0.8 * N_UNITS)


def reading(unit_id: int, sensor: str) -> float | None:
    value = float(READINGS[unit_id, int(sensor[1:]) - 1])
    return None if math.isnan(value) else round(value, 6)


def est(
    value: float,
    half: float,
    n: int | None = None,
    method: str = "stratified bootstrap, 2000 resamples",
) -> Estimate:
    lo, hi = value - half, value + half
    return Estimate(
        value=round(value, 4),
        ci_low=round(lo, 4),
        ci_high=round(hi, 4),
        method=method,
        n=n,
        note=SYNTHETIC,
    )


def prob_est(value: float, half: float, n: int | None = None) -> Estimate:
    return Estimate(
        value=round(value, 4),
        ci_low=round(max(0.0, value - half), 4),
        ci_high=round(min(1.0, value + half), 4),
        method="stratified bootstrap, 2000 resamples",
        n=n,
        note=SYNTHETIC,
    )


def write(name: str, value: BaseModel | Sequence[BaseModel]) -> None:
    data: Any
    if isinstance(value, BaseModel):
        data = value.model_dump(mode="json")
    else:
        data = [v.model_dump(mode="json") for v in value]
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- SECOM timeline (synthetic)

times = [ROW_TIMES[r] for r in ORDER]  # real
unit_ids = ORDER  # real row indices
fail = ROW_LABELS[ORDER] == 1  # real final-test results
# Placeholders for model outputs until the SECOM bundle exists: T², SPE, risk.
t2 = rng.chisquare(12, N_UNITS) * 1.1
spe = rng.chisquare(20, N_UNITS) * 1.4
DRIFT_START = POSITION - 80
drift = slice(DRIFT_START, DRIFT_START + 45)
t2[drift] += np.linspace(0, 14, 45)
spe[drift] += np.linspace(0, 20, 45)
t2[FOCUS_SEQ] = 35.8
spe[FOCUS_SEQ] = 47.6
risk = np.clip(rng.beta(1.2, 14, N_UNITS), 0.001, 0.99)
risk[drift] += np.linspace(0.0, 0.12, 45)
risk[FOCUS_SEQ] = 0.184


def block(seq: int) -> str:
    return "train" if seq < TRAIN_END else "validation" if seq < VAL_END else "test"


def unit(seq: int, position: int = POSITION) -> UnitSummary:
    r = None if seq < 60 else round(float(min(risk[seq], 0.99)), 4)
    band = (
        None if r is None else "high" if r >= OP.threshold else "elevated" if r >= 0.08 else "low"
    )
    source = (
        None
        if r is None
        else {"train": "oof", "validation": "validation", "test": "test"}[block(seq)]
    )
    level = (
        "alarm"
        if t2[seq] > LIMITS.t2_999 or spe[seq] > LIMITS.spe_999
        else "warning"
        if t2[seq] > LIMITS.t2_99 or spe[seq] > LIMITS.spe_99
        else "none"
    )
    return UnitSummary(
        unit_id=int(unit_ids[seq]),
        sequence=seq,
        timestamp=times[seq],
        block=block(seq),  # type: ignore[arg-type]
        risk=r,
        risk_source=source,  # type: ignore[arg-type]
        risk_band=band,  # type: ignore[arg-type]
        t2=round(float(t2[seq]), 3),
        spe=round(float(spe[seq]), 3),
        fdc_alarm=level,  # type: ignore[arg-type]
        fdc_period="reference" if seq < 150 else "monitoring",
        ewma_alarm=bool(DRIFT_START + 15 <= seq < DRIFT_START + 45),
        cusum_alarm=bool(DRIFT_START + 20 <= seq < DRIFT_START + 45),
        final_test=("fail" if fail[seq] else "pass") if seq <= position - LAG else None,
    )


units = [unit(s) for s in range(POSITION + 1)]
FOCUS = units[FOCUS_SEQ]

clock = PlantClock(
    epoch=EPOCH,
    now=NOW,
    seconds_per_unit=SECONDS_PER_UNIT,
    units_total=N_UNITS,
    position=POSITION,
    cycle=CYCLE,
    plant_time=times[POSITION],
    final_test_lag_units=LAG,
)


def alarms_for(u: UnitSummary) -> list[Alarm]:
    out: list[Alarm] = []

    def add(
        kind: str, severity: str, value: float | None, limit: float | None, message: str
    ) -> None:
        recent = u.sequence > POSITION - 60
        status = (
            "investigating"
            if u.sequence == FOCUS_SEQ and kind == "t2"
            else "open"
            if recent
            else "closed"
        )
        out.append(
            Alarm(
                alarm_id=f"AL-{u.unit_id}-{kind}",
                unit_id=u.unit_id,
                sequence=u.sequence,
                timestamp=u.timestamp,
                kind=kind,  # type: ignore[arg-type]
                severity=severity,  # type: ignore[arg-type]
                value=value,
                limit=limit,
                message=message,
                status=status,  # type: ignore[arg-type]
                investigation_id="inv_01jae5x9k3m2q7r8s0t1v2w3x4"
                if status == "investigating"
                else None,
            )
        )

    if u.risk_band == "high" and u.risk is not None:
        add(
            "risk",
            "alarm",
            u.risk,
            OP.threshold,
            f"Failure risk {u.risk:.1%} is above the {OP.label} threshold.",
        )
    if u.t2 > LIMITS.t2_99:
        sev = "alarm" if u.t2 > LIMITS.t2_999 else "warning"
        lim = LIMITS.t2_999 if sev == "alarm" else LIMITS.t2_99
        add(
            "t2",
            sev,
            u.t2,
            lim,
            f"T² {u.t2:.1f} is beyond the {'99.9' if sev == 'alarm' else '99'}% limit {lim:.1f}.",
        )
    if u.spe > LIMITS.spe_99:
        sev = "alarm" if u.spe > LIMITS.spe_999 else "warning"
        lim = LIMITS.spe_999 if sev == "alarm" else LIMITS.spe_99
        add(
            "spe",
            sev,
            u.spe,
            lim,
            f"SPE {u.spe:.1f} is beyond the {'99.9' if sev == 'alarm' else '99'}% limit {lim:.1f}.",
        )
    if u.sequence == DRIFT_START + 15:
        add(
            "ewma",
            "warning",
            None,
            None,
            "EWMA of the leading sensor groups left its control band.",
        )
    if u.sequence == DRIFT_START + 20:
        add(
            "cusum",
            "warning",
            None,
            None,
            "CUSUM of the leading sensor groups crossed its decision interval.",
        )
    return out


all_alarms = [a for u in units for a in alarms_for(u)]
open_alarms = sorted((a for a in all_alarms if a.status != "closed"), key=lambda a: -a.sequence)


def kpis(window: list[UnitSummary]) -> LineKpis:
    return LineKpis(
        window_units=len(window),
        high_risk=sum(u.risk_band == "high" for u in window),
        elevated_risk=sum(u.risk_band == "elevated" for u in window),
        fdc_warnings=sum(u.fdc_alarm == "warning" for u in window),
        fdc_alarms=sum(u.fdc_alarm == "alarm" for u in window),
        failures_revealed=sum(u.final_test == "fail" for u in window),
    )


recent = units[-120:]
line_state = LineState(
    clock=clock, operating_point=OP, recent=recent, kpis=kpis(recent), open_alarms=open_alarms[:20]
)
write("get_line_state", line_state)
write(
    "list_alarms",
    AlarmPage(
        items=sorted(all_alarms, key=lambda a: -a.sequence)[:50],
        next_cursor="50",
        total=len(all_alarms),
    ),
)
write("list_units", UnitPage(items=units[:200], next_cursor="200", total=len(units)))

next_unit = unit(POSITION + 1, POSITION + 1)
write(
    "line_socket",
    [
        LineEvent(LineHello(type="hello", state=line_state)),
        LineEvent(
            LineUnitMessage(
                type="unit",
                clock=clock.model_copy(update={"position": POSITION + 1}),
                unit=next_unit,
            )
        ),
        LineEvent(LineAlarmMessage(type="alarm", alarm=open_alarms[0])),
        LineEvent(
            LineFinalTestMessage(
                type="final_test",
                unit_id=units[POSITION + 1 - LAG].unit_id,
                sequence=POSITION + 1 - LAG,
                result="pass",
            )
        ),
        LineEvent(LineHeartbeat(type="heartbeat", clock=clock)),
        LineEvent(
            LineCycle(
                type="cycle", clock=clock.model_copy(update={"position": 0, "cycle": CYCLE + 1})
            )
        ),
    ],
)

# ---------------------------------------------------------------- unit detail, SHAP, FDC

REF_SEQS = np.array([q for q in range(150) if not fail[q]])  # passing units in the first 150


def reference_values(sensor: str) -> np.ndarray:
    values = READINGS[ORDER[REF_SEQS], int(sensor[1:]) - 1]
    return values[~np.isnan(values)]


def reference_median(sensor: str) -> float | None:
    values = reference_values(sensor)
    return round(float(np.median(values)), 6) if values.size else None


focus_risk = UnitRisk(
    unit_id=FOCUS.unit_id,
    block=FOCUS.block,
    risk=FOCUS.risk,
    risk_source=FOCUS.risk_source,
    risk_band=FOCUS.risk_band,
    operating_point=OP,
    above_threshold=True,
    note=SYNTHETIC,
)
focus_alarms = [a for a in all_alarms if a.unit_id == FOCUS.unit_id]
unit_detail = UnitDetail(
    **FOCUS.model_dump(),
    risk_detail=focus_risk,
    sensors_measured=int(np.isfinite(READINGS[FOCUS.unit_id]).sum()),
    sensors_missing=int(np.isnan(READINGS[FOCUS.unit_id]).sum()),
    explanation_available=True,
    alarms=focus_alarms,
    investigation_ids=["inv_01jae5x9k3m2q7r8s0t1v2w3x4"],
)
write("get_unit", unit_detail)
write("get_unit_risk", focus_risk)

groups_of = {
    "S060": "G01",
    "S061": "G01",
    "S104": "G02",
    "S130": "G03",
    "S026": "G04",
    "S034": "G05",
}
shap_sensors = [
    "S060",
    "S104",
    "S130",
    "S061",
    "S026",
    "S034",
    "S487",
    "S211",
    "S348",
    "S065",
    "S590",
    "S435",
    "S090",
    "S029",
    "S511",
]
shap_values = [
    0.62,
    0.41,
    -0.33,
    0.29,
    0.22,
    0.18,
    -0.15,
    0.12,
    0.09,
    -0.08,
    0.07,
    0.06,
    -0.05,
    0.04,
    0.03,
]
contribs = [
    ShapContribution(
        feature=s if i != 6 else f"{s}__missing",
        sensor=s,
        kind="reading" if i != 6 else "missing_indicator",
        value=reading(FOCUS.unit_id, s) if i != 6 else float(reading(FOCUS.unit_id, s) is None),
        shap=v,
        group_id=groups_of.get(s),
    )
    for i, (s, v) in enumerate(zip(shap_sensors, shap_values, strict=True))
]
base_value = -2.65
other_shap = 0.19
raw = base_value + sum(shap_values) + other_shap
explanation = Explanation(
    unit_id=FOCUS.unit_id,
    risk=FOCUS.risk,
    base_value=base_value,
    raw_score=round(raw, 4),
    contributions=contribs,
    other_features=401,
    other_shap=other_shap,
    groups=[
        GroupContribution(group_id="G01", sensors=["S060", "S061"], shap=0.91),
        GroupContribution(group_id="G02", sensors=["S104"], shap=0.41),
        GroupContribution(group_id="G03", sensors=["S130"], shap=-0.33),
    ],
    method="TreeSHAP (LightGBM pred_contrib), exact for tree models",
)
write("get_unit_explanation", explanation)

fdc_contribs = [
    FdcContribution(
        sensor=s,
        contribution=c,
        share=sh,
        value=reading(FOCUS.unit_id, s),
        reference_median=reference_median(s),
    )
    for s, c, sh in [
        ("S060", 9.1, 0.254),
        ("S061", 6.3, 0.176),
        ("S104", 4.0, 0.112),
        ("S026", 2.9, 0.081),
        ("S348", 2.2, 0.061),
        ("S211", 1.6, 0.045),
    ]
]
contributions = FdcContributions(
    unit_id=FOCUS.unit_id,
    statistic="t2",
    value=FOCUS.t2,
    limit_99=LIMITS.t2_99,
    limit_999=LIMITS.t2_999,
    alarm=FOCUS.fdc_alarm,
    contributions=fdc_contribs,
    other_share=round(1 - sum(c.share for c in fdc_contribs), 3),
    method="Per-sensor contributions to Hotelling T² of a PCA model fit on the reference period",
)
write("get_unit_contributions", contributions)

reference = ReferencePeriod(
    start=times[int(REF_SEQS[0])],
    end=times[int(REF_SEQS[-1])],
    units=len(REF_SEQS),
    stationarity="Placeholder: worker 2 reports the stationarity test of the real reference period.",
)
fdc_series = FdcSeries(
    limits=LIMITS,
    n_components=12,
    explained_variance=0.902,
    features=438,
    reference=reference,
    points=[
        FdcPoint(
            unit_id=u.unit_id,
            sequence=u.sequence,
            timestamp=u.timestamp,
            t2=u.t2,
            spe=u.spe,
            fdc_alarm=u.fdc_alarm,
            fdc_period=u.fdc_period,
            ewma_alarm=u.ewma_alarm,
            cusum_alarm=u.cusum_alarm,
        )
        for u in units
    ],
    method="PCA on robust-scaled reference data (90% variance, parallel analysis), T² limit from the F distribution, SPE limit by Jackson-Mudholkar",
)
write("get_fdc_series", fdc_series)

# ---------------------------------------------------------------- sensor groups and health

group_rows = [
    ("G01", ["S060", "S061", "S062"], "S060", 0.214, 0.97, 0.004, 0.021),
    ("G02", ["S104"], "S104", 0.133, 0.91, 0.009, 0.032),
    ("G03", ["S130", "S131"], "S130", 0.101, 0.84, 0.012, 0.036),
    ("G04", ["S026", "S027", "S028", "S029"], "S026", 0.088, 0.78, 0.021, 0.049),
    ("G05", ["S034"], "S034", 0.064, 0.66, 0.048, 0.101),
    ("G06", ["S487", "S488"], "S487", 0.051, 0.52, 0.090, 0.150),
    ("G07", ["S211"], "S211", 0.043, 0.41, 0.160, 0.214),
    ("G08", ["S348", "S349"], "S348", 0.039, 0.33, 0.240, 0.270),
]
groups = [
    SensorGroup(
        group_id=g,
        sensors=sensors,
        representative=rep,
        importance=imp,
        stability=stab,
        p_value=p,
        q_value=q,
        significant=q < 0.05,
        stable=stab >= 0.7,
        univariate=[
            UnivariateTest(
                sensor=s,
                mann_whitney_p=round(p * 0.5, 4),
                q_value=round(min(1.0, q * 0.9), 4),
                direction="higher_in_failures" if i % 2 == 0 else "lower_in_failures",
            )
            for i, s in enumerate(sensors)
        ],
    )
    for g, sensors, rep, imp, stab, p, q in group_rows
]
sensor_groups = SensorGroups(
    method=GroupingMethod(
        correlation="spearman",
        threshold=0.8,
        linkage="average",
        stability_refits=100,
        stability_threshold=0.7,
        permutations=200,
        fdr_q=0.05,
    ),
    groups=groups,
    sensors_total=590,
    significant_groups=sum(g.significant for g in groups),
    sensors_in_significant_groups=sum(len(g.sensors) for g in groups if g.significant),
    wording="Statistically associated with failure in held-out data; association, not causation.",
)
write("get_sensor_groups", sensor_groups)

# Sensor health computed from the real readings with the rules of PLAN 6.4, applied provisionally
# here; worker 2's health.json replaces these values when the SECOM bundle exists.
WEEK0 = times[0].replace(hour=0, minute=0, second=0)
window_of = np.array([(t - WEEK0).days // 7 for t in times])
n_windows = int(window_of.max()) + 1
windows = [
    HealthWindow(
        window_id=w,
        start=WEEK0 + timedelta(days=7 * w),
        end=WEEK0 + timedelta(days=7 * (w + 1)),
        units=int((window_of == w).sum()),
    )
    for w in range(n_windows)
]
X = READINGS[ORDER]


def _log_choose(n: int, k: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Exact two-sided p-value of the 2x2 table [[a, b], [c, d]] (sum of tables as likely or less)."""
    row1, col1, n = a + b, a + c, a + b + c + d
    lo, hi = max(0, row1 + col1 - n), min(row1, col1)
    base = _log_choose(n, col1)

    def logp(x: int) -> float:
        return _log_choose(row1, x) + _log_choose(n - row1, col1 - x) - base

    observed = logp(a)
    total = sum(math.exp(logp(x)) for x in range(lo, hi + 1) if logp(x) <= observed + 1e-9)
    return min(1.0, total)


def bh(pvalues: list[float]) -> list[float]:
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    q = [0.0] * len(pvalues)
    running = 1.0
    for rank in range(len(order), 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * len(pvalues) / rank)
        q[i] = running
    return q


rows: list[dict[str, Any]] = []
for j in range(X.shape[1]):
    sid = f"S{j + 1:03d}"
    col = X[:, j]
    missing = np.isnan(col)
    present = col[~missing]
    never = present.size == 0
    constant = not never and float(present.max()) == float(present.min())
    by_window = [
        round(float(missing[window_of == w].mean()), 4) if (window_of == w).any() else None
        for w in range(n_windows)
    ]
    flat = [
        w
        for w in range(n_windows)
        if (vals := col[(window_of == w) & ~missing]).size >= 2 and float(np.ptp(vals)) == 0.0
    ]
    jumps: list[int] = []
    oor: float | None = None
    if not never and not constant:
        idx = np.where(~missing)[0]
        diffs = np.diff(col[idx])
        med = float(np.median(diffs))
        mad = float(np.median(np.abs(diffs - med))) * 1.4826
        if mad > 0:
            jumps = [int(ORDER[idx[k + 1]]) for k in np.where(np.abs(diffs - med) / mad > 6)[0]]
        ref = reference_values(sid)
        if ref.size >= 10 and float(np.ptp(ref)) > 0:
            q01, q99 = np.quantile(ref, [0.01, 0.99])
            oor = round(float(((present < q01) | (present > q99)).mean()), 4)
    test = None
    if 0 < int(missing.sum()) < len(col):
        a = int((missing & fail).sum())
        b = int((missing & ~fail).sum())
        c = int((~missing & fail).sum())
        d = int((~missing & ~fail).sum())
        odds = (a * d) / (b * c) if b * c > 0 else None
        test = (odds, fisher_two_sided(a, b, c, d))
    reasons: list[str] = []
    if never:
        status, reasons = "dead", ["Never measured"]
    elif constant:
        status, reasons = "dead", ["Constant over the whole period"]
    else:
        if len(flat) >= 2:
            reasons.append(f"Flat line in {len(flat)} weeks")
        if oor is not None and oor > 0.10:
            reasons.append(f"{oor:.0%} of readings outside the reference range")
        status = "maintenance" if reasons else "ok"
        if status == "ok":
            if any(m is not None and m > 0.05 for m in by_window):
                reasons.append("Missing rate above 5% in at least one week")
            if jumps:
                reasons.append(f"{len(jumps)} sudden jumps (robust z above 6)")
            status = "watch" if reasons else "ok"
    rows.append(
        {
            "sensor": sid,
            "status": status,
            "reasons": reasons,
            "missing_rate": round(float(missing.mean()), 4),
            "missing_by_window": by_window,
            "flatline_windows": flat,
            "stuck_value": round(float(present[0]), 6) if constant else None,
            "jump_unit_ids": jumps[:20],
            "out_of_reference_rate": oor,
            "test": test,
        }
    )
tested = [r for r in rows if r["test"] is not None]
for r, q in zip(tested, bh([r["test"][1] for r in tested]), strict=True):
    r["q"] = q
health_rows = [
    SensorHealth(
        sensor=r["sensor"],
        status=r["status"],
        reasons=r["reasons"],
        missing_rate=r["missing_rate"],
        missing_by_window=r["missing_by_window"],
        flatline_windows=r["flatline_windows"],
        stuck_value=r["stuck_value"],
        jump_unit_ids=r["jump_unit_ids"],
        out_of_reference_rate=r["out_of_reference_rate"],
        missing_vs_failure=None
        if r["test"] is None
        else MissingnessTest(
            odds_ratio=None if r["test"][0] is None else round(r["test"][0], 4),
            p_value=round(r["test"][1], 6),
            q_value=round(r["q"], 6),
        ),
    )
    for r in rows
]
counts = {k: sum(r["status"] == k for r in rows) for k in ("ok", "watch", "maintenance", "dead")}
write(
    "get_sensor_health",
    SensorHealthReport(
        windows=windows,
        sensors=health_rows,
        counts=HealthCounts(**counts),
        rules=[
            "dead: never measured, or constant over the whole period",
            "maintenance: flat line in two or more weeks, or more than 10% of readings outside the 1st to 99th percentile of the reference period",
            "watch: missing rate above 5% in a week, or a jump with robust z above 6 in the first difference",
            "ok: none of the above",
            "Provisional rules applied to the real readings for interface development; the SECOM bundle's health.json replaces them.",
        ],
    ),
)
SERIES_SENSOR = "S060"
series_ref = reference_values(SERIES_SENSOR)
write(
    "get_sensor_series",
    SensorSeries(
        sensor=SERIES_SENSOR,
        status=next(r["status"] for r in rows if r["sensor"] == SERIES_SENSOR),
        group_id="G01",
        reference=SensorReference(
            median=round(float(np.median(series_ref)), 6),
            q01=round(float(np.quantile(series_ref, 0.01)), 6),
            q99=round(float(np.quantile(series_ref, 0.99)), 6),
        ),
        points=[
            SensorPoint(
                unit_id=u.unit_id,
                sequence=u.sequence,
                timestamp=u.timestamp,
                value=reading(u.unit_id, SERIES_SENSOR),
            )
            for u in units
        ],
    ),
)

# ---------------------------------------------------------------- operating points and metrics

TEST_FAILURES = int(fail[VAL_END:].sum())  # real count in the provisional test block
TEST_PASSES = N_UNITS - VAL_END - TEST_FAILURES


def confusion(recall: float, fpr: float) -> dict[str, int]:
    """Placeholder rates turned into counts that add up to the real test-block totals."""
    tp = round(recall * TEST_FAILURES)
    fp = round(fpr * TEST_PASSES)
    return {"tp": tp, "fn": TEST_FAILURES - tp, "fp": fp, "tn": TEST_PASSES - fp}


curve = []
for thr in np.linspace(0.01, 0.6, 40):
    fpr = float(math.exp(-thr * 18))
    rec = float(min(1.0, math.exp(-thr * 5.5)))
    prec = float(min(1.0, 0.07 + 0.6 * thr))
    curve.append(
        CurvePoint(
            threshold=round(float(thr), 4),
            fpr=round(fpr, 4),
            recall=round(rec, 4),
            precision=round(prec, 4),
        )
    )
points = [
    OperatingPoint(
        id="fpr_0.05",
        label="5% false-alarm rate",
        threshold=0.15,
        target_fpr=0.05,
        fpr=prob_est(0.061, 0.025, 288),
        recall=prob_est(0.42, 0.21, 19),
        precision=prob_est(0.31, 0.15, 26),
        false_alarms_per_100=est(5.7, 2.4, 307),
        **confusion(0.42, 0.061),
    ),
    OperatingPoint(
        id="fpr_0.10",
        label="10% false-alarm rate",
        threshold=0.11,
        target_fpr=0.10,
        fpr=prob_est(0.108, 0.034, 288),
        recall=prob_est(0.58, 0.21, 19),
        precision=prob_est(0.26, 0.11, 42),
        false_alarms_per_100=est(10.1, 3.3, 307),
        **confusion(0.58, 0.108),
    ),
]
write(
    "get_operating_points",
    OperatingPoints(
        block="test",
        default="fpr_0.05",
        units=N_UNITS - VAL_END,
        failures=TEST_FAILURES,
        prevalence=round(TEST_FAILURES / (N_UNITS - VAL_END), 4),
        points=points,
        curve=curve,
    ),
)


def model_result(
    model: str, label: str, main: bool, pr: float, roc: float, brier: float
) -> ModelResult:
    return ModelResult(
        model=model,
        label=label,
        main=main,
        metrics=[
            MetricValue(metric="pr_auc", label="PR-AUC", estimate=prob_est(pr, 0.09, 307)),
            MetricValue(metric="roc_auc", label="ROC-AUC", estimate=prob_est(roc, 0.08, 307)),
            MetricValue(metric="brier", label="Brier score", estimate=prob_est(brier, 0.01, 307)),
        ],
    )


write(
    "get_secom_metrics",
    SecomMetrics(
        bundle=SECOM_BUNDLE,
        blocks=[
            BlockInfo(
                block=name,  # type: ignore[arg-type]
                start=times[lo],
                end=times[hi - 1],
                units=hi - lo,
                failures=int(fail[lo:hi].sum()),
            )
            for name, lo, hi in (
                ("train", 0, TRAIN_END),
                ("validation", TRAIN_END, VAL_END),
                ("test", VAL_END, N_UNITS),
            )
        ],
        models=[
            model_result("lightgbm", "LightGBM (class weights, Optuna)", True, 0.21, 0.74, 0.055),
            model_result(
                "logistic_regression", "Logistic regression (L2)", False, 0.14, 0.68, 0.059
            ),
            model_result("random_forest", "Balanced random forest", False, 0.16, 0.70, 0.061),
            model_result("prevalence", "No skill (prevalence)", False, 0.062, 0.50, 0.058),
        ],
        comparisons=[
            PairedComparison(
                baseline="logistic_regression",
                metric="pr_auc",
                difference=est(0.07, 0.06, 307, "paired bootstrap, 2000 resamples"),
                p_value=0.03,
            ),
            PairedComparison(
                baseline="random_forest",
                metric="pr_auc",
                difference=est(0.05, 0.07, 307, "paired bootstrap, 2000 resamples"),
                p_value=0.11,
            ),
            PairedComparison(
                baseline="prevalence",
                metric="pr_auc",
                difference=est(0.148, 0.08, 307, "paired bootstrap, 2000 resamples"),
                p_value=0.002,
            ),
        ],
        calibration=Calibration(
            method="platt",
            a=-1.02,
            b=0.31,
            brier=prob_est(0.055, 0.011, 307),
            ece=prob_est(0.021, 0.012, 307),
            bins=[
                ReliabilityBin(
                    bin=b,
                    mean_predicted=round(0.02 + 0.03 * b, 3),
                    observed_rate=round(max(0.0, 0.02 + 0.03 * b + float(rng.normal(0, 0.015))), 3),
                    units=31,
                )
                for b in range(10)
            ],
            caveat="Few failures per bin, so the reliability diagram has wide uncertainty; bins hold equal numbers of units.",
        ),
        tuning=Tuning(
            sampler="Optuna TPE, seed 20261014",
            trials=80,
            objective="mean average precision over rolling-origin folds",
            best_value=0.19,
            best_params={
                "num_leaves": 7,
                "learning_rate": 0.03,
                "min_child_samples": 40,
                "feature_fraction": 0.3,
                "lambda_l2": 8.0,
            },
            folds=[
                CvFold(
                    fold=f,
                    train_units=150 + 50 * f,
                    validation_start=times[150 + 50 * f],
                    validation_end=times[199 + 50 * f],
                    validation_units=50,
                    validation_failures=3 + f % 2,
                    average_precision=round(0.15 + 0.02 * f, 3),
                )
                for f in range(4)
            ],
        ),
        fdc=FdcValidation(
            holdout_units=75,
            false_alarm_rate_99=prob_est(0.013, 0.013, 75),
            false_alarm_rate_999=prob_est(0.0, 0.02, 75),
            ewma="lambda 0.2, L 2.86; in-control ARL 370",
            cusum="k 0.5, h 4.77; in-control ARL 370",
        ),
        limitations=[
            SYNTHETIC,
            "SECOM sensors are anonymous, so groups are reported by ID only.",
            "SECOM has no drift labels; FDC alarms are validated by false-alarm rate only.",
        ],
    ),
)

# ---------------------------------------------------------------- wafer maps (synthetic shapes)


def make_map(kind: str, size: int, seed: int) -> np.ndarray:
    r = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    c = (size - 1) / 2
    d = np.hypot(yy - c, xx - c) / (size / 2)
    cells = np.where(d <= 0.98, 1, 0).astype(np.uint8)
    fail = r.random((size, size)) < 0.02
    if kind == "Edge-Ring":
        fail |= (d > 0.84) & (r.random((size, size)) < 0.8)
    elif kind == "Center":
        fail |= (d < 0.3) & (r.random((size, size)) < 0.85)
    elif kind == "Scratch":
        fail |= (np.abs((yy - c) - 0.6 * (xx - c)) < 0.8) & (d < 0.8)
    elif kind == "Loc":
        fail |= (np.hypot(yy - c * 0.6, xx - c * 1.3) < size * 0.12) & (
            r.random((size, size)) < 0.85
        )
    elif kind == "Edge-Loc":
        fail |= (d > 0.75) & (xx > c * 1.4) & (r.random((size, size)) < 0.85)
    elif kind == "Random":
        fail |= r.random((size, size)) < 0.25
    cells[(cells == 1) & fail] = 2
    return cells


def wafer_map(cells: np.ndarray) -> WaferMap:
    return WaferMap(
        height=int(cells.shape[0]),
        width=int(cells.shape[1]),
        cells=base64.b64encode(cells.tobytes()).decode("ascii"),
    )


def summary(
    lot: str,
    idx: int,
    label: WaferLabel | None,
    predicted: WaferLabel | None,
    size: int,
    split: str | None = "test",
) -> WaferSummary:
    return WaferSummary(
        wafer_id=f"{lot}-{idx}",
        lot=lot,
        wafer_index=idx,
        die_size=int(size * size * 0.75),
        height=size,
        width=size,
        label=label,
        official_split=split,
        predicted_label=predicted,
        unknown=predicted is None,
    )  # type: ignore[arg-type]


LABELS: list[WaferLabel] = [
    "Center",
    "Donut",
    "Edge-Loc",
    "Edge-Ring",
    "Loc",
    "Near-full",
    "Random",
    "Scratch",
    "none",
]


def probabilities(top: WaferLabel, p: float) -> list[ClassProbability]:
    rest = [lab for lab in LABELS if lab != top]
    weights = rng.dirichlet(np.ones(len(rest))) * (1 - p)
    probs = [ClassProbability(label=top, probability=round(p, 4))] + [
        ClassProbability(label=lab, probability=round(float(w), 4))
        for lab, w in zip(rest, weights, strict=True)
    ]
    return sorted(probs, key=lambda c: -c.probability)


def prediction(wafer_id: str, top: WaferLabel, p: float, unknown: bool = False) -> WaferPrediction:
    score = 410.0 if unknown else 120.0
    return WaferPrediction(
        wafer_id=wafer_id,
        top_label=top,
        top_probability=p,
        probabilities=probabilities(top, p),
        temperature=1.42,
        unknown=UnknownScore(
            score=score,
            threshold=270.0,
            is_unknown=unknown,
            in_distribution_recall=0.95,
            energy_score=-3.1 if unknown else -8.7,
        ),
        model=WAFER_BUNDLE,
    )


ATTRIBUTION = "Synthetic map for interface development. Real maps come from WM-811K (Wu, Jang and Chen, 2015, IEEE TSM 28(1)); see demo/ATTRIBUTION.md."
hero_cells = make_map("Edge-Ring", 45, 1)
hero = WaferHero(
    wafer=summary("lot47542", 12, "Edge-Ring", "Edge-Ring", 45),
    map=wafer_map(hero_cells),
    prediction=prediction("lot47542-12", "Edge-Ring", 0.93),
    spatial=SpatialTest(
        statistic=212.0, expected=31.4, p_value=0.001, permutations=999, clustered=True
    ),
    attribution=ATTRIBUTION,
    selection="Synthetic fixture: the first test-split wafer of the most frequent defect class with a confident prediction.",
)
write("get_hero_wafer", hero)
write("get_wafer", WaferDetail(**{k: v for k, v in hero.model_dump().items() if k != "selection"}))
write("get_wafer_prediction", hero.prediction)  # type: ignore[arg-type]

similar_kinds: list[tuple[str, int, WaferLabel, float]] = [
    ("lot47542", 13, "Edge-Ring", 0.96),
    ("lot47542", 7, "Edge-Ring", 0.94),
    ("lot31102", 3, "Edge-Ring", 0.91),
    ("lot28763", 19, "Edge-Loc", 0.86),
    ("lot31102", 4, "Edge-Ring", 0.84),
    ("lot9021", 11, "Edge-Loc", 0.79),
]
write(
    "get_similar_wafers",
    SimilarWafers(
        wafer_id="lot47542-12",
        k=6,
        results=[
            SimilarWafer(
                wafer=summary(lot, idx, lab, lab, 45),
                similarity=sim,
                map=wafer_map(make_map(lab, 45, 100 + i)),
            )
            for i, (lot, idx, lab, sim) in enumerate(similar_kinds)
        ],
        method="Cosine similarity of L2-normalised CNN embeddings (pgvector HNSW)",
        precision_at_10=prob_est(0.88, 0.02, 25519),
    ),
)

lot_kinds: list[WaferLabel] = (
    ["Edge-Ring"] * 9 + ["none"] * 12 + ["Center", "Scratch", "Loc", "Random"]
)
lot_maps = [make_map(k, 45, 200 + i) for i, k in enumerate(lot_kinds)]
lot_wafers = [summary("lot47542", i + 1, k, k, 45) for i, k in enumerate(lot_kinds)]
dies = np.stack([m > 0 for m in lot_maps])
fails = np.stack([m == 2 for m in lot_maps])
with np.errstate(invalid="ignore"):
    freq = fails.sum(0) / dies.sum(0)
frequencies = [
    None if not dies[:, y, x].any() else round(float(freq[y, x]), 4)
    for y in range(45)
    for x in range(45)
]
write(
    "get_lot",
    LotDetail(
        lot="lot47542",
        wafers=lot_wafers,
        tests=[
            PatternTest(
                label="Edge-Ring",
                count=9,
                wafers=25,
                expected_rate=0.058,
                p_value=0.00002,
                q_value=0.0004,
                flagged=True,
            ),
            PatternTest(
                label="Center",
                count=1,
                wafers=25,
                expected_rate=0.026,
                p_value=0.48,
                q_value=0.91,
                flagged=False,
            ),
            PatternTest(
                label="Scratch",
                count=1,
                wafers=25,
                expected_rate=0.007,
                p_value=0.16,
                q_value=0.62,
                flagged=False,
            ),
        ],
        stacked=StackedMap(height=45, width=45, wafers=25, frequencies=frequencies),
        method="One-sided binomial test per pattern against the training-period rate, Benjamini-Hochberg across lots",
    ),
)
write(
    "list_lots",
    LotPage(
        items=[
            LotSummary(
                lot="lot47542",
                wafers=25,
                labelled=25,
                flagged_labels=["Edge-Ring"],
                min_q_value=0.0004,
            ),
            LotSummary(lot="lot31102", wafers=25, labelled=25, flagged_labels=[], min_q_value=0.21),
            LotSummary(
                lot="lot28763",
                wafers=24,
                labelled=24,
                flagged_labels=["Edge-Loc"],
                min_q_value=0.012,
            ),
        ],
        next_cursor=None,
        total=3,
    ),
)
write("list_wafers", WaferPage(items=lot_wafers, next_cursor="25", total=1250))


def split_result(split: str, f1: float, overlap: int | None) -> SplitResult:
    per_class = [
        ClassMetrics(
            label=lab,
            precision=prob_est(f1 + 0.02, 0.03, 500),
            recall=prob_est(f1 - 0.02, 0.03, 500),
            f1=prob_est(f1, 0.03, 500),
            support=500 + 37 * i,
        )
        for i, lab in enumerate(LABELS)
    ]
    counts = [[(480 if i == j else 3) for j in range(9)] for i in range(9)]
    return SplitResult(
        split=split,
        test_wafers=25519,
        macro_f1=prob_est(f1, 0.01, 25519),
        accuracy=prob_est(f1 + 0.05, 0.01, 25519),
        per_class=per_class,
        confusion=ConfusionMatrix(labels=LABELS, counts=counts),
        seeds=[
            SeedResult(seed=s, macro_f1=round(f1 + d, 4))
            for s, d in [(1, -0.004), (2, 0.002), (3, 0.003)]
        ],
        seed_mean=f1,
        seed_sd=0.0036,
        lots_in_both=overlap,
    )  # type: ignore[arg-type]


write(
    "get_wafer_metrics",
    WaferMetrics(
        bundle=WAFER_BUNDLE,
        splits=[split_result("official", 0.86, 112), split_result("lot_grouped", 0.83, 0)],
        baseline=[split_result("official", 0.71, 112)],
        calibration=WaferCalibration(
            temperature=1.42,
            ece_before=prob_est(0.061, 0.006, 25519),
            ece_after=prob_est(0.014, 0.004, 25519),
        ),
        ood=OodMetrics(
            threshold=270.0,
            in_distribution_recall=0.95,
            in_distribution_recall_test=0.94,
            leave_one_class_out=[
                LeaveOneClassOut(held_out=lab, auroc=prob_est(0.7 + 0.03 * i, 0.04, 2000))
                for i, lab in enumerate(LABELS[:-1])
            ],
            mean_auroc=prob_est(0.8, 0.03, 8),
            energy_mean_auroc=prob_est(0.77, 0.03, 8),
            note=SYNTHETIC,
        ),
        similarity_precision_at_10=prob_est(0.88, 0.02, 25519),
        auto_classification=[
            AutoClassification(
                precision_target=0.95,
                confidence_threshold=0.9,
                share=prob_est(0.72, 0.01, 25519),
                precision=prob_est(0.951, 0.004, 18374),
            )
        ],
        published=[
            PublishedResult(
                source="Synthetic fixture source", metric="accuracy", value=0.9, note=SYNTHETIC
            )
        ],
        limitations=[SYNTHETIC],
    ),
)

# ---------------------------------------------------------------- knowledge (placeholders, not real citations)

source = KnowledgeSource(
    source_id="src_fixture_1",
    title="Example source title (synthetic fixture)",
    authors=["Example A."],
    venue="Synthetic fixture",
    year=None,
    doi=None,
    url=None,
    open_access=True,
)
write(
    "get_pattern_causes",
    PatternCauses(
        framing="Hypotheses to check, drawn from published literature; not conclusions about this fab.",
        causes=[
            PatternCause(
                label=lab,
                hypothesis=f"Example hypothesis for {lab} (synthetic fixture).",
                confidence="medium",
                quotes=[
                    SourceQuote(
                        source_id=source.source_id,
                        quote="Example quote for interface development.",
                        location="p. 1",
                    )
                ],
            )
            for lab in LABELS[:-1]
        ],
        sources=[source],
    ),
)
write(
    "search_knowledge",
    KnowledgeSearchResult(
        query="edge ring",
        hits=[
            KnowledgeHit(
                chunk_id="chk_fixture_1",
                source=source,
                location="p. 1",
                snippet="Example snippet for interface development.",
                rank=0.61,
            )
        ],
        method="PostgreSQL full-text search (websearch_to_tsquery, ts_rank_cd)",
    ),
)

# ---------------------------------------------------------------- investigation (synthetic run)

INV = "inv_01jae5x9k3m2q7r8s0t1v2w3x4"
t = NOW - timedelta(minutes=9)


def at(seconds: float) -> datetime:
    return t + timedelta(seconds=seconds)


def evidence(
    eid: str, tool: str, args: dict[str, Any], data: BaseModel, summary_text: str, seconds: float
) -> Evidence:
    return Evidence(
        evidence_id=eid,
        investigation_id=INV,
        tool=tool,
        arguments=args,
        data=data.model_dump(mode="json"),
        summary=summary_text,
        created_at=at(seconds),
        source=SECOM_BUNDLE,
    )  # type: ignore[arg-type]


ev = [
    evidence(
        "E1",
        "get_unit",
        {"unit_id": FOCUS.unit_id},
        unit_detail,
        f"Unit {FOCUS.unit_id}: risk {FOCUS.risk:.1%}, T² {FOCUS.t2:.1f} (alarm).",
        4,
    ),
    evidence(
        "E2",
        "get_contributions",
        {"unit_id": FOCUS.unit_id, "statistic": "t2", "top_k": 6},
        contributions,
        "Top T² contributors: S060, S061, S104.",
        7,
    ),
    evidence(
        "E3",
        "get_shap",
        {"unit_id": FOCUS.unit_id, "top_k": 15},
        explanation,
        "Largest SHAP contribution: S060 (+0.62 log-odds).",
        10,
    ),
    evidence(
        "E4",
        "get_feature_groups",
        {"significant_only": True, "limit": 8},
        sensor_groups,
        "4 sensor groups are significant at q < 0.05.",
        13,
    ),
]
llm_write = CallUsage(
    role="writer",
    model_id="MiMo-V2.6-Flash",
    tokens_in=6120,
    tokens_out=812,
    tokens_reasoning=0,
    points=0.00109,
    latency_ms=4120,
    cached=False,
)
llm_plan = CallUsage(
    role="investigator",
    model_id="DeepSeek-V4.1-Flash",
    tokens_in=3410,
    tokens_out=286,
    tokens_reasoning=120,
    points=0.00056,
    latency_ms=2310,
    cached=False,
)
llm_verify = CallUsage(
    role="verifier",
    model_id="GLM-5.3-Flash",
    tokens_in=5230,
    tokens_out=402,
    tokens_reasoning=260,
    points=0.00099,
    latency_ms=3870,
    cached=False,
)
steps = [
    InvestigationStep(
        index=0,
        node="triage",
        status="completed",
        title=f"Read alarm AL-{FOCUS.unit_id}-t2 on unit {FOCUS.unit_id}",
        started_at=at(0),
        finished_at=at(1),
        tool=None,
        evidence_ids=[],
        llm=[],
    ),
    InvestigationStep(
        index=1,
        node="plan",
        status="completed",
        title="Planned four evidence steps",
        started_at=at(1),
        finished_at=at(3),
        tool=None,
        evidence_ids=[],
        llm=[llm_plan],
    ),
    InvestigationStep(
        index=2,
        node="evidence",
        status="completed",
        title=f"Read unit {FOCUS.unit_id}",
        started_at=at(3),
        finished_at=at(4),
        tool="get_unit",
        evidence_ids=["E1"],
        llm=[],
    ),
    InvestigationStep(
        index=3,
        node="evidence",
        status="completed",
        title="Read the T² contributions",
        started_at=at(4),
        finished_at=at(7),
        tool="get_contributions",
        evidence_ids=["E2"],
        llm=[],
    ),
    InvestigationStep(
        index=4,
        node="evidence",
        status="completed",
        title="Read the SHAP explanation",
        started_at=at(7),
        finished_at=at(10),
        tool="get_shap",
        evidence_ids=["E3"],
        llm=[],
    ),
    InvestigationStep(
        index=5,
        node="evidence",
        status="completed",
        title="Read the significant sensor groups",
        started_at=at(10),
        finished_at=at(13),
        tool="get_feature_groups",
        evidence_ids=["E4"],
        llm=[],
    ),
    InvestigationStep(
        index=6,
        node="write",
        status="completed",
        title="Wrote the report",
        started_at=at(13),
        finished_at=at(18),
        tool=None,
        evidence_ids=[],
        llm=[llm_write],
    ),
    InvestigationStep(
        index=7,
        node="verify",
        status="completed",
        title="Checked 4 numbers and 3 findings against the evidence",
        started_at=at(18),
        finished_at=at(22),
        tool=None,
        evidence_ids=[],
        llm=[llm_verify],
    ),
]
report = Report(
    summary=f"Unit {FOCUS.unit_id} crossed the 99.9% T² limit and has a failure risk of 18.4%. The readings that move T² most belong to sensor group G01 (S060, S061), which is also statistically associated with failure across held-out units.",
    findings=[
        Finding(
            claim=f"Unit {FOCUS.unit_id} has a calibrated failure risk of 18.4%, above the 5% false-alarm threshold.",
            evidence_ids=["E1"],
            strength="strong",
        ),
        Finding(
            claim="S060 explains 25.4% of the unit's T², the largest share of any sensor.",
            evidence_ids=["E2"],
            strength="strong",
        ),
        Finding(
            claim="Group G01 (S060, S061) is statistically associated with failure (q = 0.021); this is an association, not a cause.",
            evidence_ids=["E3", "E4"],
            strength="moderate",
        ),
    ],
    actions=[
        Action(
            action="Inspect the tool behind sensors S060 and S061 before the next lot.",
            rationale="They dominate the T² excursion and form the most important significant group.",
            evidence_ids=["E2", "E4"],
        ),
        Action(
            action="Hold the unit for an extra electrical test.",
            rationale="Its risk is above the operating threshold.",
            evidence_ids=["E1"],
        ),
    ],
    numbers=[
        NumberRef(value=18.4, as_written="18.4%", unit="%", evidence_id="E1", path="/risk"),
        NumberRef(
            value=25.4,
            as_written="25.4%",
            unit="%",
            evidence_id="E2",
            path="/contributions/0/share",
        ),
        NumberRef(
            value=0.021, as_written="0.021", unit=None, evidence_id="E4", path="/groups/0/q_value"
        ),
        NumberRef(
            value=99.9, as_written="99.9%", unit="%", evidence_id="E1", path="/alarms/0/limit"
        ),
    ],
    limitations=[
        "SECOM sensors are anonymous, so the tool behind S060 is not named in the data.",
        "Association, not causation: no work-order outcome confirms a cause yet.",
        SYNTHETIC,
    ],
)
verification = Verification(
    passed=False,
    rounds=1,
    numbers_checked=4,
    numbers_matched=3,
    issues=[
        VerificationIssue(
            code="number_mismatch",
            severity="warning",
            location="numbers[3]",
            message="99.9 is the limit's confidence level, not the value at /alarms/0/limit (32.9). Synthetic example of a flagged issue.",
        )
    ],
    claims=[
        ClaimVerdict(finding_index=0, verdict="supported", note=None),
        ClaimVerdict(finding_index=1, verdict="supported", note=None),
        ClaimVerdict(
            finding_index=2,
            verdict="partially_supported",
            note="The group's q-value supports association only.",
        ),
    ],
    verifier_model="GLM-5.3-Flash",
)
usage = Usage(
    requests=3, tokens_in=14760, tokens_out=1500, tokens_reasoning=380, points=0.00264, cache_hits=0
)
trigger = InvestigationTrigger(kind="alarm", ref=f"AL-{FOCUS.unit_id}-t2", question=None)
models = [
    RoleModel(role="investigator", model_id="DeepSeek-V4.1-Flash"),
    RoleModel(role="writer", model_id="MiMo-V2.6-Flash"),
    RoleModel(role="verifier", model_id="GLM-5.3-Flash"),
]
investigation = Investigation(
    investigation_id=INV,
    title=f"Unit {FOCUS.unit_id}: T² beyond the 99.9% limit",
    status="awaiting_decision",
    trigger=trigger,
    created_at=at(0),
    updated_at=at(22),
    recorded=True,
    models=models,
    usage=usage,
    work_order_id=None,
    steps=steps,
    evidence=ev,
    report=report,
    verification=verification,
    decision=None,
    error=None,
)
write("get_investigation", investigation)
write(
    "create_investigation",
    investigation.model_copy(
        update={
            "status": "queued",
            "steps": [],
            "evidence": [],
            "report": None,
            "verification": None,
            "usage": None,
            "recorded": False,
            "updated_at": at(0),
        }
    ),
)
write("get_evidence", ev[1])
approved = investigation.model_copy(
    update={
        "status": "approved",
        "work_order_id": "WO-000012",
        "decision": Decision(
            verdict="approve",
            actions=[0, 1],
            note="Tool check booked for the next shift.",
            decided_by="Guest engineer",
            decided_at=at(240),
        ),
        "updated_at": at(240),
    }
)
write("decide_investigation", approved)
summaries = [
    InvestigationSummary(
        **{
            k: v
            for k, v in investigation.model_dump().items()
            if k in InvestigationSummary.model_fields
        }
    ),
    InvestigationSummary(
        **{k: v for k, v in approved.model_dump().items() if k in InvestigationSummary.model_fields}
    ).model_copy(
        update={
            "investigation_id": "inv_01jae2kq0c4w6f8h1j3m5n7p9r",
            "title": "Lot lot47542: Edge-Ring above the expected rate",
            "trigger": InvestigationTrigger(kind="lot", ref="lot47542", question=None),
            "created_at": at(-3600),
            "updated_at": at(-3400),
            "work_order_id": "WO-000011",
        }
    ),
]
write("list_investigations", InvestigationPage(items=summaries, next_cursor=None, total=2))

events: list[InvestigationEvent] = []
seq = 0


def push(event: Any) -> None:
    global seq
    seq += 1
    events.append(InvestigationEvent(event.model_copy(update={"seq": seq})))


push(StatusEvent(type="status", seq=0, at=at(0), status="queued"))
push(StatusEvent(type="status", seq=0, at=at(0), status="running"))
for s in steps:
    push(
        StepEvent(
            type="step",
            seq=0,
            at=s.started_at,
            step=s.model_copy(
                update={"status": "running", "finished_at": None, "evidence_ids": [], "llm": []}
            ),
        )
    )
    for e in ev:
        if e.evidence_id in s.evidence_ids:
            push(EvidenceEvent(type="evidence", seq=0, at=e.created_at, evidence=e))
    if s.node == "write":
        push(ReportEvent(type="report", seq=0, at=at(18), round=0, report=report))
    if s.node == "verify":
        push(
            VerificationEvent(
                type="verification", seq=0, at=at(22), round=0, verification=verification
            )
        )
    push(StepEvent(type="step", seq=0, at=s.finished_at or at(22), step=s))
push(StatusEvent(type="status", seq=0, at=at(22), status="awaiting_decision"))
push(EndEvent(type="end", seq=0, at=at(22), status="awaiting_decision"))
write("stream_investigation_events", events)

# ---------------------------------------------------------------- work orders and audit

work_orders = [
    WorkOrder(
        work_order_id="WO-000012",
        investigation_id=INV,
        title=f"Inspect the tool behind S060 and S061 (unit {FOCUS.unit_id})",
        status="open",
        created_at=at(240),
        updated_at=at(240),
        created_by="Guest engineer",
        actions=report.actions,
        note="Tool check booked for the next shift.",
        outcome=None,
        outcome_confirmed=False,
    ),
    WorkOrder(
        work_order_id="WO-000011",
        investigation_id="inv_01jae2kq0c4w6f8h1j3m5n7p9r",
        title="Review the edge exposure on lot lot47542",
        status="done",
        created_at=at(-3400),
        updated_at=at(-600),
        created_by="Guest engineer",
        actions=[
            Action(
                action="Review the edge bead removal step for lot lot47542.",
                rationale="Edge-Ring is above the expected rate in this lot.",
                evidence_ids=["E1"],
            )
        ],
        note=None,
        outcome="Synthetic fixture outcome.",
        outcome_confirmed=True,
    ),
]
write("list_work_orders", WorkOrderPage(items=work_orders, next_cursor=None, total=2))
write("get_work_order", work_orders[0])
write(
    "update_work_order",
    work_orders[0].model_copy(update={"status": "in_progress", "updated_at": at(400)}),
)
audit = [
    AuditEntry(
        audit_id=6,
        at=at(240),
        actor_role="engineer",
        actor_name="Guest engineer",
        action="work_order.created",
        target_kind="work_order",
        target_id="WO-000012",
        details={"investigation_id": INV},
    ),
    AuditEntry(
        audit_id=5,
        at=at(240),
        actor_role="engineer",
        actor_name="Guest engineer",
        action="investigation.approved",
        target_kind="investigation",
        target_id=INV,
        details={"actions": [0, 1]},
    ),
    AuditEntry(
        audit_id=4,
        at=at(0),
        actor_role="system",
        actor_name=None,
        action="investigation.created",
        target_kind="investigation",
        target_id=INV,
        details={"trigger": f"AL-{FOCUS.unit_id}-t2"},
    ),
    AuditEntry(
        audit_id=3,
        at=at(-200),
        actor_role="engineer",
        actor_name="Guest engineer",
        action="session.guest",
        target_kind="session",
        target_id="guest",
        details={},
    ),
    AuditEntry(
        audit_id=2,
        at=at(-600),
        actor_role="engineer",
        actor_name="Guest engineer",
        action="work_order.updated",
        target_kind="work_order",
        target_id="WO-000011",
        details={"status": "done"},
    ),
    AuditEntry(
        audit_id=1,
        at=at(-900),
        actor_role="admin",
        actor_name="admin",
        action="role.updated",
        target_kind="role",
        target_id="verifier",
        details={"model_id": "GLM-5.3-Flash"},
    ),
]
write("list_audit_entries", AuditPage(items=audit, next_cursor=None, total=6))

# ---------------------------------------------------------------- language models (profiles documented in docs/vendor/token-factory.md)

TIERS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
catalog = [
    CatalogModel(
        model_id="DeepSeek-V4-Flash",
        kind="llm",
        context_length=1_048_576,
        inputs=["text"],
        thinks_by_default=False,
        reasoning_efforts=TIERS,
        system_message_rule="any position, several allowed; system or developer",
        json_schema=False,
        tools=True,
        pricing=Pricing(input=0.14, output=0.28, cache_read=0.0028),
        available=True,
        profile="documented",
    ),  # type: ignore[arg-type]
    CatalogModel(
        model_id="DeepSeek-V4.1-Flash",
        kind="vlm",
        context_length=1_048_576,
        inputs=["text", "image"],
        thinks_by_default=False,
        reasoning_efforts=TIERS,
        system_message_rule="any position, several allowed; system or developer",
        json_schema=False,
        tools=True,
        pricing=Pricing(input=0.14, output=0.28, cache_read=0.0028),
        available=True,
        profile="documented",
    ),  # type: ignore[arg-type]
    CatalogModel(
        model_id="DeepSeek-V4-Flash-Vision-Exp",
        kind="vlm",
        context_length=1_048_576,
        inputs=["text", "image"],
        thinks_by_default=False,
        reasoning_efforts=TIERS,
        system_message_rule="any position, several allowed; system or developer",
        json_schema=False,
        tools=True,
        pricing=Pricing(input=0.14, output=0.28, cache_read=0.0028),
        available=True,
        profile="documented",
    ),  # type: ignore[arg-type]
    CatalogModel(
        model_id="MiMo-V2.6-Flash",
        kind="vlm",
        context_length=1_048_576,
        inputs=["text", "image", "audio"],
        thinks_by_default=True,
        reasoning_efforts=TIERS,
        system_message_rule="any position; developer accepted",
        json_schema=True,
        tools=True,
        pricing=Pricing(input=0.14, output=0.28, cache_read=0.0028),
        available=True,
        profile="documented",
    ),  # type: ignore[arg-type]
    CatalogModel(
        model_id="GLM-5.3-Flash",
        kind="llm",
        context_length=262_144,
        inputs=["text"],
        thinks_by_default=True,
        reasoning_efforts=["low", "medium", "high"],
        system_message_rule="any position; system only (developer is rejected)",
        json_schema=False,
        tools=True,
        pricing=Pricing(input=0.15, output=0.50, cache_read=0.03),
        available=True,
        profile="documented",
    ),
    CatalogModel(
        model_id="Qwen3.8-Flash-Next",
        kind="vlm",
        context_length=262_144,
        inputs=["text", "image"],
        thinks_by_default=True,
        reasoning_efforts=["none", "low", "medium", "xhigh"],
        system_message_rule="exactly one system message, first",
        json_schema=False,
        tools=True,
        pricing=Pricing(input=0.15, output=0.47, cache_read=0.016),
        available=True,
        profile="documented",
    ),
    CatalogModel(
        model_id="Qwen3.8-27B",
        kind="vlm",
        context_length=131_072,
        inputs=["text", "image"],
        thinks_by_default=True,
        reasoning_efforts=["low", "medium", "xhigh"],
        system_message_rule="at most one system message, first",
        json_schema=False,
        tools=True,
        pricing=Pricing(input=0.50, output=3.00, cache_read=0.05),
        available=True,
        profile="documented",
    ),
    CatalogModel(
        model_id="MiniCPM5-2B",
        kind="llm",
        context_length=131_072,
        inputs=["text"],
        thinks_by_default=False,
        reasoning_efforts=[],
        system_message_rule="any position; system",
        json_schema=False,
        tools=True,
        pricing=Pricing(input=0.124, output=0.7425, cache_read=0.124),
        available=True,
        profile="documented",
    ),
    CatalogModel(
        model_id="Gemma-4-31B-IT",
        kind="vlm",
        context_length=262_144,
        inputs=["text", "image"],
        thinks_by_default=False,
        reasoning_efforts=[],
        system_message_rule="system as the first message",
        json_schema=False,
        tools=True,
        pricing=Pricing(input=0.50, output=3.00, cache_read=0.05),
        available=True,
        profile="documented",
    ),
    CatalogModel(
        model_id="MinerU2.5-Pro",
        kind="ocr",
        context_length=None,
        inputs=["document", "image"],
        thinks_by_default=None,
        reasoning_efforts=[],
        system_message_rule="not applicable",
        json_schema=False,
        tools=False,
        pricing=None,
        available=True,
        profile="documented",
    ),
]
write("get_model_catalog", catalog)
roles = [
    RoleAssignment(
        role="investigator",
        model_id="DeepSeek-V4.1-Flash",
        reasoning_effort="low",
        fallbacks=["GLM-5.3-Flash", "Qwen3.8-Flash-Next"],
        updated_at=None,
        updated_by=None,
    ),
    RoleAssignment(
        role="writer",
        model_id="MiMo-V2.6-Flash",
        reasoning_effort="low",
        fallbacks=["Qwen3.8-27B"],
        updated_at=None,
        updated_by=None,
    ),
    RoleAssignment(
        role="verifier",
        model_id="GLM-5.3-Flash",
        reasoning_effort="low",
        fallbacks=["DeepSeek-V4-Flash"],
        updated_at=at(-900),
        updated_by="admin",
    ),
    RoleAssignment(
        role="chat",
        model_id="Qwen3.8-Flash-Next",
        reasoning_effort="none",
        fallbacks=["DeepSeek-V4-Flash"],
        updated_at=None,
        updated_by=None,
    ),
    RoleAssignment(
        role="router",
        model_id="MiniCPM5-2B",
        reasoning_effort=None,
        fallbacks=["DeepSeek-V4-Flash"],
        updated_at=None,
        updated_by=None,
    ),
    RoleAssignment(
        role="ocr",
        model_id="MinerU2.5-Pro",
        reasoning_effort=None,
        fallbacks=[],
        updated_at=None,
        updated_by=None,
    ),
    RoleAssignment(
        role="vision",
        model_id="DeepSeek-V4.1-Flash",
        reasoning_effort="low",
        fallbacks=["Qwen3.8-Flash-Next"],
        updated_at=None,
        updated_by=None,
    ),
]
write("get_role_assignments", roles)
write("update_role_assignment", roles[2])
write(
    "get_llm_usage",
    UsageReport(
        since=datetime(2026, 10, 14, 11, 0, tzinfo=UTC),
        total=Usage(
            requests=14,
            tokens_in=61200,
            tokens_out=6100,
            tokens_reasoning=1540,
            points=0.0118,
            cache_hits=3,
        ),
        by_role=[
            RoleUsage(
                role="investigator",
                usage=Usage(
                    requests=5,
                    tokens_in=17050,
                    tokens_out=1430,
                    tokens_reasoning=600,
                    points=0.0028,
                    cache_hits=1,
                ),
            ),
            RoleUsage(
                role="writer",
                usage=Usage(
                    requests=4,
                    tokens_in=24480,
                    tokens_out=3248,
                    tokens_reasoning=0,
                    points=0.0044,
                    cache_hits=1,
                ),
            ),
            RoleUsage(
                role="verifier",
                usage=Usage(
                    requests=4,
                    tokens_in=19670,
                    tokens_out=1422,
                    tokens_reasoning=940,
                    points=0.0046,
                    cache_hits=1,
                ),
            ),
        ],
        by_model=[
            ModelUsage(
                model_id="DeepSeek-V4.1-Flash",
                usage=Usage(
                    requests=5,
                    tokens_in=17050,
                    tokens_out=1430,
                    tokens_reasoning=600,
                    points=0.0028,
                    cache_hits=1,
                ),
            ),
            ModelUsage(
                model_id="MiMo-V2.6-Flash",
                usage=Usage(
                    requests=4,
                    tokens_in=24480,
                    tokens_out=3248,
                    tokens_reasoning=0,
                    points=0.0044,
                    cache_hits=1,
                ),
            ),
            ModelUsage(
                model_id="GLM-5.3-Flash",
                usage=Usage(
                    requests=4,
                    tokens_in=19670,
                    tokens_out=1422,
                    tokens_reasoning=940,
                    points=0.0046,
                    cache_hits=1,
                ),
            ),
        ],
        quota=Quota(
            limit=1.0,
            used=0.0118,
            remaining=0.9882,
            resets_at=datetime(2026, 10, 15, 11, 0, tzinfo=UTC),
            rpm_limit=20,
            source="usage_endpoint",
            checked_at=NOW,
        ),
        deterministic_answers=9,
        model_answers=2,
        recent=[
            LlmCall(
                at=at(18),
                role="verifier",
                model_id="GLM-5.3-Flash",
                status="ok",
                tokens_in=5230,
                tokens_out=402,
                tokens_reasoning=260,
                points=0.00099,
                latency_ms=3870,
                error=None,
            ),
            LlmCall(
                at=at(13),
                role="writer",
                model_id="MiMo-V2.6-Flash",
                status="ok",
                tokens_in=6120,
                tokens_out=812,
                tokens_reasoning=0,
                points=0.00109,
                latency_ms=4120,
                error=None,
            ),
            LlmCall(
                at=at(1),
                role="investigator",
                model_id="DeepSeek-V4.1-Flash",
                status="cached",
                tokens_in=0,
                tokens_out=0,
                tokens_reasoning=0,
                points=0.0,
                latency_ms=3,
                error=None,
            ),
        ],
    ),
)
write(
    "get_llm_evaluations",
    Evaluations(
        results=[
            EvaluationResult(
                role="investigator",
                model_id="DeepSeek-V4.1-Flash",
                task_set="tool_calls_v1",
                tasks=24,
                success_rate=prob_est(0.88, 0.12, 24),
                violations=1,
                latency_ms_p50=2300.0,
                tokens_in=81000,
                tokens_out=6900,
                points=0.0133,
                run_at=at(-7200),
            ),
            EvaluationResult(
                role="investigator",
                model_id="GLM-5.3-Flash",
                task_set="tool_calls_v1",
                tasks=24,
                success_rate=prob_est(0.79, 0.15, 24),
                violations=3,
                latency_ms_p50=3900.0,
                tokens_in=80400,
                tokens_out=9100,
                points=0.0166,
                run_at=at(-7100),
            ),
            EvaluationResult(
                role="writer",
                model_id="MiMo-V2.6-Flash",
                task_set="report_faithfulness_v1",
                tasks=12,
                success_rate=prob_est(0.92, 0.1, 12),
                violations=1,
                latency_ms_p50=4100.0,
                tokens_in=73000,
                tokens_out=9700,
                points=0.0129,
                run_at=at(-7000),
            ),
        ],
        note=SYNTHETIC,
    ),
)

# ---------------------------------------------------------------- chat

chat_evidence = Evidence(
    evidence_id="E1",
    investigation_id=None,
    tool="get_risk",
    arguments={"unit_id": FOCUS.unit_id},
    data=focus_risk.model_dump(mode="json"),
    summary=f"Unit {FOCUS.unit_id}: risk {FOCUS.risk:.1%} (high).",
    created_at=NOW,
    source=SECOM_BUNDLE,
)
answer = f"Unit {FOCUS.unit_id} has a calibrated failure risk of 18.4% [E1], above the threshold of the 5% false-alarm operating point."
write(
    "chat",
    [
        ChatEvent(
            ChatRouteEvent(type="route", route="deterministic", intent="unit_risk", model_id=None)
        ),
        ChatEvent(
            ChatToolEvent(type="tool", tool="get_risk", arguments={"unit_id": FOCUS.unit_id})
        ),
        ChatEvent(ChatCitationEvent(type="citation", evidence=chat_evidence)),
        *[ChatEvent(ChatTokenEvent(type="token", text=w + " ")) for w in answer.split(" ")],
        ChatEvent(ChatDoneEvent(type="done", usage=None, numbers_checked=1, numbers_unverified=[])),
    ],
)

# ---------------------------------------------------------------- methods, results, session, meta

placeholder = hashlib.sha256(b"synthetic fixture").hexdigest()
write(
    "get_methods_overview",
    MethodsOverview(
        datasets=[
            DatasetCard(
                name="SECOM",
                description="Production units of a semiconductor fab with 590 anonymous sensor readings, a pass or fail result and a timestamp.",
                source_url="https://archive.ics.uci.edu/dataset/179/secom",
                citation="McCann, M. and Johnston, A. (2008). SECOM. UCI Machine Learning Repository.",
                licence="Synthetic fixture: the licence is recorded at download.",
                retrieved_at=NOW,
                files=[DatasetFile(path="data/secom/secom.data", sha256=placeholder, bytes=0)],
            ),
            DatasetCard(
                name="WM-811K",
                description="Wafer maps from real fabs, about a fifth of them labelled with one of nine patterns.",
                source_url="http://mirlab.org/dataSet/public/",
                citation="Wu, M.-J., Jang, J.-S. R. and Chen, J.-L. (2015). Wafer map failure pattern recognition and similarity ranking for large-scale data sets. IEEE TSM 28(1), 1-12.",
                licence="Synthetic fixture: the licence is recorded at download.",
                retrieved_at=NOW,
                files=[DatasetFile(path="data/raw/wm811k/LSWMD.pkl", sha256=placeholder, bytes=0)],
            ),
        ],
        bundles=[
            BundleInfo(bundle=SECOM_BUNDLE, files=14, verified=True),
            BundleInfo(bundle=WAFER_BUNDLE, files=11, verified=True),
        ],
        model_cards=[
            ModelCardRef(name="secom", title="SECOM failure-risk model"),
            ModelCardRef(name="wafermap", title="Wafer-map pattern model"),
        ],
        limitations=[SYNTHETIC],
    ),
)
write(
    "get_model_card",
    ModelCard(
        name="secom",
        title="SECOM failure-risk model",
        markdown="# SECOM failure-risk model\n\nSynthetic fixture for interface development. The real card is written by the training pipeline.\n\n## Intended use\n\nRank units by failure risk so engineers can act before final test.\n\n| Metric | Value | 95% CI |\n|---|---|---|\n| PR-AUC | 0.21 | 0.12 to 0.30 |\n",
    ),
)
results_rows: list[tuple[str, str, Estimate | None, str, str, str]] = [
    (
        "secom_pr_auc",
        "SECOM PR-AUC (test block)",
        prob_est(0.21, 0.09, 307),
        "ratio",
        "SECOM test block, held out and used once",
        "artifacts/secom/v1/metrics.json",
    ),
    (
        "secom_recall_at_fpr_0.05",
        "Failures caught at a 5% false-alarm rate",
        prob_est(0.42, 0.21, 19),
        "percent",
        "SECOM test block",
        "artifacts/secom/v1/operating_points.json",
    ),
    (
        "secom_false_alarms_per_100",
        "False alarms per 100 units at that rate",
        est(5.7, 2.4, 307),
        "number",
        "SECOM test block",
        "artifacts/secom/v1/operating_points.json",
    ),
    (
        "secom_sensors_to_inspect",
        "Sensors to inspect per investigation (median), of 590",
        None,
        "count",
        "SECOM",
        "artifacts/secom/v1/groups.json",
    ),
    (
        "fdc_false_alarm_rate",
        "FDC false-alarm rate on held-out reference",
        prob_est(0.013, 0.013, 75),
        "percent",
        "SECOM reference period, held-out half",
        "artifacts/secom/v1/metrics.json",
    ),
    (
        "wafer_macro_f1_official",
        "Wafer-map macro-F1, official split",
        prob_est(0.86, 0.01, 25519),
        "ratio",
        "WM-811K official test split",
        "artifacts/wafermap/v1/metrics.json",
    ),
    (
        "wafer_macro_f1_lot_grouped",
        "Wafer-map macro-F1, lot-grouped split",
        None,
        "ratio",
        "WM-811K lot-grouped test split",
        "artifacts/wafermap/v1/metrics.json",
    ),
    (
        "unknown_auroc_loco",
        "Unknown-pattern AUROC (leave-one-class-out, mean)",
        None,
        "ratio",
        "WM-811K",
        "artifacts/wafermap/v1/metrics.json",
    ),
    (
        "similar_precision_at_10",
        "Similar-wafer precision@10",
        None,
        "percent",
        "WM-811K labelled test maps",
        "artifacts/wafermap/v1/metrics.json",
    ),
    (
        "auto_classified_share",
        "Wafer maps classified automatically at 95% precision",
        None,
        "percent",
        "WM-811K test split",
        "artifacts/wafermap/v1/metrics.json",
    ),
    (
        "points_per_investigation",
        "Points per full investigation (Token Factory)",
        None,
        "number",
        "Recorded investigations",
        "database: llm_calls",
    ),
]
write(
    "get_measured_results",
    MeasuredResults(
        results=[
            MeasuredResult(id=i, label=lab, estimate=e, format=f, data=d, source=s)
            for i, lab, e, f, d, s in results_rows
        ],
        updated_at=NOW,
    ),
)  # type: ignore[arg-type]
write(
    "get_session", SessionInfo(role="visitor", display_name=None, expires_at=None, csrf_token=None)
)
engineer = SessionInfo(
    role="engineer",
    display_name="Guest engineer",
    expires_at=NOW + timedelta(hours=2),
    csrf_token="synthetic-csrf-token-0000000000000000",
)
write("start_guest_session", engineer)
write(
    "login",
    SessionInfo(
        role="admin",
        display_name="admin",
        expires_at=NOW + timedelta(hours=2),
        csrf_token="synthetic-csrf-token-1111111111111111",
    ),
)
write(
    "get_meta",
    Meta(
        app_name="Yield Guardian",
        version="0.1.0",
        git_commit=None,
        started_at=NOW - timedelta(hours=3),
        bundles=[
            BundleInfo(bundle=SECOM_BUNDLE, files=14, verified=True),
            BundleInfo(bundle=WAFER_BUNDLE, files=11, verified=True),
        ],
        features=Features(live_investigations=True, chat=True, admin_login=True),
    ),
)
print(f"wrote {len(list(OUT.glob('*.json')))} fixtures to {OUT}")
