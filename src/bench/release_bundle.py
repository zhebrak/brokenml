"""The release evidence bundle: one stamped record of what qualified the frozen test split.

  uv run bench release-bundle [--out results/release]

For every test task: its task and grader digests and each qualification record (bootcheck, separation sweep, release
QA, memory margins) with its status as `bench validation` derives it (a result, `stale` when its inputs changed since
it ran, `-` when missing); the commit, image IDs, Harbor version and host; and the pooled oracle flake bound over the
release QA runs (with no failure in n runs, the one-sided 95% upper bound on the failure rate is 1 - 0.05^(1/n), about
3/n). Writes manifest.json, README.md and the task cards (cards/, `bench cards`) under --out; exits non-zero unless
every test task is green, the same gate as `bench validation --gate`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from bench import cards, sweep, validation
from bench.paths import RESULTS
from bench.provenance import describe, grader_digest, image_tags, stamp, task_digest
from bench.spec import load_specs, task_dir

OUT = RESULTS / "release"


def oracle_runs(record: dict | None, current: dict | None = None) -> tuple[int, int]:
    """(passed, run) pooled over every oracle run the release QA record keeps against its inputs (`oracle_history`:
    a flake that a re-run then passed stays counted), else from its oracle check ("oracle 10/10 ..."); (0, 0) without
    one, or when `current` is given and the record's inputs are not the current ones (a stale record proves nothing
    about the images and grader that ship)."""
    record = record or {}
    if current is not None and record.get("inputs") != current:
        return 0, 0
    history = [h for h in record.get("oracle_history") or [] if isinstance(h, dict)]
    if history:
        return sum(int(h.get("passed", 0)) for h in history), sum(int(h.get("runs", 0)) for h in history)
    for check in record.get("checks", []):
        m = re.match(r"oracle (\d+)/(\d+)", str(check.get("check", "")))
        if m:
            return int(m.group(1)), int(m.group(2))
    return 0, 0


def flake_bound(passed: int, runs: int) -> dict:
    """Pooled oracle failures and the one-sided 95% upper bound on the failure rate when none failed."""
    failures = runs - passed
    bound = 1 - 0.05 ** (1 / runs) if runs and not failures else None
    return {"runs": runs, "failures": failures, "upper95": round(bound, 4) if bound is not None else None}


def image_builds() -> dict[str, str]:
    """Each configured image's build ID (/opt/*/BUILD inside it), read once per release; "" when it is not built."""
    out = {}
    for role, ref in image_tags().items():
        path = {"harness": "/opt/harness/BUILD", "serve": "/opt/engine/BUILD"}.get(role, "/opt/ocb/BUILD")
        res = subprocess.run(["docker", "run", "--rm", "--entrypoint", "cat", ref, path], capture_output=True,
                             text=True, check=False, timeout=120)  # fmt: skip
        out[role] = res.stdout.strip() if res.returncode == 0 else ""
    return out


def build(rows: dict | None = None) -> dict:
    rows = rows if rows is not None else validation.build()
    passed = runs = 0
    for task in rows:
        p, n = oracle_runs(validation._load(RESULTS / "qa" / f"{task}.json"), sweep.inputs(task))
        passed, runs = passed + p, runs + n
    tasks = {}
    for spec in sorted((s for s in load_specs() if s.split == "test"), key=lambda s: s.id):
        d = task_dir(spec)
        tasks[spec.id] = {"version": spec.version, "task_digest": task_digest(d), "grader_digest": grader_digest(d),
                          **rows[spec.id]}  # fmt: skip
    return {"stamp": stamp(), "image_builds": image_builds(), "green": sum(r["green"] for r in tasks.values()),
            "tasks": tasks, "oracle_flake": flake_bound(passed, runs)}  # fmt: skip


def readme(bundle: dict) -> str:
    flake = bundle["oracle_flake"]
    if flake["runs"] == 0:
        flake_text = "no release QA oracle runs recorded yet"
    elif flake["upper95"] is not None:
        flake_text = (f"0 failures in {flake['runs']} oracle runs: the failure rate is at most "
                      f"{flake['upper95']:.2%} (one-sided 95%)")  # fmt: skip
    else:
        flake_text = f"{flake['failures']} failures in {flake['runs']} oracle runs"
    lines = [
        "# Release evidence",
        "",
        f"{describe(bundle['stamp'])}. {bundle['green']} of {len(bundle['tasks'])} test tasks green. Oracle flake: "
        f"{flake_text}.",
        "",
        "| Task | Version | Bootcheck | Separation | Oracle / nop | Memory margins | Green |",
        "|---|---|---|---|---|---|---|",
    ]
    for task, r in bundle["tasks"].items():
        lines.append(f"| {task} | {r['version']} | {r.get('bootcheck', '-')} | {r['separation']} | {r['qa']} | "
                     f"{r['margins']} | {'yes' if r['green'] else 'no'} |")  # fmt: skip
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench release-bundle", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    rows = validation.build()
    bundle = build(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "manifest.json").write_text(json.dumps(bundle, indent=1) + "\n")
    (args.out / "README.md").write_text(readme(bundle))
    cards.write(args.out / "cards", rows)
    print(f"wrote {args.out}: {bundle['green']} of {len(bundle['tasks'])} test tasks green")
    if bundle["green"] < len(bundle["tasks"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
