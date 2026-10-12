"""Held-out loss of an exported model on the corpus's held-out split (`ocb score`).

    python3 -m ocb.score WEIGHTS CORPUS MODEL_JSON

Loads the safetensors export strictly into the platform model and reports mean next-token cross-entropy over
positions 2+ on held-out sequences: the same computation, on as many sequences, as the evaluation of a
finished job (on its own fresh held-out data).
"""

from __future__ import annotations

import json
import sys

import torch
from safetensors.torch import load_file

from ocb.model import ExportError, GPTConfig, heldout_count, heldout_loss, load_export, well_formed


def main(weights: str, corpus: str, model_json: str) -> None:
    torch.set_num_threads(1)
    cfg = GPTConfig(**json.loads(model_json))
    try:
        model = load_export(weights, cfg)
    except ExportError as exc:
        print(json.dumps({"error": f"the export does not load into the platform model: {exc}"}))
        sys.exit(1)
    tokens = well_formed(load_file(corpus)["heldout"][: heldout_count(cfg, model)], cfg.vocab)
    print(json.dumps({"loss": heldout_loss(model, tokens)}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
