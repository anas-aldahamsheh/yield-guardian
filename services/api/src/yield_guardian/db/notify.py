"""PostgreSQL LISTEN/NOTIFY: one listening connection per process wakes in-process waiters.

Writers call `pg_notify(channel, key)` inside their transaction, so the wake-up arrives after the
commit, in every API process. Waiters always re-read the database when woken and also poll, so a
lost connection only delays them.
"""

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import Iterator
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger(__name__)

JOBS_CHANNEL = "yg_jobs"
EVENTS_CHANNEL = "yg_investigation_events"
ALARMS_CHANNEL = "yg_alarm_states"
CHANNELS = (JOBS_CHANNEL, EVENTS_CHANNEL, ALARMS_CHANNEL)

HEALTH_CHECK_S = 30.0
RECONNECT_S = 2.0


class Notifier:
    """Listens on every channel of this app and wakes subscribers by channel and payload."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._waiters: defaultdict[tuple[str, str | None], set[asyncio.Event]] = defaultdict(set)
        self._ready = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @contextlib.contextmanager
    def subscribe(self, channel: str, key: str | None = None) -> Iterator[asyncio.Event]:
        """An event set on each notification for `key` (any payload when None) or on reconnect."""
        event = asyncio.Event()
        waiters = self._waiters[(channel, key)]
        waiters.add(event)
        try:
            yield event
        finally:
            waiters.discard(event)
            if not waiters:
                self._waiters.pop((channel, key), None)

    def _dispatch(self, _connection: Any, _pid: int, channel: str, payload: str) -> None:
        for key in (payload, None):
            for event in self._waiters.get((channel, key), ()):
                event.set()

    def _wake_all(self) -> None:
        for waiters in self._waiters.values():
            for event in waiters:
                event.set()

    async def _listen_once(self) -> None:
        connection = await asyncpg.connect(self._dsn)
        lost = asyncio.Event()
        try:
            connection.add_termination_listener(lambda _c: lost.set())
            for channel in CHANNELS:
                await connection.add_listener(channel, self._dispatch)
            self._ready.set()
            self._wake_all()
            while not lost.is_set():
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(lost.wait(), HEALTH_CHECK_S)
                if not lost.is_set():
                    await asyncio.wait_for(connection.fetchval("SELECT 1"), HEALTH_CHECK_S)
        finally:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(connection.close(), 5)

    async def _run(self) -> None:
        while True:
            try:
                await self._listen_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("notify_listener_lost", exc_info=True)
            self._ready.clear()
            self._wake_all()
            await asyncio.sleep(RECONNECT_S)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="notify-listener")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._ready.wait(), 10)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
