"""Check the trivial baselines of Harbor jobs: every oracle trial scores 1, every nop trial scores 0, each with a real
verdict (no Harbor error, no infrastructure failure). Exits non-zero otherwise, so `make smoke` and `make reproduce`
fail instead of reporting.

  bench check-baselines ORACLE_JOB_DIR NOP_JOB_DIR [--split test|dev]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bench.qa import read_trials, scored
from bench.spec import load_specs


def problems(oracle: list[dict], nop: list[dict], expected: set[str] | None = None) -> list[str]:
    out = []
    if not oracle or not nop:
        out.append(f"no trials (oracle {len(oracle)}, nop {len(nop)})")
    if expected is not None:  # every task the split defines, not just the ones that happened to run
        for name, trials in (("oracle", oracle), ("nop", nop)):
            absent = sorted(expected - {t["task"] for t in trials})
            if absent:
                out.append(f"{name}: no trial of {absent}")
    for t in oracle:
        if not scored(t, 1.0):
            out.append(f"oracle {t['task']}: reward {t['reward']}, error {t['error']}, infra {t['infra']} ({t['dir']})")
    for t in nop:
        if not scored(t, 0.0):
            out.append(f"nop {t['task']}: reward {t['reward']}, error {t['error']}, infra {t['infra']} ({t['dir']})")
    missing = {t["task"] for t in oracle} ^ {t["task"] for t in nop}
    if missing:
        out.append(f"tasks run by only one baseline: {sorted(missing)}")
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench check-baselines", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("oracle", type=Path)
    ap.add_argument("nop", type=Path)
    ap.add_argument("--split", choices=["test", "dev"], help="require a trial of every task of this split")
    args = ap.parse_args(argv)
    oracle, nop = read_trials(args.oracle), read_trials(args.nop)
    expected = {s.id for s in load_specs() if s.split == args.split} if args.split else None
    found = problems(oracle, nop, expected)
    print(f"oracle: {sum(scored(t, 1.0) for t in oracle)}/{len(oracle)} scored 1; "
          f"nop: {sum(scored(t, 0.0) for t in nop)}/{len(nop)} scored 0")  # fmt: skip
    for p in found:
        print(f"  {p}")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
