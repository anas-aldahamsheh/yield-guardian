"""Builds the database-backed services: sessions, investigations, work orders, audit, alarm
states and live runs."""

from dataclasses import dataclass, field

from yield_guardian.core.settings import Settings
from yield_guardian.db.engine import Database
from yield_guardian.db.notify import Notifier
from yield_guardian.services.alarms import DbAlarmStateStore
from yield_guardian.services.audit import DbAuditLog
from yield_guardian.services.investigations import DbInvestigationStore
from yield_guardian.services.jobs import JobWorker, RunnerProvider
from yield_guardian.services.registry import Resource, ServiceRegistry
from yield_guardian.services.runs import DbRunStore
from yield_guardian.services.sessions import DbSessionManager
from yield_guardian.services.workorders import DbWorkOrderStore


@dataclass(slots=True)
class Persistence:
    database: Database
    notifier: Notifier
    sessions: DbSessionManager
    investigations: DbInvestigationStore
    work_orders: DbWorkOrderStore
    audit: DbAuditLog
    alarms: DbAlarmStateStore
    jobs: JobWorker
    runs: DbRunStore
    resources: list[Resource] = field(default_factory=list)

    def install(self, registry: ServiceRegistry) -> None:
        """Put the stores on the registry and append the resources (database, listener, jobs)."""
        registry.sessions = self.sessions
        registry.investigations = self.investigations
        registry.work_orders = self.work_orders
        registry.audit = self.audit
        registry.run_reader = self.runs
        registry.resources.extend(self.resources)

        def on_status(ok: bool) -> None:
            registry.database_ok = ok

        self.database.on_status = on_status


def build_persistence(
    settings: Settings, *, runner_provider: RunnerProvider, migrate: bool = True
) -> Persistence:
    """The stores and their resources, started in order: database (migrated to head when
    `migrate`), the LISTEN connection, the job worker. Raises ValueError on bad configuration."""
    if settings.database_url is None:
        raise ValueError("DATABASE_URL is not set.")
    database = Database(settings.database_url.get_secret_value(), migrate_on_start=migrate)
    notifier = Notifier(database.dsn)
    investigations = DbInvestigationStore(database.sessionmaker, notifier)
    jobs = JobWorker(database.sessionmaker, investigations, runner_provider, notifier)
    return Persistence(
        database=database,
        notifier=notifier,
        sessions=DbSessionManager(database.sessionmaker, settings),
        investigations=investigations,
        work_orders=DbWorkOrderStore(database.sessionmaker),
        audit=DbAuditLog(database.sessionmaker),
        alarms=DbAlarmStateStore(database.sessionmaker),
        jobs=jobs,
        runs=DbRunStore(database.sessionmaker, notifier),
        resources=[database, notifier, jobs],
    )
