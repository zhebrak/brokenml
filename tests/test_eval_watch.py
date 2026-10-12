"""Eval exports count only when written during training: the watch records order and rewrites, the check rejects
the final model's weights."""

from __future__ import annotations

import time

from harness.verify.run import EvalExportWatch, Snapshot


def test_watch_records_whether_the_final_export_existed_first(tmp_path):
    evals, final = tmp_path / "eval", tmp_path / "model.safetensors"
    evals.mkdir()
    watch = EvalExportWatch(evals, final)
    (evals / "step_10.safetensors").write_bytes(b"w10")
    watch.poll()
    final.write_bytes(b"final")
    (evals / "step_20.safetensors").write_bytes(b"w20")
    watch.poll()
    assert watch.after_final == {10: False, 20: True}


def test_mid_run_only_rejects_late_unseen_and_rewritten_exports(tmp_path):
    from harness.verify.__main__ import mid_run_only

    evals, final = tmp_path / "eval", tmp_path / "model.safetensors"
    evals.mkdir()
    watch = EvalExportWatch(evals, final)
    for step in (5, 10):
        (evals / f"step_{step}.safetensors").write_bytes(b"w%d" % step)
    watch.poll()
    final.write_bytes(b"final")
    time.sleep(0.05)  # coarse ctime clocks: the rewrite must land in a later tick
    (evals / "step_10.safetensors").write_bytes(b"fin")  # same size, written over after the run
    (evals / "step_15.safetensors").write_bytes(b"w15")
    watch.poll()
    snap = Snapshot(final, {}, {s: evals / f"step_{s}.safetensors" for s in (5, 10, 15, 20, 25)})
    out = mid_run_only({s: "" for s in snap.eval_exports}, snap, watch, steps=25)
    assert out[5] == "" and out[25] == ""
    assert out[10] == "changed after training ended"
    assert out[15] == "written after training ended" and out[20] == "not seen during the run"


def test_removing_the_final_export_does_not_reopen_the_window(tmp_path):
    evals, final = tmp_path / "eval", tmp_path / "model.safetensors"
    evals.mkdir()
    watch = EvalExportWatch(evals, final)
    (evals / "step_10.safetensors").write_bytes(b"w10")
    watch.poll()
    final.write_bytes(b"final")
    watch.poll()
    final.unlink()
    time.sleep(0.05)
    (evals / "step_10.safetensors").write_bytes(b"fin")
    watch.poll()  # the final export is gone, but it was seen: nothing is recorded any more
    assert watch.rewritten(10)


def test_the_verifiers_own_chown_after_the_run_is_not_a_rewrite(tmp_path):
    import os

    evals, final = tmp_path / "eval", tmp_path / "model.safetensors"
    evals.mkdir()
    watch = EvalExportWatch(evals, final)
    (evals / "step_10.safetensors").write_bytes(b"w10")
    (evals / "step_20.safetensors").write_bytes(b"w20")
    watch.poll()
    final.write_bytes(b"final")
    time.sleep(0.05)
    (evals / "step_20.safetensors").write_bytes(b"fin")  # the job rewrites one after the run, before it is stopped
    watch.poll()
    watch.seal()  # stop_account: processes gone, before the run directories become root's
    time.sleep(0.05)
    for f in evals.iterdir():
        os.chmod(f, 0o444)  # what the verifier's chown does to every ctime
    assert not watch.rewritten(10) and watch.rewritten(20)


def test_export_watch_bounds_step_keys_during_observation_and_sealing(tmp_path):
    evals = tmp_path / "eval"
    evals.mkdir()
    for step in ("1", "2", "999999999999999999999999999999999999999999999999999", "03"):
        (evals / f"step_{step}.safetensors").write_bytes(b"weights")
    watch = EvalExportWatch(evals, tmp_path / "final", steps=3)
    watch.poll()
    watch.seal()
    assert set(watch.after_final) <= {1, 2}
    assert set(watch.sealed) <= {1, 2}
