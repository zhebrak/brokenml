"""Measured task labels from labelling trials:

    uv run bench labels runs/jobs --prefix e2- [--static-at 0.333]

- **Evidence** (results/labels.json): from the ops-only ablation trials (variant `ablation`: the same `/ops`, no
  cluster), pooled over every model that ran them. A task is `static` when that pooled success rate is at least
  `--static-at` (default 1/3: solved from `/ops` alone at least once in three attempts on average), else `runtime`.
- **Pass rates** (results/pilots/pass_rates.json): mean reward of the standard-variant trials per task, pooled over
  configurations, for `bench lite --pass-rates`.

Left out are trials in which the agent never had its chance: a verifier infrastructure error, an environment or agent
setup that failed, an API usage or credit limit that stopped it, or no agent step at all. They say nothing about
whether the task can be solved, and the cut-off ones are re-run. Any other error (an agent crash, a context overflow)
is the attempt's result and counts as a failure, as on the leaderboard. A label from fewer than MIN_TRIALS trials is
marked provisional; each label carries a 95% Wilson interval on its success rate. The labelling trials must not be
the trials the leaderboard reports: the labelling trials are not scored, the main runs after the freeze are
(docs/leaderboard.md, Scoring: tuning is not scored).
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from bench.analyze import SCORED, broad_configs, current_digest, known_tasks, load_trials
from bench.paths import RESULTS
from bench.provenance import stamp
from bench.spec import load_specs

MIN_TRIALS = 3  # the labelling pass: k=3, pooled over models
# Errors that end a trial before the agent had its chance (Harbor's retry list, and API limits).
SETUP_ERRORS = {"HealthcheckError", "EnvironmentStartTimeoutError", "SandboxBuildFailedError", "AgentSetupTimeoutError"}


def counts(t: dict) -> bool:
    """Whether a trial says anything about solvability: the same classification as the leaderboard (bench analyze
    `outcome`): passes and the agent's own failures count; trials never attempted, infrastructure failures and verifier
    bugs do not."""
    if "outcome" in t:
        return t["outcome"] in SCORED
    if t["infra"]:  # trial dicts without an outcome (older callers)
        return False
    if t["errored"]:
        return not (t.get("exception") in SETUP_ERRORS or t.get("limit") or not t.get("agent_steps", 1))
    return True


def wilson(successes: float, n: int, z: float = 1.96) -> list[float]:
    p = successes / n
    centre, half = p + z * z / (2 * n), z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5
    return [
        round(max(0.0, (centre - half) / (1 + z * z / n)), 3),
        round(min(1.0, (centre + half) / (1 + z * z / n)), 3),
    ]


def evidence_labels(trials: list[dict], static_at: float, current: Callable[[str], str] | None = None) -> dict:
    """Per task, the measured label from its ops-only trials; with `current` (task -> the current ablation render's
    digest), only trials of the task as it is now count, so a label never pools versions (docs/leaderboard.md, Scoring:
    non-provisional, current labels only)."""
    by_task: dict[str, list[dict]] = defaultdict(list)
    for t in trials:
        if t["variant"] == "ablation" and counts(t) and (current is None or t["digest"] == current(t["task"])):
            by_task[t["task"]].append(t)
    out = {}
    for task, ts in sorted(by_task.items()):
        solved = sum(t["reward"] for t in ts)
        rate = solved / len(ts)
        out[task] = {"evidence": {
            "value": "static" if rate >= static_at else "runtime",
            "ops_only_success": round(rate, 4), "ci95": wilson(solved, len(ts)), "trials": len(ts),
            "provisional": len(ts) < MIN_TRIALS, "configs": sorted({t["config"] for t in ts}),
            "digests": sorted({t["digest"] for t in ts}), "static_at": static_at}}  # fmt: skip
    return out


def pass_rates(trials: list[dict], tasks: set[str] | None = None) -> dict[str, float]:
    """Standard-variant pass rate per task, each configuration's trials averaged first, over the configurations that
    attempted at least half of `tasks` (as bench analyze's empirical difficulty)."""
    tasks = tasks if tasks is not None else {t["task"] for t in trials}
    configs = broad_configs(trials, tasks)
    by_task: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for t in trials:
        if t["config"] in configs and t["task"] in tasks and counts(t):
            by_task[t["task"]][t["config"]].append(t["reward"])
    return {task: round(sum(sum(v) / len(v) for v in cs.values()) / len(cs), 4) for task, cs in sorted(by_task.items())}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench labels", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("jobs", nargs="+", type=Path)
    ap.add_argument("--prefix", default="", help="only job directories whose name starts with this (e.g. e2-)")
    ap.add_argument("--static-at", type=float, default=1 / 3)
    args = ap.parse_args(argv)
    trials, unknown = known_tasks(load_trials(args.jobs, args.prefix))
    if unknown:
        print(f"ignored trials of tasks that are not in the current specs: {', '.join(unknown)}")
    test = {s.id for s in load_specs() if s.split == "test"}
    labels = evidence_labels(trials, args.static_at, lambda task: current_digest(task, "ablation"))
    rates, run_stamp = pass_rates(trials, test), stamp()
    if labels:
        (RESULTS / "labels.json").write_text(json.dumps({**labels, "_stamp": run_stamp}, indent=1) + "\n")
        static = sum(v["evidence"]["value"] == "static" for v in labels.values())
        provisional = sum(v["evidence"]["provisional"] for v in labels.values())
        print(f"wrote results/labels.json: {static} static, {len(labels) - static} runtime "
              f"({provisional} provisional, fewer than {MIN_TRIALS} trials)")  # fmt: skip
    if rates:
        out = RESULTS / "pilots" / "pass_rates.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rates, indent=1) + "\n")
        print(f"wrote {out.relative_to(RESULTS.parent)}: {len(rates)} tasks")


if __name__ == "__main__":
    main()
