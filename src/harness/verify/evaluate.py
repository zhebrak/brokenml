"""Held-out loss of an exported model, run by the verifier as an unprivileged subprocess:

    python3 -m harness.verify.evaluate WEIGHTS TEACHER_JSON MODEL_JSON HELDOUT_SEED
    python3 -m harness.verify.evaluate --load-only MODEL_JSON [--final FINAL] FILE...

Prints one JSON line: {"loss": L, "floor": F}, or {"error": ..., "stage": "load"} when the export does not load
strictly into the platform model (the job's fault), or {"error": ..., "stage": "evaluate"} otherwise. Held-out
sequences are drawn fresh from the verifier's private dataset definition with a seed the job never saw; the count
and the loss are computed exactly as `ocb score` computes them (ocb.model).
"""

from __future__ import annotations

import json
import sys

import torch

from harness.teacher import Teacher
from ocb.model import ExportError, GPTConfig, heldout_count, heldout_loss, load_export, well_formed


def main(weights: str, teacher_json: str, model_json: str, heldout_seed: str) -> None:
    torch.set_num_threads(1)
    cfg = GPTConfig(**json.loads(model_json))
    try:
        model = load_export(weights, cfg)
    except ExportError as exc:
        print(json.dumps({"error": str(exc), "stage": "load"}))
        return
    teacher = Teacher.load(teacher_json)
    tokens = teacher.sample(heldout_count(cfg, model), cfg.ctx + 1, seed=int(heldout_seed))
    loss = heldout_loss(model, well_formed(tokens, cfg.vocab))
    print(json.dumps({"loss": loss, "floor": teacher.entropy_rate}))


def check_loads(model_json: str, files: list[str], final: str | None = None) -> None:
    """--load-only MODEL_JSON [--final FINAL] FILE...: prints {file: "" if it loads strictly into the platform model,
    else why}; with --final, a file whose weights equal the final export's is reported as such."""
    cfg = GPTConfig(**json.loads(model_json))
    try:
        reference = load_export(final, cfg).state_dict() if final else None
    except ExportError as exc:
        print(json.dumps(dict.fromkeys(files, f"invalid final export: {str(exc)[:300]}")))
        return
    out = {}
    for f in files:
        try:
            weights = load_export(f, cfg).state_dict()
        except ExportError as exc:
            out[f] = str(exc)[:300]
            continue
        same = reference is not None and all(torch.equal(weights[k], reference[k]) for k in reference)
        out[f] = "same weights as the final export" if same else ""
    print(json.dumps(out))


if __name__ == "__main__":
    if sys.argv[1] == "--load-only":
        rest = sys.argv[3:]
        final = rest[1] if rest[:1] == ["--final"] else None
        check_loads(sys.argv[2], rest[2:] if final else rest, final)
    else:
        main(*sys.argv[1:5])
