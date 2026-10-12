"""Build the status dashboard (one self-contained HTML page) from the repo's real state.

  uv run python -m bench.dashboard OUT.html

Reads: the task specs (catalogue), results/sweep/sweep.json (separation; a row is stale when the task's digest
changed since it ran), results/calibration/{base-job,perf}.json, results/fidelity/fidelity.json and jobs.jsonl (GPU),
and agent trials under runs/jobs/ (and the legacy jobs/pilot-*/).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from bench.analyze import variant_of
from bench.paths import RESULTS, ROOT, RUNS
from bench.render import NAMESPACES
from bench.spec import load_specs
from bench.sweep import fresh
from bench.sweep import inputs as sweep_inputs


def separation(task: str, table: dict) -> dict:
    """The task's row from the sweep table (results/sweep/sweep.json); stale when the task changed since."""
    row = table.get("tasks", {}).get(task)
    if not row:
        return {"status": "untested"}
    runs = row["runs"]
    stale = not fresh(row.get("inputs"), sweep_inputs(task))
    status = {"PASS": "separates", "FAIL": "fails", "INCONCLUSIVE": "inconclusive"}[row["verdict"]]
    return {
        "status": status + ("-stale" if stale else ""),
        "problems": [] if row["why"] == "ok" else row["why"].split("; "),
        "ref": runs.get("reference"),
        "broken": runs.get("pristine"),
        "wrong": {k[6:]: v.get("reward") for k, v in runs.items() if k.startswith("wrong:")},
        "accepted": {k[9:]: v.get("reward") for k, v in runs.items() if k.startswith("accepted:")},
        "when": row["stamp"].get("utc", "?"),
        "source": "results/sweep/sweep.json",
    }


def agent_trials() -> list[dict]:
    out = []
    for result in sorted([*RUNS.glob("jobs/*/*/result.json"), *ROOT.glob("jobs/pilot-*/*/result.json")]):
        r = json.loads(result.read_text())
        agent = (r.get("config") or {}).get("agent") or {}
        name = r.get("task_name") or ""
        reward = ((r.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        job = result.parent.parent.name
        if not any(job.startswith(k) for k in CONFIG_NAMES):  # QA, probes and smoke runs are not agent trials
            continue
        ctrf = result.parent / "verifier" / "ctrf.json"
        tests = json.loads(ctrf.read_text()).get("results", {}).get("tests", []) if ctrf.exists() else []
        failed_checks = [t.get("name", "?") for t in tests if t.get("status") == "failed"]
        res = r.get("agent_result") or {}
        exc = r.get("exception_info") or {}
        try:
            variant = variant_of(name if "/" in name else f"{NAMESPACES['standard']}/{name}")
        except ValueError:
            variant = " [?]"
        out.append({
            "run": CONFIG_NAMES.get(next((k for k in CONFIG_NAMES if job.startswith(k)), ""), job.split("-202")[0]),
            "task": name.split("/")[-1],
            "model": (agent.get("model_name") or "?").split("/")[-1],
            "agent": f"{agent.get('name')}{variant}",
            "reward": reward,
            "cost": res.get("cost_usd"),
            "tokens_in": res.get("n_input_tokens"),
            "tokens_out": res.get("n_output_tokens"),
            "error": exc.get("exception_type"),
            "failed_checks": failed_checks,
            "started": r.get("started_at"),
            "finished": r.get("finished_at"),
            "analysis": any((result.parent / "artifacts").rglob("ANALYSIS.md")),
        })  # fmt: skip
    return out


# Job-name prefixes (bench run --name) and the run each belongs to, longest prefix first.
CONFIG_NAMES = {
    "h2-qwen-ops": "Qwen 3.8 27B, ops-only (reasoning high)",
    "h2-qwen-std": "Qwen 3.8 27B, full access (reasoning high)",
    "e2-sonnet-lite": "Sonnet 5.5, lite subset",
    "e2-sonnet-rerun": "Sonnet 5.5, re-runs",
    "e2-sonnet": "Sonnet 5.5, full split",
    "e2-qwen-rerun": "Qwen 3.8 27B, re-runs",
    "e2-qwen": "Qwen 3.8 27B, full split",
    "gate-ops": "Sonnet 5.5, ops-only",
    "floor-llama3b": "Llama 3.2 3B, lite subset (floor)",
    "pilot-": "Exploratory runs",
}


def analysis_summary(record: dict) -> dict:
    """What the page shows from `bench analyze` (runs/analysis-e2.json): per configuration and per task difficulty."""
    keep = ("tasks", "complete", "pass@1", "cost_per_solve", "tokens_per_solve", "uncached_tokens_per_solve",
            "edit_first_passing")  # fmt: skip
    configs = {c: {k: s.get(k) for k in keep} for c, s in (record.get("configs") or {}).items()}
    return {
        "stamp": (record.get("stamp") or {}).get("time"),
        "configs": configs,
        "difficulty": record.get("difficulty"),
    }


def load(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def fidelity_records(name: str) -> list[dict]:
    """GPU fidelity rows: the current runners' JSONL (runs/gpu/, or the archived copy under results/fidelity/), else
    the archived JSON array of the first measurement."""
    for path in (RUNS / "gpu" / f"{name}.jsonl", RESULTS / "fidelity" / f"{name}.jsonl"):
        if path.exists():
            return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return load(RESULTS / "fidelity" / f"{name}.json", [])


def main(argv: list[str] | None = None) -> None:
    out = (argv or [str(RUNS / "dashboard.html")])[0]
    sweep = load(RESULTS / "sweep" / "sweep.json", {})
    labels = load(RESULTS / "labels.json", {})
    tasks = []
    for spec in load_specs():
        m, v = spec.metadata, spec.verify
        gates = (
            ["completes"]
            + (["loss"] if v.loss_max is not None else [])
            + (["throughput"] if v.throughput else [])
            + (["serving SLO"] if spec.substrate == "serving" else [])
        )
        tasks.append({
            "id": spec.id, "split": spec.split, "title": spec.title, "category": m.category, "family": m.family,
            "difficulty": m.difficulty, "evidence": m.evidence_author, "fault": m.fault_kind,
            "provenance": m.provenance_kind,
            "principle": m.principle, "mechanism": " ".join(m.mechanism.split()), "gates": gates,
            "links": m.provenance, "sep": separation(spec.id, sweep),
            "measured": ((labels.get(spec.id) or {}).get("evidence") or {}),
            "margins": (load(RESULTS / "margins" / f"{spec.id}.json", {}) or {}).get("verdict"),
        })  # fmt: skip
    gpu_jobs = fidelity_records("jobs")
    data = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "tasks": tasks,
        "base": load(RESULTS / "calibration" / "base-job.json", {}),
        "perf": load(RESULTS / "calibration" / "perf.json", {}),
        "fidelity": fidelity_records("fidelity"),
        "gpu_jobs": gpu_jobs,
        "agents": agent_trials(),
        "analysis": analysis_summary(load(RUNS / "analysis-e2.json", {})),
        "status": load(RESULTS / "status.json", {}),
    }
    template = Path(__file__).with_name("dashboard.html").read_text()
    # "<" is escaped so no agent-written string (an exception text, a task name) can close the script element
    Path(out).write_text(template.replace("/*DATA*/null", json.dumps(data).replace("<", "\\u003c")))
    print(f"wrote {out}: {len(tasks)} tasks, {len(data['agents'])} agent trials, {len(gpu_jobs)} GPU job runs")


if __name__ == "__main__":
    main()
