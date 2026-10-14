"""WaferService on a verified wafer-map bundle: maps, predictions, unknown patterns, similar
wafers and lot excursions.

Every value comes from the bundle: the demo maps and lot tests as stored, and the model outputs
computed once at load (see bundles/wafermap.py). Similar wafers are an exact cosine search over
the demo wafers' embeddings in memory.
"""

import base64

import numpy as np

from yield_guardian.bundles.wafermap import WafermapBundle
from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError
from yield_guardian.contracts.wafer import (
    ClassProbability,
    LotDetail,
    LotPage,
    LotSummary,
    PatternTest,
    SimilarWafer,
    SimilarWafers,
    SpatialTest,
    UnknownScore,
    WaferDetail,
    WaferHero,
    WaferLabel,
    WaferMap,
    WaferMetrics,
    WaferPage,
    WaferPrediction,
    WaferSummary,
)
from yield_guardian.services import cursors

WAFER_CURSOR = "wafers"
LOT_CURSOR = "lots"
SPATIAL_ALPHA = 0.05  # a wafer's fail dies "cluster" when the join-count p-value is below this

HERO_RULE = (
    "Deterministic rule: the lot test with the smallest q-value among the flagged defect-pattern "
    "tests (ties: smaller p-value, then lot name, then pattern); in that lot, among the wafers "
    "the model assigns to that pattern without an unknown-pattern flag, preferring wafers whose "
    "WM-811K label is the same pattern, the one with the highest calibrated probability (ties: "
    "lower wafer index)."
)


class WaferInference:
    def __init__(self, bundle: WafermapBundle) -> None:
        self.bundle = bundle
        self.wafers = bundle.wafers
        self.scores = bundle.scores
        self.labels = bundle.labels
        self.top = self.scores.probabilities.argmax(axis=1)
        self.lot_rows: dict[str, list[int]] = {}
        for i, lot in enumerate(self.wafers.lot):
            self.lot_rows.setdefault(lot, []).append(i)
        self.lot_names = sorted(self.lot_rows)
        self.tests = {name: self._tests(name) for name in self.lot_names}
        self.hero_row = self._hero()

    # Wafers -----------------------------------------------------------------------------------

    def _row(self, wafer_id: str) -> int:
        row = self.wafers.index_of.get(wafer_id)
        if row is None:
            raise NotFoundError(f"Wafer {wafer_id} is not in the demo set.")
        return row

    def _summary(self, i: int) -> WaferSummary:
        w = self.wafers
        return WaferSummary(
            wafer_id=w.wafer_id[i],
            lot=w.lot[i],
            wafer_index=w.wafer_index[i],
            die_size=w.die_size[i],
            height=w.height[i],
            width=w.width[i],
            label=w.label[i],
            official_split=w.official_split[i],
            predicted_label=self.labels[int(self.top[i])],
            unknown=bool(self.scores.is_unknown[i]),
        )

    def _map(self, i: int) -> WaferMap:
        return WaferMap(
            height=self.wafers.height[i],
            width=self.wafers.width[i],
            cells=base64.b64encode(self.wafers.maps[i]).decode("ascii"),
        )

    def _prediction(self, i: int) -> WaferPrediction:
        probabilities = self.scores.probabilities[i]
        order = sorted(range(len(self.labels)), key=lambda c: (-probabilities[c], c))
        ood = self.bundle.mahalanobis
        return WaferPrediction(
            wafer_id=self.wafers.wafer_id[i],
            top_label=self.labels[order[0]],
            top_probability=float(probabilities[order[0]]),
            probabilities=[
                ClassProbability(label=self.labels[c], probability=float(probabilities[c]))
                for c in order
            ],
            temperature=self.bundle.temperature,
            unknown=UnknownScore(
                score=float(self.scores.mahalanobis[i]),
                threshold=ood.threshold,
                is_unknown=bool(self.scores.is_unknown[i]),
                in_distribution_recall=ood.in_distribution_recall_validation,
                energy_score=float(self.scores.energy[i]),
            ),
            model=self.bundle.bundle.info.bundle,
        )

    def _spatial(self, i: int) -> SpatialTest | None:
        jc = self.bundle.join_count[i]
        if jc.expected is None or jc.p is None:
            return None  # fewer than two fail dies: nothing to test
        return SpatialTest(
            statistic=float(jc.bb),
            expected=jc.expected,
            p_value=jc.p,
            permutations=self.bundle.permutations,
            clustered=jc.p < SPATIAL_ALPHA,
        )

    def _detail(self, i: int) -> WaferDetail:
        return WaferDetail(
            wafer=self._summary(i),
            map=self._map(i),
            prediction=self._prediction(i),
            spatial=self._spatial(i),
            attribution=self.bundle.attribution,
        )

    async def list_wafers(
        self,
        *,
        lot: str | None = None,
        label: WaferLabel | None = None,
        unknown: bool | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> WaferPage:
        """Demo wafers by lot and wafer index; `label` filters on the WM-811K label."""
        if limit < 1:
            raise InvalidArgumentError("limit must be at least 1.")
        rows = [
            i
            for i in (self.lot_rows.get(lot, []) if lot is not None else range(len(self.wafers)))
            if (label is None or self.wafers.label[i] == label)
            and (unknown is None or bool(self.scores.is_unknown[i]) == unknown)
        ]
        start = 0
        if cursor is not None:
            (after,) = cursors.decode(WAFER_CURSOR, cursor, str)
            last = self.wafers.index_of.get(str(after))
            if last is None:
                raise InvalidArgumentError("The cursor is not valid for this list.")
            start = next((n for n, i in enumerate(rows) if i > last), len(rows))
        page = rows[start : start + limit]
        more = start + limit < len(rows)
        return WaferPage(
            items=[self._summary(i) for i in page],
            next_cursor=cursors.encode(WAFER_CURSOR, self.wafers.wafer_id[page[-1]])
            if more and page
            else None,
            total=len(rows),
        )

    async def get_wafer(self, wafer_id: str) -> WaferDetail:
        return self._detail(self._row(wafer_id))

    async def get_prediction(self, wafer_id: str) -> WaferPrediction:
        return self._prediction(self._row(wafer_id))

    # Hero -------------------------------------------------------------------------------------

    def _hero(self) -> int | None:
        flagged = sorted(
            (t.q_value, t.p_value, name, t.label)
            for name, tests in self.tests.items()
            for t in tests
            if t.flagged and t.label != "none"
        )
        for _, _, name, pattern in flagged:
            c = self.labels.index(pattern)
            candidates = [
                i
                for i in self.lot_rows[name]
                if int(self.top[i]) == c and not self.scores.is_unknown[i]
            ]
            if candidates:
                return min(
                    candidates,
                    key=lambda i: (
                        self.wafers.label[i] != pattern,
                        -float(self.scores.probabilities[i, c]),
                        self.wafers.wafer_index[i],
                    ),
                )
        return None

    async def get_hero(self) -> WaferHero:
        if self.hero_row is None:
            raise NotFoundError("No demo wafer meets the hero rule. " + HERO_RULE)
        detail = self._detail(self.hero_row)
        return WaferHero(**dict(detail), selection=HERO_RULE)

    # Similar wafers ---------------------------------------------------------------------------

    async def get_similar(self, wafer_id: str, *, k: int = 10) -> SimilarWafers:
        if k < 1:
            raise InvalidArgumentError("k must be at least 1.")
        i = self._row(wafer_id)
        embedding = self.scores.embedding
        similarity = (embedding @ embedding[i]).astype(np.float64)
        similarity[i] = -np.inf  # never the query itself
        k = min(k, len(similarity) - 1)
        nearest = np.argpartition(-similarity, k - 1)[:k] if k else np.array([], dtype=np.int64)
        ranked = sorted(nearest.tolist(), key=lambda j: (-similarity[j], j))
        return SimilarWafers(
            wafer_id=wafer_id,
            k=k,
            results=[
                SimilarWafer(
                    wafer=self._summary(j),
                    similarity=float(np.clip(similarity[j], -1.0, 1.0)),
                    map=self._map(j),
                )
                for j in ranked
            ],
            method=(
                "Cosine similarity of the L2-normalised CNN embeddings, exact search over the "
                f"{len(self.wafers)} demo wafers; the query wafer is excluded."
            ),
            precision_at_10=self.bundle.metrics.similarity_precision_at_10,
        )

    # Lots -------------------------------------------------------------------------------------

    def _tests(self, name: str) -> list[PatternTest]:
        return [
            PatternTest(
                label=t.pattern,
                count=t.count,
                wafers=t.wafers,
                expected_rate=t.expected_rate,
                p_value=t.p,
                q_value=t.q,
                flagged=t.flagged,
            )
            for t in self.bundle.lots[name].tests
            if t.pattern in self.labels  # the energy-based unknown tests are not served
        ]

    def _lot(self, name: str) -> LotSummary:
        tests = self.tests[name]
        return LotSummary(
            lot=name,
            wafers=len(self.lot_rows[name]),
            labelled=sum(self.wafers.label[i] is not None for i in self.lot_rows[name]),
            flagged_labels=[t.label for t in tests if t.flagged],
            min_q_value=min((t.q_value for t in tests), default=None),
        )

    async def list_lots(
        self, *, flagged_only: bool = False, cursor: str | None = None, limit: int = 100
    ) -> LotPage:
        if limit < 1:
            raise InvalidArgumentError("limit must be at least 1.")
        names = [
            n for n in self.lot_names if not flagged_only or any(t.flagged for t in self.tests[n])
        ]
        start = 0
        if cursor is not None:
            (after,) = cursors.decode(LOT_CURSOR, cursor, str)
            start = next((n for n, name in enumerate(names) if name > str(after)), len(names))
        page = names[start : start + limit]
        more = start + limit < len(names)
        return LotPage(
            items=[self._lot(n) for n in page],
            next_cursor=cursors.encode(LOT_CURSOR, page[-1]) if more and page else None,
            total=len(names),
        )

    async def get_lot(self, lot: str) -> LotDetail:
        if lot not in self.lot_rows:
            raise NotFoundError(f"Lot {lot} is not in the demo set.")
        return LotDetail(
            lot=lot,
            wafers=[self._summary(i) for i in self.lot_rows[lot]],
            tests=self.tests[lot],
            stacked=self.bundle.stacked[lot],
            method=self.bundle.lot_method,
        )

    # Metrics ----------------------------------------------------------------------------------

    async def get_metrics(self) -> WaferMetrics:
        return self.bundle.metrics
