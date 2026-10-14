"""Building blocks shared by every API contract.

Every request and response body derives from `Contract`: unknown fields are rejected, values are
immutable, and NaN or infinity is refused, so a missing value is always an explicit `null`.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Contract(BaseModel):
    """Base class of every API body."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


SensorId = Annotated[
    str,
    StringConstraints(pattern=r"^S\d{3}$"),
    Field(
        description="Sensor ID. Column i (0-based) of secom.data is sensor S{i+1:03d}: S001 to S590.",
        examples=["S060"],
    ),
]

UnitId = Annotated[
    int,
    Field(ge=0, description="Production unit: row index (0-based) in secom.data.", examples=[1043]),
]

SequenceNo = Annotated[
    int,
    Field(ge=0, description="Position of a unit in time order (0 is the earliest unit)."),
]

LotId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.]+$"),
    Field(description="WM-811K lot name.", examples=["lot47542"]),
]

WaferId = Annotated[
    str,
    StringConstraints(max_length=80, pattern=r"^[A-Za-z0-9_.]+-\d+$"),
    Field(description='"<lot>-<wafer index>".', examples=["lot47542-12"]),
]

EvidenceId = Annotated[
    str,
    StringConstraints(pattern=r"^E\d+$"),
    Field(
        description="Evidence ID, unique within one investigation or one chat answer.",
        examples=["E3"],
    ),
]

InvestigationId = Annotated[
    str,
    StringConstraints(pattern=r"^inv_[0-9a-z]{8,40}$"),
    Field(examples=["inv_01jae5x9k3m2q7r8s0t1v2w3x4"]),
]

WorkOrderId = Annotated[
    str, StringConstraints(pattern=r"^WO-\d{6}$"), Field(examples=["WO-000012"])
]

AlarmId = Annotated[
    str,
    StringConstraints(pattern=r"^AL-\d+-(risk|t2|spe|ewma|cusum)$"),
    Field(
        description='"AL-<unit_id>-<kind>": one alarm per unit and kind.', examples=["AL-1043-t2"]
    ),
]

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
Share = Annotated[float, Field(ge=0.0, le=1.0)]
Count = Annotated[int, Field(ge=0)]


class Estimate(Contract):
    """A measured value with its confidence interval. Every metric in the product is one of these."""

    value: float
    ci_low: float | None = Field(
        description="Lower CI bound; null only when it cannot be computed (see `note`)."
    )
    ci_high: float | None = Field(
        description="Upper CI bound; null only when it cannot be computed (see `note`)."
    )
    ci_level: float = Field(0.95, gt=0.0, lt=1.0)
    method: str | None = Field(None, examples=["stratified bootstrap, 2000 resamples"])
    n: int | None = Field(None, ge=0, description="Number of observations behind the estimate.")
    note: str | None = None


class FieldError(Contract):
    loc: list[str | int]
    msg: str
    type: str


ProblemCode = Literal[
    "bad_request",
    "validation_error",
    "unauthorized",
    "forbidden",
    "csrf_failed",
    "not_found",
    "conflict",
    "not_ready",
    "upstream_error",
    "internal_error",
]


class Problem(Contract):
    """RFC 9457 problem details, served as application/problem+json for every error."""

    type: str = "about:blank"
    title: str
    status: int = Field(ge=400, le=599)
    detail: str | None = None
    instance: str | None = None
    code: ProblemCode
    errors: list[FieldError] | None = None
    retry_after_s: int | None = Field(
        None, ge=0, description="Seconds to wait, when retrying makes sense."
    )


BundleName = Literal["secom", "wafermap"]


class BundleRef(Contract):
    """Which artifact bundle a value comes from (see packages/contracts/ARTIFACTS.md)."""

    name: BundleName
    version: str = Field(examples=["v1"])
    created_at: datetime
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")


class Page(Contract):
    """Shared fields of every list response. `next_cursor` is opaque; pass it back to get the next page."""

    next_cursor: str | None = None
    total: int = Field(ge=0, description="Items matching the query across all pages.")
