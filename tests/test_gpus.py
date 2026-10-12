"""The verifier's GPU gates, from recorded nvidia-smi output (no GPU needed)."""

from __future__ import annotations

from harness.verify import gpus

IDLE = """GPU-aaa, NVIDIA A100-SXM4-80GB, 81920, 65000, 16384, Default, Enabled, 400.00, 1410, Disabled
GPU-bbb, NVIDIA A100-SXM4-80GB, 81920, 65000, 16384, Default, Enabled, 400.00, 1410, Disabled"""


def test_parse_and_class():
    g = gpus.parse(IDLE)
    assert [x.uuid for x in g] == ["GPU-aaa", "GPU-bbb"] and g[0].free_mb == 16384
    assert gpus.class_problem(g, "NVIDIA A100-SXM4-80GB/NV12/r580") == ""
    assert "calibrated on" in gpus.class_problem(g, "NVIDIA H100 80GB HBM3/NV18/r580")
    assert "1 GPUs visible" in gpus.class_problem(g[:1], None)


def test_budget_gate():
    g = gpus.parse(IDLE)
    assert gpus.budget_problem(g, 16384) == ""
    held = gpus.parse(IDLE.replace("65000, 16384", "70000, 11384", 1))
    assert "GPU-aaa" in gpus.budget_problem(held, 16384)
    no_ballast = gpus.parse(IDLE.replace("65000, 16384", "500, 80884", 1))  # the ballast has not taken its share yet
    assert "GPU-aaa" in gpus.budget_problem(no_ballast, 16384)


def test_persistent_settings_left_behind_are_detected():
    before = gpus.parse(IDLE)
    after = gpus.parse(IDLE.replace("Default, Enabled, 400.00", "Exclusive_Process, Enabled, 250.00", 1))
    assert gpus.changed(before, after) == ["GPU-aaa compute_mode: Default -> Exclusive_Process",
                                           "GPU-aaa power_limit: 400.00 -> 250.00"]  # fmt: skip
    assert gpus.changed(before, before) == []


def test_busy_gpus_are_those_above_their_idle_memory():
    idle = {g.uuid: g.used_mb for g in gpus.parse(IDLE)}
    running = gpus.parse(IDLE.replace("65000, 16384", "75000, 6384", 1))
    assert gpus.busy(running, idle) == {"GPU-aaa"}
