#!/usr/bin/env bash
# Everything after the 6 main training runs, in order (see README.md). Run from training/wafermap.
set -euo pipefail
export MLFLOW_DISABLE_AGENT_HINT=1 PYTHONUNBUFFERED=1
LOGS=../../artifacts/wafermap/logs
mkdir -p "$LOGS"
step() { echo "== $(date +%H:%M:%S) $*"; "$@" > "$LOGS/$(echo "$*" | tr ' /' '__' | cut -c1-80).log" 2>&1; }
step uv run python -m wm.evaluate --split lot
step uv run python -m wm.evaluate --split official
for s in 0 1 2; do step uv run python -m wm.ood fit --split lot --seed $s; done
for c in Center Donut Edge-Loc Edge-Ring Loc Near-full Random Scratch; do
  step uv run python -m wm.train --split lot --seed 0 --exclude $c --max-epochs 12
done
step uv run python -m wm.ood loco
step uv run python -m wm.similarity --split lot
step uv run python -m wm.similarity --split official
DEPLOYED=$(uv run python -c "from wm.bundle import choose_model; print(choose_model())")
echo "deployed: $DEPLOYED"
step uv run python -m wm.export --model "$DEPLOYED"
step uv run python -m wm.lots --model "$DEPLOYED"
step uv run python -m wm.bundle
echo "== $(date +%H:%M:%S) done"
