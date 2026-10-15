"""The wafer-map bundle, loaded once, scored with the ONNX model and held in memory.

At load the deployed CNN (model.onnx, onnxruntime on CPU) scores every demo wafer once: calibrated
class probabilities, the 128-d embedding, the Mahalanobis unknown-pattern score and the energy
score. The predictions stored in demo/lots.json at bundle build time must agree with these
(parity), or the bundle is refused. The v1 wafer pages read these cached results. Live runs score
the user's maps at request time with the same `WaferModel.score`, so a live score of a demo wafer
equals its load-time score by construction.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, get_args

import numpy as np
import numpy.typing as npt
import onnxruntime as ort
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from yield_guardian.bundles.manifest import BundleError, VerifiedBundle
from yield_guardian.contracts.base import Estimate, Probability, Share
from yield_guardian.contracts.wafer import (
    AutoClassification,
    ClassMetrics,
    ConfusionMatrix,
    EvaluationSplit,
    LeaveOneClassOut,
    OfficialSplit,
    OodMetrics,
    SeedResult,
    SplitResult,
    StackedMap,
    WaferCalibration,
    WaferLabel,
    WaferMetrics,
)

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]

LABELS: tuple[WaferLabel, ...] = get_args(WaferLabel)
CHANNELS = ["no_die", "pass", "fail"]
BATCH = 64

# The predictions in demo/lots.json were computed on a GPU under bf16 autocast
# (training/wafermap/wm/train.py `predict`); onnxruntime runs the same network in float32. The
# bundle's own float32 parity check (metrics.json `onnx_parity`) is far tighter; these bounds
# only absorb bf16 rounding. A near-tie may flip the top class, hence the agreement share.
PARITY_MIN_AGREEMENT = 0.995
PARITY_MAX_CONFIDENCE_DIFF = 0.05
PARITY_MAX_ENERGY_DIFF = 0.05
EMBEDDING_NORM_TOLERANCE = 1e-3


class _File(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class PreprocessFile(_File):
    size: int = Field(ge=1)
    resize: str
    channels: list[str]
    source_values: dict[str, int]
    resize_rule: str


class CalibrationFile(_File):
    method: str
    temperature: float = Field(gt=0)


class MahalanobisSection(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, allow_inf_nan=False)

    threshold: float
    in_distribution_recall_validation: Share
    in_distribution_recall_test: Share | None = None
    covariance: str
    parameters: str
    score: str


class OodFile(BaseModel):
    """ood.json: the bundle names energy as its method; the API uses the Mahalanobis section.
    The energy threshold is still read: the lot tests counted the wafers it flagged as unknown."""

    model_config = ConfigDict(extra="ignore", frozen=True, allow_inf_nan=False)

    method: str
    threshold: float
    mahalanobis: MahalanobisSection


class JoinCountRecord(_File):
    bb: int = Field(ge=0)
    fails: int = Field(ge=0)
    dies: int = Field(ge=0)
    expected: float | None
    z: float | None
    p: Probability | None


class LotWaferRecord(_File):
    wafer_id: str
    wafer_index: int = Field(ge=1)
    label: str | None
    predicted: str
    confidence: Probability
    energy: float
    unknown: bool
    join_count: JoinCountRecord


class LotTestRecord(_File):
    pattern: str
    count: int = Field(ge=0)
    wafers: int = Field(ge=0)
    expected_rate: Probability
    p: Probability
    q: Probability
    flagged: bool


class StackedRecord(_File):
    height: int | None
    width: int | None
    wafers: int | None = None
    fail_frequency: list[float] | None = None
    note: str


class LotRecord(_File):
    wafers: list[LotWaferRecord]
    pattern_counts: dict[str, int]
    tests: list[LotTestRecord]
    flagged: bool
    stacked_failure_map: StackedRecord


@dataclass(frozen=True, slots=True)
class DemoWafers:
    """demo/wafers.parquet, sorted by lot and wafer index: index i is wafer i everywhere."""

    wafer_id: list[str]
    lot: list[str]
    wafer_index: list[int]
    die_size: list[int | None]
    label: list[WaferLabel | None]
    official_split: list[OfficialSplit | None]
    height: list[int]
    width: list[int]
    maps: list[bytes]
    index_of: dict[str, int]

    def __len__(self) -> int:
        return len(self.wafer_id)

    def grid(self, i: int) -> npt.NDArray[np.uint8]:
        return np.frombuffer(self.maps[i], dtype=np.uint8).reshape(self.height[i], self.width[i])


@dataclass(frozen=True, slots=True)
class Scores:
    """Model outputs for every demo wafer, from onnxruntime at load time."""

    probabilities: FloatArray  # [N, classes], temperature-scaled
    embedding: npt.NDArray[np.float32]  # [N, 128], L2-normalised
    mahalanobis: FloatArray  # [N]
    energy: FloatArray  # [N]
    is_unknown: BoolArray  # mahalanobis > threshold


@dataclass(frozen=True, slots=True)
class Parity:
    """Agreement of the onnxruntime outputs with the predictions stored in demo/lots.json."""

    wafers: int
    top_label_agreement: float
    max_confidence_diff: float
    max_energy_diff: float


@dataclass(frozen=True, slots=True)
class LotReference:
    """What the bundle's lot tests compared against (metrics.json `lot_excursions`).

    `rates` are the shares of the validation lots' wafers (all of them, labelled or not) that
    the deployed model assigned to each defect pattern, or to "unknown" when the energy score was
    above `energy_threshold`; a wafer the energy score flagged counts as unknown, not as its
    pattern. `fdr_q` is the Benjamini-Hochberg level.
    """

    rates: dict[str, float]
    fdr_q: float
    energy_threshold: float
    lots: int
    wafers: int


@dataclass(frozen=True, slots=True)
class WafermapBundle:
    bundle: VerifiedBundle
    labels: list[WaferLabel]
    temperature: float
    mahalanobis: MahalanobisSection
    model: "WaferModel"
    wafers: DemoWafers
    scores: Scores
    parity: Parity
    lot_reference: LotReference
    lots: dict[str, LotRecord]
    stacked: dict[str, StackedMap | None]
    join_count: list[JoinCountRecord]
    permutations: int
    lot_method: str
    metrics: WaferMetrics
    attribution: str
    model_card: str


def _read_json(bundle: VerifiedBundle, name: str) -> Any:
    def missing(constant: str) -> None:
        if constant == "NaN":  # lots.json writes a missing label as NaN: read it as null
            return None
        raise ValueError(f"{constant} is not allowed")

    try:
        return json.loads(bundle.file(name).read_text(encoding="utf-8"), parse_constant=missing)
    except (OSError, ValueError) as error:
        raise BundleError(f"wafermap/{bundle.path.name}/{name}: {error}") from error


def _json[M: BaseModel](bundle: VerifiedBundle, name: str, model: type[M]) -> M:
    try:
        return model.model_validate(_read_json(bundle, name))
    except ValidationError as error:
        raise BundleError(f"wafermap/{bundle.path.name}/{name}: {error}") from error


def _missing(value: Any) -> Any:
    """A pandas null (None or NaN) as None."""
    return None if value is None or value != value else value


# Demo wafers ----------------------------------------------------------------------------------


def _load_wafers(bundle: VerifiedBundle) -> DemoWafers:
    frame = pq.read_table(bundle.file("demo/wafers.parquet")).to_pandas()
    frame = frame.sort_values(["lot", "wafer_index"], kind="stable").reset_index(drop=True)
    splits = {"Training": "training", "Test": "test"}
    labels: list[WaferLabel | None] = []
    official: list[OfficialSplit | None] = []
    for label, split in zip(frame["label"].tolist(), frame["official_split"].tolist(), strict=True):
        label = _missing(label)
        split = _missing(split)
        if label is not None and label not in LABELS:
            raise BundleError(f"demo/wafers.parquet: unknown label {label!r}.")
        if split is not None and split not in splits:
            raise BundleError(f"demo/wafers.parquet: unknown official split {split!r}.")
        labels.append(label)
        official.append(None if split is None else splits[split])  # type: ignore[arg-type]
    wafer_id = [str(v) for v in frame["wafer_id"]]
    lot = [str(v) for v in frame["lot"]]
    index = [int(v) for v in frame["wafer_index"]]
    if any(w != f"{lt}-{i}" for w, lt, i in zip(wafer_id, lot, index, strict=True)):
        raise BundleError('demo/wafers.parquet: wafer_id must be "<lot>-<wafer_index>".')
    if len(set(wafer_id)) != len(wafer_id):
        raise BundleError("demo/wafers.parquet: duplicate wafer_id.")
    height = [int(v) for v in frame["height"]]
    width = [int(v) for v in frame["width"]]
    maps = [bytes(v) for v in frame["map"]]
    for w, h, wd, m in zip(wafer_id, height, width, maps, strict=True):
        if len(m) != h * wd or not set(m) <= {0, 1, 2}:
            raise BundleError(f"demo/wafers.parquet: the map of {w} is not {h}x{wd} values 0-2.")
    return DemoWafers(
        wafer_id=wafer_id,
        lot=lot,
        wafer_index=index,
        die_size=[None if d != d else int(d) for d in frame["die_size"].tolist()],
        label=labels,
        official_split=official,
        height=height,
        width=width,
        maps=maps,
        index_of={w: i for i, w in enumerate(wafer_id)},
    )


# Model ----------------------------------------------------------------------------------------


def _nearest(source: int, size: int) -> IntArray:
    """Source index sampled by each output cell (preprocess.json `resize_rule`)."""
    centres = (np.arange(size) + 0.5) * source / size
    return np.minimum(np.floor(centres).astype(np.int64), source - 1)


def model_input(
    grids: Sequence[npt.NDArray[np.uint8]], prep: PreprocessFile
) -> npt.NDArray[np.float32]:
    """uint8 maps of any size -> float32 [N, 3, size, size], one-hot no_die, pass, fail."""
    values = np.array([prep.source_values[c] for c in prep.channels], dtype=np.uint8)
    out = np.empty((len(grids), len(values), prep.size, prep.size), dtype=np.float32)
    for i, grid in enumerate(grids):
        small = grid[np.ix_(_nearest(grid.shape[0], prep.size), _nearest(grid.shape[1], prep.size))]
        out[i] = small[None, :, :] == values[:, None, None]
    return out


def _energy(logits: FloatArray) -> FloatArray:
    top = logits.max(axis=1)
    result: FloatArray = -(top + np.log(np.exp(logits - top[:, None]).sum(axis=1)))
    return result


def _softmax(z: FloatArray) -> FloatArray:
    shifted = np.exp(z - z.max(axis=1, keepdims=True))
    result: FloatArray = shifted / shifted.sum(axis=1, keepdims=True)
    return result


def mahalanobis_score(
    embedding: npt.NDArray[np.floating[Any]], means: FloatArray, precision: FloatArray
) -> FloatArray:
    """Smallest squared Mahalanobis distance to a class mean (ood.json `mahalanobis.score`)."""
    z = embedding.astype(np.float64)
    best = np.full(len(z), np.inf)
    for mu in means:
        d = z - mu
        best = np.minimum(best, ((d @ precision) * d).sum(axis=1))
    return best


class WaferModel:
    """The deployed CNN with its calibration and unknown-pattern parameters.

    `score` is the one scoring function of the bundle: it scores the demo wafers at load and
    every live map at request time, so the two agree by construction. Maps go through the
    network in batches of `BATCH`, in the order given (a different batching changes the float32
    outputs by about 1e-6, metrics.json `onnx_parity`). onnxruntime allows concurrent `run`
    calls on one session, so one model serves every request thread.
    """

    def __init__(
        self,
        session: ort.InferenceSession,
        prep: PreprocessFile,
        temperature: float,
        ood: MahalanobisSection,
        means: FloatArray,
        precision: FloatArray,
    ) -> None:
        self.session = session
        self.prep = prep
        self.temperature = temperature
        self.threshold = ood.threshold
        self.means = means
        self.precision = precision
        self.classes = means.shape[0]
        self.dim = means.shape[1]

    def score(self, grids: Sequence[npt.NDArray[np.uint8]]) -> Scores:
        """Model outputs for uint8 maps of any size (0 no die, 1 pass, 2 fail)."""
        logits: list[npt.NDArray[np.float32]] = [np.empty((0, self.classes), dtype=np.float32)]
        embeddings: list[npt.NDArray[np.float32]] = [np.empty((0, self.dim), dtype=np.float32)]
        for start in range(0, len(grids), BATCH):
            batch = model_input(grids[start : start + BATCH], self.prep)
            out_logits, out_embedding = self.session.run(None, {"maps": batch})
            logits.append(np.asarray(out_logits, dtype=np.float32))
            embeddings.append(np.asarray(out_embedding, dtype=np.float32))
        z = np.concatenate(logits).astype(np.float64)
        embedding = np.concatenate(embeddings)
        mahalanobis = mahalanobis_score(embedding, self.means, self.precision)
        return Scores(
            probabilities=_softmax(z / self.temperature),
            embedding=embedding,
            mahalanobis=mahalanobis,
            energy=_energy(z),
            is_unknown=mahalanobis > self.threshold,
        )


def _load_model(
    bundle: VerifiedBundle,
    prep: PreprocessFile,
    temperature: float,
    labels: list[WaferLabel],
    ood: MahalanobisSection,
) -> WaferModel:
    try:
        session = ort.InferenceSession(
            str(bundle.file("model.onnx")), providers=["CPUExecutionProvider"]
        )
    except Exception as error:  # onnxruntime raises its own exception types
        raise BundleError(f"wafermap/{bundle.path.name}/model.onnx: {error}") from error
    inputs = [i.name for i in session.get_inputs()]
    outputs = [o.name for o in session.get_outputs()]
    if inputs != ["maps"] or outputs != ["logits", "embedding"]:
        raise BundleError(
            f"model.onnx: expected maps -> logits, embedding; got {inputs} -> {outputs}."
        )
    logits_shape, embedding_shape = (o.shape for o in session.get_outputs())
    if len(logits_shape) != 2 or logits_shape[1] != len(labels):
        raise BundleError(f"model.onnx: logits {logits_shape} do not match {len(labels)} labels.")
    with np.load(bundle.file(ood.parameters), allow_pickle=False) as params:
        if {"class_means", "precision"} - set(params.files):
            raise BundleError(f"{ood.parameters} lacks class_means or precision.")
        means = np.asarray(params["class_means"], dtype=np.float64)
        precision = np.asarray(params["precision"], dtype=np.float64)
    dim = embedding_shape[1] if len(embedding_shape) == 2 else None
    if means.shape != (len(labels), dim) or precision.shape != (dim, dim):
        raise BundleError(f"{ood.parameters}: shapes do not match the model's embedding.")
    return WaferModel(session, prep, temperature, ood, means, precision)


def _score(model: WaferModel, wafers: DemoWafers) -> Scores:
    """Score every demo wafer, in bundle order, and check the outputs."""
    scores = model.score([wafers.grid(i) for i in range(len(wafers))])
    norms = np.linalg.norm(scores.embedding.astype(np.float64), axis=1)
    if np.any(np.abs(norms - 1.0) > EMBEDDING_NORM_TOLERANCE):
        raise BundleError("model.onnx: embeddings are not L2-normalised.")
    return scores


def _parity(
    wafers: DemoWafers, scores: Scores, lots: dict[str, LotRecord], labels: list[WaferLabel]
) -> Parity:
    stored = {w.wafer_id: w for lot in lots.values() for w in lot.wafers}
    if set(stored) != set(wafers.wafer_id):
        raise BundleError("demo/lots.json and demo/wafers.parquet hold different wafers.")
    order = [stored[w] for w in wafers.wafer_id]
    top = scores.probabilities.argmax(axis=1)
    predicted = np.array([labels.index(r.predicted) for r in order])  # type: ignore[arg-type]
    confidence = np.array([r.confidence for r in order])
    energy = np.array([r.energy for r in order])
    parity = Parity(
        wafers=len(order),
        top_label_agreement=float((top == predicted).mean()),
        max_confidence_diff=float(np.abs(scores.probabilities.max(axis=1) - confidence).max()),
        max_energy_diff=float(np.abs(scores.energy - energy).max()),
    )
    if (
        parity.top_label_agreement < PARITY_MIN_AGREEMENT
        or parity.max_confidence_diff > PARITY_MAX_CONFIDENCE_DIFF
        or parity.max_energy_diff > PARITY_MAX_ENERGY_DIFF
    ):
        raise BundleError(f"model.onnx disagrees with the predictions in demo/lots.json: {parity}.")
    return parity


# Lots -----------------------------------------------------------------------------------------


def _stacked(name: str, lot: LotRecord) -> StackedMap | None:
    """The lot's stacked failure map (-1, no die on any wafer, becomes null); None when the lot's
    wafers differ in shape."""
    record = lot.stacked_failure_map
    if record.height is None:
        return None
    if record.width is None or record.wafers is None or record.fail_frequency is None:
        raise BundleError(f"demo/lots.json: {name} has an incomplete stacked map.")
    if len(record.fail_frequency) != record.height * record.width:
        raise BundleError(f"demo/lots.json: the stacked map of {name} has the wrong size.")
    if record.wafers != len(lot.wafers):
        raise BundleError(f"demo/lots.json: the stacked map of {name} counts other wafers.")
    if any(not (f == -1.0 or 0.0 <= f <= 1.0) for f in record.fail_frequency):
        raise BundleError(f"demo/lots.json: the stacked map of {name} is not -1 or a share.")
    return StackedMap(
        height=record.height,
        width=record.width,
        wafers=record.wafers,
        frequencies=[None if f == -1.0 else f for f in record.fail_frequency],
    )


def _check_lots(
    lots: dict[str, LotRecord], wafers: DemoWafers, labels: list[WaferLabel]
) -> dict[str, StackedMap | None]:
    patterns = {*labels, "unknown"}
    for name, lot in lots.items():
        for w in lot.wafers:
            i = wafers.index_of.get(w.wafer_id)
            if i is None or wafers.lot[i] != name or wafers.wafer_index[i] != w.wafer_index:
                raise BundleError(f"demo/lots.json: {name} lists {w.wafer_id}, not in that lot.")
            if w.predicted not in labels:
                raise BundleError(f"demo/lots.json: {w.wafer_id} has prediction {w.predicted!r}.")
        if any(t.pattern not in patterns for t in lot.tests):
            raise BundleError(f"demo/lots.json: {name} tests an unknown pattern.")
    if sum(len(lot.wafers) for lot in lots.values()) != len(wafers):
        raise BundleError("demo/lots.json does not list every demo wafer exactly once.")
    return {name: _stacked(name, lot) for name, lot in lots.items()}


# Metrics --------------------------------------------------------------------------------------


def _estimate(raw: dict[str, Any], note: str | None = None) -> Estimate:
    return Estimate(
        value=raw["value"],
        ci_low=raw["ci_low"],
        ci_high=raw["ci_high"],
        ci_level=raw.get("ci_level", 0.95),
        method=raw.get("method"),
        n=raw.get("n"),
        note=note,
    )


def _point(value: float, n: int | None, note: str) -> Estimate:
    """A measured value for which the pipeline computed no interval."""
    return Estimate(value=value, ci_low=None, ci_high=None, n=n, note=note)


def _best_seed(part: dict[str, Any]) -> str:
    """The seed with the highest validation macro-F1: the rule that chose the deployed model."""
    seeds: dict[str, Any] = part["seeds"]
    return max(sorted(seeds), key=lambda s: float(seeds[s]["validation_macro_f1"]))


def _split_result(
    split: EvaluationSplit,
    part: dict[str, Any],
    test: dict[str, Any],
    lots_in_both: int,
    labels: list[WaferLabel],
    note: str,
    *,
    seeded: bool,
) -> SplitResult:
    confusion = test["confusion_matrix"]
    across = part["across_seeds"]["macro_f1"]
    return SplitResult(
        split=split,
        test_wafers=part["test_wafers"],
        macro_f1=_estimate(test["macro_f1"], note),
        accuracy=_estimate(test["accuracy"]),
        per_class=[
            ClassMetrics(
                label=label,
                precision=_estimate(test["per_class"][label]["precision"]),
                recall=_estimate(test["per_class"][label]["recall"]),
                f1=_estimate(test["per_class"][label]["f1"]),
                support=test["per_class"][label]["support"],
            )
            for label in labels
        ],
        confusion=ConfusionMatrix(
            labels=confusion["classes"], counts=confusion["rows_true_cols_pred"]
        ),
        seeds=[
            SeedResult(seed=int(s), macro_f1=part["seeds"][s]["test"]["macro_f1"]["value"])
            for s in sorted(part["seeds"])
        ]
        if seeded
        else [],
        seed_mean=across["mean"] if seeded else None,
        seed_sd=across["sd"] if seeded else None,
        lots_in_both=lots_in_both,
    )


def _limitations(model_card: str) -> list[str]:
    """The bullets of the model card's Limitations section."""
    match = re.search(r"^## Limitations\n(.*?)(?=^## |\Z)", model_card, re.M | re.S)
    if match is None:
        raise BundleError("model_card.md has no Limitations section.")
    items: list[str] = []
    for line in match.group(1).splitlines():
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif line.strip() and items:
            items[-1] += " " + line.strip()
    if not items:
        raise BundleError("model_card.md lists no limitations.")
    return items


def _metrics(
    bundle: VerifiedBundle,
    raw: dict[str, Any],
    labels: list[WaferLabel],
    temperature: float,
    ood: MahalanobisSection,
    model_card: str,
) -> WaferMetrics:
    deployed: str = raw["deployed_model"]
    lot, official = raw["lot_split"], raw["official_split"]
    seed = _best_seed(lot)
    if deployed != f"lot-seed{seed}":
        raise BundleError(f"metrics.json: deployed model {deployed} is not lot-seed{seed}.")
    deployed_run = lot["seeds"][seed]
    if abs(deployed_run["calibration"]["temperature"] - temperature) > 1e-9:
        raise BundleError("metrics.json and calibration.json give different temperatures.")
    official_seed = _best_seed(official)
    overlap = raw["splits"]
    splits = [
        _split_result(
            "lot_grouped",
            lot,
            deployed_run["test"],
            overlap["lot"]["lot_overlap"]["test&train"],
            labels,
            f"Deployed model {deployed}: the seed with the highest validation macro-F1.",
            seeded=True,
        ),
        _split_result(
            "official",
            official,
            official["seeds"][official_seed]["test"],
            overlap["official"]["lot_overlap"]["test&train"],
            labels,
            f"Seed {official_seed}: the seed with the highest validation macro-F1 on this split.",
            seeded=True,
        ),
    ]
    parts: list[tuple[EvaluationSplit, str, dict[str, Any]]] = [
        ("lot_grouped", "lot", lot),
        ("official", "official", official),
    ]
    baseline = [
        _split_result(
            name,
            part,
            part["baseline"]["test"],
            overlap[key]["lot_overlap"]["test&train"],
            labels,
            f"Baseline: {part['baseline']['model']}, {len(part['baseline']['features'])} "
            "features; a single fit, so no seeds.",
            seeded=False,
        )
        for name, key, part in parts
    ]
    calibration = deployed_run["calibration"]
    test_n = deployed_run["test"]["macro_f1"].get("n")
    measured_ood = raw["ood"]["mahalanobis"]
    if measured_ood["threshold"] != ood.threshold:
        raise BundleError("metrics.json and ood.json give different Mahalanobis thresholds.")
    loco = raw["leave_one_class_out"]
    held_out = [c for c in labels if c in loco["classes"]]
    similarity = raw["similarity"]["lot"]["seeds"][seed]["all_neighbours"]
    return WaferMetrics(
        bundle=bundle.info.bundle,
        splits=splits,
        baseline=baseline,
        calibration=WaferCalibration(
            temperature=calibration["temperature"],
            ece_before=_point(
                calibration["test_ece_raw"], test_n, "Before temperature scaling; no interval."
            ),
            ece_after=_estimate(calibration["test_ece_calibrated"]),
        ),
        ood=OodMetrics(
            threshold=ood.threshold,
            in_distribution_recall=ood.in_distribution_recall_validation,
            in_distribution_recall_test=measured_ood.get("in_distribution_recall_test"),
            leave_one_class_out=[
                LeaveOneClassOut(
                    held_out=c, auroc=_estimate(loco["classes"][c]["mahalanobis"]["auroc"])
                )
                for c in held_out
            ],
            mean_auroc=_point(
                loco["mean_auroc_mahalanobis"],
                len(held_out),
                "Mean over the held-out classes; no interval.",
            ),
            energy_mean_auroc=_point(
                loco["mean_auroc_energy"],
                len(held_out),
                "Mean over the held-out classes; no interval.",
            ),
            note=(
                f"Score: {ood.score}, on L2-normalised embeddings ({ood.covariance}). Threshold "
                f"set on validation wafers. Leave-one-class-out: {loco['split']}-grouped split, "
                f"seed {loco['seed']}, training capped at {loco['epochs_cap']} epochs; a model "
                "trained without each defect class scores that class against in-distribution "
                "test wafers. Mahalanobis was chosen over the energy score after these results, "
                "so they are not an independent estimate for it."
            ),
        ),
        similarity_precision_at_10=_estimate(
            similarity["macro_precision_at_10"],
            f"Deployed model, lot-grouped test set ({raw['similarity']['lot']['queries']} "
            "labelled wafers, each querying the others); share of the 10 nearest with the same "
            "label, averaged over classes.",
        ),
        auto_classification=[
            AutoClassification(
                precision_target=a["target_precision"],
                confidence_threshold=a["threshold"],
                share=_estimate(a["test_coverage"]),
                precision=_estimate(a["test_precision"]),
            )
            for a in deployed_run["auto_classification"]
            if a["threshold"] is not None
        ],
        published=[],  # model card: no published comparison could be cited
        limitations=_limitations(model_card),
    )


def _lot_method(raw: dict[str, Any]) -> str:
    summary = raw["lot_excursions"]
    return (
        f"{summary['method']}, q = {summary['fdr_q']}, over the {summary['tested']['tests']} "
        f"tests of the {summary['tested']['lots']} lot-grouped test lots; reference rates from "
        f"the {summary['reference']['lots']} validation lots ({summary['reference']['wafers']} "
        "wafers). Patterns are the deployed model's predictions, computed when the bundle was "
        "built; wafers its energy score then called unknown were counted as unknown, not as "
        "their pattern. The bundle's unknown-pattern tests used that energy score and are not "
        "shown: the unknown score is Mahalanobis."
    )


def _lot_reference(
    raw: dict[str, Any], ood: OodFile, labels: list[WaferLabel], lots: dict[str, LotRecord]
) -> LotReference:
    """The reference of the lot tests, checked against the tests and flags in demo/lots.json."""
    summary = raw["lot_excursions"]
    rates = {str(k): float(v) for k, v in summary["reference"]["pattern_rates"].items()}
    patterns = [*(c for c in labels if c != "none"), "unknown"]
    if sorted(rates) != sorted(patterns) or any(not 0.0 <= r <= 1.0 for r in rates.values()):
        raise BundleError(f"metrics.json: lot reference rates must be shares for {patterns}.")
    fdr_q = float(summary["fdr_q"])
    if not 0.0 < fdr_q < 1.0:
        raise BundleError("metrics.json: lot_excursions.fdr_q must be between 0 and 1.")
    if ood.method != "energy":
        raise BundleError(f"ood.json: method {ood.method!r}; the lot tests used energy.")
    for name, lot in lots.items():
        if any(t.expected_rate != rates[t.pattern] for t in lot.tests):
            raise BundleError(f"demo/lots.json: {name} was tested against other rates.")
        if any(w.unknown != (w.energy > ood.threshold) for w in lot.wafers):
            raise BundleError(f"demo/lots.json: {name} flags unknowns by another threshold.")
    return LotReference(
        rates=rates,
        fdr_q=fdr_q,
        energy_threshold=ood.threshold,
        lots=int(summary["reference"]["lots"]),
        wafers=int(summary["reference"]["wafers"]),
    )


# Loading --------------------------------------------------------------------------------------


def load_wafermap_bundle(bundle: VerifiedBundle) -> WafermapBundle:
    """Load a verified wafer-map bundle and score the demo wafers; raise BundleError on a problem."""
    labels_raw = _read_json(bundle, "labels.json")
    if not isinstance(labels_raw, list) or tuple(labels_raw) != LABELS:
        raise BundleError(f"labels.json must list {list(LABELS)} in order.")
    labels: list[WaferLabel] = list(LABELS)
    prep = _json(bundle, "preprocess.json", PreprocessFile)
    if (
        prep.resize != "nearest"
        or prep.channels != CHANNELS
        or set(CHANNELS) - set(prep.source_values)
    ):
        raise BundleError("preprocess.json: expected nearest resize to no_die, pass, fail.")
    calibration = _json(bundle, "calibration.json", CalibrationFile)
    if calibration.method != "temperature":
        raise BundleError(f"calibration.json: method {calibration.method!r} is not temperature.")
    ood_file = _json(bundle, "ood.json", OodFile)
    ood = ood_file.mahalanobis

    wafers = _load_wafers(bundle)
    try:
        raw_lots = _read_json(bundle, "demo/lots.json")
        lots = {
            str(name): LotRecord.model_validate(value) for name, value in sorted(raw_lots.items())
        }
    except (AttributeError, ValidationError) as error:
        raise BundleError(f"demo/lots.json: {error}") from error
    stacked = _check_lots(lots, wafers, labels)
    model = _load_model(bundle, prep, calibration.temperature, labels, ood)
    scores = _score(model, wafers)
    parity = _parity(wafers, scores, lots, labels)

    model_card = bundle.file("model_card.md").read_text(encoding="utf-8")
    raw_metrics = _read_json(bundle, "metrics.json")
    try:
        metrics = _metrics(bundle, raw_metrics, labels, calibration.temperature, ood, model_card)
        permutations = int(raw_metrics["lot_excursions"]["join_count_demo"]["permutations"])
        lot_method = _lot_method(raw_metrics)
        lot_reference = _lot_reference(raw_metrics, ood_file, labels, lots)
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise BundleError(f"wafermap/{bundle.path.name}/metrics.json: {error!r}") from error
    stored = {w.wafer_id: w.join_count for lot in lots.values() for w in lot.wafers}
    return WafermapBundle(
        bundle=bundle,
        labels=labels,
        temperature=calibration.temperature,
        mahalanobis=ood,
        model=model,
        wafers=wafers,
        scores=scores,
        parity=parity,
        lot_reference=lot_reference,
        lots=lots,
        stacked=stacked,
        join_count=[stored[w] for w in wafers.wafer_id],
        permutations=permutations,
        lot_method=lot_method,
        metrics=metrics,
        attribution=bundle.file("demo/ATTRIBUTION.md").read_text(encoding="utf-8").strip(),
        model_card=model_card,
    )
