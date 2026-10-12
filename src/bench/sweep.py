"""Separation sweep: every task's reference must pass, its broken /ops and every scripted wrong fix must fail.

  bench sweep [TASK ...] [--split test|dev|all] [--skip-done]

Runs `bench calibrate TASK --runs 1` per task (reference, pristine, wrong:*) through the real verifier on a fresh
cluster. Raw logs and per-run records go to runs/sweep/<task>.{log,jsonl}; the table, with each row's task digest
and provenance stamp, goes to results/sweep/sweep.json and results/sweep/SWEEP.md.

A run that ended in an infrastructure error (the reference run failed, the cluster never came up, the verifier
died) is INCONCLUSIVE, never a pass: a broken job that "scores 0" because the reference could not run proves nothing.
This is the fast inner loop; the release gate is `bench qa --release` (Harbor oracle x10, nop x3, wrong fixes).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from bench import outcomes, patches
from bench.paths import RESULTS, RUNS
from bench.provenance import describe, grader_digest, image_ids, stamp, task_digest, task_image_ids
from bench.spec import by_id, load_specs, task_dir

LOGS = RUNS / "sweep"
TABLE = RESULTS / "sweep"

PASS, FAIL, INCONCLUSIVE = "PASS", "FAIL", "INCONCLUSIVE"


def infra(record: dict) -> bool:
    return outcomes.kind(record) == outcomes.INFRA


def expectation(task: str, variant: str) -> list[str] | None:
    """The checks a wrong fix must fail (any of them; `policy` for a contract shortcut; `check: reason` when the
    check's message must say why), from wrong_fixes/<name>.expect (`#` starts a comment); None if it declares
    none."""
    if not variant.startswith("wrong:"):
        return None
    path = by_id(task).dir / "wrong_fixes" / f"{variant[6:]}.expect"
    lines = path.read_text().splitlines() if path.exists() else None
    return [x.strip() for x in lines if x.strip() and not x.lstrip().startswith("#")] if lines is not None else None


def contract_control(task: str, variant: str) -> bool:
    """A wrong fix that fails only a rule of the contract (the policy, or a format the contract fixes) rather than the
    fault's mechanism: its .expect says `# contract control`. Counted with the policy shortcuts, not as runtime
    coverage (bench validation)."""
    if not variant.startswith("wrong:"):
        return False
    path = by_id(task).dir / "wrong_fixes" / f"{variant[6:]}.expect"
    return path.exists() and any(x.strip().startswith("# contract control") for x in path.read_text().splitlines())


def expected_variants(task: str) -> list[str]:
    spec = by_id(task)
    return ["reference", "pristine", *(f"{kind}:{n}" for kind in ("wrong", "accepted")
                                       for n in patches.fix_patches(spec, kind))]  # fmt: skip


def verdict(
    rows: dict[str, dict], expected: list[str] | None = None, expects: dict[str, list[str] | None] | None = None
) -> tuple[str, str]:
    """PASS when the reference and every accepted fix pass and the broken job and every wrong fix fail, each with a
    complete verdict of the agent's (bench.outcomes), every wrong fix on a check it declares (`expects`). A variant
    that did not run, or ended in an infrastructure error, makes the task INCONCLUSIVE (unless something already
    failed outright); a verifier bug fails the task: a crashed grader is no evidence either way."""
    problems, unsure = [], []
    expected = expected or ["reference", "pristine"]
    expects = expects or {}
    missing = [n for n in expected if n not in rows]
    if missing:
        unsure.append(f"not run: {', '.join(missing)}")
    for name, r in rows.items():
        should_pass = name == "reference" or name.startswith("accepted:")
        label = "broken job" if name == "pristine" else name
        got = outcomes.kind(r)
        if got == outcomes.INFRA:
            unsure.append(f"{label}: infrastructure error")
        elif got == outcomes.BUG:
            problems.append(f"{label}: verifier bug")
        elif should_pass and got != outcomes.PASS:
            problems.append(f"{'reference' if name == 'reference' else name} fails")
        elif not should_pass and got != outcomes.AGENT:
            problems.append(f"{label} passes")
        elif not should_pass and (want := expects.get(name)) and not outcomes.failed_for(r, want):
            failed = ", ".join(r.get("failed_checks") or []) or "no check recorded"
            problems.append(f"{label} failed on {failed}, not on {' / '.join(want)}")
    if problems:
        return FAIL, "; ".join(problems + unsure)
    if unsure:
        return INCONCLUSIVE, "; ".join(unsure)
    return PASS, "ok"


def read_records(jsonl: Path) -> tuple[dict, dict[str, dict]]:
    """(header, {variant: record}) from a calibrate --jsonl file; the last run of each variant wins."""
    header: dict = {}
    rows: dict[str, dict] = {}
    if not jsonl.exists():
        return header, rows
    for line in jsonl.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "variant" in rec:
            rows[rec["variant"]] = {k: v for k, v in rec.items() if k not in ("task", "variant", "run")}
        else:
            header = rec
    return header, rows


def fmt(r: dict | None) -> str:
    if not r:
        return "-"
    bits = [f"r={r.get('reward')}"]
    bits += [f"{key.split('_')[0]}={r[key]}" for key in ("loss", "tput_ratio", "elapsed_s") if key in r]
    return " ".join(bits) + (" infra" if infra(r) else "")


def inputs(task: str) -> dict:
    """Everything a row's verdict depends on: the rendered task, its wrong fixes and the images it ran on."""
    wrong = hashlib.sha256()
    for name, path in sorted(patches.wrong_fix_patches(by_id(task)).items()):
        expect = path.with_suffix(".expect")  # what the fix must fail on is part of the verdict
        wrong.update(name.encode() + b"\0" + patches.body(path) + (expect.read_bytes() if expect.exists() else b""))
    d = task_dir(task)
    out = {"task_digest": task_digest(d), "grader_digest": grader_digest(d), "wrong_fixes": wrong.hexdigest()[:16],
           "images": task_image_ids(d, image_ids())}  # fmt: skip
    accepted = patches.accepted_fix_patches(by_id(task))
    if accepted:  # only tasks that have accepted fixes carry the key, so adding none leaves other rows fresh
        h = hashlib.sha256()
        for name, path in sorted(accepted.items()):
            h.update(name.encode() + b"\0" + patches.body(path))
        out["accepted_fixes"] = h.hexdigest()[:16]
    return out


def fresh(recorded: dict | None, current: dict, *, ignore_images: bool = False) -> bool:
    """Whether a recorded result still holds: what grading depends on is unchanged (grader digest, wrong fixes,
    images). Results recorded before grader digests existed compare the whole task digest; a result whose whole task
    digest still matches is fresh whatever its grader digest says (the task is byte-identical, so only the digest's
    definition can have changed). `ignore_images` leaves the image IDs out of the comparison: a local image ID differs
    on every host that rebuilds the images, so it cannot say whether a record made elsewhere still describes the
    task."""
    if not recorded:
        return False
    same_task = "task_digest" in recorded and recorded["task_digest"] == current.get("task_digest")
    key = "grader_digest" if "grader_digest" in recorded and not same_task else "task_digest"
    return all(
        recorded.get(k) == current.get(k)
        for k in (key, "wrong_fixes", "accepted_fixes", *(() if ignore_images else ("images",)))
    )


def adopt_grader_digests(table: dict) -> list[str]:
    """One-time migration: rows recorded before grader digests existed, whose task digest still matches the current
    render, get the current grader digest. Run before any wording-only change, or those rows go stale."""
    adopted = []
    for task, row in table["tasks"].items():
        rec = row.get("inputs") or {}
        try:
            exists = task_dir(task).exists()
        except KeyError:  # a retired task's row: nothing to migrate
            continue
        if "grader_digest" in rec or not exists:
            continue
        now = inputs(task)
        if fresh(rec, now):
            rec["grader_digest"] = now["grader_digest"]
            adopted.append(task)
    return adopted


def load_table() -> dict:
    path = TABLE / "sweep.json"
    return json.loads(path.read_text()) if path.exists() else {"tasks": {}}


def merge_task(task: str, row: dict) -> None:
    """Write one task's row under a lock, re-reading the table first: a sweep chain and a one-off sweep may run at the
    same time, and neither may erase the other's rows."""
    import fcntl

    TABLE.mkdir(parents=True, exist_ok=True)
    with open(TABLE / "sweep.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        table = load_table()
        table["tasks"][task] = row
        write_table(table)
        fcntl.flock(fh, fcntl.LOCK_UN)


def write_table(table: dict) -> None:
    TABLE.mkdir(parents=True, exist_ok=True)
    (TABLE / "sweep.json").write_text(json.dumps(table, indent=1) + "\n")
    current = {s.id: inputs(s.id) for s in load_specs() if task_dir(s).exists()}
    lines = [
        "# Separation sweep",
        "",
        "Reference and every accepted alternative fix must pass; the broken job and every scripted wrong fix must "
        "fail. A row is stale when what grading depends on (the task without its text, its wrong and accepted fixes, "
        "the images) changed since it ran. Raw logs: runs/sweep/.",
        "",
        "| Task | Verdict | Reference | Broken | Wrong fixes | Ran |",
        "|---|---|---|---|---|---|",
    ]
    counts: dict[str, int] = {}
    for task, row in sorted(table["tasks"].items()):
        if task not in current:
            continue
        stale = not fresh(row.get("inputs"), current[task])
        state = "STALE" if stale else row["verdict"]
        counts[state] = counts.get(state, 0) + 1
        runs = row["runs"]
        wrong = ", ".join(f"{k[6:]}: {fmt(v)}" for k, v in runs.items() if k.startswith("wrong:")) or "-"
        accepted = [f"{k[9:]}: {fmt(v)}" for k, v in runs.items() if k.startswith("accepted:")]
        wrong += "; accepted: " + ", ".join(accepted) if accepted else ""
        verdict_cell = state if row["why"] == "ok" or stale else f"{state}: {row['why']}"
        lines.append(
            f"| {task} | {verdict_cell} | {fmt(runs.get('reference'))} | {fmt(runs.get('pristine'))} | {wrong} | "
            f"{describe(row['stamp']).split(' · ')[0]} |"
        )
    lines += ["", ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) + f" (of {len(current)} tasks)."]
    (TABLE / "SWEEP.md").write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench sweep", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("tasks", nargs="*")
    ap.add_argument("--split", default="all", choices=["test", "dev", "all"])
    ap.add_argument("--skip-done", action="store_true", help="skip tasks whose current digest already passed")
    adopt_help = "migrate rows recorded before grader digests existed, then exit (never while a sweep runs)"
    ap.add_argument("--adopt-grader-digests", action="store_true", help=adopt_help)
    args = ap.parse_args(argv)
    if args.adopt_grader_digests:
        table = load_table()
        adopted = adopt_grader_digests(table)
        write_table(table)
        print(f"adopted grader digests for {len(adopted)} rows: {', '.join(adopted)}")
        return
    names = args.tasks or [s.id for s in load_specs() if args.split in ("all", s.split)]
    LOGS.mkdir(parents=True, exist_ok=True)
    table = load_table()
    for task in names:
        now = inputs(task)
        done = table["tasks"].get(task, {})
        if args.skip_done and done.get("verdict") == PASS and fresh(done.get("inputs"), now):
            continue
        jsonl, log = LOGS / f"{task}.jsonl", LOGS / f"{task}.log"
        jsonl.unlink(missing_ok=True)
        with log.open("w") as f:
            code = subprocess.run(
                [sys.executable, "-u", "-m", "bench.calibrate", task, "--runs", "1", "--jsonl", str(jsonl)],
                stdout=f,
                stderr=subprocess.STDOUT,
                check=False,
            ).returncode
        header, rows = read_records(jsonl)
        variants = expected_variants(task)
        state, why = verdict(rows, variants, {v: expectation(task, v) for v in variants})
        if code != 0 and state == PASS:
            state, why = INCONCLUSIVE, f"bench calibrate exited {code} (see {log.relative_to(RUNS.parent)})"
        table["tasks"][task] = {
            "verdict": state,
            "why": why,
            "inputs": now,
            "stamp": header.get("stamp") or stamp(),
            "runs": rows,
        }
        print(f"{time.strftime('%H:%M')} {task:32s} {state}  {why}", flush=True)
        merge_task(task, table["tasks"][task])
    write_table(load_table())
    failed = [t for t in names if table["tasks"].get(t, {}).get("verdict") != PASS]
    if failed:  # a release gate must be scriptable: any task not PASS fails the command
        print(f"not PASS: {', '.join(failed)}", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
