"""An inconclusive verification never contaminates the next calibration run: its cluster is discarded."""

from __future__ import annotations

from contextlib import contextmanager

from bench import calibrate


def test_an_inconclusive_run_discards_the_cluster_before_the_next_variant(tmp_path, monkeypatch):
    task = tmp_path / "task"
    (task / "tests").mkdir(parents=True)
    (task / "tests/verify.yaml").write_text("deadline_s: 10\n")
    monkeypatch.setattr(calibrate, "RUNS", tmp_path)
    monkeypatch.setattr(calibrate, "task_dir", lambda _: task)
    monkeypatch.setattr(calibrate, "task_digest", lambda _: "digest")
    monkeypatch.setattr(calibrate, "stamp", lambda: {})
    lifecycle: list[tuple[str, str]] = []

    @contextmanager
    def cluster(task_id, policy_skip=True, throughput=False):
        name = str(len(lifecycle))
        lifecycle.append(("start", name))
        yield name
        lifecycle.append(("stop", name))

    calls: list[str] = []

    def once(main, tree, timeout, logs=None):
        calls.append(main)
        first = len(calls) == 1
        return ({"reward": 0.0, "failure": "verifier_bug", "complete": 0.0} if first
                else {"reward": 1.0, "failure": "none", "complete": 1.0}), ""  # fmt: skip

    monkeypatch.setattr(calibrate, "verifier_cluster", cluster)
    monkeypatch.setattr(calibrate, "run_once", once)
    results = calibrate.run_variants("task", {"first": task, "second": task}, 1, None)
    # the inconclusive run is retried once on a fresh cluster; the next variant reuses that cluster once it concluded
    assert calls == ["0", "2", "2"]
    assert lifecycle == [("start", "0"), ("stop", "0"), ("start", "2"), ("stop", "2")]
    assert results["first"][0]["reward"] == 1.0 and len(results["first"]) == 1  # the retry's record, not the first
