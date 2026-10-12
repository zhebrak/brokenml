"""Chart data for the post, from the study dataset, so that every figure regenerates with it.

    uv run python tools/release/post_charts.py [--trials results/study/trials.csv]
        [--scoreboard results/study/scoreboard.csv] [--probe results/readonly-probe.json] [--out charts-data.json]

Reported rows only, one verdict per model, task and condition (the `solved` column: counted, reward 1, not zeroed).
The paired differences and their intervals use the same procedure and seeds as docs/report/findings.md (tasks resampled
with both scores together, 10,000 resamples, seed 0; the pooled intervals resample tasks with all of a task's model
pairs together, 4,000 resamples), so the chart numbers equal the report's."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

COND = ("live cluster", "live logs + files", "files only")
SHORT = {"live cluster": "live", "live logs + files": "logs", "files only": "files"}
NAME = {
    "openai/gpt-6.1-sol": "GPT-6.1 Sol",
    "anthropic/claude-sonnet-5-5": "Claude Sonnet 5.5",
    "openrouter/z-ai/glm-5.3-flash": "GLM-5.3-flash",
    "openai/gpt-6-luna": "GPT-6 Luna",
    "openrouter/moonshotai/kimi-k2.7-code": "Kimi K2.7 Code",
    "openrouter/minimax/minimax-m3": "MiniMax M3",
    "openrouter/deepseek/deepseek-v4.1-flash": "DeepSeek V4.1 Flash",
    "openrouter/qwen/qwen3.8-27b": "Qwen3.8 27B",
    "openrouter/nvidia/nemotron-3-super-120b-a12b": "Nemotron 3 Super",
}
CLASSES = (
    ("job did not complete", ("job completed before deadline",)),
    ("wrong held-out loss", ("held-out loss",)),
    ("too slow or misplaced", ("throughput vs reference", "ranks placed as required", "p95 time to first token")),
    ("policy check", ("policy",)),
)
PAIRS = (("live", "files", COND[0], COND[2]), ("live", "logs", COND[0], COND[1]), ("logs", "files", COND[1], COND[2]))


def load(path: Path) -> list[dict]:
    with path.open() as fh:
        return [r for r in csv.DictReader(line for line in fh if not line.startswith("#")) if not r["not_reported"]]


def paired(a: dict, b: dict, n: int = 10000, seed: int = 0) -> dict:
    d = [a[t] - b[t] for t in sorted(a.keys() & b.keys())]
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(n))
    return {
        "diff": 100 * sum(d) / len(d),
        "lo": 100 * means[int(0.025 * n)],
        "hi": 100 * means[int(0.975 * n) - 1],
        "only_a": sum(1 for x in d if x > 0),
        "only_b": sum(1 for x in d if x < 0),
    }


def pooled_cluster(res: dict, a: str, b: str, models: list, tasks: list, n: int = 4000, seed: int = 0) -> dict:
    per = {}
    for t in tasks:
        v = [res[(m, a, t)] - res[(m, b, t)] for m in models if (m, a, t) in res and (m, b, t) in res]
        if v:
            per[t] = (sum(v), len(v))
    ts = list(per)
    rng = random.Random(seed)
    st = []
    for _ in range(n):
        s = c = 0
        for _ in ts:
            t = rng.choice(ts)
            s += per[t][0]
            c += per[t][1]
        st.append(s / c)
    st.sort()
    s = sum(v[0] for v in per.values())
    c = sum(v[1] for v in per.values())
    return {"diff": 100 * s / c, "lo": 100 * st[int(0.025 * n)], "hi": 100 * st[int(0.975 * n) - 1], "pairs": c}


def fail_class(r: dict) -> str:
    if r["zeroed"]:
        return "zeroed after review"
    for label, checks in CLASSES:
        if r["first_failed_check"] in checks:
            return label
    return "other"


def rate(res: dict, models: list, tasks: list, cond: str) -> float:
    cells = [res[(m, cond, t)] for m in models for t in tasks if (m, cond, t) in res]
    return 100 * sum(cells) / len(cells) if cells else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--trials", type=Path, default=Path("results/study/trials.csv"))
    ap.add_argument("--scoreboard", type=Path, default=Path("results/study/scoreboard.csv"))
    ap.add_argument("--probe", type=Path, default=Path("results/readonly-probe.json"))
    ap.add_argument("--out", type=Path, default=Path("charts-data.json"))
    args = ap.parse_args()
    rows = load(args.trials)
    counted = [r for r in rows if r["counted"] == "True"]
    res = {(r["model"], r["condition"], r["task"]): int(r["solved"] == "True") for r in counted}
    tasks = sorted({r["task"] for r in counted})
    cat = {r["task"]: r["category"] for r in counted}
    label = {r["task"]: r["evidence_label"] for r in counted}
    sb = {}
    with args.scoreboard.open() as fh:
        for r in csv.DictReader(line for line in fh if not line.startswith("#")):
            sb[(r["model"], r["condition"])] = r
    models = sorted({r["model"] for r in counted}, key=lambda m: tuple(-int(sb[(m, c)]["solved"]) for c in COND))

    def by(m: str, c: str) -> dict:
        return {t: res[(m, c, t)] for t in tasks if (m, c, t) in res}

    def cell(m: str, c: str) -> dict:
        s = sb[(m, c)]
        return {
            "solved": int(s["solved"]),
            "tasks": int(s["tasks"]),
            "rate": 100 * float(s["pass_rate"]),
            "lo": 100 * float(s["ci95_low"]),
            "hi": 100 * float(s["ci95_high"]),
            "cost_per_run": float(s["cost_per_run"]),
            "cost_per_solve": float(s["cost_per_solve"] or 0),
        }

    out: dict = {
        "source": str(args.trials),
        "trials_sha256": hashlib.sha256(args.trials.read_bytes()).hexdigest(),
        "conditions": list(COND),
        "models": [{"id": m, "name": NAME.get(m, m)} for m in models],
    }

    def meta(m: str) -> dict:
        rs = [r for r in counted if r["model"] == m]
        stamps = sorted(r["job"].rsplit("-", 2)[-2] for r in rs)
        return {
            "api": m.split("/")[0],
            "route": next((r["route"] for r in rs if r["route"]), ""),
            "routes": sorted({r["route"] for r in rs if r["route"]}),
            "effort": next((r["effort"] for r in rs if r["effort"]), ""),
            "hosts": sorted({r["host"] for r in rs}),
            "first_run": stamps[0], "last_run": stamps[-1],
        }  # fmt: skip

    out["leaderboard"] = [
        {"model": m, "name": NAME.get(m, m), **meta(m), **{SHORT[c]: cell(m, c) for c in COND}} for m in models
    ]
    out["gains"] = [
        {
            "model": m,
            "name": NAME.get(m, m),
            **{f"{a}_minus_{b}": paired(by(m, ca), by(m, cb)) for a, b, ca, cb in PAIRS},
        }
        for m in models
    ]
    all_three = [(m, t) for m in models for t in tasks if all((m, c, t) in res for c in COND)]
    out["pooled"] = {"pairs": len(all_three)}
    for c in COND:
        out["pooled"][SHORT[c]] = 100 * sum(res[(m, c, t)] for m, t in all_three) / len(all_three)
    for a, b, ca, cb in PAIRS:
        out["pooled"][f"{a}_minus_{b}"] = {
            **pooled_cluster(res, ca, cb, models, tasks),
            "only_a": sum(1 for m, t in all_three if res[(m, ca, t)] > res[(m, cb, t)]),
            "only_b": sum(1 for m, t in all_three if res[(m, cb, t)] > res[(m, ca, t)]),
        }
    visible = {}
    if args.probe.exists():
        visible = {t: v.get("evidence_visible") for t, v in json.loads(args.probe.read_text()).items()}
    groups = {
        "needs a node shell": [t for t in tasks if visible.get(t) is False],
        "visible read-only": [t for t in tasks if visible.get(t) is not False],
    }
    out["node_shell"] = [
        {"group": g, "tasks": len(ts), **{SHORT[c]: rate(res, models, ts, c) for c in COND}} for g, ts in groups.items()
    ]
    out["categories"] = [
        {"category": k, "tasks": len(ts), **{SHORT[c]: rate(res, models, ts, c) for c in COND}}
        for k, ts in sorted({k: [t for t in tasks if cat[t] == k] for k in set(cat.values())}.items())
    ]
    out["tasks"] = [
        {
            "task": t,
            "category": cat[t],
            "label": label[t],
            "n": len(models),
            **{SHORT[c]: sum(res[(m, c, t)] for m in models if (m, c, t) in res) for c in COND},
        }
        for t in tasks
    ]
    fails = [r for r in counted if r["solved"] != "True"]
    out["failures"] = {SHORT[c]: dict(Counter(fail_class(r) for r in fails if r["condition"] == c)) for c in COND}
    out["failures"]["all"] = dict(Counter(fail_class(r) for r in fails))

    def timeouts(m: str, c: str) -> dict:
        rs = [r for r in counted if r["model"] == m and r["condition"] == c]
        to = [r for r in rs if r["exception"] == "AgentTimeoutError"]
        return {"timeouts": len(to), "passed": sum(r["solved"] == "True" for r in to), "runs": len(rs)}

    out["timeouts"] = [{"model": m, "name": NAME.get(m, m), **{SHORT[c]: timeouts(m, c) for c in COND}} for m in models]
    cost: dict = defaultdict(lambda: {"recorded": 0.0, "billed": 0.0, "runs": 0})
    for r in rows:
        k = (r["model"], r["condition"])
        cost[k]["recorded"] += float(r["cost_recorded"] or 0)
        cost[k]["billed"] += float(r["cost_billed"] or 0)
        cost[k]["runs"] += 1
    out["cost"] = [{"model": m, "name": NAME.get(m, m), **{SHORT[c]: cost[(m, c)] for c in COND}} for m in models]
    beh = []
    for m in models:
        rs = [r for r in counted if r["model"] == m and r["condition"] == COND[0] and r["category"] != "serving"]
        rs = [r for r in rs if r["n_submit"] != ""]
        edited = [r for r in rs if r["verified_after_last_edit"] != ""]
        beh.append({
            "model": m, "name": NAME.get(m, m), "runs": len(rs),
            "mean_submissions": sum(float(r["n_submit"]) for r in rs) / max(1, len(rs)),
            "used_ocb_score": sum(r["used_ocb_score"] == "True" for r in rs),
            "verified_after_last_edit": sum(r["verified_after_last_edit"] == "True" for r in edited),
            "edited": len(edited),
        })  # fmt: skip
    out["behaviour_live"] = beh
    args.out.write_text(json.dumps(out, indent=1))
    p = out["pooled"]
    print(f"chart data for {len(models)} models, {len(tasks)} tasks written to {args.out} "
          f"(pooled {p['live']:.0f}/{p['logs']:.0f}/{p['files']:.0f})")  # fmt: skip


if __name__ == "__main__":
    main()
