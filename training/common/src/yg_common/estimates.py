"""Point estimates with a confidence interval, in the artifact contract format.

Every estimate that leaves a training pipeline is an object
``{"value", "ci_low", "ci_high", "ci_level", "method", "n"}`` plus an optional ``note``
(see ``packages/contracts/ARTIFACTS.md``). The contract rules:

- ``value`` is never null. An undefined quantity (for example precision when nothing is
  flagged) must be left out by the caller; ``to_dict`` refuses to serialise it.
- ``ci_low`` and ``ci_high`` may be null only when a bound cannot be computed, and then
  ``note`` says why (a default reason is supplied when the caller gives none).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

type JsonScalar = float | int | str | bool | None

UNDEFINED_BOUND_NOTE = "interval bound undefined: no resample gave a finite value"


class UndefinedEstimateError(ValueError):
    """An estimate whose point value is undefined was about to be published."""


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
        note: Why a bound is missing, or another caveat (optional).
    """

    value: float
    ci_low: float
    ci_high: float
    ci_level: float
    method: str
    n: int
    note: str | None = None

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

    @property
    def defined(self) -> bool:
        """True when the point value is a finite number (publishable)."""
        return math.isfinite(self.value)

    def to_dict(self) -> dict[str, JsonScalar]:
        """Serialise in the artifact contract format.

        Raises:
            UndefinedEstimateError: if ``value`` is not finite; leave the quantity out
                and state the reason in the limitations instead.
        """
        if not self.defined:
            raise UndefinedEstimateError(
                f"estimate value is undefined ({self.value}); omit it and say why"
            )
        out: dict[str, JsonScalar] = {
            "value": float(self.value),
            "ci_low": finite_or_none(self.ci_low),
            "ci_high": finite_or_none(self.ci_high),
            "ci_level": self.ci_level,
            "method": self.method,
            "n": self.n,
        }
        note = self.note
        if note is None and (out["ci_low"] is None or out["ci_high"] is None):
            note = UNDEFINED_BOUND_NOTE
        if note is not None:
            out["note"] = note
        return out
