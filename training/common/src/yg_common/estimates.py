"""Point estimates with a confidence interval, in the artifact contract format.

Every estimate that leaves a training pipeline is an object
``{"value", "ci_low", "ci_high", "ci_level", "method", "n"}`` (see
``packages/contracts/ARTIFACTS.md``). Non-finite numbers are written as JSON ``null``
because JSON has no NaN.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

type JsonScalar = float | int | str | bool | None


def finite_or_none(x: float) -> float | None:
    """Return ``x`` as a float, or None when it is NaN or infinite."""
    value = float(x)
    return value if math.isfinite(value) else None


@dataclass(frozen=True, slots=True)
class Estimate:
    """A point estimate with a two-sided confidence interval.

    Attributes:
        value: The point estimate computed on the full sample.
        ci_low: Lower confidence limit (NaN when undefined).
        ci_high: Upper confidence limit (NaN when undefined).
        ci_level: Confidence level, for example 0.95.
        method: How the interval was computed, in words.
        n: Number of observations (units) the estimate is based on.
    """

    value: float
    ci_low: float
    ci_high: float
    ci_level: float
    method: str
    n: int

    def __post_init__(self) -> None:
        if not 0.0 < self.ci_level < 1.0:
            raise ValueError(f"ci_level must be in (0, 1), got {self.ci_level}")
        if self.n < 0:
            raise ValueError(f"n must be non-negative, got {self.n}")
        if (
            math.isfinite(self.ci_low)
            and math.isfinite(self.ci_high)
            and self.ci_low > self.ci_high
        ):
            raise ValueError(f"ci_low {self.ci_low} exceeds ci_high {self.ci_high}")

    def to_dict(self) -> dict[str, JsonScalar]:
        """Serialise in the artifact contract format."""
        return {
            "value": finite_or_none(self.value),
            "ci_low": finite_or_none(self.ci_low),
            "ci_high": finite_or_none(self.ci_high),
            "ci_level": self.ci_level,
            "method": self.method,
            "n": self.n,
        }
