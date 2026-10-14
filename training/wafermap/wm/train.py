"""W4: train the wafer CNN on one split and seed.

    uv run python -m wm.train --split lot --seed 0
    uv run python -m wm.train --split lot --seed 0 --exclude Donut --max-epochs 12   # W6 LOCO

Selection uses validation macro-F1 only (early stopping). Test data is never loaded here.
Writes artifacts/wafermap/runs/<run>/model.pt and history.json, and logs to MLflow.
"""

from __future__ import annotations

import argparse
import json
import math
import time

import numpy as np
import torch
from sklearn.metrics import f1_score

from wm.common import (
    CLASSES,
    RUNS,
    amp_dtype,
    device,
    environment,
    load_index,
    load_part,
    mlflow_setup,
    run_tags,
    seed_everything,
)
from wm.model import WaferNet, class_balanced_weights, focal_loss, random_dihedral
from wm.preprocess import one_hot

CONFIG = {
    "batch_size": 256,
    "lr": 2e-3,
    "weight_decay": 0.05,
    "warmup_epochs": 1,
    "max_epochs": 40,
    "patience": 8,
    "focal_gamma": 2.0,
    "cb_beta": 0.9999,
    "eval_batch": 2048,
}


@torch.no_grad()
def predict(
    model: WaferNet, maps: torch.Tensor, dev: torch.device, batch: int = 2048
) -> tuple[np.ndarray, np.ndarray]:
    """maps: uint8 [N, 64, 64] (any device). Returns float32 logits and embeddings."""
    model.eval()
    logits, embeddings = [], []
    dtype = amp_dtype(dev)
    for start in range(0, len(maps), batch):
        x = one_hot(maps[start : start + batch].to(dev))
        with torch.autocast(dev.type, dtype=dtype, enabled=dtype is not None):
            out, emb = model(x)
        logits.append(out.float().cpu())
        embeddings.append(emb.float().cpu())
    return torch.cat(logits).numpy(), torch.cat(embeddings).numpy()


def run_name(split: str, seed: int, exclude: str | None) -> str:
    return f"loco-{exclude}-{split}-seed{seed}" if exclude else f"{split}-seed{seed}"


def train(split: str, seed: int, exclude: str | None = None, max_epochs: int | None = None) -> dict:
    config = dict(CONFIG, max_epochs=max_epochs or CONFIG["max_epochs"])
    seed_everything(seed)
    dev = device()
    classes = [c for c in CLASSES if c != exclude]
    index = load_index()
    train_part = load_part(index, split, "train", classes)
    val_part = load_part(index, split, "validation", classes)

    x_train = torch.from_numpy(train_part.maps).to(dev)
    y_train = torch.from_numpy(train_part.labels).to(dev)
    x_val = torch.from_numpy(val_part.maps)
    counts = torch.bincount(y_train, minlength=len(classes)).cpu()
    weights = class_balanced_weights(counts, config["cb_beta"]).to(dev)

    model = WaferNet(len(classes)).to(dev)
    optimiser = torch.optim.AdamW(
        model.parameters(), lr=config["lr"], weight_decay=config["weight_decay"]
    )
    steps_per_epoch = math.ceil(len(x_train) / config["batch_size"])
    total = steps_per_epoch * config["max_epochs"]
    warmup = steps_per_epoch * config["warmup_epochs"]

    def schedule(step: int) -> float:
        if step < warmup:
            return (step + 1) / warmup
        return 0.5 * (1 + math.cos(math.pi * (step - warmup) / max(1, total - warmup)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimiser, schedule)
    generator = torch.Generator(device=dev).manual_seed(seed)
    dtype = amp_dtype(dev)

    name = run_name(split, seed, exclude)
    out_dir = RUNS / name
    out_dir.mkdir(parents=True, exist_ok=True)
    mlflow = mlflow_setup("wafermap")
    history: list[dict] = []
    best = {"macro_f1": -1.0, "epoch": -1}
    with mlflow.start_run(run_name=name):
        mlflow.set_tags(run_tags())
        mlflow.log_params({**config, "split": split, "seed": seed, "exclude": exclude or ""})
        mlflow.log_dict(environment(), "environment.json")
        mlflow.log_params({"train_wafers": len(x_train), "validation_wafers": len(x_val)})
        stale = 0
        for epoch in range(config["max_epochs"]):
            started = time.perf_counter()
            model.train()
            order = torch.randperm(len(x_train), generator=generator, device=dev)
            running = 0.0
            for step in range(steps_per_epoch):
                idx = order[step * config["batch_size"] : (step + 1) * config["batch_size"]]
                x = one_hot(random_dihedral(x_train[idx], generator))
                with torch.autocast(dev.type, dtype=dtype, enabled=dtype is not None):
                    logits, _ = model(x)
                loss = focal_loss(logits, y_train[idx], weights, config["focal_gamma"])
                optimiser.zero_grad(set_to_none=True)
                loss.backward()
                optimiser.step()
                scheduler.step()
                running += loss.item()
            logits, _ = predict(model, x_val, dev, config["eval_batch"])
            pred = logits.argmax(1)
            macro = f1_score(
                val_part.labels, pred, average="macro", labels=list(range(len(classes)))
            )
            row = {
                "epoch": epoch,
                "train_loss": running / steps_per_epoch,
                "val_macro_f1": float(macro),
                "val_accuracy": float((pred == val_part.labels).mean()),
                "lr": scheduler.get_last_lr()[0],
                "seconds": time.perf_counter() - started,
            }
            history.append(row)
            mlflow.log_metrics({k: v for k, v in row.items() if k != "epoch"}, step=epoch)
            print(json.dumps(row))
            if macro > best["macro_f1"]:
                best = {"macro_f1": float(macro), "epoch": epoch}
                torch.save(model.state_dict(), out_dir / "model.pt")
                stale = 0
            else:
                stale += 1
                if stale >= config["patience"]:
                    break
        summary = {
            "name": name,
            "split": split,
            "seed": seed,
            "exclude": exclude,
            "classes": classes,
            "config": config,
            "train_class_counts": dict(zip(classes, counts.tolist(), strict=True)),
            "best": best,
            "epochs_run": len(history),
            "history": history,
            "tags": run_tags(),
            "environment": environment(),
        }
        (out_dir / "history.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        mlflow.log_metrics({"best_val_macro_f1": best["macro_f1"], "best_epoch": best["epoch"]})
        mlflow.log_artifact(str(out_dir / "history.json"))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["official", "lot"], required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--exclude", choices=CLASSES[:-1])
    parser.add_argument("--max-epochs", type=int)
    args = parser.parse_args()
    result = train(args.split, args.seed, args.exclude, args.max_epochs)
    print(json.dumps(result["best"]))


if __name__ == "__main__":
    main()
