"""The checkpoint watch: copies and hashes every committed checkpoint at first sight, keeps only the newest per
cadence window (and the last), so only decoded checkpoints can count, and bounds what job-controlled files can make
the verifier read or write."""

from __future__ import annotations

import hashlib
import os

from harness.verify import rules
from harness.verify.run import CheckpointWatch, checkpoint_bytes_max


def _commit(root, step, payload=b"shard"):
    d = root / f"step_{step}"
    d.mkdir(parents=True)
    (d / "__0_0.distcp").write_bytes(payload + str(step).encode())
    (d / ".metadata").write_bytes(b"meta")
    return d


def _watch(tmp_path, **kw):
    return CheckpointWatch(tmp_path / "ckpt", **{"every": 100, "steps": 500, **kw})


def test_keeps_only_the_newest_per_window_and_the_last(tmp_path):
    watch = _watch(tmp_path)
    try:
        for step in (50, 100, 150, 200, 210):
            _commit(tmp_path / "ckpt", step)
            watch.poll()
        assert watch.kept == set(watch.hashes) == {100, 200, 210}  # newest of (0, 100] and (100, 200], plus the last
        assert watch.hashes[100]["__0_0.distcp"] == hashlib.sha256(b"shard100").hexdigest()
        assert (watch.store / "100" / "__0_0.distcp").read_bytes() == b"shard100"
        assert not (watch.store / "150").exists() and 150 in watch.done
    finally:
        watch.close()


def test_an_older_checkpoint_in_a_window_cannot_cover_it(tmp_path):
    """A second checkpoint: the older one is forgotten, so only the decoded newest counts."""
    watch = _watch(tmp_path)
    try:
        for step in (99, 100):
            _commit(tmp_path / "ckpt", step)
            watch.poll()
        checked = {s: ("" if s == 99 else "model.head.weight: its data does not decode") for s in watch.kept}
        replicas = {s: dict(h) for s, h in watch.hashes.items()}
        assert not rules.checkpoints_written(checked, replicas, watch.hashes, 100, 1, 100, "/shared/ckpt").ok
    finally:
        watch.close()


def test_job_controlled_files_are_bounded(tmp_path):
    root = tmp_path / "ckpt"
    watch = _watch(tmp_path, max_bytes=1 << 20)
    try:
        d = _commit(root, 100)
        with (d / "sparse.distcp").open("wb") as f:  # costs the job nothing, would cost the verifier 512 MiB
            f.truncate(512 << 20)
        os.mkfifo(d / "fifo.distcp")  # would hang a plain read
        (d / "link.distcp").symlink_to("/dev/zero")
        os.link(d / "__0_0.distcp", tmp_path / "hardlink")
        _commit(root, 200, payload=b"x" * (2 << 20))  # over the step's byte budget
        _commit(root, 900)  # outside the run's steps: never copied
        watch.poll()
        assert watch.hashes[100]["sparse.distcp"] == "" and not (watch.store / "100" / "sparse.distcp").exists()
        assert watch.hashes[100]["__0_0.distcp"] == ""  # hard-linked
        assert "fifo.distcp" not in watch.hashes[100] and "link.distcp" not in watch.hashes[100]
        assert watch.hashes[200]["__0_0.distcp"] == ""
        assert 900 not in watch.kept and 900 in watch.done
    finally:
        watch.close()


def test_the_byte_budget_follows_the_model():
    small = checkpoint_bytes_max({"vocab": 32, "ctx": 64, "d_model": 128, "n_layer": 2, "n_head": 4})
    assert 20 << 20 < small < 40 << 20  # about 5 MB of state, twice over, plus 16 MiB
    assert checkpoint_bytes_max({}) == 1 << 30
