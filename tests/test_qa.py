import json

import pytest

from bench import qa
from bench.spec import load_specs, task_dir


def record(**runs):
    kinds = {k: ("shortcut" if k.startswith("short") else "legitimate") for k in runs}
    return {
        "set": "c",
        "kinds": kinds,
        "results": {
            k: [{"loss": x, "reward": 1.0, "failure": "none", "complete": 1.0} for x in v] for k, v in runs.items()
        },
    }


def test_two_sided_window():
    assert qa.loss_window({"loss_max": 1.545}, record(reference=[1.50, 1.505, 1.502], short_half=[1.60]))[1]


def test_bound_too_close_to_shortcut_fails():
    assert not qa.loss_window({"loss_max": 1.59}, record(reference=[1.50, 1.505, 1.502], short_half=[1.60]))[1]


def test_lower_bound_only_needs_throughput_gate():
    rec = record(reference=[1.44, 1.45, 1.445])
    assert qa.loss_window({"loss_max": 1.55, "throughput": {"ratio_min": 0.67}}, rec)[1]
    assert not qa.loss_window({"loss_max": 1.55}, rec)[1]


def test_too_few_legitimate_runs_cannot_calibrate():
    assert not qa.loss_window({"loss_max": 1.545}, record(reference=[1.50], short_half=[1.60]))[1]


def test_a_must_fail_variant_needs_no_margin_but_every_run_must_miss_the_bound():
    rec = record(reference=[1.50, 1.505, 1.502], short_half=[1.60, 1.61, 1.60], short_80=[1.554, 1.5625, 1.5605])
    rec["kinds"]["short_80"] = "must-fail"
    ok, detail = qa.loss_window({"loss_max": 1.545}, rec)[1:]
    assert ok and "must fail short_80 >= 1.5540" in detail  # 3 spreads to the 50% shortcut; the 80% run only misses
    rec["results"]["short_80"][0]["loss"] = 1.544  # one 80% run under the bound: not rejected
    ok, detail = qa.loss_window({"loss_max": 1.545}, rec)[1:]
    assert not ok and "NOT REJECTED" in detail


def test_infra_errors_and_harbor_errors_never_count_as_a_score():
    ok = {"error": None, "infra": False, "reward": 0.0}
    assert qa.scored(ok, 0.0)
    assert not qa.scored({**ok, "infra": True}, 0.0)  # e.g. the reference run failed on a throughput task
    assert not qa.scored({**ok, "error": "VerifierTimeoutError", "reward": None}, 0.0)


@pytest.mark.parametrize("spec", load_specs(), ids=lambda s: s.id)
def test_static_and_isolation_checks_pass_on_every_rendered_task(spec):
    failing = [(name, detail) for name, ok, detail in qa.static_checks(task_dir(spec))
               if not ok and not name.startswith(("[release]", "[bundle]"))]  # fmt: skip
    assert not failing


def test_a_zero_counts_for_nop_only_when_the_job_itself_failed():
    base = {"reward": 0.0, "error": None, "infra": False}
    assert qa.scored({**base, "rewards": {"failure": "agent", "complete": 1.0}}, 0.0)
    assert not qa.scored({**base, "rewards": {"failure": "verifier_bug", "complete": 1.0}}, 0.0)
    assert not qa.scored({**base, "rewards": {"failure": "agent", "complete": 0.0}}, 0.0)  # killed mid-grading
    assert qa.scored({"reward": 1.0, "error": None, "infra": False, "rewards": {"failure": "none"}}, 1.0)


def test_throughput_window_needs_conclusive_legitimate_runs_and_a_margin():
    rec = {"set": "perf", "kinds": {"reference": "legitimate"},
           "results": {"reference": [{"reward": 1.0, "failure": "none", "complete": 1.0, "tput_ratio": r}
                                     for r in (0.97, 0.98, 0.99)]}}  # fmt: skip
    assert qa.throughput_window({"throughput": {"ratio_min": 0.67}}, rec)[1]
    assert not qa.throughput_window({"throughput": {"ratio_min": 0.96}}, rec)[1]  # within 3 noise units of the slowest
    # a deliberately slower legitimate configuration widens the across-variant spread, not the noise unit
    rec["kinds"]["fsdp"] = "legitimate"
    rec["results"]["fsdp"] = [{"reward": 1.0, "failure": "none", "complete": 1.0, "tput_ratio": r}
                              for r in (0.78, 0.80, 0.79)]  # fmt: skip
    ok, detail = qa.throughput_window({"throughput": {"ratio_min": 0.67}}, rec)[1:]
    assert ok and "noise 0.020" in detail  # hi = 0.78 - 3 x 0.02 = 0.72
    assert not qa.throughput_window({"throughput": {"ratio_min": 0.75}}, rec)[1]
    rec["results"]["reference"][0]["failure"] = "verifier_bug"
    ok, detail = qa.throughput_window({"throughput": {"ratio_min": 0.67}}, rec)[1:]
    assert not ok and "inconclusive" in detail
    two = {**rec, "kinds": {"reference": "legitimate"}, "results": {"reference": rec["results"]["reference"][1:]}}
    assert "need at least 3" in qa.throughput_window({"throughput": {"ratio_min": 0.67}}, two)[2]
    short = {**rec, "kinds": {"reference": "legitimate", "short-half-steps": "shortcut"},
             "results": {**rec["results"], "short-half-steps": [{"reward": 0.0, "failure": "agent", "complete": 1.0,
                                                                  "tput_ratio": 0.9}]}}  # fmt: skip
    short["results"]["reference"][0]["failure"] = "none"
    assert not qa.throughput_window({"throughput": {"ratio_min": 0.67}}, short)[1]  # a shortcut at 0.9 is too close


def test_the_release_gate_cannot_be_run_with_fewer_trials_than_it_requires():
    with pytest.raises(SystemExit) as exc:
        qa.main(["dev-pending", "--release", "--oracle", "2"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        qa.main(["dev-pending", "--release", "--no-wrong"])
    assert exc.value.code == 2


@pytest.mark.parametrize("change", ["bug", "incomplete", "missing", "undersampled", "infinite", "huge"])
def test_loss_calibration_needs_every_variant_and_conclusive_finite_measurements(change):
    rec = record(reference=[1.50, 1.505, 1.502], legitimate_alt=[1.50, 1.505, 1.502], short_half=[1.60])
    first = rec["results"]["reference"][0]
    if change == "bug":
        first.update(reward=0, failure="verifier_bug")
    elif change == "incomplete":
        first["complete"] = 0
    elif change == "missing":
        del rec["results"]["short_half"]
    elif change == "undersampled":
        rec["results"]["legitimate_alt"] = rec["results"]["legitimate_alt"][:1]
    else:
        first["loss"] = float("inf") if change == "infinite" else 10**400
    assert not qa.loss_window({"loss_max": 1.545}, rec)[1]


def test_cpu_calibration_does_not_require_unrelated_cuda_image(tmp_path, monkeypatch):
    import json

    from bench.provenance import task_image_refs

    rec = record(reference=[1.50, 1.505, 1.502], short_half=[1.60])
    required = {ref: "build-1" for ref in task_image_refs(task_dir("dev-pending")).values()}
    rec.update(task="dev-pending", task_digest="digest", inputs="variants", stamp={"images": required})
    folder = tmp_path / "calibration"
    folder.mkdir()
    (folder / "cpu.json").write_text(json.dumps(rec))
    monkeypatch.setattr(qa, "RESULTS", tmp_path)
    monkeypatch.setattr(qa, "image_ids", lambda: {**required, "bench/runtime-cuda:dev": ""})
    monkeypatch.setattr(qa, "task_digest", lambda task: "digest")
    monkeypatch.setattr(qa, "set_inputs", lambda name: "variants")
    monkeypatch.setattr(qa, "set_kinds", lambda name: rec["kinds"])
    monkeypatch.setattr(qa, "set_declaration", lambda name: None)
    assert all(ok for _, ok, _ in qa._calibration_set({"loss_max": 1.545}, "cpu", "loss"))
    required[next(iter(required))] = "different-build"
    assert not qa._calibration_set({"loss_max": 1.545}, "cpu", "loss")[-1][1]


def test_a_set_without_shortcuts_needs_a_throughput_gate_or_a_declared_rejecting_rule():
    rec = record(reference=[1.3987, 1.3993, 1.3995])
    rec["kinds"]["half"] = "probe"
    rec["results"]["half"] = [{"loss": x, "reward": 0.0, "failure": "agent", "complete": 1.0} for x in (1.4056, 1.4065)]
    assert not qa.loss_window({"loss_max": 1.42}, rec)[1]  # no shortcut run, no gate: nothing bounds the limit
    ok, detail = qa.loss_window({"loss_max": 1.42}, rec, "require_step_coverage")[1:]
    assert ok and "shortcuts rejected by require_step_coverage" in detail
    assert "probe half 1.4056-1.4065 (not rejected by loss_max)" in detail  # measured and reported, not a gate
    assert not qa.loss_window({"loss_max": 1.399}, rec, "require_step_coverage")[1]  # still must clear legit runs


def _regrade_env(tmp_path, monkeypatch, calibrated: bool, inputs: dict):
    monkeypatch.setattr(qa, "RESULTS", tmp_path)
    monkeypatch.setattr(qa, "task_dir", lambda name: tmp_path / name)
    monkeypatch.setattr(qa, "by_id", lambda name: None)
    monkeypatch.setattr(qa, "static_checks", lambda task: [("canary in task files", True, "")])
    monkeypatch.setattr(qa, "calibration_checks",
                        lambda task: [("[release] loss threshold calibrated", calibrated, "")])  # fmt: skip
    monkeypatch.setattr(qa.sweep, "inputs", lambda task: inputs)

    def no_trials(*a, **k):
        raise AssertionError("a regrade runs no trial")

    monkeypatch.setattr(qa, "harbor", no_trials)


def test_regrade_reuses_the_trial_rows_and_re_evaluates_calibration(tmp_path, monkeypatch):
    inputs = {"task_digest": "t", "wrong_fixes": "w", "images": {"x": "1"}}
    (tmp_path / "qa").mkdir()
    old = {"task": "demo", "mode": "release", "pass": False, "inputs": inputs, "stamp": {"utc": "2026-10-06T00:00:00Z"},
           "oracle_history": [{"passed": 10, "runs": 10}],
           "checks": [{"check": "canary in task files", "ok": True, "detail": ""},
                      {"check": "[release] loss threshold calibrated", "ok": False, "detail": "not measured yet"},
                      {"check": "oracle 10/10", "ok": True, "detail": "r"},
                      {"check": "nop 3/3 score 0", "ok": True, "detail": "r"},
                      {"check": "symptom observed at bootstrap", "ok": True, "detail": "r"},
                      {"check": "wrong fix 'raise-timeout' scores 0", "ok": True, "detail": "r"}]}  # fmt: skip
    (tmp_path / "qa" / "demo.json").write_text(json.dumps(old))
    _regrade_env(tmp_path, monkeypatch, calibrated=True, inputs=inputs)
    qa.main(["demo", "--release", "--regrade"])
    new = json.loads((tmp_path / "qa" / "demo.json").read_text())
    assert new["pass"] is True and new["regraded_from"] == old["stamp"]
    assert new["oracle_history"] == old["oracle_history"]  # a regrade adds no oracle run to the flake bound
    names = [c["check"] for c in new["checks"]]
    assert names == ["canary in task files", "[release] loss threshold calibrated", "oracle 10/10", "nop 3/3 score 0",
                     "symptom observed at bootstrap", "wrong fix 'raise-timeout' scores 0"]  # fmt: skip
    assert "Regraded:" in (tmp_path / "qa" / "demo.md").read_text()


def test_regrade_refuses_a_record_made_on_other_inputs(tmp_path, monkeypatch):
    (tmp_path / "qa").mkdir()
    old = {"task": "demo", "mode": "release", "inputs": {"task_digest": "old"}, "checks": [], "stamp": {}}
    (tmp_path / "qa" / "demo.json").write_text(json.dumps(old))
    _regrade_env(tmp_path, monkeypatch, calibrated=True, inputs={"task_digest": "new"})
    with pytest.raises(SystemExit, match="other inputs"):
        qa.main(["demo", "--release", "--regrade"])
    with pytest.raises(SystemExit):
        qa.main(["demo", "--regrade"])  # dev records are never regraded
