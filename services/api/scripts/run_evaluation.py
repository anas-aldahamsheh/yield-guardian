"""Evaluate one model in one role on a hand-written task set (``scripts/evaluation/*.json``).

It spends points from the team's shared daily quota, so it refuses to run in CI (any non-empty
``CI``), without ``TOKEN_FACTORY_API_KEY``, and without ``--confirm``. It always prints the
upper bound of the points the run can spend first; without ``--confirm`` it stops there.

Usage (from ``services/api``)::

    uv run python scripts/run_evaluation.py scripts/evaluation/router_intents.json \
        --model MiniCPM5-2B
    TOKEN_FACTORY_API_KEY=... uv run python scripts/run_evaluation.py \
        scripts/evaluation/router_intents.json --model MiniCPM5-2B --confirm --out result.json

The result (an ``EvaluationResult`` plus each task's outcome) is printed and, with ``--out``,
written as JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from yield_guardian.agent.evaluation import (
    CostEstimate,
    EvaluationError,
    estimate_cost,
    load_task_set,
    run_task_set,
    single_model_registry,
    task_role,
)
from yield_guardian.core.settings import Settings
from yield_guardian.llm.factory import assemble_llm_stack, key_configured
from yield_guardian.llm.profiles import ProfileCatalog

EXIT_REFUSED = 2


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("task_set", type=Path, help="a task set JSON file")
    parser.add_argument("--model", required=True, help="the model to evaluate")
    parser.add_argument("--confirm", action="store_true", help="confirm spending shared quota")
    parser.add_argument("--out", type=Path, help="write the result as JSON to this file")
    return parser.parse_args(argv)


def refusal(env: Mapping[str, str], *, confirmed: bool, has_key: bool) -> str | None:
    """Why the run must not call the endpoint, or None when it may."""
    if env.get("CI", "").strip():
        return "refusing to run in CI: an evaluation spends the team's shared quota"
    if not has_key:
        return "TOKEN_FACTORY_API_KEY is not set"
    if not confirmed:
        return "add --confirm to run (this spends the points bounded above)"
    return None


def describe(estimate: CostEstimate) -> str:
    lines = [
        f"Model {estimate.model}: {estimate.calls} call(s), {estimate.prompt_bytes} request "
        f"bytes, at most {estimate.max_output_tokens} output tokens",
        f"Upper bound for this run: {estimate.points_upper_bound:.6f} points",
    ]
    lines += [f"  assumes {a}" for a in estimate.assumptions]
    return "\n".join(lines)


def fail(message: str) -> int:
    print(f"evaluation: {message}", file=sys.stderr)
    return EXIT_REFUSED


async def run(args: argparse.Namespace, settings: Settings, env: Mapping[str, str]) -> int:
    if env.get("CI", "").strip():  # before anything else, even reading the task set
        return fail("refusing to run in CI: an evaluation spends the team's shared quota")
    try:
        task_set = load_task_set(args.task_set)
        estimate = estimate_cost(task_set, args.model, ProfileCatalog())
    except (OSError, ValueError) as exc:
        return fail(str(exc))
    print(describe(estimate))
    reason = refusal(env, confirmed=args.confirm, has_key=key_configured(settings))
    if reason is not None:
        return fail(reason)
    stack = assemble_llm_stack(settings)
    try:
        role = task_role(task_set)
        stack.gateway.registry = await single_model_registry(role, args.model, stack.catalog)
        result = await run_task_set(stack.gateway, task_set, args.model)
    except EvaluationError as exc:
        return fail(str(exc))
    finally:
        await stack.aclose()
    payload = result.to_json()
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(run(args, Settings(), os.environ))


if __name__ == "__main__":
    raise SystemExit(main())
