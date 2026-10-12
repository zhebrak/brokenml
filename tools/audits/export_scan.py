"""Finds graded trials whose /ops job scripts pass --export with variables to sbatch/srun/salloc.
For the report: how many such trials the study has, their outcome, and whether grading lost a node the way
outlives-time-limit's did (the getenv defect, docs/report/known-issues.md).

    uv run python tools/audits/export_scan.py --data PATH   # PATH holds bench/ and bench-logs/ run trees (runs/jobs)
"""

import argparse
import glob
import json
import os
import re
from pathlib import Path

PAT = re.compile(r"\b(sbatch|srun|salloc)\b[^\n]*--export[= ]+\"?(ALL|NONE)?,?[A-Za-z_][A-Za-z0-9_]*=")
TREES = ("bench", "bench-logs")


def hits_in(ops: str) -> list[str]:
    hits = []
    for dirpath, dirnames, filenames in os.walk(ops):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.getsize(path) > 200_000:
                continue
            try:
                text = open(path, errors="replace").read()
            except OSError:
                continue
            for m in PAT.finditer(text):
                line = text[text.rfind("\n", 0, m.start()) + 1 : text.find("\n", m.end())]
                hits.append(f"{os.path.relpath(path, ops)}: {line.strip()[:110]}")
    return hits


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--data", type=Path, help="data root holding bench/ and bench-logs/ (each with runs/jobs)")
    args = ap.parse_args()
    if args.data is None:
        ap.error("--data PATH is required: the directory holding the study's bench/ and bench-logs/ run trees")
    data = args.data.expanduser()
    for tree in TREES:
        for ops in sorted(glob.glob(f"{data}/{tree}/runs/jobs/*/t-*/artifacts/ops")):
            hits = hits_in(ops)
            if not hits:
                continue
            trial = os.path.dirname(os.path.dirname(ops))
            try:
                result = json.load(open(trial + "/result.json"))
            except OSError:
                continue
            reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
            stdout = trial + "/verifier/test-stdout.txt"
            out = open(stdout, errors="replace").read() if os.path.exists(stdout) else ""
            lost = "Not responding" in out or "site services kept running" in out
            task = (result.get("task_name") or "").split("/")[-1][:24]
            print(f"{trial.split('/')[-2][:62]:62s} {task:24s} reward {reward} node-lost {lost}")
            for hit in hits[:2]:
                print("    " + hit)


if __name__ == "__main__":
    main()
