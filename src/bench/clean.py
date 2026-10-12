"""Tear down compose projects this checkout's commands left behind (a killed sweep, a bootcheck --keep):

  uv run bench clean [--run RUN] [--down]

Lists the projects named by bench.paths.project_name for this checkout (`{kind}-{checkout}-{run}-...`), optionally
one run; with --down, takes them down with their volumes. Projects of other checkouts and Harbor's own trial
projects are never touched. Without --down nothing changes.
"""

from __future__ import annotations

import argparse
import json
import subprocess

from bench.paths import CHECKOUT

KINDS = ("cal", "mg", "boot", "bootv", "leak")


def ours(name: str, run: str | None = None) -> bool:
    parts = name.split("-")
    return len(parts) >= 3 and parts[0] in KINDS and parts[1] == CHECKOUT and (run is None or parts[2] == run)


def projects() -> list[dict]:
    out = subprocess.run(["docker", "compose", "ls", "-a", "--format", "json"], capture_output=True, text=True,
                         check=True).stdout  # fmt: skip
    return json.loads(out or "[]")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench clean", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--run", help="only this run's projects (the 4-hex run id in the project name)")
    ap.add_argument("--down", action="store_true", help="take them down (default: list only)")
    args = ap.parse_args(argv)
    found = [p for p in projects() if ours(p["Name"], args.run)]
    for p in found:
        print(f"{p['Name']:60} {p['Status']}")
        if args.down:
            subprocess.run(["docker", "compose", "-p", p["Name"], "down", "-v", "--remove-orphans"], check=False,
                           capture_output=True)  # fmt: skip
    print(f"{len(found)} project(s) of checkout {CHECKOUT}" + (" taken down" if args.down and found else ""))


if __name__ == "__main__":
    main()
