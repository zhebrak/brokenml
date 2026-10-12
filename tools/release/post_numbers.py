"""Every number the post and the report's findings quote, from the study dataset (results/study/trials.csv), so they
regenerate with it. Reported rows only; one verdict per model, task and condition (the counted trial; a trial in
results/study/zeroed.yaml scores 0).

    uv run python tools/release/post_numbers.py [--trials results/study/trials.csv]"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

COND = ("live cluster", "live logs + files", "files only")
SHORT = {"live cluster": "live", "live logs + files": "logs", "files only": "files"}


def load(path: Path) -> list[dict]:
    with path.open() as fh:
        return [r for r in csv.DictReader(line for line in fh if not line.startswith("#")) if not r["not_reported"]]


def verdicts(rows: list[dict]) -> dict[tuple[str, str, str], bool]:
    return {(r["model"], r["task"], r["condition"]): r["reward"] == "1.0" and not r["zeroed"]
            for r in rows if r["counted"] == "True"}  # fmt: skip


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "-"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--trials", type=Path, default=Path("results/study/trials.csv"))
    rows = load(ap.parse_args().trials)
    v = verdicts(rows)
    models = sorted({m for m, _, _ in v})
    tasks = sorted({t for _, t, _ in v})
    cat = {r["task"]: r["category"] for r in rows}

    print("A. Same model, same task, all three conditions graded")
    pooled = defaultdict(int)
    n_all = 0
    for m in models:
        both = [t for t in tasks if all((m, t, c) in v for c in COND)]
        rates = {c: sum(v[(m, t, c)] for t in both) for c in COND}
        n_all += len(both)
        for c in COND:
            pooled[c] += rates[c]
        print(f"  {m:45} n {len(both):2}  " + "  ".join(f"{SHORT[c]} {pct(rates[c], len(both)):>4}" for c in COND)
              + f"  live-files {100 * (rates[COND[0]] - rates[COND[2]]) / max(len(both), 1):+.0f} pp"
              + f"  live-logs {100 * (rates[COND[0]] - rates[COND[1]]) / max(len(both), 1):+.0f} pp")  # fmt: skip
    print(f"  pooled n {n_all}: " + "  ".join(f"{SHORT[c]} {pct(pooled[c], n_all)}" for c in COND))
    for a, b in ((COND[0], COND[2]), (COND[0], COND[1]), (COND[1], COND[2])):
        pairs = [(m, t) for m in models for t in tasks if (m, t, a) in v and (m, t, b) in v]
        only_a = sum(v[(m, t, a)] and not v[(m, t, b)] for m, t in pairs)
        only_b = sum(v[(m, t, b)] and not v[(m, t, a)] for m, t in pairs)
        print(
            f"  {SHORT[a]} vs {SHORT[b]}: {len(pairs)} pairs, solved only {SHORT[a]} {only_a}, only {SHORT[b]} {only_b}"
        )

    print("\nB. By category (pooled over models, every graded verdict)")
    for c_name in sorted(set(cat.values())):
        ts = [t for t in tasks if cat.get(t) == c_name]
        parts = []
        for c in COND:
            vals = [v[(m, t, c)] for m in models for t in ts if (m, t, c) in v]
            parts.append(f"{SHORT[c]} {pct(sum(vals), len(vals)):>4}")
        print(f"  {c_name:12} {len(ts):2} tasks  " + "  ".join(parts))

    print("\nC. Per task (pooled over models), sorted by live minus files")
    lines = []
    for t in tasks:
        cells = {c: [v[(m, t, c)] for m in models if (m, t, c) in v] for c in COND}
        rate = {c: sum(cells[c]) / len(cells[c]) if cells[c] else 0.0 for c in COND}
        lines.append((rate[COND[0]] - rate[COND[2]], t, cells))
    for gap, t, cells in sorted(lines, reverse=True):
        print(f"  {t:32} {cat.get(t, ''):12} " + "  ".join(f"{SHORT[c]} {sum(cells[c])}/{len(cells[c])}" for c in COND)
              + f"  gap {100 * gap:+.0f}")  # fmt: skip

    print("\nD. Cost per run and per solve (recorded cost: cut-off responses excluded), time-outs")
    for m in models:
        parts = []
        for c in COND:
            rs = [r for r in rows if r["model"] == m and r["condition"] == c]
            cost = sum(float(r["cost_recorded"] or 0) for r in rs)
            solves = sum(v.get((m, t, c), False) for t in tasks)
            timeouts = sum(r["exception"] == "AgentTimeoutError" for r in rs if r["counted"] == "True")
            mins = sorted(float(r["agent_s"]) / 60 for r in rs if r["counted"] == "True" and r["agent_s"])
            med = (mins[(len(mins) - 1) // 2] + mins[len(mins) // 2]) / 2 if mins else 0.0  # the true median
            per_run, per_solve = cost / max(len(rs), 1), cost / solves if solves else 0.0
            parts.append(f"{SHORT[c]} ${per_run:.3f}/run ${per_solve:.2f}/solve {med:.1f}m to {timeouts}"
                         if solves else f"{SHORT[c]} -")  # fmt: skip
        print(f"  {m:45} " + " | ".join(parts))

    print("\nE. Responses cut off at the output limit (not in the recorded cost)")
    for m in models:
        rs = [r for r in rows if r["model"] == m]
        n = sum(int(r["cutoff_responses"] or 0) for r in rs)
        if n:
            billed = sum(float(r["cost_billed"] or 0) for r in rs)
            recorded = sum(float(r["cost_recorded"] or 0) for r in rs)
            print(f"  {m:45} {n} cut-off responses in {sum(int(r['cutoff_responses'] or 0) > 0 for r in rs)} runs; "
                  f"recorded ${recorded:.2f}, billed ${billed:.2f}")  # fmt: skip

    print("\nF. Why failures failed (counted verdicts that are not solves)")
    for c in COND:
        rs = [r for r in rows if r["condition"] == c and r["counted"] == "True"
              and not (r["reward"] == "1.0" and not r["zeroed"])]  # fmt: skip
        policy = sum("policy" in r["failed_checks"] for r in rs)
        incomplete = sum("completed" in r["first_failed_check"] for r in rs)
        print(f"  {SHORT[c]:5} {len(rs)} fails: first failed check 'job completed...' {incomplete}, policy {policy}, "
              f"zeroed {sum(bool(r['zeroed']) for r in rs)}")  # fmt: skip

    print(
        "\nG. Robustness: solved cells by the study's rule, by first attempts only (a first attempt without a verdict"
    )
    print("   counts as a fail), and with the Slurm-defect cells re-graded on the patched runtime (deviation ag) at 0")
    first: dict[tuple[str, str, str], bool] = {}
    for r in sorted(rows, key=lambda r: int(r["attempt"])):
        key = (r["model"], r["task"], r["condition"])
        if key not in first:
            first[key] = r["reward"] == "1.0" and not r["zeroed"] and r["outcome"] == "pass"
    for m in models:
        rule = [sum(v.get((m, t, c), False) for t in tasks) for c in COND]
        firsts = [sum(first.get((m, t, c), False) for t in tasks) for c in COND]
        patched = {(r["task"], r["condition"]) for r in rows if r["model"] == m and r["patched_runtime"] == "True"}
        slurm0 = [sum(v.get((m, t, c), False) and (t, c) not in patched for t in tasks) for c in COND]
        print(f"  {m:45} rule {'/'.join(map(str, rule))}  first attempts {'/'.join(map(str, firsts))}  "
              f"Slurm cells at 0 {'/'.join(map(str, slurm0))}")  # fmt: skip

    print("\nH. Live-cluster behaviour on the training tasks (serving excluded; the dataset's behaviour columns, from"
          " results/study/behaviour.jsonl): submissions per run, `ocb score`, a check after the last edit")  # fmt: skip
    for m in models:
        rs = [r for r in rows if r["model"] == m and r["condition"] == COND[0] and r["counted"] == "True"
              and r["category"] != "serving" and r["n_submit"] != ""]  # fmt: skip
        if not rs:
            continue
        subs = [int(float(r["n_submit"])) for r in rs]
        passes = sorted(int(float(r["n_submit"])) for r in rs if v[(r["model"], r["task"], r["condition"])])
        fails = sorted(int(float(r["n_submit"])) for r in rs if not v[(r["model"], r["task"], r["condition"])])
        median = lambda xs: (xs[(len(xs) - 1) // 2] + xs[len(xs) // 2]) / 2 if xs else None
        edited = [r for r in rs if r["verified_after_last_edit"] != ""]
        scored = sum(r["used_ocb_score"] == "True" for r in rs)
        checked = sum(r["verified_after_last_edit"] == "True" for r in edited)
        print(f"  {m:45} n {len(rs)}: submitted at least once {sum(s > 0 for s in subs)}; "
              f"mean submissions {sum(subs) / len(rs):.1f}; median passes {median(passes)}, "
              f"fails {median(fails) if fails else '-'} (n={len(fails)}); ocb score {scored}; "
              f"checked after the last edit {checked}/{len(edited)} runs that edited")  # fmt: skip


if __name__ == "__main__":
    main()
