"""The investigation job queue worker, a registry Resource.

Jobs live in `investigation_jobs` and are claimed with `SELECT ... FOR UPDATE SKIP LOCKED`, so any
number of API processes can work the same queue. A job of an investigation waits while another
job of the same investigation runs. Every claimed job runs in its own task: there is no
concurrency cap (PLAN D-009). Running jobs send a heartbeat; a job whose heartbeat stops (its
process died) is recovered by any worker: a run is failed with an error event, a resume is queued
again because the engineer's decision must be applied. An investigation left queued or running
with no live job (its job ended without closing it) is failed the same way, its alarm reopened.
A run is also bounded in wall time (``run_timeout_s``): past it, it fails with
:data:`TIMED_OUT` and its alarm reopens.
"""

import asyncio
import contextlib
import os
import socket
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import structlog
from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from yield_guardian.contracts.base import Problem
from yield_guardian.contracts.services import InvestigationRunner, ServiceError
from yield_guardian.contracts.workorders import ActorRole
from yield_guardian.db.notify import JOBS_CHANNEL, Notifier
from yield_guardian.db.tables import InvestigationJobRow, InvestigationRow
from yield_guardian.services import audit
from yield_guardian.services.investigations import INTERRUPTED, DbInvestigationStore, close_run_in

log = structlog.get_logger(__name__)

RunnerProvider = Callable[[], InvestigationRunner | None]

NO_RUNNER_DETAIL = (
    "No investigator is configured on this server, so the investigation could not run."
)
NO_RUNNER = Problem(
    title="Investigator not available", status=503, code="not_ready", detail=NO_RUNNER_DETAIL
)
INVESTIGATION_TIMEOUT_S = 1800.0
"""Wall-time bound of one investigation run (30 minutes, the recorder's default); each model call has its own deadline
in the gateway, so this only stops a run that keeps going call after call."""


def timed_out(limit_s: float) -> Problem:
    return Problem(
        title="Investigation timed out",
        status=504,
        code="upstream_error",
        detail=(
            f"The investigation did not finish within {limit_s / 60:g} minutes, so it was "
            "stopped. The alarm is open again; start a new investigation."
        ),
    )


RUN_FAILED = Problem(
    title="Investigation failed",
    status=500,
    code="internal_error",
    detail="The investigator stopped with an unexpected error. It has been logged.",
)


@dataclass(frozen=True, slots=True)
class Job:
    job_id: int
    investigation_id: str
    kind: str
    payload: dict[str, Any]
    attempts: int


class JobWorker:
    """Claims queued jobs and runs them; `resume_attempts` bounds crash recovery of a resume, after
    which the decision is applied without calling the runner again."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        store: DbInvestigationStore,
        runner_provider: RunnerProvider,
        notifier: Notifier | None = None,
        *,
        poll_s: float = 5.0,
        heartbeat_s: float = 10.0,
        stale_after_s: float = 60.0,
        resume_attempts: int = 3,
        run_timeout_s: float = INVESTIGATION_TIMEOUT_S,
    ) -> None:
        self._run_timeout_s = run_timeout_s
        self._sessionmaker = sessionmaker
        self._store = store
        self._runner_provider = runner_provider
        self._notifier = notifier
        self._poll_s = poll_s
        self._heartbeat_s = heartbeat_s
        self._stale_after = timedelta(seconds=stale_after_s)
        self._resume_attempts = resume_attempts
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._wake = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        self._loop_task = asyncio.create_task(self._loop(), name="investigation-jobs")

    async def stop(self) -> None:
        """Stop claiming, then interrupt running jobs (their state is saved before they end)."""
        tasks = [t for t in (self._loop_task, *self._tasks) if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._loop_task = None

    async def _loop(self) -> None:
        subscription = (
            self._notifier.subscribe(JOBS_CHANNEL)
            if self._notifier is not None
            else contextlib.nullcontext(asyncio.Event())
        )
        with subscription as notified:
            while True:
                try:
                    await self._recover_stale()
                    while (job := await self._claim()) is not None:
                        task = asyncio.create_task(self._execute(job), name=f"job-{job.job_id}")
                        self._tasks.add(task)
                        task.add_done_callback(self._tasks.discard)
                except Exception:
                    log.exception("job_loop_error")
                await self._wait(notified)

    async def _wait(self, notified: asyncio.Event) -> None:
        waiters = [asyncio.create_task(notified.wait()), asyncio.create_task(self._wake.wait())]
        try:
            await asyncio.wait(waiters, timeout=self._poll_s, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for waiter in waiters:
                waiter.cancel()
            notified.clear()
            self._wake.clear()

    async def _claim(self) -> Job | None:
        running = aliased(InvestigationJobRow)
        candidate = (
            select(InvestigationJobRow.job_id)
            .where(
                InvestigationJobRow.status == "queued",
                ~exists().where(
                    running.investigation_id == InvestigationJobRow.investigation_id,
                    running.status == "running",
                ),
            )
            .order_by(InvestigationJobRow.job_id)
            .limit(1)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        claim = (
            update(InvestigationJobRow)
            .where(InvestigationJobRow.job_id == candidate)
            .values(
                status="running",
                attempts=InvestigationJobRow.attempts + 1,
                worker=self.worker_id,
                started_at=func.now(),
                heartbeat_at=func.now(),
            )
            .returning(
                InvestigationJobRow.job_id,
                InvestigationJobRow.investigation_id,
                InvestigationJobRow.kind,
                InvestigationJobRow.payload,
                InvestigationJobRow.attempts,
            )
        )
        async with self._sessionmaker() as db, db.begin():
            row = (await db.execute(claim)).first()
        if row is None:
            return None
        return Job(
            job_id=row.job_id,
            investigation_id=row.investigation_id,
            kind=row.kind,
            payload=row.payload,
            attempts=row.attempts,
        )

    async def _recover_stale(self) -> None:
        """Requeue stale resumes and fail stale runs, in one transaction per batch."""
        async with self._sessionmaker() as db, db.begin():
            stale = (
                await db.scalars(
                    select(InvestigationJobRow)
                    .where(
                        InvestigationJobRow.status == "running",
                        InvestigationJobRow.heartbeat_at < func.now() - self._stale_after,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for job in stale:
                log.warning("job_recovered", job_id=job.job_id, kind=job.kind, worker=job.worker)
                if job.kind == "resume":
                    job.status, job.worker = "queued", None
                else:
                    job.status, job.error = "failed", "interrupted"
                    job.finished_at = datetime.now(UTC)
                    await close_run_in(db, job.investigation_id, INTERRUPTED)
            live_job = exists().where(
                InvestigationJobRow.investigation_id == InvestigationRow.investigation_id,
                InvestigationJobRow.status.in_(("queued", "running")),
            )
            orphans = (
                await db.scalars(
                    select(InvestigationRow.investigation_id)
                    .where(
                        InvestigationRow.status.in_(("queued", "running")),
                        InvestigationRow.updated_at < func.now() - self._stale_after,
                        ~live_job,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for investigation_id in orphans:
                log.warning("investigation_orphan_closed", investigation_id=investigation_id)
                await close_run_in(db, investigation_id, INTERRUPTED)
            if stale or orphans:
                await db.execute(select(func.pg_notify(JOBS_CHANNEL, "")))

    async def _finish(self, job: Job, status: str, error: str | None = None) -> None:
        async with self._sessionmaker() as db, db.begin():
            await db.execute(
                update(InvestigationJobRow)
                .where(InvestigationJobRow.job_id == job.job_id)
                .values(status=status, error=error, finished_at=func.now())
            )

    async def _heartbeat(self, job: Job) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_s)
            try:
                async with self._sessionmaker() as db, db.begin():
                    await db.execute(
                        update(InvestigationJobRow)
                        .where(
                            InvestigationJobRow.job_id == job.job_id,
                            InvestigationJobRow.status == "running",
                        )
                        .values(heartbeat_at=func.now())
                    )
            except Exception:
                log.warning("job_heartbeat_failed", job_id=job.job_id, exc_info=True)

    async def _execute(self, job: Job) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(job))
        try:
            if job.kind == "run":
                await self._run(job)
            else:
                await self._resume(job)
            await self._finish(job, "done")
        except asyncio.CancelledError:
            await asyncio.shield(self._interrupted(job))
            raise
        except Exception as exc:
            log.exception("job_failed", job_id=job.job_id, investigation_id=job.investigation_id)
            with contextlib.suppress(Exception):
                if job.kind == "run":
                    await self._store.close_run(job.investigation_id, RUN_FAILED)
                await self._finish(job, "failed", type(exc).__name__)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            self._wake.set()

    async def _interrupted(self, job: Job) -> None:
        """Save the state of a job stopped by shutdown: fail a run, queue a resume again."""
        try:
            if job.kind == "resume":
                async with self._sessionmaker() as db, db.begin():
                    await db.execute(
                        update(InvestigationJobRow)
                        .where(InvestigationJobRow.job_id == job.job_id)
                        .values(status="queued", worker=None)
                    )
            else:
                await self._store.close_run(job.investigation_id, INTERRUPTED)
                await self._finish(job, "failed", "interrupted")
        except Exception:
            log.exception("job_interrupt_not_saved", job_id=job.job_id)

    async def _run(self, job: Job) -> None:
        investigation_id = job.investigation_id
        await self._store.mark_running(investigation_id)
        runner = self._runner_provider()
        if runner is None:
            await self._store.close_run(investigation_id, NO_RUNNER)
            return
        trigger = await self._store.trigger(investigation_id)
        # Only DbInvestigationStore.create_recorded puts a position in the payload.
        as_of = job.payload.get("as_of")
        try:
            async with asyncio.timeout(self._run_timeout_s):
                await runner.run(
                    investigation_id,
                    trigger,
                    self._store.sink(investigation_id),
                    as_of=as_of if isinstance(as_of, int) else None,
                )
        except TimeoutError:
            log.warning("run_timed_out", investigation_id=investigation_id)
            await self._store.close_run(investigation_id, timed_out(self._run_timeout_s))
            return
        except ServiceError as exc:
            log.warning("runner_error", investigation_id=investigation_id, detail=exc.detail)
            await self._store.close_run(investigation_id, exc.problem())
            return
        except Exception:
            log.exception("runner_crashed", investigation_id=investigation_id)
            await self._store.close_run(investigation_id, RUN_FAILED)
            return
        await self._store.close_run(investigation_id)

    async def _resume(self, job: Job) -> None:
        """Resume the graph with the decision, then apply the decision whatever the graph did."""
        investigation_id = job.investigation_id
        runner = self._runner_provider()
        if runner is None:
            log.warning("resume_without_runner", investigation_id=investigation_id)
        elif job.attempts > self._resume_attempts:
            log.warning("resume_skipped", investigation_id=investigation_id, attempts=job.attempts)
        else:
            decision = await self._store.decision(investigation_id)
            sink = self._store.sink(investigation_id, resuming=True)
            try:
                async with asyncio.timeout(self._run_timeout_s):
                    await runner.resume(investigation_id, decision, sink)
            except Exception:
                log.exception("runner_resume_failed", investigation_id=investigation_id)
        actor = audit.Actor(
            role=cast(ActorRole, job.payload.get("actor_role", "system")),
            name=job.payload.get("actor_name"),
        )
        await self._store.finalize(investigation_id, actor)
