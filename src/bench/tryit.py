"""Five tasks to try the benchmark on: quick to grade and known to work on current records.

  uv run bench try-it [--n 5]

A task qualifies when its bootcheck and separation records are current (results/bootcheck.json and
results/sweep/sweep.json, the same freshness rules as `bench validation` except that local image IDs are not compared,
so it still finds tasks on a machine that rebuilt the images) and its reference fix was graded in under 3
minutes; among those, one per category first, fastest first. Prints the tasks and the Harbor command that runs the
reference fix on them (`make try-it` does it); a new user sees oracle scores of 1 in a few minutes.
"""

from __future__ import annotations

import argparse
import json

from bench import sweep, validation
from bench.paths import RESULTS
from bench.spec import load_specs

MAX_REFERENCE_S = 180


def candidates() -> list[tuple[float, str, str]]:
    """(reference wall seconds, category, task) for every test task with current, passing records."""
    table = sweep.load_table()["tasks"]
    boot = validation._load(RESULTS / "bootcheck.json") or {}
    out = []
    for spec in (s for s in load_specs() if s.split == "test"):
        row = table.get(spec.id)
        if row is None or row.get("verdict") != "PASS":
            continue
        # Local image IDs differ on every host that rebuilds the images, so they are left out here; the image guard at
        # trial time still refuses a run on images that do not match the task.
        if not sweep.fresh(row.get("inputs"), sweep.inputs(spec.id), ignore_images=True):
            continue
        if not validation.bootcheck_cell(spec.id, boot.get(spec.id), ignore_images=True)[1]:
            continue
        wall = (row["runs"].get("reference") or {}).get("wall_s")
        if wall is not None and wall <= MAX_REFERENCE_S:
            out.append((float(wall), spec.metadata.category, spec.id))
    return sorted(out)


def pick(rows: list[tuple[float, str, str]], n: int) -> list[str]:
    """One per category first (fastest of each), then the fastest of the rest."""
    chosen, seen = [], set()
    for _, category, task in rows:
        if category not in seen and len(chosen) < n:
            chosen.append(task)
            seen.add(category)
    for _, _, task in rows:
        if len(chosen) >= n:
            break
        if task not in chosen:
            chosen.append(task)
    return chosen


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench try-it", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--json", action="store_true", help="print the task ids as JSON")
    ap.add_argument("--args", action="store_true", help="print Harbor's -i arguments only (make try-it)")
    args = ap.parse_args(argv)
    tasks = pick(candidates(), args.n)
    if args.json:
        print(json.dumps(tasks))
        return
    if args.args:
        if not tasks:
            raise SystemExit("no task has current bootcheck and separation records yet")
        print(" ".join(f"-i {t}" for t in tasks))
        return
    if not tasks:
        raise SystemExit("no task has current bootcheck and separation records yet (bench bootcheck, bench sweep)")
    print("\n".join(tasks))
    print("harbor run -p tasks/test -a oracle -n 1 " + " ".join(f"-i {t}" for t in tasks))


if __name__ == "__main__":
    main()
