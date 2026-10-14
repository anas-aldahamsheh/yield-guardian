"""W9: export the deployed model to ONNX and check parity with PyTorch.

    uv run python -m wm.export --model lot-seed0

Input "maps" float32 [N, 3, 64, 64] (no_die, pass, fail); outputs "logits" [N, 9] and
"embedding" [N, 128] (L2-normalised). Parity is measured in float32 on CPU for both
runtimes, on lot-grouped test maps.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from wm.common import CLASSES, RUNS, load_index, load_part
from wm.evaluate import load_model
from wm.preprocess import one_hot

PARITY_WAFERS = 4096
OPSET = 18


def export(model: torch.nn.Module, path: Path) -> None:
    example = torch.zeros(2, 3, 64, 64)
    batch = torch.export.Dim("N", min=1, max=65536)
    program = torch.onnx.export(
        model,
        (example,),
        input_names=["maps"],
        output_names=["logits", "embedding"],
        dynamic_shapes={"x": {0: batch}},
        opset_version=OPSET,
        dynamo=True,
    )
    program.save(str(path))
    onnx.checker.check_model(onnx.load(str(path)))


def parity(model: torch.nn.Module, path: Path) -> dict:
    test = load_part(load_index(), "lot", "test")
    rng = np.random.default_rng(0)
    pick = np.sort(rng.choice(len(test.rows), size=PARITY_WAFERS, replace=False))
    x = one_hot(torch.from_numpy(test.maps[pick]))
    with torch.no_grad():
        ref_logits, ref_emb = (t.numpy() for t in model(x))
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    logits, emb = session.run(["logits", "embedding"], {"maps": x.numpy()})
    single = session.run(["logits"], {"maps": x[:1].numpy()})[0]
    return {
        "wafers": PARITY_WAFERS,
        "max_abs_diff_logits": float(np.abs(logits - ref_logits).max()),
        "max_abs_diff_embedding": float(np.abs(emb - ref_emb).max()),
        "argmax_agreement": float((logits.argmax(1) == ref_logits.argmax(1)).mean()),
        "embedding_norm_range": [
            float(np.linalg.norm(emb, axis=1).min()),
            float(np.linalg.norm(emb, axis=1).max()),
        ],
        "batch_of_one_max_abs_diff": float(np.abs(single - ref_logits[:1]).max()),
        "opset": OPSET,
        "onnxruntime": ort.__version__,
    }


def main() -> None:
    sys.stdout.reconfigure(
        encoding="utf-8"
    )  # the exporter prints emoji; Windows consoles use cp1252
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="lot-seed0")
    args = parser.parse_args()
    path = RUNS / args.model / "model.onnx"
    model = load_model(args.model, len(CLASSES), torch.device("cpu"))
    export(model, path)
    result = parity(model, path)
    (RUNS / args.model / "parity.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    assert result["max_abs_diff_logits"] < 1e-3 and result["argmax_agreement"] == 1.0


if __name__ == "__main__":
    main()
