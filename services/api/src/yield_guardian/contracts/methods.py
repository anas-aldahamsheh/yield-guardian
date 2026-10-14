"""Methods page and the measured-results table: provenance, model cards, limitations."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from yield_guardian.contracts.base import BundleRef, Contract, Count, Estimate

ResultFormat = Literal["ratio", "percent", "count", "number"]


class DatasetFile(Contract):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: Count


class DatasetCard(Contract):
    name: Literal["SECOM", "WM-811K"]
    description: str
    source_url: str
    citation: str
    licence: str
    retrieved_at: datetime
    files: list[DatasetFile]


class BundleInfo(Contract):
    bundle: BundleRef
    files: Count
    verified: bool = Field(description="Every file matched its SHA-256 from MANIFEST.json at load.")


class ModelCardRef(Contract):
    name: Literal["secom", "wafermap"]
    title: str


class ModelCard(Contract):
    name: Literal["secom", "wafermap"]
    title: str
    markdown: str


class MethodsOverview(Contract):
    datasets: list[DatasetCard]
    bundles: list[BundleInfo]
    model_cards: list[ModelCardRef]
    limitations: list[str]


class MeasuredResult(Contract):
    """One row of the measured-results table. `estimate` is null until the value is measured."""

    id: str = Field(examples=["secom_recall_at_fpr_0.05"])
    label: str
    estimate: Estimate | None
    format: ResultFormat
    data: str = Field(examples=["SECOM test block (held out, used once)"])
    source: str = Field(examples=["artifacts/secom/v1/operating_points.json"])


class MeasuredResults(Contract):
    results: list[MeasuredResult]
    updated_at: datetime | None
