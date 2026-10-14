"""Resources start in order with the app and stop in reverse order, also after a failed start."""

import pytest

from yield_guardian.api.app import create_app
from yield_guardian.core.settings import Settings
from yield_guardian.services.registry import ServiceRegistry


class Recorder:
    def __init__(self, name: str, log: list[str], *, fail: bool = False) -> None:
        self.name, self.log, self.fail = name, log, fail

    async def start(self) -> None:
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        self.log.append(f"start {self.name}")

    async def stop(self) -> None:
        self.log.append(f"stop {self.name}")


async def test_resources_start_in_order_and_stop_in_reverse(settings: Settings) -> None:
    log: list[str] = []
    registry = ServiceRegistry(
        settings=settings, resources=[Recorder("a", log), Recorder("b", log)]
    )
    app = create_app(settings, registry)
    async with app.router.lifespan_context(app):
        assert log == ["start a", "start b"]
    assert log == ["start a", "start b", "stop b", "stop a"]


async def test_a_failed_start_stops_what_already_started(settings: Settings) -> None:
    log: list[str] = []
    registry = ServiceRegistry(
        settings=settings, resources=[Recorder("a", log), Recorder("b", log, fail=True)]
    )
    app = create_app(settings, registry)
    with pytest.raises(RuntimeError, match="b failed"):
        async with app.router.lifespan_context(app):
            pass
    assert log == ["start a", "stop a"]
