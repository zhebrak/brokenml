"""Finds scored time-outs whose agent was waiting on a model call when its 25 minutes ran out.
A model call's wait is the time from one agent step to the next, less the waits the agent asked for in its commands;
the tail is the same for the call still open at the time-out. For the report: compared with the row's completed calls.

    uv run python tools/audits/hang_audit.py --data PATH   # PATH holds bench/ and bench-logs/ (runs/jobs, protocol/)
"""

import argparse
import collections
import glob
import json
import statistics
from datetime import datetime
from pathlib import Path

from bench import analyze

SETS = [
    ("bench", "scored-manifest-v0.1.json"),
    ("bench", "scored-manifest-v0.1-sol.json"),
    ("bench", "scored-manifest-v0.1-luna.json"),
    ("bench", "scored-manifest-v0.1-glm.json"),
    ("bench-logs", "scored-manifest-v0.1-logs.json"),
    ("bench-logs", "scored-manifest-v0.1-logs-openai.json"),
]


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--data", type=Path, help="data root holding bench/ and bench-logs/ (runs/jobs and protocol/)")
    args = ap.parse_args()
    if args.data is None:
        ap.error("--data PATH is required: the directory holding the study's bench/ and bench-logs/ trees")
    data = args.data.expanduser()
    calls = collections.defaultdict(list)  # model -> [(latency s, completion tokens)]
    tails = []
    for root, n in SETS:
        mf = json.load(open(data / root / "protocol" / n))
        prefix = "scored-" + mf["id"][:12] + "-"
        for t in analyze.load_trials([data / root / "runs/jobs"], prefix=prefix):
            job = t["job"]
            if n == "scored-manifest-v0.1.json" and any(
                s in job for s in ("gpt-oss-120b", "gpt-6-luna", "glm-5.3-flash")
            ):
                continue
            if t["outcome"] not in ("pass", "agent"):
                continue
            d = glob.glob(str(data / root / "runs/jobs" / job / "t-*"))[0]
            try:
                traj = json.load(open(d + "/agent/trajectory.json"))["steps"]
                steps = [s for s in traj if s.get("source") == "agent" and s.get("timestamp")]
                res = json.load(open(d + "/result.json"))
            except Exception:
                continue
            model = job.split("-standard-")[-1].split("-ablation-")[-1].split("-logs-")[-1].rsplit("-", 2)[0]
            waits = [
                sum(float((tc.get("arguments") or {}).get("duration") or 0) for tc in s.get("tool_calls") or [])
                for s in steps
            ]
            for prev, cur, w in zip(steps, steps[1:], waits):
                latency = ts(cur["timestamp"]) - ts(prev["timestamp"]) - w
                calls[model].append((latency, (cur.get("metrics") or {}).get("completion_tokens") or 0))
            if t["outcome"] == "agent" and t.get("exception") == "AgentTimeoutError" and steps:
                end = ts(res["agent_execution"]["finished_at"])
                tail = end - ts(steps[-1]["timestamp"]) - waits[-1]
                tails.append((tail, model, n[17:-5] or "study", job[20:75], len(steps)))
    print("completed model calls per row: median, p99 and max wait (s); completion tokens of the slowest call")
    ref = {}
    for model, cs in sorted(calls.items()):
        lat = sorted(c[0] for c in cs)
        slow = max(cs)
        ref[model] = (lat[int(0.99 * (len(lat) - 1))], slow[0])
        print(
            f"  {model:28s} calls {len(cs):5d} median {statistics.median(lat):6.1f} p99 {ref[model][0]:6.1f} "
            f"max {slow[0]:7.1f} ({slow[1]} tokens)"
        )
    print(f"\nscored time-outs: {len(tails)}; open model call at the time-out, by length:")
    for lo, hi in ((0, 60), (60, 180), (180, 300), (300, 600), (600, 1e9)):
        print(f"  {lo:4d}-{hi if hi < 1e9 else 'inf'} s: {sum(lo <= x[0] < hi for x in tails)}")
    print("\ntime-outs whose open call had waited longer than the row's slowest completed call:")
    for tail, model, arm, job, k in sorted(tails, reverse=True):
        if tail > ref[model][1]:
            print(
                f"  {tail / 60:5.1f} min  {arm:11s} {job:55s} steps {k:3d} "
                f"(row's slowest completed call {ref[model][1] / 60:4.1f} min, p99 {ref[model][0] / 60:4.1f})"
            )


if __name__ == "__main__":
    main()
