"""Repository locations, for the host-side tools."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = ROOT / "families"  # task specs and their fault patches
TEMPLATES = ROOT / "templates"  # the base /ops repositories every task starts from
TASKS = ROOT / "tasks"  # rendered Harbor tasks (committed; checked against a fresh render)
IMAGES = ROOT / "images"
RESULTS = ROOT / "results"  # curated, stamped records
RUNS = ROOT / "runs"  # gitignored: Harbor job directories, sweep and calibration logs, variant renders


# Docker resources the bench creates are named by checkout and run: two worktrees, or two commands in one worktree,
# never share (or tear down) each other's compose projects.
CHECKOUT = hashlib.sha256(str(ROOT).encode()).hexdigest()[:6]
RUN = os.urandom(2).hex()


def project_name(kind: str, *parts: str) -> str:
    """A compose project name `{kind}-{checkout}-{run}-{parts}`, lowercase, at most 60 characters (cut at the end)."""
    head = f"{kind}-{CHECKOUT}-{RUN}-"
    tail = re.sub(r"[^a-z0-9-]", "-", "-".join(parts).lower())
    return (head + tail)[:60].rstrip("-")
