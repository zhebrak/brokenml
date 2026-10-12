"""The bootstrap report says what became of every submitted job (finished jobs leave the queue)."""

from __future__ import annotations

import pytest

pytest.importorskip("torch")  # harness.provision generates data with torch

from harness import provision
from ocb import slurm

pytestmark = pytest.mark.torch


def test_each_job_gets_its_state_exit_code_and_log_pointer(monkeypatch):
    pending = slurm.Job("8", "train", "svc-train", "PENDING", "DependencyNeverSatisfied", "", None, None, "0:0")
    jobs = [slurm.Job("7", "prepare", "svc-train", "FAILED", "None", "c1", None, None, "1:0"), pending]
    monkeypatch.setattr(slurm, "jobs", lambda ids=None: jobs)
    lines = provision.job_lines(["7", "8", "9"])
    assert lines[0] == "- 7 (prepare): FAILED, exit 1:0; output: `ocb logs 7`"
    assert lines[1] == "- 8 (train): PENDING, reason DependencyNeverSatisfied; output: `ocb logs 8`"
    assert "no longer known" in lines[2]
    assert provision.job_lines([]) == ["- none accepted (see the submission output above)"]
