"""Checks whether any provider failure was counted as the agent's fail.
Classifies every trial of the reported rows (study and live-logs arm) with bench.analyze.outcome, before deviation
ae's classifier fix and after it. For the report: the trials the fix moves, and the exception-ended and too-short fails.

    uv run python tools/audits/misattribution_audit.py --data PATH   # PATH holds bench/ and bench-logs/
"""

import argparse
import collections
import glob
import json
import re
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
SUPERSEDED = {"gpt-oss-120b", "gpt-6-luna", "glm-5.3-flash"}


def msg_of(job: Path) -> str:
    for f in glob.glob(str(job) + "/t-*/result.json"):
        e = json.load(open(f)).get("exception_info") or {}
        m = e.get("exception_message") or ""
        g = re.search(r'"message":"([^"]{0,100})', m)
        return (g.group(1) if g else m[:100]).replace("\n", " ")
    return ""


def classify(data: Path, old: bool) -> dict:
    saved = analyze.LIMIT_TEXT
    if old:
        analyze.LIMIT_TEXT = ("usage limits", "credit balance")
    try:
        out = {}
        for root, n in SETS:
            mf = json.load(open(data / root / "protocol" / n))
            prefix = "scored-" + mf["id"][:12] + "-"
            for t in analyze.load_trials([data / root / "runs/jobs"], prefix=prefix):
                out[(n, t["job"])] = t
        return out
    finally:
        analyze.LIMIT_TEXT = saved


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--data", type=Path, help="data root holding bench/ and bench-logs/ (runs/jobs and protocol/)")
    args = ap.parse_args()
    if args.data is None:
        ap.error("--data PATH is required: the directory holding the study's bench/ and bench-logs/ trees")
    data = args.data.expanduser()

    def jobdir(n: str, job: str) -> Path:
        return data / ("bench-logs" if "logs" in n else "bench") / "runs/jobs" / job

    old, new = classify(data, True), classify(data, False)
    moved = [
        (k, old[k]["outcome"], new[k]["outcome"]) for k in new if k in old and old[k]["outcome"] != new[k]["outcome"]
    ]
    print(f"trials whose outcome the fix changes: {len(moved)}")
    for (n, job), a, b in sorted(moved):
        print(
            f"  {n[17:-5] or 'study':11s} {job[20:75]:55s} {a} -> {b} | "
            f"{new[(n, job)].get('exception')} | {msg_of(jobdir(n, job))[:90]}"
        )
    crash = collections.Counter()
    rows = []
    for (n, job), t in new.items():
        if n == "scored-manifest-v0.1.json" and any(s in job for s in SUPERSEDED):
            continue
        if t["outcome"] == "agent" and t.get("exception") and t.get("exception") != "AgentTimeoutError":
            crash[t["exception"]] += 1
            rows.append((n, job, t["exception"], msg_of(jobdir(n, job))))
    print(
        f"\nscored agent fails that ended on an exception (not a time-out), after the fix: "
        f"{sum(crash.values())} {dict(crash)}"
    )
    for n, job, e, m in sorted(rows):
        print(f"  {n[17:-5] or 'study':11s} {job[20:75]:55s} {e} | {m[:110]}")
    short = [
        (n, job, t.get("steps"))
        for (n, job), t in new.items()
        if t["outcome"] == "agent"
        and t.get("exception") == "AgentTimeoutError"
        and (t.get("steps") or 0) < 8
        and not (n == "scored-manifest-v0.1.json" and any(s in job for s in SUPERSEDED))
    ]
    print(f"\nagent time-outs with fewer than 8 steps (a provider too slow to answer?): {len(short)}")
    for n, job, st in sorted(short):
        print(f"  {n[17:-5] or 'study':11s} {job[20:75]:55s} steps {st}")


if __name__ == "__main__":
    main()
