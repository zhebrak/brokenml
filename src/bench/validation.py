"""The per-task validation table (the appendix table and the freeze gate):

    uv run bench validation [--gate]

One row per test task. Every column comes from its own stamped result, and a cell is `stale` when the task, its
wrong fixes or the images changed since that result was produced, `-` when it has not run:
- bootcheck (results/bootcheck.json): the agent environment comes up with the fault's symptom every time, and the
  verifier environment starts;
- separation (results/sweep/sweep.json): the reference and every accepted alternative fix pass, the broken job
  fails, k of n wrong fixes fail as the agent's on a check they declare (bench.outcomes); wrong fixes the policy
  rejects, and those marked `# contract control`, are counted apart, not as runtime coverage; a task is green only
  with at least one wrong fix that fails at runtime;
- oracle and nop (results/qa/<task>.json, release mode): the reference passes 10 of 10, doing nothing scores 0;
- margins (results/margins/<task>.json, memory-bound tasks only): the reference passes at limit / 1.15 and the
  broken job is still OOM-killed at limit x 1.15;
- the reference's measured loss and throughput ratio against the task's thresholds, from the sweep.
- the negative controls: each wrong fix with the check it must fail and the contract clause that check enforces.

A task is green when its release QA record passes on current inputs on this host (oracle 10 of 10; nop 3 of 3 with
the symptom observed at bootstrap; every wrong fix 0 and every accepted fix 1; the calibration rows) and at least one of
its wrong fixes is declared to fail at runtime, not on the policy or a contract clause alone (the
release QA on the scoring host class qualifies the tasks; bootcheck, separation and margins, measured on the
development box, are reported beside it and not re-run on the host class). The calibration rows' 3-spread margins
(MARGIN_ROWS) are reported, not decisive. A task that is not green at the freeze is
cut (moved out of the split, so it leaves dataset.toml). Writes results/validation/VALIDATION.md and .json, stamped;
with --gate, exits non-zero unless every test task is green.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bench import outcomes, sweep
from bench.bootcheck import probes_hash
from bench.patches import wrong_fix_patches
from bench.paths import RESULTS
from bench.provenance import describe, image_ids, images_match, stamp, task_digest, task_image_ids
from bench.spec import TaskSpec, load_specs, task_dir
from harness.verify.rules import clause

OUT = RESULTS / "validation"


def needs_margins(spec: TaskSpec) -> bool:
    """Memory-bound: a memory fault, or nodes with a task-specific memory limit."""
    return spec.metadata.category == "memory" or any("mem_limit" in v for v in spec.hardware.services.values())


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def bootcheck_cell(task: str, row: dict | None, *, ignore_images: bool = False) -> tuple[str, bool]:
    """A bootcheck record as a table cell and whether it passes; `ignore_images` skips the local image IDs."""
    if row is None:
        return "-", False
    images = (row.get("stamp") or {}).get("images")
    if row.get("task_digest") != task_digest(task_dir(task)) or not (
        ignore_images or images_match(images or {}, task_image_ids(task_dir(task), image_ids()))
    ):
        return "stale", False
    if row.get("probes_hash", "") != probes_hash(task):  # records before probes existed count as stale too
        return "stale", False
    cell = f"agent {row.get('agent_env_ok', '?')}" + ("" if row.get("verifier_env_ok") else ", verifier env FAIL")
    if row.get("probes_ok") and row["probes_ok"] != "0/0":
        cell += f", probes {row['probes_ok']}"
    return (cell if row["ok"] else f"FAIL: {cell}"), bool(row["ok"])


def separation(task: str, row: dict | None, current: dict) -> tuple[str, bool]:
    if row is None:
        return "-", False
    if not sweep.fresh(row.get("inputs"), current):
        return "stale", False
    runs = row["runs"]
    wrong = {k: v for k, v in runs.items() if k.startswith("wrong:")}
    accepted = [v for k, v in runs.items() if k.startswith("accepted:")]
    expects = {k: sweep.expectation(task, k) for k in wrong}

    def failed_as_declared(k: str) -> bool:
        want = expects[k]
        return outcomes.failed_for(wrong[k], want) if want else outcomes.kind(wrong[k]) == outcomes.AGENT

    failed = sum(failed_as_declared(k) for k in wrong)
    contract = {k for k in wrong if expects[k] == ["policy"] or sweep.contract_control(task, k)}
    shortcuts = len(contract)
    runtime = sum(failed_as_declared(k) and k not in contract for k in wrong)
    ref, broken = (outcomes.kind(runs.get(k)) if k in runs else "-" for k in ("reference", "pristine"))
    cell = f"ref {ref}, broken {broken}"
    if wrong:
        cell += f", wrong {failed}/{len(wrong)}" + (f" ({shortcuts} contract controls)" if shortcuts else "")
    if accepted:
        cell += f", accepted {sum(outcomes.kind(v) == outcomes.PASS for v in accepted)}/{len(accepted)}"
    if not runtime:  # a task is frozen only with a wrong fix that fails at runtime, not just on the contract
        cell += ", no runtime negative control"
    ok = row["verdict"] == "PASS" and runtime > 0
    return (cell if row["verdict"] == "PASS" else f"{row['verdict']}: {cell}"), ok


# The calibration rows' 3-spread margins are reported beside the verdict, not part of it: on the
# development box every calibration run was classified right by the thresholds, but the spread counts the systematic
# FSDP-DDP difference as noise, so for 38 tasks no threshold keeps 3 spreads on both sides.
MARGIN_ROWS = ("loss threshold calibrated", "throughput threshold calibrated")


def qa_cell(record: dict | None, current: dict) -> tuple[str, bool]:
    if record is None or record.get("mode") != "release":
        return "-", False
    if not sweep.fresh(record.get("inputs"), current):
        return "stale", False
    checks = {c["check"].split(" ")[0]: c for c in record["checks"]}
    cell = ", ".join(c["check"].split(" score")[0] for k, c in checks.items() if k in ("oracle", "nop"))
    decisive = [c for c in record["checks"] if not c["check"].startswith("[bundle]") and c["check"] not in MARGIN_ROWS]
    ok = bool(decisive) and all(c["ok"] for c in decisive)
    thin = [c["check"].split(" ")[0] for c in record["checks"] if c["check"] in MARGIN_ROWS and not c["ok"]]
    if thin:
        cell += f"; {' and '.join(thin)} margin under 3 spreads (reported)"
    return (cell if ok else f"FAIL: {cell}"), ok


def margins_cell(spec: TaskSpec, record: dict | None) -> tuple[str, bool]:
    if not needs_margins(spec):
        return "n/a", True
    if record is None:
        return "-", False
    from bench.margins import REQUIRED_FACTOR, node_limits

    if not sweep.fresh(record.get("inputs"), sweep.inputs(spec.id)):
        return "stale", False
    factor = record.get("factor", 0)
    if not isinstance(factor, int | float) or not REQUIRED_FACTOR <= factor < float("inf"):
        return "insufficient margin factor", False
    if record.get("limits_mib") != node_limits(spec.id):
        return "stale", False
    verdict = record.get("verdict") or ("PASS" if record["pass"] else "FAIL")
    return f"{verdict.lower() if verdict == 'PASS' else verdict} (x{record['factor']})", verdict == "PASS"


# A margin is "thin" below one unit: 3x the loss spread of legitimate runs (the threshold rule), or 10% of a
# throughput or latency limit. LOSS_SPREAD is the base job's spread over seeds, DDP/FSDP2 and accumulation splits
# (measured 2026-10-01); per-task calibration sets replace it.
LOSS_SPREAD = 0.012
THIN_RATIO = 0.10


def _distances(spec: TaskSpec, run: dict) -> list[tuple[float, str]]:
    """Every measured check as (distance inside its limit in thin units, label); negative means outside."""
    v, out = spec.verify, []
    if v.loss_max is not None and run.get("loss") is not None:
        d = v.loss_max - run["loss"]
        out.append((d / (3 * LOSS_SPREAD), f"loss {abs(d):.3f} nats"))
    if v.throughput is not None and run.get("tput_ratio") is not None:
        r = run["tput_ratio"] / v.throughput.ratio_min - 1
        out.append((r / THIN_RATIO, f"tput {abs(r):.0%}"))
    if v.ttft_p95_max_s is not None and run.get("ttft_p95_s") is not None:
        r = 1 - run["ttft_p95_s"] / v.ttft_p95_max_s
        out.append((r / THIN_RATIO, f"ttft {abs(r):.0%}"))
    return out


def miss(spec: TaskSpec, run: dict) -> tuple[float, str] | None:
    """How far a failing run is from passing, in thin units with a label: the largest miss over the checks it fails,
    or infinity when it failed outright (policy rejection, a job that never completed, a discrete rule such as
    placement or checkpoints). None for a run that passed."""
    if run.get("reward") == 1.0:
        return None
    if run.get("policy_ok") == 0.0 or run.get("completed") == 0.0:
        return float("inf"), "decisive"
    failing = [(-d, label) for d, label in _distances(spec, run) if d < 0]
    return max(failing) if failing else (float("inf"), "decisive")


def slack(spec: TaskSpec, run: dict) -> tuple[float, str] | None:
    """How far a passing run sits inside its limits, in thin units with a label: the smallest over measured checks."""
    return min(_distances(spec, run), default=None)


def margins_text(spec: TaskSpec, row: dict | None) -> tuple[str, list[str]]:
    """The reference's slack and the closest miss among the broken run and the wrong fixes; the reference and any
    failing run within one thin unit of the limit are returned by name."""
    runs = (row or {}).get("runs", {})
    passing = [r for k, r in runs.items() if k == "reference" or k.startswith("accepted:")]
    ref = min((s for s in (slack(spec, r) for r in passing) if s is not None), default=None)
    failing = {k: miss(spec, r) for k, r in runs.items() if k != "reference" and not k.startswith("accepted:")}
    failing = {k: m for k, m in failing.items() if m is not None}
    thin = sorted(k for k, m in failing.items() if m[0] < 1)
    if ref is not None and ref[0] < 1:
        thin.insert(0, "reference")
    closest = min(failing.values(), default=None)
    parts = [f"ref inside by {ref[1]}" if ref is not None else "ref -"]
    if closest is not None:
        parts.append("closest miss " + closest[1])
    return ", ".join(parts), thin


def headroom(spec: TaskSpec, row: dict | None) -> str:
    """The reference's measured values next to the thresholds they must meet (from the sweep's single run)."""
    ref = (row or {}).get("runs", {}).get("reference") or {}
    parts = []
    loss_max = spec.verify.loss_max
    if loss_max is not None and ref.get("loss") is not None:
        parts.append(f"loss {ref['loss']:.3f} / max {loss_max}")
    tput = spec.verify.throughput
    if tput is not None and ref.get("tput_ratio") is not None:
        parts.append(f"tput {ref['tput_ratio']:.2f} / min {tput.ratio_min}")
    return "; ".join(parts) or "-"


def runtime_controls(task: str, names) -> list[str]:
    """The wrong fixes declared to fail at runtime: not the policy alone, nor a contract control."""
    return [
        name
        for name in sorted(names)
        if (sweep.expectation(task, f"wrong:{name}") or []) != ["policy"]
        and not sweep.contract_control(task, f"wrong:{name}")
    ]


def build() -> dict:
    table = sweep.load_table()["tasks"]
    boot = _load(RESULTS / "bootcheck.json") or {}
    rows = {}
    for spec in sorted((s for s in load_specs() if s.split == "test"), key=lambda s: s.id):
        current = sweep.inputs(spec.id)
        bc, bc_ok = bootcheck_cell(spec.id, boot.get(spec.id))
        sep, sep_ok = separation(spec.id, table.get(spec.id), current)
        qa, qa_ok = qa_cell(_load(RESULTS / "qa" / f"{spec.id}.json"), current)
        mg, mg_ok = margins_cell(spec, _load(RESULTS / "margins" / f"{spec.id}.json"))
        slack_miss = margins_text(spec, table.get(spec.id))
        controls = []
        for name in sorted(wrong_fix_patches(spec)):
            want = sweep.expectation(spec.id, f"wrong:{name}") or []
            checks = [{"check": w, "clause": clause(w.partition(": ")[0])} for w in want]
            controls.append({"wrong_fix": name, "checks": checks,
                             "contract_control": sweep.contract_control(spec.id, f"wrong:{name}")})  # fmt: skip
        rows[spec.id] = {"category": spec.metadata.category, "bootcheck": bc, "separation": sep, "qa": qa,
                         "margins": mg, "headroom": headroom(spec, table.get(spec.id)),
                         "margins_text": slack_miss[0], "thin": slack_miss[1],
                         "controls": controls,
                         "runtime_controls": runtime_controls(spec.id, wrong_fix_patches(spec)),
                         "supplementary_ok": bc_ok and sep_ok and mg_ok}  # fmt: skip
        rows[spec.id]["green"] = qa_ok and bool(rows[spec.id]["runtime_controls"])
    return rows


def markdown(rows: dict, run_stamp: dict) -> str:
    green = sum(r["green"] for r in rows.values())
    lines = [
        "# Task validation (test split)",
        "",
        f"{green} of {len(rows)} tasks green. {describe(run_stamp)}. `stale`: inputs changed since the result; "
        "`-`: not run. Bootcheck: the agent environment came up with the fault showing (k of n) and the verifier's "
        "started. Separation: one run each of the reference, the broken job and every scripted wrong fix, typed "
        "(pass, agent, infra, verifier_bug); a wrong fix counts only when it fails on a check it declares. QA "
        "(release): oracle 10 runs, nop 3, every wrong and accepted fix. Margins: memory-bound tasks only. Green: the "
        "release QA passes on this host and a wrong fix is declared to fail at runtime; bootcheck, "
        "separation and margins, from the development box, are evidence beside it. Records are "
        "stamped with the image ids of the machine that produced them, so on another host every row shows as stale "
        "until release QA is re-run there; this does not affect the published study records.",
        "",
        "| Task | Category | Bootcheck | Separation | Oracle / nop | Memory margins | Reference vs thresholds "
        "| Slack and miss | Green |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for task, r in rows.items():
        mark = "yes" if r["green"] else "no"
        lines.append(f"| {task} | {r['category']} | {r.get('bootcheck', '-')} | {r['separation']} | {r['qa']} | "
                     f"{r['margins']} | {r['headroom']} | {r['margins_text']} | {mark} |")  # fmt: skip
    lines += ["", "## Negative controls", "", "The check each wrong fix must fail, and the contract clause that check "
              "enforces (harness.verify.rules.CLAUSES); a wrong fix marked contract control fails a rule of the "
              "contract rather than the fault's mechanism.", ""]  # fmt: skip
    for task, r in rows.items():
        for c in r.get("controls") or []:
            mark = " (contract control)" if c["contract_control"] else ""
            if not c["checks"]:
                lines.append(f"- {task} / {c['wrong_fix']}{mark}: no declared check (any failure of the agent kind)")
            for w in c["checks"]:
                text = w["clause"] or "no contract clause: add one to harness.verify.rules.CLAUSES"
                lines.append(f"- {task} / {c['wrong_fix']}{mark}: `{w['check']}`: {text}")
    thin = [f"{task} ({', '.join(r['thin'])})" for task, r in rows.items() if r["thin"]]
    note = (
        "Thin margins (within 3x the loss spread, or 10% of a throughput or latency limit; the reference "
        "risks failing, a wrong fix or broken run risks passing)"
    )
    lines += ["", f"{note}: " + ("; ".join(thin) if thin else "none") + "."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench validation", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--gate", action="store_true", help="exit non-zero unless every test task is green")
    args = ap.parse_args(argv)
    rows, run_stamp = build(), stamp()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "validation.json").write_text(json.dumps({"stamp": run_stamp, "tasks": rows}, indent=1) + "\n")
    (OUT / "VALIDATION.md").write_text(markdown(rows, run_stamp))
    green = sum(r["green"] for r in rows.values())
    print(f"wrote {(OUT / 'VALIDATION.md').relative_to(RESULTS.parent)}: {green} of {len(rows)} tasks green")
    if args.gate and green < len(rows):
        raise SystemExit(f"not green: {', '.join(t for t, r in rows.items() if not r['green'])}")


if __name__ == "__main__":
    main()
