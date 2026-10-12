"""The validation table marks results stale or missing and applies margins only to memory-bound tasks."""

from __future__ import annotations

from bench.spec import by_id
from bench.validation import bootcheck_cell, margins_cell, needs_margins, qa_cell, separation

CURRENT = {"task_digest": "sha256:a", "wrong_fixes": "w", "images": {"r": "1"}}


def _row(verdict="PASS", inputs=CURRENT):
    runs = {"reference": {"reward": 1.0}, "pristine": {"reward": 0.0}, "wrong:a": {"reward": 0.0},
            "wrong:b": {"reward": 1.0 if verdict != "PASS" else 0.0}}  # fmt: skip
    return {"verdict": verdict, "inputs": inputs, "runs": runs}


def test_separation_is_green_only_on_current_inputs():
    assert separation("rank0-eval-desync", _row(), CURRENT) == ("ref pass, broken agent, wrong 2/2", True)
    stale = _row(inputs={**CURRENT, "task_digest": "sha256:b"})
    assert separation("rank0-eval-desync", stale, CURRENT) == ("stale", False)
    assert separation("rank0-eval-desync", None, CURRENT) == ("-", False)
    cell, ok = separation("rank0-eval-desync", _row("FAIL"), CURRENT)
    assert not ok and cell.startswith("FAIL") and "wrong 1/2" in cell


def test_wrong_fixes_count_only_on_a_declared_check_and_shortcuts_apart():
    agent = {"reward": 0.0, "failure": "agent", "complete": 1.0}
    runs = {"reference": {"reward": 1.0, "failure": "none", "complete": 1.0}, "pristine": agent,
            "wrong:delete-eval": {**agent, "failed_checks": ["throughput"]},  # declared: validation logged
            "wrong:no-eval": {**agent, "failed_checks": ["policy"]},
            "wrong:catch-error": {**agent, "failed_checks": ["job completed before deadline"]},
            "wrong:fake-late-metrics": {"reward": 0.0, "failure": "infra"}}  # fmt: skip
    cell, _ = separation("rank0-eval-desync", {"verdict": "PASS", "inputs": CURRENT, "runs": runs}, CURRENT)
    assert "wrong 2/4 (1 contract controls)" in cell


def test_bootcheck_is_stale_when_the_task_changed(monkeypatch):
    import bench.validation as validation
    from bench.bootcheck import probes_hash
    from bench.provenance import image_tags, task_digest
    from bench.spec import task_dir

    # fixed image ids, so the test does not depend on which images this host has built (a fresh run host has none)
    fake = {ref: f"sha256:{i:064x}" for i, ref in enumerate(image_tags().values())}
    monkeypatch.setattr(validation, "image_ids", lambda: fake)
    row = {"ok": True, "agent_env_ok": "3/3", "verifier_env_ok": True, "probes_hash": probes_hash("rank0-eval-desync"),
           "task_digest": task_digest(task_dir("rank0-eval-desync")), "stamp": {"images": fake}}  # fmt: skip
    assert bootcheck_cell("rank0-eval-desync", row) == ("agent 3/3", True)
    assert bootcheck_cell("rank0-eval-desync", {**row, "task_digest": "sha256:old"}) == ("stale", False)
    assert bootcheck_cell("rank0-eval-desync", {**row, "probes_hash": "old"}) == ("stale", False)  # probes changed
    assert bootcheck_cell("rank0-eval-desync", {**row, "ok": False, "agent_env_ok": "2/3"})[1] is False
    assert bootcheck_cell("rank0-eval-desync", None) == ("-", False)


def test_qa_counts_only_release_mode():
    checks = [{"check": "oracle 10/10", "ok": True}, {"check": "nop 3/3 score 0", "ok": True}]
    rec = {"mode": "release", "pass": True, "inputs": CURRENT, "checks": checks}
    assert qa_cell(rec, CURRENT) == ("oracle 10/10, nop 3/3", True)
    assert qa_cell({**rec, "mode": "dev"}, CURRENT) == ("-", False)


def test_margins_apply_to_memory_bound_tasks_only():
    assert needs_margins(by_id("consolidated-copy-oom")) and needs_margins(by_id("activation-oom"))
    assert not needs_margins(by_id("degraded-node"))
    assert margins_cell(by_id("degraded-node"), None) == ("n/a", True)
    assert margins_cell(by_id("activation-oom"), None) == ("-", False)


def test_loss_margins_count_in_nats_and_ratios_relatively():
    from bench.validation import margins_text, miss, slack

    spec = by_id("degraded-node")  # loss_max 1.545, ratio_min set
    ratio_min = spec.verify.throughput.ratio_min
    ref = {"reward": 1.0, "loss": 1.500, "tput_ratio": ratio_min * 1.3}
    assert slack(spec, ref)[1] == "loss 0.045 nats"  # 0.045 / 0.036 = 1.25 thin units, tput 30% = 3 units
    near = {"reward": 0.0, "completed": 1.0, "loss": 1.560, "tput_ratio": ratio_min * 1.2}
    far = {"reward": 0.0, "completed": 1.0, "loss": 1.50, "tput_ratio": ratio_min * 0.5}
    assert miss(spec, near)[1] == "loss 0.015 nats" and miss(spec, near)[0] < 1
    assert miss(spec, far)[1] == "tput 50%"
    assert miss(spec, {"reward": 0.0, "completed": 0.0}) == (float("inf"), "decisive")
    assert miss(spec, ref) is None
    text, thin = margins_text(spec, {"runs": {"reference": ref, "pristine": far, "wrong:x": near}})
    assert thin == ["wrong:x"] and "closest miss loss 0.015 nats" in text


def test_a_task_with_only_contract_shortcuts_is_not_green():
    agent = {"reward": 0.0, "failure": "agent", "complete": 1.0}
    runs = {"reference": {"reward": 1.0, "failure": "none", "complete": 1.0}, "pristine": agent,
            "wrong:no-eval": {**agent, "failed_checks": ["policy"]}}  # fmt: skip
    cell, ok = separation("rank0-eval-desync", {"verdict": "PASS", "inputs": CURRENT, "runs": runs}, CURRENT)
    assert not ok and "no runtime negative control" in cell


def test_a_contract_control_does_not_count_as_runtime_coverage():
    from bench.sweep import contract_control

    assert contract_control("rank0-only-checkpoint", "wrong:torch-save-rank0")
    assert not contract_control("rank0-only-checkpoint", "wrong:barrier-others")
    agent = {"reward": 0.0, "failure": "agent", "complete": 1.0}
    runs = {"reference": {"reward": 1.0, "failure": "none", "complete": 1.0}, "pristine": agent,
            "wrong:torch-save-rank0": {**agent, "failed_checks": ["checkpoints written"]}}  # fmt: skip
    cell, ok = separation("rank0-only-checkpoint", {"verdict": "PASS", "inputs": CURRENT, "runs": runs}, CURRENT)
    assert not ok and "no runtime negative control" in cell


def test_memory_margins_require_current_experiment_inputs_and_required_factor(monkeypatch):
    from bench import sweep
    from bench.margins import node_limits

    spec = by_id("activation-oom")
    current = {**CURRENT, "accepted_fixes": "fixes"}
    monkeypatch.setattr(sweep, "inputs", lambda task: current)
    record = {"inputs": current, "factor": 1.15, "limits_mib": node_limits(spec.id), "verdict": "PASS"}
    assert margins_cell(spec, record)[1]
    for changed in ({"images": {"r": "old"}}, {"accepted_fixes": "old"}):
        assert margins_cell(spec, {**record, "inputs": {**current, **changed}}) == ("stale", False)
    assert not margins_cell(spec, {**record, "factor": 0.5})[1]
    assert not margins_cell(spec, {**record, "factor": float("nan")})[1]
    assert not margins_cell(spec, {**record, "inputs": None})[1]


def test_a_task_qualifies_on_its_release_qa_and_a_declared_runtime_control(monkeypatch):
    """The release QA on the scoring host class qualifies a task; the development box's
    bootcheck, sweep and margins are reported beside it and do not decide green."""
    from bench import validation
    from bench.patches import wrong_fix_patches

    spec = by_id("rank0-only-checkpoint")
    assert validation.runtime_controls(spec.id, wrong_fix_patches(spec)) == ["barrier-others"]
    assert validation.runtime_controls(spec.id, ["torch-save-rank0"]) == []  # a contract control alone is not enough
    current = {"task_digest": "x"}
    monkeypatch.setattr(validation, "load_specs", lambda: [spec])
    monkeypatch.setattr(validation.sweep, "inputs", lambda task: current)
    monkeypatch.setattr(validation.sweep, "load_table", lambda: {"tasks": {}})
    record = {"mode": "release", "inputs": current, "pass": True, "checks": [{"check": "oracle 10/10", "ok": True}]}
    monkeypatch.setattr(validation, "_load", lambda path: record if path.parent.name == "qa" else None)
    row = validation.build()[spec.id]
    assert row["green"] and not row["supplementary_ok"] and row["separation"] == "-"
    record["checks"][0]["ok"] = False  # a failed trial row
    assert not validation.build()[spec.id]["green"]


def test_calibration_margin_rows_are_reported_not_decisive():
    current = {"task_digest": "x"}
    checks = [
        {"check": "oracle 10/10", "ok": True},
        {"check": "nop 3/3 score 0", "ok": True},
        {"check": "loss threshold calibrated", "ok": False},
        {"check": "[bundle] every image pinned", "ok": False},
    ]
    record = {"mode": "release", "inputs": current, "pass": False, "checks": checks}
    cell, ok = qa_cell(record, current)
    assert ok and "loss margin under 3 spreads (reported)" in cell
    record["checks"] = [*checks, {"check": "wrong fix 'a' scores 0", "ok": False}]
    assert not qa_cell(record, current)[1]  # a trial row still decides
