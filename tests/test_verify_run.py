"""Cleanup stays trustworthy on error paths, and what the verifier reads from the job is bounded."""

from __future__ import annotations

import subprocess

import pytest

from harness.verify import run


def test_node_cleanup_tells_survivors_from_nodes_that_did_not_answer(monkeypatch):
    contacted = []
    monkeypatch.setattr(run.slurm, "nodes", lambda: ["c1", "c2", "c3"])

    def remote(cmd, **kw):
        contacted.append(cmd[-2])
        assert "pgrep" in cmd[-1] and "--runstates" in cmd[-1]
        return subprocess.CompletedProcess(cmd, {"root@c1": 3, "root@c2": 2, "root@c3": 0}[cmd[-2]])

    monkeypatch.setattr(run.slurm, "run", remote)
    survivors, unreachable = run.clean_nodes("svc-train")
    assert survivors == ["processes of svc-train survive on c1"]  # the job's doing
    assert unreachable == ["node c2 did not answer or its cleanup could not be verified"]  # the host's
    assert contacted == ["root@c1", "root@c2", "root@c3"]  # every node is attempted


def test_an_exception_during_the_run_still_stops_the_account(tmp_path, monkeypatch):
    stopped = []

    def fail(*args, **kwargs):
        raise RuntimeError("submission failed")

    monkeypatch.setattr(run, "_run_job", fail)
    monkeypatch.setattr(run, "stop_account", lambda user: stopped.append(user) or ([], []))
    with pytest.raises(RuntimeError, match="submission"):
        run.run_job(object(), "job", "svc-train", tmp_path)  # type: ignore[arg-type]
    assert stopped == ["svc-train"]


def test_job_logs_are_kept_as_a_bounded_head_and_tail_of_regular_files(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    (shared / "logs").mkdir(parents=True)
    (shared / "logs/1.out").write_bytes(b"A" * run.LOGS_KEPT_BYTES + b"B" * run.LOGS_KEPT_BYTES)
    (shared / "logs/2.out").symlink_to("/dev/zero")  # never read
    monkeypatch.setattr(run, "SHARED", shared)
    run.save_job_logs("job", tmp_path / "logs")
    saved = (tmp_path / "logs/job-logs/job/1.out").read_bytes()
    assert len(saved) < run.LOGS_KEPT_BYTES + 100 and saved.startswith(b"AAA") and saved.endswith(b"BBB")
    assert not (tmp_path / "logs/job-logs/job/2.out").exists()


def test_metrics_are_read_from_regular_files_only(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    (shared / "metrics" / "7").mkdir(parents=True)
    (shared / "metrics" / "7" / "rank0.jsonl").write_text('{"step": 1, "loss": 2.0}\n')
    (shared / "metrics" / "7" / "rank1.jsonl").symlink_to("/dev/zero")
    (shared / "metrics" / "8").symlink_to(shared / "metrics" / "7")
    monkeypatch.setattr(run, "SHARED", shared)
    monkeypatch.setattr(run, "EXPORT", tmp_path / "none.safetensors")
    monkeypatch.setattr(run, "SNAPSHOT", tmp_path / "snapshot")
    snap = run.snapshot(["7", "8"])
    assert list(snap.metrics["7"]) == [0] and "8" not in snap.metrics


def test_synchronous_submission_is_observed_before_it_finishes(tmp_path, monkeypatch):
    from contextlib import ExitStack
    from types import SimpleNamespace
    from unittest.mock import patch

    events = []

    class Observer:
        def __enter__(self):
            events.append("observing")

        def __exit__(self, *args):
            events.append("stopped")

        def seal(self):
            pass

    def submit(*args, **kwargs):
        assert events == ["observing"]
        events.append("training finished")  # submit.sh used sbatch --wait
        return ["1"], ""

    job = run.slurm.Job("1", "train", "svc-train", "COMPLETED", "None", "c1,c2", None, None)
    cfg = SimpleNamespace(min_nodes=2, store_refill_s=0, site=None, job="train")
    with ExitStack() as stack:
        for obj, name, value in [
            (run.slurm, "deploy_cluster_config", lambda *a: 0),
            (run.slurm, "run", lambda *a, **k: SimpleNamespace(returncode=0)),
            (run.slurm, "wait_for_cluster", lambda *a, **k: True),
            (run.slurm, "jobs", lambda: []),
            (run.slurm, "submit", submit),
            (run.slurm, "drained_nodes", lambda: {}),
            (run, "protected_settings", lambda: []),
            (run, "reset_run_dirs", lambda *a: None),
            (run, "seal_jobcomp", lambda: None),
            (run, "apply_site", lambda *a: None),
            (run, "kill_local", lambda *a: True),
            (run, "cluster_cpu_usec", lambda: 0),
            (run, "host_cpu", lambda: (0, 1)),
            (run, "stop_account", lambda *a, **k: ([], [])),
            (run, "save_job_logs", lambda *a: None),
            (run, "_poll_until_done", lambda *a: (True, [job], "")),
        ]:
            stack.enter_context(patch.object(obj, name, value))
        assert run._run_job(cfg, "test", "svc-train", tmp_path, Observer()).completed
    assert events == ["observing", "training finished", "stopped"]


def _snapshot_env(tmp_path, monkeypatch, world_files: dict[str, str], export_bytes: int | None = None):
    shared = tmp_path / "shared"
    metrics = shared / "metrics/1"
    metrics.mkdir(parents=True)
    for name, text in world_files.items():
        (metrics / name).write_text(text)
    export = tmp_path / "model.safetensors"
    if export_bytes is not None:
        with export.open("wb") as f:
            f.truncate(export_bytes)
    monkeypatch.setattr(run, "SHARED", shared)
    monkeypatch.setattr(run, "EXPORT", export)
    monkeypatch.setattr(run, "EVAL_EXPORTS", tmp_path / "evals")
    monkeypatch.setattr(run, "SNAPSHOT", tmp_path / "snapshot")
    monkeypatch.setattr(run, "checkpoint_bytes_max", lambda cfg: 1 << 20)
    return export


def test_snapshot_bounds_exports_and_total_metric_bytes(tmp_path, monkeypatch):
    # rank0 fits the per-file bound (23 of 24 bytes); rank1 (25 bytes) does not, whichever the directory lists first
    export = _snapshot_env(tmp_path, monkeypatch, {"rank0.jsonl": '{"step": 1, "loss": 2}\n',
                                                   "rank1.jsonl": '{"step": 1, "loss": 2.5}\n'}, 1 << 30)  # fmt: skip
    monkeypatch.setattr(run, "METRICS_MAX_BYTES", 24)
    snap = run.snapshot(["1"], world=2)
    assert snap.export is None and not (run.SNAPSHOT / "model.safetensors").exists()  # a 1 GiB export: never read
    assert any("export" in e for e in snap.errors) and any("oversized metrics: rank1" in e for e in snap.errors)
    assert list(snap.metrics["1"]) == [0]
    # A sparse export within the budget is a valid file on this filesystem (compressed ones report fewer blocks too):
    # it is copied under the byte bound.
    with export.open("wb") as f:
        f.truncate(1 << 16)
    assert run.snapshot(["1"], world=2).export is not None


def test_snapshot_ignores_files_that_are_not_a_ranks_metrics(tmp_path, monkeypatch):
    _snapshot_env(
        tmp_path,
        monkeypatch,
        {
            "rank0.jsonl": '{"step": 1, "loss": 2}\n',
            "rank1.jsonl": '{"step": 1, "loss": 2}\n',
            "notes.txt": "a job's own file, not a rank's metrics: ignored",
        },
    )
    snap = run.snapshot(["1"], world=8)
    assert sorted(snap.metrics["1"]) == [0, 1] and not any("metric" in e or "notes" in e for e in snap.errors)


def test_snapshot_keeps_one_export_per_cadence_window(tmp_path, monkeypatch):
    exports = tmp_path / "evals"
    exports.mkdir()
    for step in range(1, 11):
        (exports / f"step_{step}.safetensors").write_bytes(b"model")
    monkeypatch.setattr(run, "SHARED", tmp_path / "shared")
    monkeypatch.setattr(run, "EXPORT", tmp_path / "none")
    monkeypatch.setattr(run, "EVAL_EXPORTS", exports)
    monkeypatch.setattr(run, "SNAPSHOT", tmp_path / "snapshot")
    snap = run.snapshot([], steps=10, eval_every=4)
    assert sorted(snap.eval_exports) == [4, 8, 10] and not snap.errors
    (exports / "step_999999999999999999999999999999999999999999999.safetensors").write_bytes(b"bad")
    assert run.snapshot([], steps=10, eval_every=4).errors
