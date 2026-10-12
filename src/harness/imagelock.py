"""The images a task was rendered against, checked against the image a container actually runs from.

bench render writes `images.lock` beside each compose file: per image role, the tag and a hash of the sources the
image is built from. The tag is mutable. A `make image` during a long run retags it, and every container started
after that runs newer code than the task was rendered and certified against, while the run's manifest (digests read
once at launch) still says otherwise: the exploratory pass of 2026-10-04 graded 9 of its 46 trials with three later
verifier builds (docs/research/qwen-trajectory-audit-2026-10-05.md). So a container compares the source hash baked
into its image at build time (/opt/ocb/VERSION, /opt/harness/VERSION) with what the task expects, and refuses to
provision or grade on a mismatch: an infrastructure failure, loud and re-runnable, never a verdict on the agent.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

VERSION_FILES = {"runtime": Path("/opt/ocb/VERSION"), "harness": Path("/opt/harness/VERSION")}
ENV_KEYS = {"runtime": "OCB_EXPECT_RUNTIME", "harness": "OCB_EXPECT_HARNESS"}  # set by bench.compose


def parse(text: str) -> dict[str, tuple[str, str]]:
    """role -> (image tag, source hash) from an images.lock; comments and blank lines are skipped."""
    out: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        parts = line.split()
        if parts and not parts[0].startswith("#") and len(parts) >= 3:
            out[parts[0]] = (parts[1], parts[2])
    return out


def expected_from_env(env: Mapping[str, str] = os.environ) -> dict[str, tuple[str, str]]:
    """What the compose file tells a container to expect, for containers that do not carry the lock file."""
    return {role: ("", env[key]) for role, key in ENV_KEYS.items() if env.get(key)}


def running(files: Mapping[str, Path] = VERSION_FILES) -> dict[str, str]:
    """The source hash of the image this container runs from, for each role whose VERSION file is present."""
    return {role: path.read_text().strip() for role, path in files.items() if path.exists()}


def mismatches(expected: Mapping[str, tuple[str, str]], actual: Mapping[str, str]) -> list[str]:
    """One line per role whose running image was built from other sources than the task was rendered against. A role
    the task does not pin, or that this container does not carry, is not compared."""
    out = []
    for role, (tag, want) in sorted(expected.items()):
        have = actual.get(role)
        if have is not None and have != want:
            where = f" ({tag})" if tag else ""
            out.append(f"{role}: this container runs an image built from source {have}, the task was rendered "
                       f"against {want}{where}")  # fmt: skip
    return out
