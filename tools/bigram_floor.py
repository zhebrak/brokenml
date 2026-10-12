"""The bigram-table floor of the 10-step gate (hardening plan 11.3): the held-out cross-entropy of a bigram model
counted from a training corpus of the teacher family, scored the way the verifier scores exports (positions 2+), per
teacher seed.

    uv run python tools/bigram_floor.py [--seeds 11 22 33 44 55] [--out results/calibration/bigram-floor.json]

A job that trains nothing and exports such a table would score this; legitimate 10-step training on the activation-scale
tasks scores 3.34-3.41 and 25 steps 3.33 (results/calibration/o-activation.json), so no loss bound separates them.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import torch

from harness.teacher import Teacher


def bigram_floor(seed: int, train_rows: int = 16384, length: int = 65, held_rows: int = 2048) -> dict:
    t = Teacher(seed)
    train = t.sample(train_rows, length, seed=seed + 1)
    held = t.sample(held_rows, 513, seed=seed + 2)
    counts = torch.zeros(t.vocab, t.vocab)
    prev, nxt = train[:, :-1].reshape(-1), train[:, 1:].reshape(-1)
    counts.index_put_((prev, nxt), torch.ones_like(prev, dtype=torch.float), accumulate=True)
    probs = (counts + 0.5) / (counts + 0.5).sum(dim=1, keepdim=True)
    hp, hn = held[:, 1:-1].reshape(-1), held[:, 2:].reshape(-1)  # positions 2+, as the evaluation scores
    bigram = -torch.log(probs[hp, hn]).mean().item()
    uni = (counts.sum(0) + 0.5) / (counts.sum() + 0.5 * t.vocab)
    return {"seed": seed, "bigram": round(bigram, 4), "unigram": round(-torch.log(uni[hn]).mean().item(), 4)}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--seeds", type=int, nargs="+", default=[11, 22, 33, 44, 55])
    ap.add_argument("--out", type=Path, default=Path("results/calibration/bigram-floor.json"))
    args = ap.parse_args(argv)
    rows = [bigram_floor(s) for s in args.seeds]
    record = {"uniform": round(math.log(32), 4), "rows": rows,
              "note": "held-out cross-entropy of a bigram table counted from the corpus, positions 2+; the 10-step "
                      "gate cannot separate this from legitimate training (o-activation calibration)"}  # fmt: skip
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=1) + "\n")
    for r in rows:
        print(r)
    print("uniform", record["uniform"])


if __name__ == "__main__":
    main()
