"""bench regrade --replay: a scratch copy of the task grades on the seeds the verdict recorded."""

from __future__ import annotations

import json

import yaml

from bench.regrade import recorded_seeds, replay_task
from harness.config import VerifyConfig


def test_replay_copies_the_task_with_the_recorded_seeds(tmp_path):
    trial = tmp_path / "trial"
    (trial / "verifier").mkdir(parents=True)
    (trial / "verifier" / "diagnostics.json").write_text(json.dumps({"teacher_seed": 9.0, "heldout_seed": 7.0}))
    seeds = recorded_seeds(trial)
    assert seeds == {"teacher_seed": 9, "heldout_seed": 7}
    root = replay_task("rank0-eval-desync", seeds, tmp_path / "scratch")
    cfg = VerifyConfig.model_validate(yaml.safe_load((root / "rank0-eval-desync/tests/verify.yaml").read_text()))
    assert cfg.replay is not None and cfg.replay.heldout_seed == 7
    assert recorded_seeds(tmp_path) is None


def test_a_plain_regrade_grades_the_snapshot_the_agent_faced(tmp_path):
    import shutil

    import pytest

    from bench.provenance import task_digest
    from bench.regrade import snapshot
    from bench.spec import task_dir

    snap = tmp_path / "build" / "rank0-eval-desync"
    shutil.copytree(task_dir("rank0-eval-desync"), snap)
    trial = tmp_path / "trial"
    trial.mkdir()
    (trial / "lock.json").write_text(json.dumps({"task": {"path": str(snap), "digest": task_digest(snap)}}))
    assert snapshot(trial) == snap
    (snap / "tests" / "verify.yaml").write_text((snap / "tests" / "verify.yaml").read_text() + "\n# edited\n")
    with pytest.raises(ValueError, match="changed since the trial ran"):
        snapshot(trial)
    shutil.rmtree(snap)
    with pytest.raises(ValueError, match="is gone"):
        snapshot(trial)


def test_a_patched_runtime_copy_swaps_only_the_runtime_image_and_its_expected_version(tmp_path):
    """Deviation ag: in the copy, only the services that run the runtime image change (their image and the version
    their nodes expect); harness sidecars keep expecting the study runtime, comments and tests/images.lock stay."""
    import pytest

    from bench.provenance import task_digest
    from bench.regrade import patched_snapshot, register

    snap = tmp_path / "snap"
    (snap / "tests").mkdir(parents=True)
    (snap / "environment").mkdir()
    grading = (
        "# benchmark-canary GUID x\nservices:\n  c1:\n    image: bench/runtime:dev\n    environment:\n"
        "      OCB_EXPECT_RUNTIME: aaaa\n  provision:\n    build: .\n    environment:\n      OCB_EXPECT_RUNTIME: aaaa\n"
        "  objstore:\n    image: bench/harness:dev\nvolumes:\n  ops: {}\n"
    )
    (snap / "tests" / "docker-compose.yaml").write_text(grading)
    (snap / "tests" / "images.lock").write_text("harness bench/harness:dev hhhh\nruntime bench/runtime:dev aaaa\n")
    (snap / "environment" / "docker-compose.yaml").write_text("services:\n  c1:\n    image: bench/runtime:dev\n")
    (snap / "environment" / "images.lock").write_text(
        "harness bench/harness:dev hhhh\nruntime bench/runtime:dev aaaa\n"
    )
    (snap / "task.toml").write_text("[task]\n")
    dst = patched_snapshot(snap, "bench/runtime:fix1", "bbbb", "aaaa", tmp_path / "out" / "snap")
    node = "    image: bench/runtime:{}\n    environment:\n      OCB_EXPECT_RUNTIME: {}\n"
    want = grading.replace(node.format("dev", "aaaa"), node.format("fix1", "bbbb"), 1)
    assert (dst / "tests" / "docker-compose.yaml").read_text() == want
    assert want.count("OCB_EXPECT_RUNTIME: aaaa") == 1  # the sidecar's expectation is left as it was
    assert (dst / "tests" / "images.lock").read_text() == (snap / "tests" / "images.lock").read_text()
    assert (dst / "environment" / "images.lock").read_text() == (
        "harness bench/harness:dev hhhh\nruntime bench/runtime:fix1 bbbb\n"
    )
    assert (dst / "task.toml").read_text() == "[task]\n" and task_digest(dst) != task_digest(snap)
    with pytest.raises(ValueError, match="rendered against runtime aaaa, not cccc"):
        patched_snapshot(snap, "bench/runtime:fix1", "bbbb", "cccc", tmp_path / "out2" / "snap")
    reg = tmp_path / "patched-gradings.json"
    trial = tmp_path / "job" / "t__a"
    register(trial, {"id": "id-a", "task_name": "brokenml/t1"}, {"original_digest": "d1", "patched_digest": "d2"}, reg)
    register(trial, {"id": "id-b", "task_name": "brokenml/t2"}, {"original_digest": "d3", "patched_digest": "d4"}, reg)
    trials = json.loads(reg.read_text())["trials"]
    assert trials["id-a"] == {
        "job": "job",
        "trial": "t__a",
        "task": "t1",
        "original_digest": "d1",
        "patched_digest": "d2",
    }
    assert set(trials) == {"id-a", "id-b"}
