"""Computes the test-retest agreement of cells the study ran twice.
Luna (OpenRouter, superseded) against Luna (OpenAI API), GLM (Baseten, superseded) against GLM (Z.AI): same model, task
and arm, latest attempt per cell, graded outcomes only (pass/fail, agent time limit = fail). For the report's retests.

    uv run python tools/audits/retest.py --data PATH   # PATH holds bench/ (runs/jobs and protocol/)
"""

import argparse
import glob
import json
import os
from pathlib import Path


def outcomes(root: Path, manifest: str, keep: str) -> dict:
    mf = json.load(open(root / "protocol" / manifest))
    prefix = "scored-" + mf["id"][:12] + "-"
    latest = {}
    for job in glob.glob(f"{root}/runs/jobs/{prefix}*"):
        rest = os.path.basename(job)[len(prefix) :].split("-")
        cell = int(rest[0])
        att = int(rest[1][1:]) if rest[1].startswith("r") and rest[1][1:].isdigit() else 0
        for f in glob.glob(job + "/*/result.json"):
            try:
                d = json.load(open(f))
            except (OSError, ValueError):
                continue
            if cell not in latest or att >= latest[cell][0]:
                latest[cell] = (att, d)
    out = {}
    for cell, (_, d) in latest.items():
        spec = mf["schedule"][cell]
        model = mf["configurations"][spec["configuration"]]["model"].split("/")[-1]
        if model != keep:
            continue
        exc = (d.get("exception_info") or {}).get("exception_type")
        rew = ((d.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        if rew is None and exc not in (None, "AgentTimeoutError"):
            continue
        out[(spec["task"], spec["variant"])] = int(rew == 1.0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--data", type=Path, help="data root holding bench/ (with runs/jobs and protocol/)")
    args = ap.parse_args()
    if args.data is None:
        ap.error("--data PATH is required: the directory holding the study's bench/ tree")
    root = args.data.expanduser() / "bench"
    for model, other in (
        ("gpt-6-luna", "scored-manifest-v0.1-luna.json"),
        ("glm-5.3-flash", "scored-manifest-v0.1-glm.json"),
    ):
        a, b = outcomes(root, "scored-manifest-v0.1.json", model), outcomes(root, other, model)
        both = sorted(set(a) & set(b))
        for arm in ("standard", "ablation"):
            ks = [k for k in both if k[1] == arm]
            agree = sum(a[k] == b[k] for k in ks)
            flips = [(k[0], a[k], b[k]) for k in ks if a[k] != b[k]]
            pa, pb = sum(a[k] for k in ks), sum(b[k] for k in ks)
            print(
                f"{model:14s} {arm:9s} cells run twice {len(ks):2d}: agree {agree}/{len(ks)}; "
                f"passes first route {pa}, second {pb}; flips {flips}"
            )


if __name__ == "__main__":
    main()
