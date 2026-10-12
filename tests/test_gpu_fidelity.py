"""The GPU fidelity runners assemble every supported task from the current template, build each node's environment the
way TaskProlog does, and (torch-marked) run a real two-rank Gloo job and the healthy control on CPU."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from bench.paths import ROOT

HERE = ROOT / "experiments/gpu_fidelity"
sys.path.insert(0, str(HERE))
module_spec = importlib.util.spec_from_file_location("gpu_jobs", HERE / "jobs.py")
assert module_spec is not None and module_spec.loader is not None
jobs = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(jobs)


@pytest.mark.parametrize("task", sorted(jobs.SUPPORTED))
@pytest.mark.parametrize("variant", ["broken", "fixed"])
def test_supported_tasks_assemble_and_port_the_current_trainer(tmp_path, task, variant):
    jobs.validate(task, 2)
    ops = jobs.assemble(task, variant, tmp_path)
    cfg = jobs.config(ops)
    assert cfg["steps"] > 0
    jobs.port(ops)
    assert "OCB_BACKEND" in (ops / "src/trainer/dist.py").read_text()
    assert "torch.get_default_device()" in (ops / "src/trainer/evaluation.py").read_text()


def test_unsupported_tasks_and_insufficient_world_size_are_refused(monkeypatch):
    with pytest.raises(ValueError, match="unsupported"):
        jobs.validate("checkpoint-every-step", 2)
    with pytest.raises(ValueError, match="at least 2"):
        jobs.validate("subgroup-skip-deadlock", 1)
    monkeypatch.setitem(jobs.SUPPORTED, "stale-hosts-entry", 1)  # listed, but its fault is host state
    with pytest.raises(ValueError, match="host, exporter or NCCL state"):
        jobs.validate("stale-hosts-entry", 1)


@pytest.mark.parametrize(
    ("task", "variable"),
    [
        ("hash-ordered-buckets", "PYTHONHASHSEED"),
        ("subgroup-skip-deadlock", "REPORT_THROUGHPUT"),
        ("node-thread-oversubscription", "OMP_NUM_THREADS"),
    ],
)
def test_node_scoped_faults_live_in_the_site_env_and_differ_between_nodes(tmp_path, task, variable):
    from bench.spec import by_id

    spec = by_id(task)
    ops = jobs.assemble(task, "broken", tmp_path)
    c1, c2 = jobs.node_env(ops, "c1", spec), jobs.node_env(ops, "c2", spec)
    assert c1["LC_ALL"] == c2["LC_ALL"] == "C.UTF-8"  # the site's job.env comes first on every node
    assert c1[variable] != c2[variable], (c1, c2)  # the broken job's node asymmetry survives the port


def test_gather_report_counts_corrupt_elements_without_asserting():
    torch = pytest.importorskip("torch")
    spec = importlib.util.spec_from_file_location("gpu_scenarios", HERE / "scenarios.py")
    assert spec is not None and spec.loader is not None
    scenarios = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scenarios)
    good = [torch.full((128,), 1.0), torch.full((127,), 2.0)]
    assert scenarios.gather_report(good, [128, 127]) == {
        "shapes": [[128], [127]], "expected_lengths": [128, 127], "corrupt_elements": 0, "outputs_valid": True,
    }  # fmt: skip
    # Buffers sized like the receiver's own slice (the task's bug): rank 1's view lacks one element of rank 0's slice
    # and its own slot still holds the NaN sentinel where nothing arrived.
    as_rank1 = [torch.full((127,), 1.0), torch.cat([torch.full((126,), 2.0), torch.tensor([float("nan")])])]
    report = scenarios.gather_report(as_rank1, [128, 127])
    assert not report["outputs_valid"] and report["corrupt_elements"] == 2


def test_gpu_visibility_uses_the_inherited_mask_and_real_uuids(monkeypatch):
    from types import SimpleNamespace

    import common

    fake_cuda = SimpleNamespace(
        device_count=lambda: 2, get_device_properties=lambda i: SimpleNamespace(uuid=f"GPU-{i}")
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=fake_cuda))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "4,7")
    assert common.visible_devices(2) == (["4", "7"], ["GPU-0", "GPU-1"])
    with pytest.raises(ValueError, match="need 4"):
        common.visible_devices(4)


def test_rows_never_carry_non_finite_numbers():
    import common

    assert common.finite({"loss": float("nan"), "x": [1.0, float("inf")], "ok": 2.5}) == {
        "loss": None, "x": [1.0, None], "ok": 2.5,
    }  # fmt: skip


@pytest.mark.torch
def test_distributed_runner_cpu_smoke(tmp_path):
    pytest.importorskip("torch")
    row = jobs.run(
        "rank0-eval-desync",
        "fixed",
        1,
        120,
        {"steps": 2, "eval_every": 1, "train_seqs": 128, "val_seqs": 16},
        tmp_path,
        backend="gloo",
    )
    assert row["status"] == "completed", row
    assert row["steps"] == 2 and row["evaluation"]["loss"] > 0
    assert (Path(row["run_dir"]) / "manifest.json").exists()


@pytest.mark.torch
def test_healthy_control_and_gather_report_on_gloo(tmp_path):
    pytest.importorskip("torch")
    spec = importlib.util.spec_from_file_location("gpu_scenarios_runner", HERE / "run.py")
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    row = runner.run("healthy_control", "gloo", 90, tmp_path)
    assert row["status"] == "completed", row
    assert Path(row["log"]).read_text().count("healthy control passed") == 2
    gather = runner.run("uneven_all_gather", "gloo", 90, tmp_path)
    # Gloo: the rank whose buffer is too small aborts with the size mismatch. Whether rank 0's own gather returns
    # first (with part of the shorter slice missing: 64 of 127 elements in a measured run) or is torn down before it
    # reports is a race; the row records whichever happened, and never a valid output.
    assert gather["status"] == "failed" and gather["collective_mismatch_reported"]
    assert gather.get("outputs_valid") is not True
    if "outputs_valid" in gather:
        assert gather["corrupt_elements"] > 0


def test_device_locks_use_canonical_order_without_changing_cuda_mapping(tmp_path, monkeypatch):
    import common

    monkeypatch.setattr(common, "visible_devices", lambda n: (["7", "4"], ["GPU-7", "GPU-4"]))
    monkeypatch.setattr(common.tempfile, "gettempdir", lambda: str(tmp_path))
    acquired = []
    monkeypatch.setattr(common.fcntl, "flock", lambda stream, flags: acquired.append(Path(stream.name).name))
    with common.devices("nccl", 2) as (tokens, uuids):
        assert tokens == ["7", "4"] and uuids == ["GPU-7", "GPU-4"]
    assert acquired == ["gpu4.lock", "gpu7.lock", "bench-gpu-GPU-4.lock", "bench-gpu-GPU-7.lock"]
