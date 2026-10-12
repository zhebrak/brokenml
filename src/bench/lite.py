"""The lite subset: the test tasks that repeat trials (for pass^k) run on. Every configuration runs the full test
split at least once; repeats beyond the first may be limited to lite (docs/leaderboard.md). Chosen reproducibly so
every configuration's repeats cover the same tasks:

    uv run bench lite --size 20 [--seed 0] [--pass-rates results/pilots/pass_rates.json]

- **Every category is represented**, in proportion to its share of the test split (largest remainder), with at least
  one task each when the size allows.
- **Within a category,** tasks whose evidence is only at runtime come first (measured labels from
  results/labels.json where they exist, otherwise the author's). Difficulty is spread across hard,
  medium and easy: from measured pass rates when given (a task id to mean reward over pilot configurations), otherwise
  from the author's label.
- **Ties** are broken by the seed.

Writes tasks/test/lite.txt (one task id per line, with a header naming the inputs); `bench run MODEL $(grep -v '^#'
tasks/test/lite.txt)` runs it.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from bench.paths import ROOT
from bench.spec import TaskSpec, load_specs

OUT = ROOT / "tasks" / "test" / "lite.txt"


def _level(spec: TaskSpec, pass_rates: dict[str, float] | None) -> str:
    if pass_rates and spec.id in pass_rates:  # Terminal-Bench's thresholds on the empirical pass rate
        r = pass_rates[spec.id]
        return "hard" if r < 1 / 3 else "medium" if r < 2 / 3 else "easy"
    return spec.metadata.difficulty


def quotas(counts: dict[str, int], size: int) -> dict[str, int]:
    """Seats per category in proportion to its tasks (largest remainder), at least one each when size allows."""
    total = sum(counts.values())
    exact = {c: size * n / total for c, n in counts.items()}
    seats = {c: int(x) for c, x in exact.items()}
    if size >= len(counts):
        for c in counts:
            seats[c] = max(seats[c], 1)
    while sum(seats.values()) > size:  # the minimum of one pushed the total over: take back from the largest
        c = max(seats, key=lambda k: (seats[k] - exact[k], seats[k]))
        seats[c] -= 1
    for c in sorted(exact, key=lambda k: exact[k] - seats[k], reverse=True):
        if sum(seats.values()) >= size:
            break
        if seats[c] < counts[c]:
            seats[c] += 1
    return seats


def evidence(spec: TaskSpec, labels: dict) -> str:
    return ((labels.get(spec.id) or {}).get("evidence") or {}).get("value") or spec.metadata.evidence_author


def select(
    specs: list[TaskSpec],
    size: int,
    seed: int = 0,
    pass_rates: dict[str, float] | None = None,
    labels: dict | None = None,
) -> list[str]:
    rng, labels = random.Random(seed), labels or {}
    by_cat: dict[str, list[TaskSpec]] = defaultdict(list)
    for s in specs:
        by_cat[s.metadata.category].append(s)
    seats = quotas({c: len(v) for c, v in by_cat.items()}, min(size, len(specs)))
    chosen: list[str] = []
    for cat in sorted(by_cat):
        pool = sorted(by_cat[cat], key=lambda s: s.id)
        rng.shuffle(pool)
        pool.sort(key=lambda s: evidence(s, labels) != "runtime")  # stable: runtime first, shuffled within
        levels: dict[str, list[TaskSpec]] = defaultdict(list)
        for s in pool:
            levels[_level(s, pass_rates)].append(s)
        order = []  # round-robin over hard, medium, easy so a category's seats spread difficulty
        while any(levels.values()):
            for lv in ("hard", "medium", "easy"):
                if levels[lv]:
                    order.append(levels[lv].pop(0))
        chosen += [s.id for s in order[: seats.get(cat, 0)]]
    return sorted(chosen)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench lite", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pass-rates", type=Path, help="JSON {task id: mean reward over pilot configurations}")
    args = ap.parse_args(argv)
    rates = json.loads(args.pass_rates.read_text()) if args.pass_rates else None
    specs = [s for s in load_specs() if s.split == "test"]
    labels_path = ROOT / "results" / "labels.json"
    labels = json.loads(labels_path.read_text()) if labels_path.exists() else None
    ids = select(specs, args.size, args.seed, rates, labels)
    header = [f"# lite subset: {len(ids)} of {len(specs)} test tasks; bench lite --size {args.size} --seed {args.seed}"
              + (f" --pass-rates {args.pass_rates}" if args.pass_rates else "")]  # fmt: skip
    OUT.write_text("\n".join(header + ids) + "\n")
    cats: dict[str, int] = defaultdict(int)
    for s in specs:
        if s.id in ids:
            cats[s.metadata.category] += 1
    print(f"wrote {OUT.relative_to(ROOT)}: " + ", ".join(f"{c} {n}" for c, n in sorted(cats.items())))


if __name__ == "__main__":
    main()
