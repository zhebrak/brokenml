"""Measure how many trials this host can run at once without moving a throughput verdict.

  uv run bench concurrency [--levels 1,2,3] [--k 3] [--tasks T ...]

Throughput rules compare two timed runs inside one trial, so co-scheduled trials matter only through host load that
differs between a trial's reference run and its job run; the verifier records the host's busy share around each timed
run (less the cluster's own CPU) and requires a complete regrade on a shift. This command runs the reference fix on the
throughput-ruled tasks at each concurrency level and derives the largest level at which every trial passed, no
verdict was flagged for review (host busy at or above BUSY_HIGH, or a shift of BUSY_SHIFT between the paired runs),
and every task's ratios stayed within RATIO_DRIFT of their level-1 mean. The result is written to
results/concurrency.json for this host (CPU model, physical cores, memory) and read by `bench run -n` and
`bench doctor`. Run it on an otherwise idle host; a busier host only lowers the answer.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import time
from collections import Counter
from pathlib import Path

from bench import analyze
from bench.doctor import memory_gb, physical_cores
from bench.paths import RESULTS, RUNS, TASKS
from bench.provenance import _cpu, grader_digest, image_ids, stamp, task_image_ids
from bench.spec import load_specs

HARBOR = os.environ.get("HARBOR", "harbor").split()
RECORD = RESULTS / "concurrency.json"
RATIO_DRIFT = 0.10  # a task's mean throughput ratio at level n may differ this much from its level-1 mean
RULE_VERSION = 1  # bump when derive() or its thresholds change: a record measured under another rule expires
# One trial per task from each throughput family, chosen for short reference runs: a straggler (S), a store-latency
# straggler (S), communication over the emulated link (B), serving (V).
DEFAULT_TASKS = ("degraded-node", "checkpoint-every-step", "tiny-ddp-buckets", "engine-single-slot")


def host_signature() -> dict:
    return {"cpu": _cpu(), "physical_cores": physical_cores(), "memory_gb": round(memory_gb())}


def throughput_tasks() -> list[str]:
    return sorted(s.id for s in load_specs() if s.split == "test" and s.verify.throughput is not None)


def _finite(value: object) -> bool:
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def derive(levels: dict[int, list[dict]], *, tasks: list[str] | None = None, k: int = 1) -> dict:
    """From the trials per level: the per-level summary and the largest safe level. A level is safe when every trial
    passed, none carries a timing-review flag, and each task's mean ratio is within RATIO_DRIFT of level 1's."""
    expected = Counter({t: k for t in tasks}) if tasks is not None else Counter(t["task"] for t in levels.get(1, []))
    base: dict[str, float] = {}
    if 1 in levels:
        for task in {t["task"] for t in levels[1]}:
            ratios = [t["tput_ratio"] for t in levels[1] if t["task"] == task and _finite(t.get("tput_ratio"))]
            if ratios:
                base[task] = statistics.mean(ratios)
    summary: dict[str, dict] = {}
    safe = 0
    for n in sorted(levels):
        trials = levels[n]
        complete = bool(expected) and Counter(t["task"] for t in trials) == expected
        valid = [
            t
            for t in trials
            if _finite(t.get("tput_ratio"))
            and t["tput_ratio"] > 0
            and all(_finite(t.get(key)) and 0 <= t[key] <= 1 for key in ("host_busy_ref", "host_busy_job"))
        ]
        # Load alone decides here (not closeness to the bound, as in the leaderboard's review list): the question is
        # whether this many trials make the host busy enough, or uneven enough, to matter for any verdict.
        flagged = sorted(
            f"{t['task']}: host busy {t.get('host_busy_ref') or 0:.0%} / {t.get('host_busy_job') or 0:.0%}"
            for t in valid
            if max(t.get("host_busy_ref") or 0, t.get("host_busy_job") or 0) >= analyze.BUSY_HIGH
            or abs((t.get("host_busy_ref") or 0) - (t.get("host_busy_job") or 0)) >= analyze.BUSY_SHIFT
        )
        drift = {}
        for task in sorted({t["task"] for t in valid}):
            ratios = [t["tput_ratio"] for t in valid if t["task"] == task]
            if ratios and task in base:
                drift[task] = statistics.mean(ratios) - base[task]
        passed = sum(1 for t in trials if t["reward"] == 1.0 and t["outcome"] == "pass")
        ok = (
            complete
            and len(valid) == len(trials)
            and set(drift) == set(expected)
            and passed == len(trials)
            and not flagged
            and all(abs(d) <= RATIO_DRIFT for d in drift.values())
        )
        busiest = max((max(t["host_busy_ref"], t["host_busy_job"]) for t in valid), default=None)
        summary[str(n)] = {"trials": len(trials), "passed": passed, "flagged": flagged,
                           "complete": complete, "missing_measurements": len(trials) - len(valid),
                           "ratio_drift": {task: round(d, 3) for task, d in drift.items()},
                           "safe": ok, "max_host_busy": busiest}  # fmt: skip
        if ok and n == safe + 1:
            safe = n  # levels must be safe without a gap: a safe 3 beside a failed 2 is noise, not a result
    return {"safe_n": safe, "levels": summary}


def inputs(tasks: list[str]) -> dict:
    """Measurements expire when any measured task, its images, or the measurement rule changes."""
    available = image_ids()
    images = {ref: iid for t in tasks for ref, iid in task_image_ids(TASKS / "test" / t, available).items()}
    if not images or not all(images.values()):
        raise ValueError("concurrency measurement requires locally available task images")
    return {
        "tasks": {t: grader_digest(TASKS / "test" / t) for t in tasks},
        "images": images,
        "rule": RULE_VERSION,
        "thresholds": [RATIO_DRIFT, analyze.BUSY_HIGH, analyze.BUSY_SHIFT],
    }


def run_level(n: int, tasks: list[str], k: int, name: str) -> Path:
    job = f"{name}-n{n}"
    argv = [*HARBOR, "run", "-p", str(TASKS / "test"), "-a", "oracle", "-n", str(n), "-k", str(k), "-o",
            str(RUNS / "jobs"), "-y", "--job-name", job]  # fmt: skip
    for t in tasks:
        argv += ["-i", t]
    subprocess.run(argv, check=False)
    return RUNS / "jobs" / job


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench concurrency", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--levels", default="1,2,3", help="concurrency levels to measure, lowest first")
    ap.add_argument("--k", type=int, default=3, help="oracle trials per task per level")
    ap.add_argument("--tasks", nargs="*", help=f"throughput-ruled tasks (default: {', '.join(DEFAULT_TASKS)})")
    ap.add_argument("--out", type=Path, default=RECORD)
    args = ap.parse_args(argv)
    try:
        levels = sorted({int(x) for x in args.levels.split(",")})
    except ValueError:
        ap.error("levels must be comma-separated positive integers starting at 1")
    tasks: list[str] = list(args.tasks or DEFAULT_TASKS)
    unknown = sorted(set(tasks) - set(throughput_tasks()))
    if unknown:
        ap.error(f"not throughput-ruled test tasks: {unknown}")
    if levels != list(range(1, max(levels) + 1)) or args.k < 1 or len(set(tasks)) != len(tasks):
        ap.error("levels must be consecutive from 1, k positive, and tasks unique")
    before = inputs(tasks)
    name = f"conc-{time.strftime('%Y%m%d-%H%M%S')}"
    per_level: dict[int, list[dict]] = {}
    for n in levels:
        job = run_level(n, tasks, args.k, name)
        per_level[n] = analyze.known_tasks(analyze.load_trials([RUNS / "jobs"], prefix=job.name))[0]
        print(f"level {n}: {json.dumps(derive(per_level, tasks=tasks, k=args.k)['levels'][str(n)])}", flush=True)
    if before != inputs(tasks):
        ap.error("task/image inputs changed during measurement; rerun on stable inputs")
    result = {**derive(per_level, tasks=tasks, k=args.k), "host": host_signature(), "tasks": tasks,
              "k": args.k, "job": name, "inputs": before, "stamp": stamp()}  # fmt: skip
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    print(f"safe concurrency on this host: -n {result['safe_n']} (written to {args.out})")


def why_unmeasured(path: Path = RECORD) -> str:
    """Why measured() is None: no record, another host, or a record whose tasks, images or rule have changed."""
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return "nothing measured"
    if record.get("host") != host_signature():
        return "measured on another host"
    try:
        if record.get("inputs") != inputs(record["tasks"]):
            return "measurement stale: the measured tasks, their images or the rule changed"
    except (ValueError, KeyError, TypeError):
        return "measurement stale: images missing"
    return "measurement invalid"


def measured(path: Path = RECORD) -> int | None:
    """The measured safe concurrency for current host/tasks/images; subset probes cannot raise the global limit."""
    try:
        record = json.loads(path.read_text())
        tasks, safe = record["tasks"], record["safe_n"]
        if (
            record.get("host") != host_signature()
            or type(safe) is not int
            or safe < 0
            or not isinstance(tasks, list)
            or not all(isinstance(t, str) for t in tasks)
            or not set(DEFAULT_TASKS) <= set(tasks) <= set(throughput_tasks())
            or record.get("inputs") != inputs(tasks)
            or any(not record["levels"].get(str(n), {}).get("safe") for n in range(1, safe + 1))
        ):
            return None
        return safe
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


if __name__ == "__main__":
    main()
