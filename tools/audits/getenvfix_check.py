"""Runs the task-level check of the patched runtime (deviation ag) on a free host, sequentially.
For the report: the reference fix passes and a do-nothing agent fails on the patched image as on the study's;
the reference fix with a --export variable on the first submission passes on the patched one and loses its node on
the study's.

    uv run python tools/audits/getenvfix_check.py --data PATH   # PATH: working directory (build/, runs/)
"""

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

from bench.regrade import patched_snapshot
from bench.spec import task_dir

IMAGE, VERSION, BASE = "bench/runtime:getenvfix1", "13589f05b723d886", "8631a20f3ea56bdc"
EXPORT_SUBMIT = """#!/bin/bash
# How this job is submitted (run as svc-train, e.g. by `ocb submit train`).
set -euo pipefail
cd "$(dirname "$0")"
sbatch --export=ALL,TRAIN_SEGMENT=0 launch.sbatch
"""
RUNS = [
    ("outlives-time-limit", True, False, "oracle"),
    ("outlives-time-limit", True, False, "nop"),
    ("outlives-time-limit", True, True, "oracle"),
    ("outlives-time-limit", False, True, "oracle"),
    ("failed-dependency", True, False, "oracle"),
    ("failed-dependency", True, False, "nop"),
]


def copy(work: Path, task: str, patched: bool, export: bool) -> Path:
    name = f"{task}-{'patched' if patched else 'study'}{'-export' if export else ''}"
    dst = work / name / task
    if dst.exists():
        shutil.rmtree(dst.parent)
    if patched:
        patched_snapshot(task_dir(task), IMAGE, VERSION, BASE, dst)
    else:
        shutil.copytree(task_dir(task), dst)
    if export:
        (dst / "solution" / "files" / "jobs" / "train").mkdir(parents=True, exist_ok=True)
        (dst / "solution" / "files" / "jobs" / "train" / "submit.sh").write_text(EXPORT_SUBMIT)
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--data", type=Path, help="working directory: task copies go to PATH/build, jobs to PATH/runs")
    args = ap.parse_args()
    if args.data is None:
        ap.error("--data PATH is required: a working directory with room for task copies and Harbor jobs")
    work, jobs = (
        args.data.expanduser() / "build" / "getenvfix-check",
        args.data.expanduser() / "runs" / "getenvfix-check",
    )
    jobs.mkdir(parents=True, exist_ok=True)
    for task, patched, export, agent in RUNS:
        path = copy(work, task, patched, export)
        job = f"{path.parent.name}-{agent}-{int(time.time())}"
        t0 = time.time()
        res = subprocess.run(
            ["harbor", "run", "-p", str(path), "-a", agent, "-k", "1", "-n", "1", "-o", str(jobs), "-y",
             "--job-name", job, "-q"],
            capture_output=True, text=True, check=False,
        )  # fmt: skip
        out = {"run": f"{path.parent.name} {agent}", "minutes": round((time.time() - t0) / 60, 1),
               "harbor_exit": res.returncode}  # fmt: skip
        for f in (jobs / job).glob("*/result.json"):
            d = json.loads(f.read_text())
            diag = f.parent / "verifier" / "diagnostics.json"
            dg = json.loads(diag.read_text()) if diag.exists() else {}
            stdout = f.parent / "verifier" / "test-stdout.txt"
            text = stdout.read_text() if stdout.exists() else ""
            lost = "Not responding" in text or "[FAIL] site services kept running" in text
            out.update(
                reward=((d.get("verifier_result") or {}).get("rewards") or {}).get("reward"),
                failure=dg.get("failure"), runtime_version=dg.get("runtime_version"),
                runtime_build=dg.get("runtime_build"), node_lost=lost,
                exception=(d.get("exception_info") or {}).get("exception_type"),
            )  # fmt: skip
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
