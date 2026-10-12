"""bench clean touches only this checkout's projects, optionally one run's."""

from __future__ import annotations

from bench.clean import ours
from bench.paths import CHECKOUT, project_name


def test_only_this_checkouts_projects_are_ours():
    name = project_name("cal", "rank0-eval-desync")
    run = name.split("-")[2]
    assert ours(name) and ours(name, run) and not ours(name, "ffff" if run != "ffff" else "0000")
    assert not ours(name.replace(CHECKOUT, "abcdef" if CHECKOUT != "abcdef" else "fedcba"))
    assert not ours("same-shard__ra5dd6f__env") and not ours("n8n-docker")
