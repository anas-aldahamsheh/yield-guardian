"""Plant clock: every visitor sees the same replay position, and a restart does not reset it."""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from yield_guardian.contracts.line import PlantClock


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ReplayClock:
    """`tick` counts units off the line since the epoch; `position = tick mod units_total`."""

    epoch: datetime
    seconds_per_unit: float
    plant_times: list[datetime] = field(repr=False)
    final_test_lag_units: int
    now: Callable[[], datetime] = utc_now

    @property
    def units_total(self) -> int:
        return len(self.plant_times)

    def tick(self, at: datetime | None = None) -> int:
        elapsed = ((at or self.now()) - self.epoch).total_seconds()
        return max(0, math.floor(elapsed / self.seconds_per_unit))

    def tick_time(self, tick: int) -> datetime:
        """Wall-clock time at which unit number `tick` comes off the line."""
        return self.epoch + timedelta(seconds=tick * self.seconds_per_unit)

    def at_tick(self, tick: int, now: datetime | None = None) -> PlantClock:
        position = tick % self.units_total
        return PlantClock(
            epoch=self.epoch,
            now=now or self.tick_time(tick),
            seconds_per_unit=self.seconds_per_unit,
            units_total=self.units_total,
            position=position,
            cycle=tick // self.units_total,
            plant_time=self.plant_times[position],
            final_test_lag_units=self.final_test_lag_units,
        )

    def read(self) -> PlantClock:
        now = self.now()
        return self.at_tick(self.tick(now), now)
