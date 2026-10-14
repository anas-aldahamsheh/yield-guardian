"""MethodsService from what the API has loaded: dataset provenance, verified bundles, model cards,
limitations and the measured-results table.

Every number in the results table comes from a loaded bundle's evaluation; a row whose value has
not been measured keeps a null estimate. The texts written here describe sources, never results.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from yield_guardian.contracts.base import Estimate
from yield_guardian.contracts.methods import (
    BundleInfo,
    DatasetCard,
    DatasetFile,
    MeasuredResult,
    MeasuredResults,
    MethodsOverview,
    ModelCard,
    ModelCardRef,
    ResultFormat,
)
from yield_guardian.contracts.secom import SecomMetrics
from yield_guardian.contracts.services import (
    NotFoundError,
    NotReadyError,
    SecomService,
    WaferService,
)
from yield_guardian.contracts.wafer import WaferMetrics

CardName = Literal["secom", "wafermap"]
CARD_TITLES: dict[CardName, str] = {
    "secom": "SECOM failure risk, control charts and sensor health",
    "wafermap": "WM-811K wafer-map patterns, unknown patterns and similar wafers",
}
DESCRIPTIONS = {
    "secom": (
        "Production units of a semiconductor fab, each with 590 anonymous sensor readings, a pass "
        "or fail result from final test and a timestamp."
    ),
    "wm811k": (
        "Wafer maps from real fabs (pass or fail per die), about a fifth of them labelled with one "
        "of nine defect patterns."
    ),
}
NAMES: dict[str, Literal["SECOM", "WM-811K"]] = {"secom": "SECOM", "wm811k": "WM-811K"}


def _main_metric(metrics: SecomMetrics, model: str | None, metric: str) -> Estimate | None:
    for result in metrics.models:
        if result.main if model is None else result.model == model:
            for value in result.metrics:
                if value.metric == metric:
                    return value.estimate
    return None


def _row(
    id_: str, label: str, estimate: Estimate | None, fmt: ResultFormat, data: str, source: str
) -> MeasuredResult:
    return MeasuredResult(
        id=id_, label=label, estimate=estimate, format=fmt, data=data, source=source
    )


class BundleMethods:
    def __init__(
        self,
        *,
        bundles: list[BundleInfo],
        artifacts_dir: Path,
        manifest_path: Path,
        secom: SecomService | None,
        wafer: WaferService | None,
    ) -> None:
        self.bundles = bundles
        self.artifacts_dir = artifacts_dir
        self.manifest_path = manifest_path
        self.secom = secom
        self.wafer = wafer

    def _bundle(self, name: str) -> BundleInfo | None:
        return next((b for b in self.bundles if b.bundle.name == name), None)

    def _datasets(self) -> list[DatasetCard]:
        try:
            manifest: dict[str, Any] = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        cards = []
        for key, name in NAMES.items():
            entry = manifest.get(key)
            if not isinstance(entry, dict):
                continue
            cards.append(
                DatasetCard(
                    name=name,
                    description=DESCRIPTIONS[key],
                    source_url=str(entry.get("page") or entry.get("source")),
                    citation=str(entry["citation"]),
                    licence=str(entry["licence"]),
                    retrieved_at=datetime.fromisoformat(str(entry["retrieved_at"])),
                    files=[
                        DatasetFile(path=f["path"], sha256=f["sha256"], bytes=f["bytes"])
                        for f in entry.get("files", [])
                    ],
                )
            )
        return cards

    async def _metrics(self) -> tuple[SecomMetrics | None, WaferMetrics | None]:
        secom = await self.secom.get_metrics() if self.secom is not None else None
        wafer = await self.wafer.get_metrics() if self.wafer is not None else None
        return secom, wafer

    async def overview(self) -> MethodsOverview:
        if not self.bundles:
            raise NotReadyError("No model bundle is loaded, so there are no methods to show.")
        secom, wafer = await self._metrics()
        limitations = [
            *(f"SECOM: {text}" for text in (secom.limitations if secom else [])),
            *(f"Wafer maps: {text}" for text in (wafer.limitations if wafer else [])),
        ]
        return MethodsOverview(
            datasets=self._datasets(),
            bundles=self.bundles,
            model_cards=[
                ModelCardRef(name=name, title=CARD_TITLES[name])
                for name in ("secom", "wafermap")
                if self._bundle(name) is not None
            ],
            limitations=limitations,
        )

    async def model_card(self, name: str) -> ModelCard:
        if name not in CARD_TITLES:
            raise NotFoundError(f"There is no model card named {name!r}.")
        card_name: CardName = "secom" if name == "secom" else "wafermap"
        info = self._bundle(card_name)
        if info is None:
            raise NotReadyError(f"The {card_name} bundle is not loaded.")
        path = self.artifacts_dir / card_name / info.bundle.version / "model_card.md"
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError as error:
            raise NotReadyError(f"The {card_name} model card could not be read.") from error
        return ModelCard(name=card_name, title=CARD_TITLES[card_name], markdown=markdown)

    async def results(self) -> MeasuredResults:
        if not self.bundles:
            raise NotReadyError("No model bundle is loaded, so nothing has been measured yet.")
        secom, wafer = await self._metrics()
        points = await self.secom.get_operating_points() if self.secom is not None else None
        default = (
            next((p for p in points.points if p.id == points.default), None) if points else None
        )
        test_block = "SECOM test block, held out and used once"
        secom_metrics = "artifacts/secom/v1/metrics.json"
        rows = [
            _row(
                "secom_pr_auc",
                "SECOM failure-risk PR-AUC, LightGBM",
                _main_metric(secom, None, "pr_auc") if secom else None,
                "ratio",
                test_block,
                secom_metrics,
            ),
            _row(
                "secom_pr_auc_no_skill",
                "SECOM PR-AUC of a no-skill score (the failure rate)",
                _main_metric(secom, "prevalence", "pr_auc") if secom else None,
                "ratio",
                test_block,
                secom_metrics,
            ),
            _row(
                "secom_pr_auc_logistic",
                "SECOM PR-AUC, logistic regression baseline",
                _main_metric(secom, "logistic_regression", "pr_auc") if secom else None,
                "ratio",
                test_block,
                secom_metrics,
            ),
            _row(
                "secom_recall_at_fpr_0.05",
                f"Failures caught at the {default.label} threshold"
                if default
                else "Failures caught at the default threshold",
                default.recall if default else None,
                "percent",
                test_block,
                "artifacts/secom/v1/operating_points.json",
            ),
            _row(
                "secom_false_alarms_per_100",
                "False alarms per 100 units at that threshold",
                default.false_alarms_per_100 if default else None,
                "number",
                test_block,
                "artifacts/secom/v1/operating_points.json",
            ),
            _row(
                "fdc_false_alarm_rate",
                "T² false-alarm rate on held-out in-control units (99% limit)",
                secom.fdc.false_alarm_rate_99 if secom and secom.fdc else None,
                "percent",
                "SECOM reference period, held-out half",
                secom_metrics,
            ),
            _row(
                "secom_sensors_to_inspect",
                "Sensors to inspect per investigation (median), of 590",
                None,
                "count",
                "Recorded investigations",
                "investigations",
            ),
        ]
        if wafer is not None:
            split = {s.split: s for s in wafer.splits}
            auto = next(
                (a for a in wafer.auto_classification if abs(a.precision_target - 0.99) < 1e-9),
                None,
            )
            wafer_metrics = "artifacts/wafermap/v1/metrics.json"
            rows += [
                _row(
                    "wafer_macro_f1_lot_grouped",
                    "Wafer-map macro-F1, lot-grouped split",
                    split["lot_grouped"].macro_f1 if "lot_grouped" in split else None,
                    "ratio",
                    "WM-811K lot-grouped test split (no lot in two parts)",
                    wafer_metrics,
                ),
                _row(
                    "wafer_macro_f1_official",
                    "Wafer-map macro-F1, official split",
                    split["official"].macro_f1 if "official" in split else None,
                    "ratio",
                    "WM-811K official test split (test lots differ from training lots)",
                    wafer_metrics,
                ),
                _row(
                    "unknown_auroc_loco",
                    "Unknown-pattern AUROC, leave-one-class-out mean (Mahalanobis)",
                    wafer.ood.mean_auroc,
                    "ratio",
                    "WM-811K, 8 held-out classes",
                    wafer_metrics,
                ),
                _row(
                    "similar_precision_at_10",
                    "Similar-wafer precision@10",
                    wafer.similarity_precision_at_10,
                    "percent",
                    "WM-811K lot-grouped test maps",
                    wafer_metrics,
                ),
                _row(
                    "auto_classified_share",
                    "Wafer maps classified automatically at 99% precision",
                    auto.share if auto else None,
                    "percent",
                    "WM-811K lot-grouped test split",
                    wafer_metrics,
                ),
            ]
        rows.append(
            _row(
                "points_per_investigation",
                "Points per full investigation (Token Factory)",
                None,
                "number",
                "Recorded investigations",
                "investigations",
            )
        )
        created = [b.bundle.created_at for b in self.bundles]
        return MeasuredResults(results=rows, updated_at=max(created) if created else None)
