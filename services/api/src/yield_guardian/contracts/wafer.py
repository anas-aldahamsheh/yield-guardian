"""Wafer maps (WM-811K): maps, pattern predictions, unknown-pattern scores, similar wafers and lots."""

from typing import Literal

from pydantic import Field

from yield_guardian.contracts.base import (
    BundleRef,
    Contract,
    Count,
    Estimate,
    LotId,
    Probability,
    Share,
    WaferId,
)

WaferLabel = Literal[
    "Center", "Donut", "Edge-Loc", "Edge-Ring", "Loc", "Near-full", "Random", "Scratch", "none"
]
OfficialSplit = Literal["training", "test"]
EvaluationSplit = Literal["official", "lot_grouped"]


class WaferMap(Contract):
    """A die map. Decode `cells` from base64 to bytes: row-major, 0 = no die, 1 = pass, 2 = fail."""

    height: int = Field(ge=1, le=512)
    width: int = Field(ge=1, le=512)
    encoding: Literal["uint8-base64"] = "uint8-base64"
    cells: str = Field(description="Base64 of height x width bytes, row-major.")


class WaferSummary(Contract):
    wafer_id: WaferId
    lot: LotId
    wafer_index: int = Field(ge=1)
    die_size: int | None = Field(description="Dies on the wafer, as recorded in WM-811K.")
    height: int
    width: int
    label: WaferLabel | None = Field(
        description="Label recorded in WM-811K; null if the wafer is unlabelled."
    )
    official_split: OfficialSplit | None
    predicted_label: WaferLabel | None
    unknown: bool | None = Field(description="Unknown-pattern flag of the prediction.")


class ClassProbability(Contract):
    label: WaferLabel
    probability: Probability


class UnknownScore(Contract):
    """Energy score; a wafer above the threshold is reported as an unknown pattern."""

    method: Literal["energy"] = "energy"
    score: float
    threshold: float
    is_unknown: bool
    in_distribution_recall: Share = Field(
        description="Validation recall of known patterns at this threshold."
    )
    mahalanobis_distance: float | None
    mahalanobis_flag: bool | None


class WaferPrediction(Contract):
    wafer_id: WaferId
    top_label: WaferLabel
    top_probability: Probability
    probabilities: list[ClassProbability] = Field(description="Calibrated, highest first.")
    temperature: float = Field(gt=0)
    unknown: UnknownScore
    model: BundleRef


class SpatialTest(Contract):
    """Join-count test of whether fail dies cluster in space, with a permutation p-value."""

    method: Literal["join_count"] = "join_count"
    statistic: float
    expected: float
    p_value: Probability
    permutations: Count
    clustered: bool


class WaferDetail(Contract):
    wafer: WaferSummary
    map: WaferMap
    prediction: WaferPrediction | None
    spatial: SpatialTest | None
    attribution: str


class WaferHero(WaferDetail):
    """The wafer shown on the home page, with the rule that picked it."""

    selection: str


class WaferPage(Contract):
    items: list[WaferSummary]
    next_cursor: str | None = None
    total: Count


class SimilarWafer(Contract):
    wafer: WaferSummary
    similarity: float = Field(ge=-1.0, le=1.0, description="Cosine similarity of CNN embeddings.")
    map: WaferMap


class SimilarWafers(Contract):
    wafer_id: WaferId
    k: Count
    results: list[SimilarWafer] = Field(
        description="Most similar first; the query wafer is excluded."
    )
    method: str
    precision_at_10: Estimate | None


class PatternTest(Contract):
    """One-sided binomial test of a pattern's count in a lot against the training-period rate."""

    label: WaferLabel
    count: Count
    wafers: Count
    expected_rate: Probability
    p_value: Probability
    q_value: Probability
    flagged: bool


class StackedMap(Contract):
    """Share of wafers in the lot whose die at each position failed."""

    height: int
    width: int
    wafers: Count
    frequencies: list[Share | None] = Field(description="Row-major; null where no wafer has a die.")


class LotSummary(Contract):
    lot: LotId
    wafers: Count
    labelled: Count
    flagged_labels: list[WaferLabel]
    min_q_value: Probability | None


class LotPage(Contract):
    items: list[LotSummary]
    next_cursor: str | None = None
    total: Count


class LotDetail(Contract):
    lot: LotId
    wafers: list[WaferSummary]
    tests: list[PatternTest]
    stacked: StackedMap | None
    method: str


class ClassMetrics(Contract):
    label: WaferLabel
    precision: Estimate
    recall: Estimate
    f1: Estimate
    support: Count


class ConfusionMatrix(Contract):
    labels: list[WaferLabel]
    counts: list[list[int]] = Field(description="Rows are true labels, columns predicted labels.")


class SeedResult(Contract):
    seed: int
    macro_f1: float


class SplitResult(Contract):
    split: EvaluationSplit
    test_wafers: Count
    macro_f1: Estimate
    accuracy: Estimate | None
    per_class: list[ClassMetrics]
    confusion: ConfusionMatrix
    seeds: list[SeedResult]
    seed_mean: float
    seed_sd: float
    lots_in_both: Count | None = Field(
        description="Lots present in both training and test data of this split."
    )


class LeaveOneClassOut(Contract):
    held_out: WaferLabel
    auroc: Estimate


class OodMetrics(Contract):
    method: Literal["energy"] = "energy"
    threshold: float
    in_distribution_recall: Share
    leave_one_class_out: list[LeaveOneClassOut]
    mean_auroc: Estimate | None
    mahalanobis_mean_auroc: Estimate | None


class AutoClassification(Contract):
    """Share of wafers that can be classified automatically while precision stays at the target."""

    precision_target: Probability
    confidence_threshold: Probability
    share: Estimate
    precision: Estimate


class WaferCalibration(Contract):
    method: Literal["temperature"] = "temperature"
    temperature: float = Field(gt=0)
    ece_before: Estimate
    ece_after: Estimate


class PublishedResult(Contract):
    source: str
    metric: str
    value: float
    note: str


class WaferMetrics(Contract):
    bundle: BundleRef
    splits: list[SplitResult]
    baseline: list[SplitResult]
    calibration: WaferCalibration
    ood: OodMetrics
    similarity_precision_at_10: Estimate
    auto_classification: AutoClassification | None
    published: list[PublishedResult]
    limitations: list[str]
