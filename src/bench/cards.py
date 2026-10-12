"""Task cards: one page per test task, generated from its spec, its fixes and its qualification records.

  uv run bench cards [--out results/release/cards]

A card puts in one place what a reader needs to judge a task: why it exists (the public issue or the failure class),
what was adapted from the source, the mechanism and causal chain, what the agent sees, the reference repair and the
accepted alternatives, the known shortcuts and the check each must fail on (with what the last sweep observed), the
checks and resources, and the qualification record as `bench validation` derives it. `bench release-bundle` writes the
cards next to its manifest. Cards are host-side documentation: they quote the causal chain, which never reaches a task
directory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bench import sweep, validation
from bench.constants import CANARY, CANARY_GUID
from bench.patches import accepted_fix_patches, solution_patch, touched, wrong_fix_patches
from bench.paths import RESULTS
from bench.provenance import task_digest
from bench.spec import CATEGORY_PRINCIPLES, TaskSpec, load_specs, task_dir

OUT = RESULTS / "release" / "cards"


def files(patch: Path) -> list[str]:
    """The paths a patch touches (bench.patches.touched: the one reading of a patch's headers)."""
    return sorted(set(touched(patch.read_text())))


def _code(paths: list[str]) -> str:
    return ", ".join(f"`{p}`" for p in paths) or "-"


def expectation_text(patch: Path) -> tuple[str, str, bool]:
    """(the checks it must fail, the author's note from `#` lines, whether it is a contract control) of a wrong fix."""
    expect = patch.with_suffix(".expect")
    if not expect.exists():
        return "any check (no expectation declared)", "", False
    lines = [line.strip() for line in expect.read_text().splitlines() if line.strip() and CANARY_GUID not in line]
    checks = [line for line in lines if not line.startswith("#")]
    notes = [line.lstrip("# ").strip() for line in lines if line.startswith("#")]
    control = any(n.startswith("contract control") for n in notes)
    notes = [n for n in notes if not n.startswith("contract control")]
    return " or ".join(f"`{c}`" for c in checks) or "any check", " ".join(notes), control


def observed(run: dict | None) -> str:
    """What the last sweep recorded for one variant: the failed checks with their messages, or the reward."""
    if not run:
        return "not run"
    messages = run.get("failed_messages") or {}
    failed = run.get("failed_checks") or []
    if failed:
        return "; ".join(f"{c}: {messages[c]}" if messages.get(c) else c for c in failed)
    return f"reward {run.get('reward')}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def card(spec: TaskSpec, row: dict, sweep_row: dict | None, labels: dict) -> str:
    m = spec.metadata
    runs = (sweep_row or {}).get("runs", {})
    measured = (labels.get(spec.id) or {}).get("evidence")
    if measured and task_digest(task_dir(spec)) not in (measured.get("digests") or []):
        measured = None  # measured on an earlier version of the task: not this task's label
        earlier = True
    else:
        earlier = False
    if measured:
        ci = measured.get("ci95") or [None, None]
        evidence = (f"{measured['value']} (ops-only success {measured['ops_only_success']:.2f}, 95% CI "
                    f"{ci[0]:.2f}-{ci[1]:.2f}, {measured['trials']} trials"
                    f"{', provisional' if measured.get('provisional') else ''})")  # fmt: skip
    elif earlier:
        evidence = "measured on an earlier version of the task only (re-measure in the ops-only ablation)"
    else:
        evidence = "not measured yet (ops-only ablation)"
    if spec.adaptation:
        adaptation = spec.adaptation.strip() + " (author's note; second check pending)"
    elif m.provenance_kind == "issue-repro":
        adaptation = "Not written yet."
    else:
        adaptation = "Not applicable: the task reproduces a failure class, not one report."
    lines = [
        f"<!-- {CANARY} -->",
        f"# {spec.id} ({spec.version})",
        "",
        spec.title,
        "",
        "| | |",
        "|---|---|",
        f"| Category | {m.category}: {CATEGORY_PRINCIPLES[m.category]} |",
        f"| Principle | {_cell(m.principle)} |",
        f"| Family, subcategory | {m.family}, {m.subcategory} |",
        f"| Fault kind | {m.fault_kind} |",
        f"| Deciding evidence | {m.channel} |",
        f"| Author's labels | difficulty {m.difficulty}; evidence {m.evidence_author}; expert "
        f"{m.expert_time_estimate_min:g} min, junior {m.junior_time_estimate_min:g} min |",
        f"| Measured evidence label | {evidence} |",
        f"| GPU symptom vs CPU | {m.gpu_symptom} (docs/fidelity.md) |",
        "",
        "## Rationale",
        "",
        f"{m.provenance_kind}: " + ", ".join(f"<{u}>" for u in m.provenance),
        "",
        f"Adaptation from the source: {adaptation}",
        "",
        "## Mechanism",
        "",
        m.mechanism.strip(),
        "",
        "Causal chain (graded in ANALYSIS.md, never part of the reward):",
        "",
        *[f"{i}. {step}" for i, step in enumerate(m.causal_chain, 1)],
        "",
        "## What the agent faces",
        "",
        spec.readme.difficulty.strip(),
        "",
        "## Repair",
        "",
        spec.readme.solution.strip(),
        "",
        f"Reference fix touches {_code(files(solution_patch(spec)))}.",
        "",
    ]
    accepted = accepted_fix_patches(spec)
    if accepted:
        lines += ["Accepted alternatives (must pass):", ""]
        lines += [f"- `{name}` touches {_code(files(p))}; last sweep: {observed(runs.get(f'accepted:{name}'))}"
                  for name, p in accepted.items()]  # fmt: skip
        lines.append("")
    borderline = spec.dir / "borderline"
    if borderline.is_dir():
        names = ", ".join(f"`{p.stem}`" for p in sorted(borderline.glob("*.patch")))
        lines += [f"Borderline, not graded: {names} (families/.../borderline/README.md).", ""]
    lines += [
        "## Known shortcuts and why they fail",
        "",
        "| Wrong fix | Touches | Must fail on | Last sweep observed |",
        "|---|---|---|---|",
    ]
    for name, p in wrong_fix_patches(spec).items():
        checks, note, control = expectation_text(p)
        label = f"`{name}`" + (" (contract control)" if control else "")
        checks += f" ({_cell(note)})" if note else ""
        lines.append(f"| {label} | {_code(files(p))} | {checks} | {_cell(observed(runs.get(f'wrong:{name}')))} |")
    if sweep_row is None:
        record = "No sweep record yet."
    else:
        state = "current" if sweep.fresh(sweep_row.get("inputs"), sweep.inputs(spec.id)) else "stale"
        record = f"Sweep record: {state}, verdict {sweep_row.get('verdict')}."
    lines += [
        "",
        f"The broken job, as handed over: {_cell(observed(runs.get('pristine')))}. {record}",
        "",
        "## Checks",
        "",
        spec.readme.verification.strip(),
        "",
        "Verifier settings: " + ", ".join(f"`{k}: {json.dumps(v)}`" for k, v in spec.raw["verify"].items()) + ".",
        "",
        "## Resources",
        "",
        f"Nodes {', '.join(spec.nodes)}; agent {spec.agent_timeout_s / 60:g} min, verifier "
        f"{spec.verifier_timeout_s / 60:g} min."
        + (f" Hardware overrides: {_code(sorted(spec.raw['hardware']))}." if spec.raw.get("hardware") else ""),
        "",
        "## Qualification record",
        "",
        "| Bootcheck | Separation | Oracle / nop | Memory margins | Green |",
        "|---|---|---|---|---|",
        "| "
        + " | ".join(row.get(k, "-") for k in ("bootcheck", "separation", "qa", "margins"))
        + f" | {'yes' if row.get('green') else 'no'} |",
        "",
    ]
    return "\n".join(lines)


def index(specs: list[TaskSpec], rows: dict) -> str:
    lines = [
        f"<!-- {CANARY} -->",
        "# Task cards",
        "",
        "Generated by `bench cards` from the task specs, fixes and qualification records.",
        "",
        "| Task | Category | Provenance | Adaptation note | Green |",
        "|---|---|---|---|---|",
    ]
    for s in specs:
        note = "yes" if s.adaptation else ("missing" if s.metadata.provenance_kind == "issue-repro" else "-")
        lines.append(f"| [{s.id}]({s.id}.md) | {s.metadata.category} | {s.metadata.provenance_kind} | {note} | "
                     f"{'yes' if rows.get(s.id, {}).get('green') else 'no'} |")  # fmt: skip
    return "\n".join(lines) + "\n"


def write(out: Path, rows: dict | None = None) -> list[str]:
    """Write every test task's card and the index under `out`; returns the issue-repro tasks with no adaptation note."""
    rows = rows if rows is not None else validation.build()
    table = sweep.load_table()["tasks"]
    labels = validation._load(RESULTS / "labels.json") or {}
    specs = sorted((s for s in load_specs() if s.split == "test"), key=lambda s: s.id)
    out.mkdir(parents=True, exist_ok=True)
    for s in specs:
        (out / f"{s.id}.md").write_text(card(s, rows.get(s.id, {}), table.get(s.id), labels))
    (out / "README.md").write_text(index(specs, rows))
    return [s.id for s in specs if s.metadata.provenance_kind == "issue-repro" and not s.adaptation]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench cards", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    missing = write(args.out)
    print(f"wrote {args.out}" + (f"; issue-repro tasks without an adaptation note: {', '.join(missing)}"
                                 if missing else ""))  # fmt: skip


if __name__ == "__main__":
    main()
