"""The first step a run must cover comes from what the verifier provisioned, not from the job's records."""

from __future__ import annotations

from types import SimpleNamespace

import yaml

from harness.verify import __main__ as verify


def _reference(tmp_path, resume_from):
    job = tmp_path / "tests" / "reference" / "jobs" / "train"
    job.mkdir(parents=True)
    (job / "train.yaml").write_text(yaml.safe_dump({"resume_from": resume_from}))
    return tmp_path / "tests"


def _step(run, n, complete=True):
    d = run / f"step_{n}"
    d.mkdir(parents=True)
    if complete:
        (d / ".metadata").write_bytes(b"m")
        (d / "meta.json").write_text("{}")


def test_resume_tasks_start_after_the_newest_complete_checkpoint(tmp_path, monkeypatch):
    run = tmp_path / "store" / "runs" / "train"
    for n in (100, 700):
        _step(run, n)
    _step(run, 800, complete=False)  # half-written
    (run / "latest").write_text("step_800")
    monkeypatch.setattr(verify, "TESTS", _reference(tmp_path, str(run)))
    assert verify.run_start(SimpleNamespace(store=True, job="train")) == 701


def test_a_step_directory_or_no_store_decides_directly(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "TESTS", _reference(tmp_path, "/shared/ckpt-store/runs/train/step_300"))
    assert verify.run_start(SimpleNamespace(store=True, job="train")) == 301
    assert verify.run_start(SimpleNamespace(store=False, job="train")) == 1
