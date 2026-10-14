"""Store evaluation results written by ``scripts/run_evaluation.py --out`` in ``llm_evaluations``.

Each file holds one run (``{"result": EvaluationResult, ...}``) or a bare ``EvaluationResult``.
A result already stored (same role, model, task set and run time) is skipped, so the command can
run again safely. No model is called.

Usage (inside the API container)::

    python scripts/import_evaluation.py /app/artifacts/evaluations/router-minicpm.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from yield_guardian.contracts.models import EvaluationResult
from yield_guardian.core.settings import Settings
from yield_guardian.db.engine import Database
from yield_guardian.llm.dbstores import DbEvaluationStore

EXIT_REFUSED = 2


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("paths", type=Path, nargs="+", help="result JSON files")
    return parser.parse_args(argv)


def read_result(path: Path) -> EvaluationResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "result" in payload:
        payload = payload["result"]
    return EvaluationResult.model_validate(payload)


def same_run(a: EvaluationResult, b: EvaluationResult) -> bool:
    return (a.role, a.model_id, a.task_set, a.run_at) == (b.role, b.model_id, b.task_set, b.run_at)


async def run(args: argparse.Namespace, settings: Settings) -> int:
    if settings.database_url is None:
        print("evaluation import: DATABASE_URL is not set", file=sys.stderr)
        return EXIT_REFUSED
    try:
        results = [(path, read_result(path)) for path in args.paths]
    except (OSError, ValueError) as error:
        print(f"evaluation import: {error}", file=sys.stderr)
        return EXIT_REFUSED
    database = Database(settings.database_url.get_secret_value(), migrate_on_start=False)
    try:
        store = DbEvaluationStore(database.sessionmaker)
        stored = list(await store.all())
        for path, result in results:
            if any(same_run(result, s) for s in stored):
                print(f"{path}: already stored")
                continue
            await store.save(result)
            stored.append(result)
            print(f"{path}: stored ({result.role}, {result.model_id}, {result.task_set})")
    finally:
        await database.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(run(args, Settings()))


if __name__ == "__main__":
    raise SystemExit(main())
