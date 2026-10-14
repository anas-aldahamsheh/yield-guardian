"""Export or import the recorded investigations as JSON (PLAN A3). No model is called.

``export`` writes every recorded run waiting for a decision, with its event log and the
investigator's paused state, to a JSON file to commit (default
``docs/recorded/investigations.json``, or ``RECORDED_RUNS_FILE``). ``import`` adds the runs of
such a file that this database lacks and changes none that exist, so it can run any number of
times; the API also does this at startup when the file is present.

Usage (inside the API container)::

    python scripts/import_recorded.py export --out /app/artifacts/recorded/investigations.json
    python scripts/import_recorded.py import /app/docs/recorded/investigations.json
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from yield_guardian.agent.wiring import psycopg_conninfo, recorded_runs_file
from yield_guardian.core.settings import Settings
from yield_guardian.db.engine import Database
from yield_guardian.services.recorded import export_recorded, import_recorded, read_runs, write_runs

EXIT_REFUSED = 2


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="write the recorded runs to a JSON file")
    export.add_argument("--out", type=Path, default=None)
    load = commands.add_parser("import", help="add the runs of a JSON file that are missing")
    load.add_argument("path", type=Path, nargs="?", default=None)
    return parser.parse_args(argv)


def fail(message: str) -> int:
    print(f"recorded runs: {message}", file=sys.stderr)
    return EXIT_REFUSED


async def run(args: argparse.Namespace, settings: Settings) -> int:
    if settings.database_url is None:
        return fail("DATABASE_URL is not set")
    url = settings.database_url.get_secret_value()
    path: Path = (args.out if args.command == "export" else args.path) or recorded_runs_file()
    runs = None
    if args.command == "import":
        try:
            runs = read_runs(path)
        except (OSError, ValueError) as error:
            return fail(f"{path} cannot be read: {error}")
    database = Database(url, migrate_on_start=False)
    try:
        async with AsyncPostgresSaver.from_conn_string(psycopg_conninfo(url)) as saver:
            await saver.setup()
            if runs is None:
                exported, left_out = await export_recorded(database.sessionmaker, saver)
                write_runs(path, exported)
                print(f"Exported {len(exported.runs)} recorded run(s) to {path}")
                for run_id in left_out:
                    print(f"  left out {run_id}: not waiting for a decision")
                for item in exported.runs:
                    if item.paused_state is None:
                        print(f"  {item.investigation.investigation_id}: no paused state saved")
            else:
                report = await import_recorded(database.sessionmaker, runs, saver)
                print(
                    f"Imported {len(report.imported)}, already present {len(report.skipped)} "
                    f"(from {path})"
                )
                for run_id in report.without_state:
                    print(f"  {run_id}: imported without its paused state")
    finally:
        await database.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(run(args, Settings()))


if __name__ == "__main__":
    raise SystemExit(main())
