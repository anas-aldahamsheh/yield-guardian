"""Record demo investigations on the server (PLAN L11): real alarms, the normal job path.

It picks alarms from the real SECOM replay with a fixed rule (``agent/recording.py``: test-block
alarms at alarm severity, round-robin over risk, T2 and SPE, one per unit), lists them, and
prints the most points the runs can spend with the role chains stored on this server. It then
refuses in CI, without ``TOKEN_FACTORY_API_KEY`` and without ``--confirm``.

Confirmed, it stores each investigation as recorded (``recorded = true``) and queues it like
any other: the API's job worker runs the investigator. The script waits for each run to reach
the engineer's decision (or fail) before queueing the next, and prints its models and the points
from the usage the server reported. Decisions stay with a person in the UI. Export the runs afterwards with
``scripts/import_recorded.py export``.

Usage (inside the API container, where DATABASE_URL, the bundle and the key are set)::

    python scripts/record_investigations.py --count 3            # list and bound only
    python scripts/record_investigations.py --count 3 --confirm  # record
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections.abc import Mapping

from yield_guardian.agent.recording import (
    SELECTION_RULE,
    ChosenAlarm,
    UnboundedError,
    choose_alarms,
    investigation_bound,
)
from yield_guardian.bundles.manifest import BundleError, latest_version, verify_bundle
from yield_guardian.bundles.secom import load_secom_bundle
from yield_guardian.contracts.investigation import Investigation
from yield_guardian.core.settings import Settings
from yield_guardian.db.engine import Database
from yield_guardian.llm.dbstores import DbRoleAssignmentStore
from yield_guardian.llm.factory import key_configured
from yield_guardian.llm.profiles import ProfileCatalog
from yield_guardian.llm.registry import ModelRegistry
from yield_guardian.services.audit import Actor
from yield_guardian.services.investigations import DbInvestigationStore

EXIT_REFUSED = 2
SETTLED = frozenset({"awaiting_decision", "failed", "approved", "rejected"})
RECORDER = Actor(role="system", name="Recorded demo run")
POLL_SECONDS = 2.0
UNCLAIMED_WARNING_SECONDS = 60.0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--count", type=int, default=3, help="how many runs to record")
    parser.add_argument("--confirm", action="store_true", help="confirm spending shared quota")
    parser.add_argument(
        "--timeout", type=float, default=1800.0, help="seconds to wait for each run"
    )
    return parser.parse_args(argv)


def fail(message: str) -> int:
    print(f"record: {message}", file=sys.stderr)
    return EXIT_REFUSED


def refusal(env: Mapping[str, str], *, confirmed: bool, has_key: bool) -> str | None:
    if not has_key:
        return "TOKEN_FACTORY_API_KEY is not set"
    if not confirmed:
        return "add --confirm to record (this spends at most the points bounded above)"
    return None


def show_alarms(alarms: list[ChosenAlarm]) -> None:
    print(f"Rule: {SELECTION_RULE}")
    for n, alarm in enumerate(alarms, 1):
        print(f"  {n}. {alarm.alarm_id} (sequence {alarm.sequence}): {alarm.message}")


def usage_line(investigation: Investigation) -> str:
    """The run's models and the usage the server reported, summed over its model calls."""
    models = ", ".join(f"{m.role} {m.model_id}" for m in investigation.models) or "none"
    usage = investigation.usage
    if usage is None:
        return f"models: {models}; no model call was made: 0 points"
    unknown = (
        f"; {usage.requests_without_usage} request(s) reported no usage (not in the sum)"
        if usage.requests_without_usage
        else ""
    )
    return (
        f"models: {models}; {usage.requests} request(s), {usage.cache_hits} cached; tokens in "
        f"{usage.tokens_in}, out {usage.tokens_out} (reasoning {usage.tokens_reasoning}); "
        f"points {usage.points:.6f}{unknown}"
    )


async def wait_for(store: DbInvestigationStore, investigation_id: str, limit_s: float) -> str:
    start = time.monotonic()
    warned = False
    while True:
        investigation = await store.get(investigation_id)
        if investigation.status in SETTLED:
            return investigation.status
        waited = time.monotonic() - start
        if investigation.status == "queued" and waited > UNCLAIMED_WARNING_SECONDS and not warned:
            print("  still queued: is the API (and its job worker) running?", file=sys.stderr)
            warned = True
        if waited > limit_s:
            return f"still {investigation.status} after {limit_s:.0f} s"
        await asyncio.sleep(POLL_SECONDS)


async def run(args: argparse.Namespace, settings: Settings, env: Mapping[str, str]) -> int:
    if env.get("CI", "").strip():
        return fail("refusing to run in CI: recording spends the team's shared quota")
    if args.count < 1:
        return fail("--count must be at least 1")
    if settings.database_url is None:
        return fail("DATABASE_URL is not set: runs go through the server's job queue")
    try:
        verified = verify_bundle(latest_version(settings.artifacts_dir, "secom"), "secom")
        bundle = load_secom_bundle(verified, settings.secom_data_dir)
    except (BundleError, OSError) as error:
        return fail(f"the SECOM bundle did not load: {error}")
    alarms = choose_alarms(bundle, args.count)
    show_alarms(alarms)
    if len(alarms) < args.count:
        print(f"Only {len(alarms)} alarm(s) match the rule.")
    database = Database(settings.database_url.get_secret_value(), migrate_on_start=False)
    try:
        registry = ModelRegistry(ProfileCatalog(), DbRoleAssignmentStore(database.sessionmaker))
        for warning in await registry.load():
            print(f"Role warning: {warning}")
        try:
            bound = investigation_bound(registry)
        except UnboundedError as error:
            return fail(f"the cost cannot be bounded: {error}")
        for role in bound.roles:
            print(
                f"  {role.role}: up to {role.calls} call(s) of max_tokens {role.max_tokens} on "
                f"{', '.join(role.models)}: at most {role.points:.4f} points"
            )
        print(
            f"Upper bound: {bound.points:.4f} points per run, "
            f"{bound.points * len(alarms):.4f} points for {len(alarms)} run(s)"
        )
        print("  (each prompt counted at the model's whole context window: far above real use)")
        reason = refusal(env, confirmed=args.confirm, has_key=key_configured(settings))
        if reason is not None:
            return fail(reason)
        store = DbInvestigationStore(database.sessionmaker)
        spent = 0.0
        for alarm in alarms:
            investigation = await store.create_recorded(
                alarm.trigger(), actor=RECORDER, as_of=alarm.sequence
            )
            if not investigation.recorded:
                print(f"{alarm.alarm_id}: already under investigation {investigation.investigation_id}; skipped")  # fmt: skip
                continue
            print(f"{alarm.alarm_id}: {investigation.investigation_id} queued")
            status = await wait_for(store, investigation.investigation_id, args.timeout)
            done = await store.get(investigation.investigation_id)
            print(f"  {status}")
            print(f"  {usage_line(done)}")
            spent += done.usage.points if done.usage else 0.0
            if done.error is not None:
                print(f"  error: {done.error.title}: {done.error.detail}")
        print(f"Points spent by these runs (documented pricing, reported usage): {spent:.6f}")
    finally:
        await database.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(run(args, Settings(), os.environ))


if __name__ == "__main__":
    raise SystemExit(main())
