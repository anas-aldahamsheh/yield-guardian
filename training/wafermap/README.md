# Wafer-map science (WM-811K)

Pattern classifier, unknown-pattern score, similar-wafer search and lot statistics.
Plan: `docs/PLAN.md` §6.5–6.7. Model card: `docs/model-cards/wafermap.md`.

## Environment

```
uv sync                      # Python 3.13, torch 2.14.1 (CUDA 13.0 build), pinned by uv.lock
```

Code is device-agnostic. On AMD GPUs install the ROCm build of the same torch version
(Linux): `uv pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/rocm<ver>`;
ROCm exposes HIP through `torch.cuda`, so nothing else changes.

## Run order (from this folder)

```
python ../../data/download.py wm811k                     # or: uv run --no-project --with certifi ...
uv venv ../../data/interim/.venv-wm811k --python 3.10     # LSWMD.pkl needs pandas 1.x
uv pip install --python ../../data/interim/.venv-wm811k "pandas==1.5.3" "numpy<2" "pyarrow<18"
../../data/interim/.venv-wm811k/Scripts/python -I scripts/convert_lswmd.py \
    ../../data/raw/wm811k/LSWMD.pkl ../../data/interim/wm811k/wm811k.parquet
uv run python -m wm.facts                                # reports/wm811k_facts.*
uv run python -m wm.preprocess                           # 64x64 nearest-neighbour cache
uv run python -m wm.splits                               # reports/splits.json
for s in 0 1 2; do uv run python -m wm.train --split lot --seed $s; done
for s in 0 1 2; do uv run python -m wm.train --split official --seed $s; done
uv run python -m wm.evaluate --split lot                 # reports/metrics_lot.json
uv run python -m wm.evaluate --split official
for s in 0 1 2; do uv run python -m wm.ood fit --split lot --seed $s; done
for c in Center Donut Edge-Loc Edge-Ring Loc Near-full Random Scratch; do
  uv run python -m wm.train --split lot --seed 0 --exclude $c --max-epochs 12; done
uv run python -m wm.ood loco                             # reports/loco.json
uv run python -m wm.similarity --split lot               # reports/similarity_*.json
uv run python -m wm.similarity --split official
uv run python -m wm.export --model <deployed>            # ONNX + parity
uv run python -m wm.lots --model <deployed>              # reports/lots.json, demo lots
uv run python -m wm.bundle                               # artifacts/wafermap/v1 + model card
uv run pytest
```

`<deployed>` is the lot-grouped seed with the highest validation macro-F1 (`wm.bundle`
chooses it the same way). MLflow runs are in `../../mlruns/mlflow.db` (git-ignored).
