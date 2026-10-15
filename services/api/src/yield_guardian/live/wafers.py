"""The live wafer engine: the deployed WM-811K model applied to any map at request time.

Every result is computed from the input maps when the stage runs:

- `pattern`: the bundle's own scoring function (`WaferModel.score`: nearest-neighbour resize to
  64 x 64, one-hot channels, the ONNX CNN, temperature scaling, Mahalanobis unknown score,
  energy score), the auto-accept threshold the bundle measured for 99% precision, and the
  join-count spatial test of training/wafermap/wm/lots.py with permutations seeded from the
  map itself (live/wafer_stats.py).
- `similar`: exact cosine search over the 10,253 demo wafers' embeddings, and the literature
  causes of the predicted patterns.
- `lots`: the bundle's lot test (one-sided binomial against the validation lots' pattern rates,
  Benjamini-Hochberg) over the lots of the run, and each lot's stacked failure map.

The demo wafers are real WM-811K maps (artifacts/wafermap/v1/demo); `from_demo`, `sample` and
`draw_layouts` take real items from them by a stated rule.
"""

import base64
import binascii
import os
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from random import Random

import numpy as np
import numpy.typing as npt

from yield_guardian.bundles.wafermap import Scores, WafermapBundle
from yield_guardian.contracts.base import LotId, WaferId
from yield_guardian.contracts.runs import (
    ClassProbabilityItem,
    LotItem,
    LotResult,
    SimilarItem,
    WaferInput,
    WaferPatternItem,
    WaferPatternResult,
    WaferSimilarItem,
    WaferSimilarResult,
)
from yield_guardian.contracts.services import NotFoundError
from yield_guardian.contracts.wafer import (
    PatternTest,
    SpatialTest,
    StackedMap,
    WaferLabel,
    WaferMap,
)
from yield_guardian.live.protocols import DrawLayout, NeedsInput, PatternCausesSource, Picked
from yield_guardian.live.wafer_stats import (
    JoinCount,
    benjamini_hochberg,
    binomial_tail,
    join_count,
    stacked_failure_map,
)
from yield_guardian.science.wafermap.service import SPATIAL_ALPHA

Grid = npt.NDArray[np.uint8]

ACCEPT_PRECISION_TARGET = 0.99
SIMILAR_K = 10
MIN_LOT_WAFERS = 2
DRAW_LAYOUTS = 6
SPATIAL_WORKERS = min(4, os.cpu_count() or 1)

NEEDS_WAFERS = "needs at least one wafer map"
NEEDS_LOT = "needs at least two wafers of the same lot"


class MapError(ValueError):
    """A wafer map that cannot be read; `message` says what is wrong, in plain words."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def decode_map(wafer_map: WaferMap) -> Grid:
    """The map's cells as a height x width uint8 grid; MapError if they do not form one."""
    try:
        raw = base64.b64decode(wafer_map.cells, validate=True)
    except (binascii.Error, ValueError) as error:
        raise MapError("The map's cells are not valid base64.") from error
    expected = wafer_map.height * wafer_map.width
    if len(raw) != expected:
        raise MapError(
            f"The map has {len(raw)} cells; {wafer_map.height} x {wafer_map.width} needs "
            f"{expected}."
        )
    grid = np.frombuffer(raw, dtype=np.uint8).reshape(wafer_map.height, wafer_map.width)
    if int(grid.max()) > 2:
        raise MapError("Map cells must be 0 (no die), 1 (pass) or 2 (fail).")
    if not grid.any():
        raise MapError("The map has no die: mark at least one die as pass or fail.")
    return grid


def encode_map(grid: Grid) -> WaferMap:
    height, width = grid.shape
    cells = np.ascontiguousarray(grid, dtype=np.uint8).tobytes()
    return WaferMap(
        height=int(height), width=int(width), cells=base64.b64encode(cells).decode("ascii")
    )


def _ordinal(n: int) -> str:
    return {1: "most common", 2: "2nd most common", 3: "3rd most common"}.get(
        n, f"{n}th most common"
    )


class LiveWafers:
    """Implements :class:`~yield_guardian.live.protocols.WaferEngine` on a loaded bundle."""

    def __init__(self, bundle: WafermapBundle, causes: PatternCausesSource) -> None:
        self.bundle = bundle
        self.causes_source = causes
        self.labels = bundle.labels
        self.defects: list[WaferLabel] = [c for c in bundle.labels if c != "none"]
        self.demo = bundle.wafers
        self.demo_top = bundle.scores.probabilities.argmax(axis=1)
        self.demo_maps = [
            WaferMap(height=h, width=w, cells=base64.b64encode(m).decode("ascii"))
            for h, w, m in zip(self.demo.height, self.demo.width, self.demo.maps, strict=True)
        ]
        self.lot_rows: dict[str, list[int]] = {}
        for i, lot in enumerate(self.demo.lot):
            self.lot_rows.setdefault(lot, []).append(i)
        self.lot_names = sorted(self.lot_rows)
        self.accept_threshold = self._accept_threshold()
        self.layouts = self._layouts()
        self.pool = ThreadPoolExecutor(SPATIAL_WORKERS, thread_name_prefix="join-count")

    def _accept_threshold(self) -> float:
        for row in self.bundle.metrics.auto_classification:
            if row.precision_target == ACCEPT_PRECISION_TARGET:
                return row.confidence_threshold
        raise ValueError(f"metrics.json has no auto-classification at {ACCEPT_PRECISION_TARGET}.")

    # Pattern ----------------------------------------------------------------------------------

    def _grids(self, wafers: Sequence[WaferInput]) -> list[Grid]:
        if not wafers:
            raise NeedsInput(NEEDS_WAFERS)
        return [decode_map(w.map) for w in wafers]

    def score(self, grids: Sequence[Grid]) -> Scores:
        """The bundle's scoring function: the same one that scored the demo wafers at load."""
        return self.bundle.model.score(grids)

    def spatial(self, grids: Sequence[Grid]) -> list[JoinCount]:
        """The join-count test of each map, in parallel (each map has its own generator, so the
        result does not depend on the threads)."""
        permutations = self.bundle.permutations
        return list(self.pool.map(lambda g: join_count(g, permutations), grids))

    def _spatial_test(self, jc: JoinCount) -> SpatialTest | None:
        if jc.expected is None or jc.p is None:
            return None  # fewer than two fail dies, or no adjacent dies: nothing to test
        return SpatialTest(
            statistic=float(jc.bb),
            expected=jc.expected,
            p_value=jc.p,
            permutations=self.bundle.permutations,
            clustered=jc.p < SPATIAL_ALPHA,
        )

    def _pattern_item(
        self, i: int, wafer: WaferInput, grid: Grid, scores: Scores, spatial: JoinCount
    ) -> WaferPatternItem:
        probabilities = scores.probabilities[i]
        order = sorted(range(len(self.labels)), key=lambda c: (-probabilities[c], c))
        top = float(probabilities[order[0]])
        return WaferPatternItem(
            index=i,
            lot=wafer.lot,
            wafer=wafer.wafer,
            map=encode_map(grid),
            source_wafer=wafer.source_wafer,
            top_label=self.labels[order[0]],
            top_probability=top,
            probabilities=[
                ClassProbabilityItem(label=self.labels[c], probability=float(probabilities[c]))
                for c in order
            ],
            auto_accepted=top >= self.accept_threshold,
            unknown_score=float(scores.mahalanobis[i]),
            unknown_threshold=self.bundle.mahalanobis.threshold,
            is_unknown=bool(scores.is_unknown[i]),
            energy_score=float(scores.energy[i]),
            spatial=self._spatial_test(spatial),
            recorded_label=wafer.label,
        )

    def pattern_method(self) -> str:
        ood = self.bundle.mahalanobis
        prep = self.bundle.model.prep
        return (
            f"Each map is resized to {prep.size} x {prep.size} by nearest neighbour (every cell "
            "copies a real cell: no die, pass or fail) and one-hot encoded; the deployed CNN "
            f"(model.onnx, onnxruntime on CPU) gives logits, calibrated by temperature "
            f"{self.bundle.temperature:.4f}. Unknown pattern: the smallest squared Mahalanobis "
            f"distance of the L2-normalised embedding to a class mean ({ood.covariance}) is "
            f"above {ood.threshold:.2f}, set to accept "
            f"{ood.in_distribution_recall_validation:.0%} of validation wafers; the energy score "
            "is a cross-check only. Auto-accepted: the top probability reaches "
            f"{self.accept_threshold:.4f}, the threshold set on validation for "
            f"{ACCEPT_PRECISION_TARGET:.0%} precision. Spatial test: join count of "
            f"rook-adjacent fail-fail die pairs against {self.bundle.permutations} random "
            "permutations of the fail labels over the wafer's dies (Cliff and Ord, 1981), "
            "seeded from the map itself (SHA-256 of its size and cells), so the same map always "
            f"gets the same p-value; clustered when p < {SPATIAL_ALPHA}."
        )

    def pattern(self, wafers: Sequence[WaferInput]) -> WaferPatternResult:
        grids = self._grids(wafers)
        scores = self.score(grids)
        spatial = self.spatial(grids)
        return WaferPatternResult(
            wafers=[
                self._pattern_item(i, w, grids[i], scores, spatial[i]) for i, w in enumerate(wafers)
            ],
            accept_threshold=self.accept_threshold,
            energy_threshold=self.bundle.lot_reference.energy_threshold,
            temperature=self.bundle.temperature,
            method=self.pattern_method(),
            model=self.bundle.bundle.info.bundle,
        )

    # Similar wafers ---------------------------------------------------------------------------

    @staticmethod
    def _check(wafers: Sequence[WaferInput], pattern: WaferPatternResult) -> None:
        if len(pattern.wafers) != len(wafers) or any(
            item.index != i or item.lot != w.lot or item.wafer != w.wafer
            for i, (item, w) in enumerate(zip(pattern.wafers, wafers, strict=True))
        ):
            raise ValueError("The pattern result is for other wafers than the input.")

    def _similar_item(self, j: int, similarity: float) -> SimilarItem:
        return SimilarItem(
            wafer_id=self.demo.wafer_id[j],
            recorded_label=self.demo.label[j],
            predicted_label=self.labels[int(self.demo_top[j])],
            similarity=float(np.clip(similarity, -1.0, 1.0)),
            map=self.demo_maps[j],
        )

    def nearest(self, query: npt.NDArray[np.float32], exclude: int | None) -> list[SimilarItem]:
        """The SIMILAR_K demo wafers most similar to an embedding, most similar first (ties: the
        demo order), computed as the v1 similar-wafer search does."""
        embedding = self.bundle.scores.embedding
        similarity = (embedding @ query).astype(np.float64)
        if exclude is not None:
            similarity[exclude] = -np.inf  # never the input's own source wafer
        k = min(SIMILAR_K, len(similarity) - (exclude is not None))
        nearest = np.argpartition(-similarity, k - 1)[:k] if k > 0 else np.array([], np.int64)
        ranked = sorted(nearest.tolist(), key=lambda j: (-similarity[j], j))
        return [self._similar_item(j, float(similarity[j])) for j in ranked]

    def similar(
        self, wafers: Sequence[WaferInput], pattern: WaferPatternResult
    ) -> WaferSimilarResult:
        grids = self._grids(wafers)
        self._check(wafers, pattern)
        embedding = self.score(grids).embedding
        items = [
            WaferSimilarItem(
                index=i,
                similar=self.nearest(
                    embedding[i],
                    None if w.source_wafer is None else self.demo.index_of.get(w.source_wafer),
                ),
            )
            for i, w in enumerate(wafers)
        ]
        predicted = [item.top_label for item in pattern.wafers if item.top_label != "none"]
        labels = sorted(set(predicted), key=self.labels.index)
        return WaferSimilarResult(
            wafers=items,
            searched=len(self.demo),
            precision_at_10=self.bundle.metrics.similarity_precision_at_10,
            causes=self.causes_source.causes(labels),
            method=(
                "Cosine similarity of the L2-normalised CNN embeddings, exact search over the "
                f"{len(self.demo)} real WM-811K demo wafers; an input that is itself a demo "
                "wafer never finds itself. Literature causes are listed for every pattern the "
                "model predicted in this run other than none: hypotheses to check, not a "
                "diagnosis."
            ),
        )

    # Lots -------------------------------------------------------------------------------------

    def lot_method(self) -> str:
        ref = self.bundle.lot_reference
        return (
            "Per lot of at least two wafers and per defect pattern, a one-sided binomial test "
            "P(X >= k) of the lot's count against the rate of that pattern among the wafers of "
            f"the {ref.lots} validation lots ({ref.wafers} wafers, the deployed model's "
            "predictions), as the bundle's lot test; Benjamini-Hochberg at "
            f"q = {ref.fdr_q} over every lot and pattern tested in this run (the run is the "
            "family, so q-values depend on the lots submitted together); a lot is flagged when "
            "any of its patterns is. As in those reference rates, a wafer whose energy score is "
            f"above {ref.energy_threshold:.4f} counts as unknown, not as its predicted pattern; "
            "unknown counts are not tested, because the unknown-pattern score shown is "
            "Mahalanobis. Stacked map: per die position, the share of the lot's wafers whose "
            "die failed, when the wafers share one size."
        )

    def lots(self, wafers: Sequence[WaferInput], pattern: WaferPatternResult) -> LotResult:
        self._check(wafers, pattern)
        groups: dict[str, list[int]] = {}
        for i, w in enumerate(wafers):
            groups.setdefault(w.lot, []).append(i)
        tested = {lot: rows for lot, rows in groups.items() if len(rows) >= MIN_LOT_WAFERS}
        if not tested:
            raise NeedsInput(NEEDS_LOT)
        ref = self.bundle.lot_reference
        counted = [
            "unknown" if item.energy_score > ref.energy_threshold else item.top_label
            for item in pattern.wafers
        ]
        counts = {
            lot: {c: sum(counted[i] == c for i in rows) for c in self.defects}
            for lot, rows in tested.items()
        }
        p_values = [
            binomial_tail(counts[lot][c], len(rows), ref.rates[c])
            for lot, rows in tested.items()
            for c in self.defects
        ]
        q_values, rejected = benjamini_hochberg(p_values, ref.fdr_q)
        items: list[LotItem] = []
        for n, (lot, rows) in enumerate(tested.items()):
            at = n * len(self.defects)
            tests = [
                PatternTest(
                    label=c,
                    count=counts[lot][c],
                    wafers=len(rows),
                    expected_rate=ref.rates[c],
                    p_value=p_values[at + m],
                    q_value=q_values[at + m],
                    flagged=rejected[at + m],
                )
                for m, c in enumerate(self.defects)
            ]
            stacked = stacked_failure_map([decode_map(wafers[i].map) for i in rows])
            items.append(
                LotItem(
                    lot=lot,
                    wafers=len(rows),
                    pattern_counts=counts[lot],
                    tests=tests,
                    flagged=any(t.flagged for t in tests),
                    stacked=None
                    if stacked is None
                    else StackedMap(
                        height=stacked.height,
                        width=stacked.width,
                        wafers=stacked.wafers,
                        frequencies=stacked.frequencies,
                    ),
                )
            )
        return LotResult(lots=items, method=self.lot_method())

    # Real inputs ------------------------------------------------------------------------------

    def _input(self, i: int) -> WaferInput:
        return WaferInput(
            lot=self.demo.lot[i],
            wafer=self.demo.wafer_index[i],
            map=self.demo_maps[i],
            label=self.demo.label[i],
            source_wafer=self.demo.wafer_id[i],
        )

    def from_demo(
        self, wafer_ids: Sequence[WaferId] = (), lot: LotId | None = None
    ) -> list[WaferInput]:
        """The given demo wafers in the order given (each once), then the lot's other wafers in
        wafer order; NotFoundError names the first ID that is not in the demo set."""
        rows: list[int] = []
        for wafer_id in wafer_ids:
            i = self.demo.index_of.get(wafer_id)
            if i is None:
                raise NotFoundError(f"Wafer {wafer_id} is not in the demo set.")
            if i not in rows:
                rows.append(i)
        if lot is not None:
            if lot not in self.lot_rows:
                raise NotFoundError(f"Lot {lot} is not in the demo set.")
            rows.extend(i for i in self.lot_rows[lot] if i not in rows)
        return [self._input(i) for i in rows]

    def sample(self, rng: Random) -> Picked[WaferInput]:
        eligible = [n for n in self.lot_names if len(self.lot_rows[n]) >= MIN_LOT_WAFERS]
        lot = rng.choice(eligible)
        flagged = sum(record.flagged for record in self.bundle.lots.values())
        rule = (
            f"Every demo wafer of real WM-811K lot {lot} ({len(self.lot_rows[lot])} wafers), "
            f"drawn uniformly at random from the {len(eligible)} demo lots with at least two "
            f"wafers. The demo set keeps the {flagged} lots the bundle's lot test flagged and "
            f"{len(self.lot_rows) - flagged} others drawn at random, so most lots carry a "
            "repeating pattern."
        )
        return Picked(items=self.from_demo(lot=lot), rule=rule)

    def _layouts(self) -> list[DrawLayout]:
        demo = self.demo
        sizes = Counter(zip(demo.height, demo.width, strict=True))
        common = sorted(sizes, key=lambda s: (-sizes[s], s))[:DRAW_LAYOUTS]
        layouts: list[DrawLayout] = []
        for rank, (height, width) in enumerate(common, start=1):
            rows = [
                i for i in range(len(demo)) if (demo.height[i], demo.width[i]) == (height, width)
            ]
            masks = Counter((demo.grid(i) > 0).tobytes() for i in rows)
            mask, sharing = masks.most_common(1)[0]  # ties: the layout met first
            source = next(i for i in rows if (demo.grid(i) > 0).tobytes() == mask)
            layout = (demo.grid(source) > 0).astype(np.uint8)  # every die set to pass
            wafer_id = demo.wafer_id[source]
            layouts.append(
                DrawLayout(
                    layout_id=f"{height}x{width}",
                    map=encode_map(layout),
                    source_wafer=wafer_id,
                    rule=(
                        f"The die layout of real WM-811K wafer {wafer_id} ({height} x {width} "
                        f"cells, {int(layout.sum())} dies), every die set to pass. "
                        f"{height} x {width} is the {_ordinal(rank)} map size among the "
                        f"{len(demo)} demo wafers ({sizes[(height, width)]} wafers); "
                        f"{wafer_id} is the first of them, by lot and wafer number, with the "
                        f"size's most common die layout ({sharing} wafers share it)."
                    ),
                )
            )
        return layouts

    def draw_layouts(self) -> list[DrawLayout]:
        return list(self.layouts)
