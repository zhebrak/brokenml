"""Leaderboard maths and versioning on synthetic Harbor job directories."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench import analyze


def trial(jobs: Path, job: str, name: str, task: str, reward, *, digest="sha256:aa", model="m", infra=False, cost=0.1,
          namespace="brokenml", exception=None, message="", steps=0, kwargs=None, trial_id=None, source=None,
          finished="2026-10-02T10:00:00Z"):  # fmt: skip
    d = jobs / job / name
    d.mkdir(parents=True)
    rewards = {"reward": reward} if reward is not None else None
    config = {
        "agent": {"name": "terminus-2", "model_name": model, "kwargs": kwargs or {}},
        "task": {"path": f"tasks/{task}"},
    }
    if source:
        config["source_trial"] = {"trial_id": source}
    (d / "result.json").write_text(json.dumps({
        "id": trial_id or name, "task_name": f"{namespace}/{task}", "config": config, "finished_at": finished,
        "verifier_result": {"rewards": rewards} if rewards else None,
        "agent_result": {"cost_usd": cost, "n_input_tokens": 100, "n_output_tokens": 10},
        "exception_info": {"exception_type": exception, "exception_message": message} if exception else None,
    }))  # fmt: skip
    if steps:
        (d / "agent").mkdir()
        (d / "agent" / "trajectory.json").write_text(json.dumps({"steps": [{"source": "agent"}] * steps}))
    (d / "lock.json").write_text(json.dumps({"task": {"name": task, "digest": digest}}))
    (d / "verifier").mkdir()
    (d / "verifier" / "diagnostics.json").write_text(
        json.dumps(
            {
                "reward": reward or 0,
                "infra_error": float(infra),
                "runtime_build": "runtime-1",
                "harness_build": "harness-1",
                "node_build": "node-1",
                "harness_version": "source-1",
            }
        )
    )


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze, "task_meta", lambda d, r: {"split": "test", "category": "collectives",
                                                            "evidence_author": "static"})  # fmt: skip
    return tmp_path


def test_agent_errors_score_zero_and_unattempted_or_infra_trials_are_counted_apart(jobs):
    trial(jobs, "j1", "a1", "t1", 1.0)
    trial(jobs, "j1", "a2", "t1", 0.0)
    trial(jobs, "j1", "b1", "t2", None, exception="RuntimeError", steps=3)  # the agent crashed: its 0
    trial(jobs, "j1", "b2", "t2", 0.0, infra=True)
    trial(jobs, "j1", "b3", "t2", None, exception="BadRequestError", message="Your credit balance is too low")
    s = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1", "t2"})["terminus-2:m"]
    assert s["pass@1"] == 0.25 and s["complete"]  # t1: 0.5, t2: 0.0 (only the crash is scored)
    assert s["unscored"] == {"infra": 1, "not_attempted": 1}
    lite = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1", "t2"}, lite={"t1"})["terminus-2:m"]
    assert lite["lite_k"] == 2 and lite["pass^k_lite"] == 0.0  # t1: 1 of 2, so not both
    assert s["pass^k_lite"] is None or s["lite_k"] >= 2


def test_pass_hat_k_on_lite_needs_two_trials_of_every_lite_task():
    ok = lambda n, c: [{"reward": 1.0}] * c + [{"reward": 0.0}] * (n - c)
    assert analyze.pass_hat_k_lite({"a": ok(3, 3), "b": ok(2, 2)}, {"a", "b"}) == (2, 1.0)
    assert analyze.pass_hat_k_lite({"a": ok(3, 3), "b": ok(1, 1)}, {"a", "b"}) == (None, None)
    assert analyze.pass_hat_k_lite({"a": ok(3, 3)}, {"a", "b"}) == (None, None)  # b not attempted


def test_pass_hat_k_is_unbiased():
    assert analyze.pass_hat_k(3, 3, 3) == 1.0
    assert analyze.pass_hat_k(2, 4, 2) == pytest.approx(1 / 6)
    assert analyze.pass_hat_k(1, 1, 2) is None


def test_trials_of_different_task_versions_are_not_pooled(jobs):
    trial(jobs, "j1", "a1", "t1", 1.0, digest="sha256:old")
    trial(jobs, "j2", "a1", "t1", 0.0, digest="sha256:new")
    with pytest.raises(analyze.MixedVersions):
        analyze.check_versions(analyze.load_trials([jobs]), current_only=False)


def test_variants_are_separate_configurations_and_unknown_namespaces_fail(jobs):
    trial(jobs, "j1", "a1", "t1", 1.0)
    trial(jobs, "j1", "a2", "t1", 1.0, namespace="bench-ablation")  # the namespace used before the project was named
    configs = {t["config"] for t in analyze.load_trials([jobs])}
    assert configs == {"terminus-2:m", "terminus-2:m [ops-only]"}
    assert analyze.variant_of("brokenml-ablation/t1") == analyze.variant_of("bench-ablation/t1") == "ablation"
    trial(jobs, "j2", "a1", "t1", 1.0, namespace="renamed")
    with pytest.raises(ValueError, match="unknown task namespace"):
        analyze.load_trials([jobs])


def test_measured_evidence_labels_override_the_author_label(jobs):
    trial(jobs, "j1", "a1", "t1", 1.0)
    labels = {"t1": {"evidence": {"value": "runtime"}}}
    s = analyze.summarise(analyze.load_trials([jobs]), labels, test_set={"t1"})["terminus-2:m"]
    assert s["by_evidence"] == {"runtime": [1.0, 1]}
    s = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1"})["terminus-2:m"]
    assert s["by_evidence"] == {"static (author)": [1.0, 1]}


def test_a_configuration_that_skipped_tasks_is_marked_incomplete(jobs):
    trial(jobs, "j1", "a1", "t1", 1.0)
    s = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1", "t2"})["terminus-2:m"]
    assert not s["complete"] and s["missing_tasks"] == ["t2"]


def test_trials_of_unknown_tasks_are_dropped_and_reported(jobs):
    trial(jobs, "j1", "a1", "rank0-eval-desync", 1.0)
    trial(jobs, "j1", "a2", "partial-new-group", 1.0)  # parked, no longer a task
    kept, unknown = analyze.known_tasks(analyze.load_trials([jobs]))
    assert [t["task"] for t in kept] == ["rank0-eval-desync"] and unknown == ["partial-new-group"]


def test_paired_comparison_cancels_task_difficulty():
    from bench.analyze import holm, paired

    tasks = [f"t{i}" for i in range(40)]
    a = {t: 1.0 if i < 30 else 0.0 for i, t in enumerate(tasks)}
    b = {t: 1.0 if i < 22 else 0.0 for i, t in enumerate(tasks)}  # a solves every task b solves, plus 8 more
    r = paired(a, b)
    assert r["tasks"] == 40 and r["diff"] == 0.2 and r["ci95"][0] > 0 and r["p"] < 0.01
    same = paired(a, dict(a))
    assert same["diff"] == 0 and same["p"] == 1.0
    assert paired(a, {})["tasks"] == 0
    assert holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06]


def test_comparisons_pair_complete_configs_and_measure_evidence_gain():
    from bench.analyze import comparisons

    def cfg(scores, complete=True, digests=None):
        return {"complete": complete, "pass@1": sum(scores.values()) / len(scores), "by_task": scores,
                "task_digests": digests or dict.fromkeys(scores, "d")}  # fmt: skip

    full = {"x": 1.0, "y": 1.0, "z": 0.0}
    one = {"x": 1.0, "y": 0.0, "z": 0.0}
    summary = {"t2:opus": cfg(full), "t2:sonnet": cfg(one), "t2:opus [ops-only]": cfg(one),
               "t2:qwen": cfg(full, complete=False)}  # fmt: skip
    comp = comparisons(summary)
    assert [(p["a"], p["b"]) for p in comp["pairs"]] == [("t2:opus", "t2:sonnet")]
    assert [(g["config"], g["diff"]) for g in comp["evidence_gain"]] == [("t2:opus", 0.3333)]
    # a task that ran at different versions for the two configurations is left out of their pairing
    summary["t2:sonnet"] = cfg(one, digests={"x": "d", "y": "OLD", "z": "d"})
    pair = comparisons(summary)["pairs"][0]
    assert pair["tasks"] == 2 and pair["version_mismatch"] == 1


def test_live_state_changes_are_recognised_but_job_control_is_not():
    from bench.analyze import live_changes

    live = [
        "scontrol update nodename=c1 state=resume",
        "ssh c1 'pkill -f node-metrics'",
        "kill 4242",
        "ssh c1 rm -rf /scratch/corpus.safetensors",
        "scontrol delete reservation maint_kernel_upgrade",
        "sed -i 's/x/y/' /etc/platform/job.env",
        "echo 1 > /etc/hosts",
        "cp /tmp/hosts /etc/hosts",
        "echo 10.0.0.2 c2 | tee -a /etc/hosts",
    ]
    for cmd in live:
        assert live_changes(cmd), cmd
    job_control = [
        "sbatch /ops/jobs/train/launch.sbatch",
        "scancel 12",
        "ocb cluster apply",
        "cat /etc/hosts",
        "sed -i 's/a/b/' /ops/jobs/train/train.yaml",
        "rm /ops/ANALYSIS.md",
        "squeue -u svc-train",
        "cp /etc/slurm/slurm.conf /ops/cluster/slurm.conf",  # copying out of a live path reads it
        "cp /shared/data/train.bin /tmp/x",
    ]
    for cmd in job_control:
        assert not live_changes(cmd), cmd


def test_efficiency_counts_tokens_to_solve_and_budgeted_solve_rate():
    from bench.analyze import efficiency

    t = lambda r, tok, steps=10: {"reward": r, "tokens": tok, "agent_steps": steps}
    e = efficiency([t(1.0, 300_000, 12), t(1.0, 1_500_000, 40), t(0.0, 900_000)], 3)
    assert e["tokens_per_solve"] == 1_350_000 and e["median_tokens_passing"] == 1_500_000
    assert e["solved_within"]["500000"] == round(1 / 3, 3) and e["solved_within"]["2000000"] == round(2 / 3, 3)
    assert efficiency([t(0.0, 100)], 1)["tokens_per_solve"] is None


def test_timing_review_lists_busy_or_shifted_verdicts_either_way_and_counts_unrecorded():
    from bench.analyze import timing_review

    def t(task, ok, ref=None, job=None):
        return {"task": task, "reward": 1.0 if ok else 0.0, "tput_ok": ok, "tput_ratio": 0.7, "tput_min": 0.67,
                "host_busy_ref": ref, "host_busy_job": job}  # fmt: skip

    trials = [t("a", False, 0.3, 0.6), t("b", True, 0.6, 0.3), t("c", True, 0.3, 0.35), t("d", False, 0.2, 0.4),
              t("e", False), {"task": "f", "reward": 0.0, "tput_ok": None}]  # fmt: skip
    listed, unrecorded = timing_review(trials)
    assert [x.split()[0] for x in listed] == ["a", "b", "d"] and unrecorded == 1
    assert listed[1].startswith("b pass at ratio 0.7 (min 0.67)")


def test_empirical_difficulty_averages_configurations_first_and_buckets_like_tb():
    from bench.analyze import empirical_difficulty, spearman

    def t(task, config, r, tokens=100, variant="standard", infra=False):
        return {"task": task, "config": config, "reward": r, "variant": variant, "infra": infra, "errored": False,
                "scored": not infra, "tokens": tokens, "agent_steps": 5}  # fmt: skip

    trials = [t("a", "x", 1.0), t("a", "x", 1.0), t("a", "x", 1.0), t("a", "y", 0.0),  # x repeats; y once
              t("b", "x", 1.0), t("b", "y", 1.0), t("c", "x", 0.0), t("c", "y", 0.0, infra=True),
              t("c", "x", 1.0, variant="ablation")]  # fmt: skip
    d = empirical_difficulty(trials, {"a": "hard", "b": "easy", "c": "medium"})["tasks"]
    assert d["a"]["pass_rate"] == 0.5 and d["a"]["bucket"] == "medium"  # (1 + 0) / 2, not 3 / 4
    assert d["b"]["bucket"] == "easy" and d["c"]["pass_rate"] == 0.0 and d["c"]["configs"] == 1
    assert spearman([0, 1, 2], [0.1, 0.5, 0.9]) == 1.0 and spearman([1, 1], [0, 1]) is None


def test_edits_before_evidence_orders_ops_changes_against_deep_runtime_evidence():
    from bench.analyze import _command, edits_before_evidence

    report, code = "cat /shared/evidence/report.md", "cat /ops/src/trainer/data.py"
    assert edits_before_evidence([report, code, "sed -i 's/+ 1//' /ops/src/trainer/data.py", "squeue"]) is True
    assert edits_before_evidence(["tail /shared/logs/train-1.out", "cd /ops && sed -i 's/x/y/' a"]) is True  # logs
    assert edits_before_evidence(["head /shared/evidence/dumps/1/stacks.md", "p.write_text(s)"]) is False
    assert edits_before_evidence(["ssh c2 nproc; sed -i 's/16/1/' /ops/cluster/nodes/c2.env"]) is False
    assert edits_before_evidence(["cp /ops/a.py /tmp/a.bak", "cp /tmp/a.py /ops/a.py"]) is True  # backup, then edit
    assert edits_before_evidence(["cat > /ops/ANALYSIS.md <<'EOF'\nsee squeue\nEOF"]) is None  # write-up only
    # writes elsewhere are not edits of /ops: scratch files, backups, copies of copies
    dump = "cat /shared/evidence/dumps/1/stacks.md"
    fix = "sed -i 's/a/b/' /ops/jobs/train/train.yaml"
    assert edits_before_evidence(['python3 -c \'json.dump(d, open("/tmp/x.json", "w"))\'', dump, fix]) is False
    assert edits_before_evidence(["cp /ops/a.yaml /ops/a.yaml.orig", dump, fix]) is False
    assert edits_before_evidence(["sed -i 's/x/y/' /tmp/copy.py", dump, fix]) is False
    assert edits_before_evidence(["cd /ops && sed -i 's/a/b/' jobs/train/train.yaml", dump]) is True
    # Claude Code's file tools read and write like shell commands
    edit = {"function_name": "Edit", "arguments": {"file_path": "/ops/jobs/train/train.yaml"}}
    read = {"function_name": "Read", "arguments": {"file_path": "/shared/evidence/fr/rank0.json"}}
    assert edits_before_evidence([_command(read), _command(edit)]) is False
    assert edits_before_evidence([_command(edit), _command(read)]) is True


def test_a_verifier_that_ran_and_left_no_reward_is_never_the_agents_zero():
    from bench import outcomes
    from bench.analyze import _verifier_ran, outcome

    base = {"verifier": {"started_at": "2026-10-02T07:44:45Z"}, "verifier_result": None}
    assert _verifier_ran({**base, "exception_info": {"occurred_at": "2026-10-02T07:46:27Z"}})
    # Harbor keeps only the first exception: an agent timeout recorded before the verifier started must not hide a
    # grader that was killed afterwards (A4: a killed grader is never a negative).
    timeout = {"exception_type": "AgentTimeoutError", "occurred_at": "2026-10-02T07:40:00Z"}
    assert _verifier_ran({**base, "exception_info": timeout})
    assert outcome(None, {"failure": "verifier_bug", "complete": 0.0}, timeout, 20, True) == outcomes.BUG
    assert outcome(None, {"failure": "infra", "infra_error": 1.0}, timeout, 20, True) == outcomes.INFRA
    assert outcome(None, {}, timeout, 20, True) == outcomes.INFRA  # no record at all: its environment never came up
    assert not _verifier_ran({"verifier": None, "verifier_result": None, "exception_info": timeout})
    graded = {**base, "verifier_result": {"rewards": {"reward": 0.0}}, "exception_info": timeout}
    assert not _verifier_ran(graded)


def test_reasoning_settings_are_separate_rows(jobs):
    trial(jobs, "j1", "lo", "t1", 0.0, kwargs={"reasoning_effort": "low"})
    trial(jobs, "j1", "hi", "t1", 1.0, kwargs={"reasoning_effort": "high"})
    configs = sorted({t["config"] for t in analyze.load_trials([jobs])})
    assert configs == ["terminus-2:m {reasoning_effort=high}", "terminus-2:m {reasoning_effort=low}"]


def test_sibling_regrades_resolve_to_one_attempt_with_the_latest_grading(jobs):
    trial(jobs, "orig", "o", "t1", 0.0, trial_id="T1", infra=True)
    trial(jobs, "rg1", "r1", "t1", 0.0, trial_id="R1", source="T1", finished="2026-10-02T11:00:00Z")
    trial(jobs, "rg2", "r2", "t1", 1.0, trial_id="R2", source="T1", finished="2026-10-02T12:00:00Z")
    trials = analyze.load_trials([jobs])
    assert [(t["reward"], t["gradings"]) for t in trials] == [(1.0, 3)]


def test_missing_cost_is_unknown_not_free(jobs):
    trial(jobs, "j1", "a1", "t1", 1.0, cost=None)
    trial(jobs, "j1", "a2", "t1", 1.0, cost=0.4)
    s = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1"})["terminus-2:m"]
    assert s["cost_per_trial"] == 0.4 and s["cost_known"] == 1


def _job_meta(jobs: Path, job: str, harbor: str | None = None, attempts: int | None = None):
    (jobs / job).mkdir(parents=True, exist_ok=True)
    if harbor:
        (jobs / job / "lock.json").write_text(json.dumps({"harbor": {"version": harbor}}))
    if attempts:
        (jobs / job / "config.json").write_text(json.dumps({"n_attempts": attempts}))


def test_a_regrade_in_its_own_directory_stays_in_the_original_row(jobs):
    """The regrade's job dir has no lock.json; it must not split the row in two."""
    _job_meta(jobs, "j1", harbor="0.23.0")
    trial(jobs, "j1", "t1__a", "t1", None, infra=True, trial_id="id-a")
    trial(jobs, "j1", "t2__a", "t2", 1.0, trial_id="id-b")
    trial(jobs, "regrade-1", "t1__r", "t1", 1.0, source="id-a", finished="2026-10-02T12:00:00Z")
    s = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1", "t2"})
    assert list(s) == ["terminus-2:m"] and s["terminus-2:m"]["complete"] and s["terminus-2:m"]["pass@1"] == 1.0


def test_gradings_on_another_task_version_and_replays_are_not_scored(jobs):
    trial(jobs, "j1", "t1__a", "t1", 0.0, trial_id="id-a")
    trial(jobs, "regrade-1", "t1__r", "t1", 1.0, source="id-a", digest="sha256:new", finished="2026-10-02T12:00:00Z")
    trial(jobs, "regrades", "t1__p", "t1", 1.0, source="id-a", finished="2026-10-02T13:00:00Z")
    diag = jobs / "regrades" / "t1__p" / "verifier" / "diagnostics.json"
    diag.write_text(json.dumps({**json.loads(diag.read_text()), "replay": 1.0}))
    [t] = analyze.load_trials([jobs])
    assert t["reward"] == 0.0 and t["digest"] == "sha256:aa" and t["other_version_gradings"] == 1


def test_remaining_errors_count_as_zero_with_a_scored_only_sensitivity(jobs):
    trial(jobs, "j1", "a", "t1", 1.0)
    trial(jobs, "j1", "b", "t2", 0.0, infra=True)
    s = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1", "t2"})["terminus-2:m"]
    assert s["pass@1"] == 0.5 and s["pass@1_scored"] == 1.0 and s["complete"] and s["unscored"] == {"infra": 1}


def test_provider_errors_are_rerun_and_rows_need_k_counted_trials(jobs):
    _job_meta(jobs, "j1", attempts=2)
    trial(jobs, "j1", "a1", "t1", 1.0)
    trial(jobs, "j1", "a2", "t1", None, exception="RateLimitError", steps=5)  # the provider, not the agent
    s = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1"})["terminus-2:m"]
    assert s["unscored"] == {"provider_error": 1} and not s["complete"] and s["missing_tasks"] == ["t1"]


def test_openrouter_rows_show_their_pin_and_unpinned_ones_are_not_compared(jobs):
    pin = {"llm_call_kwargs": {"extra_body": {"provider": {"order": ["deepinfra"], "allow_fallbacks": False,
                                                           "quantizations": ["bf16"]}}}}  # fmt: skip
    trial(jobs, "j1", "a", "t1", 1.0, model="openrouter/q", kwargs=pin)
    trial(jobs, "j2", "b", "t1", 0.0, model="openrouter/q")
    trial(jobs, "j3", "c", "t1", 0.0, model="anthropic/h")
    s = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1"})
    assert set(s) == {"terminus-2:openrouter/q @deepinfra/bf16", "terminus-2:openrouter/q [unpinned]",
                      "terminus-2:anthropic/h"}  # fmt: skip
    pairs = analyze.comparisons(s)["pairs"]
    assert pairs and all("[unpinned]" not in p["a"] + p["b"] for p in pairs)


def test_a_split_identity_keeps_the_variant_mark_last():
    trials = [{"label": "t2:m", "config": "t2:m", "config_id": "a", "variant": "standard"},
              {"label": "t2:m", "config": "t2:m [ops-only]", "config_id": "b", "variant": "ablation"}]  # fmt: skip
    configs = [t["config"] for t in analyze.split_identities(trials)]
    assert configs == ["t2:m #a", "t2:m #b [ops-only]"]


def _prereg_summary():
    tasks = [f"t{i}" for i in range(8)]
    full = {t: 1.0 for t in tasks}
    ops = {t: (0.0 if i < 4 else 1.0) for i, t in enumerate(tasks)}  # t0-t3 need the cluster
    std = {"complete": True, "variant": "standard", "by_task": full, "pass@1": 1.0}
    arm = {"complete": True, "variant": "ablation", "by_task": ops, "pass@1": 0.5}
    return tasks, {"a": {**std, "config_ids": ["x"]}, "a [ops-only]": {**arm, "config_ids": ["x"]},
                   "b": {**std, "config_ids": ["y"]}, "b [ops-only]": {**arm, "config_ids": ["y"]}}  # fmt: skip


def test_preregistered_h1_pools_configurations_and_h2_permutes_labels():
    tasks, summary = _prereg_summary()
    fams = {t: "AB"[i % 2] for i, t in enumerate(tasks)}
    first = analyze.h1(summary, ["a", "b"], families=fams)
    assert first["configs"] == ["a", "b"] and first["diff"] == 0.5 and first["tasks"] == 8
    assert first["ci95_family"] and first["ci95_family"][0] <= 0.5 <= first["ci95_family"][1]
    label = {t: ("runtime" if i < 4 else "static") for i, t in enumerate(tasks)}
    second = analyze.h2(first["gain_by_task"], label, families=fams, n=2000)
    assert second["diff"] == 1.0 and second["runtime"] == 4 and second["p"] < 0.05
    assert analyze.h2({"t0": 1.0}, {"t0": "runtime"})["diff"] is None  # one label only: no test


def test_preregistered_needs_named_complete_primary_configurations():
    _, summary = _prereg_summary()
    assert analyze.preregistered(summary, {})["status"].startswith("not computed")
    short = {**summary, "b [ops-only]": {**summary["b [ops-only]"], "complete": False}}
    assert "incomplete" in analyze.preregistered(short, {}, ["a", "b"])["status"]
    assert "no such" in analyze.preregistered(summary, {}, ["c"])["status"]
    family = analyze.secondary_family(summary, ["a", "b"])
    assert [t["test"] for t in family] == ["gain a", "gain b", "a - b"] and all("p_holm" in t for t in family)


def test_a_clustered_interval_is_withheld_when_labels_and_families_confound():
    gain = {f"t{i}": float(i < 4) for i in range(8)}
    label = {t: ("runtime" if i < 4 else "static") for i, t in enumerate(gain)}
    fams = {t: ("A" if label[t] == "static" else f"R{i}") for i, t in enumerate(gain)}  # static all in one family
    r = analyze.h2(gain, label, families=fams, n=2000)
    assert r["family_dropped"] > 0.05 * 2000 and r["ci95_family"] is None


def test_task_costs_take_percentiles_over_attempted_trials():
    rows = [{"task": "t1", "outcome": "pass", "wall_s": w, "agent_s": w - 100, "verifier_s": 60.0, "cost": c}
            for w, c in ((600.0, 0.1), (900.0, 0.2), (1800.0, None))]  # fmt: skip
    rows.append({"task": "t1", "outcome": "not_attempted", "wall_s": 5.0, "cost": None})
    c = analyze.task_costs(rows)["t1"]
    assert c["trials"] == 3 and c["wall_p50_s"] == 900.0 and c["wall_p90_s"] == 1800.0 and c["cost_p50"] == 0.2
    assert analyze._seconds({"started_at": "2026-10-02T15:50:49Z", "finished_at": "2026-10-02T16:00:49Z"}) == 600.0


def test_snapshot_variant_has_its_label_namespace_and_is_not_pooled(jobs):
    trial(jobs, "j1", "a1", "t1", 1.0)
    trial(jobs, "j1", "a2", "t1", 1.0, namespace="brokenml-snapshot")
    trials = analyze.load_trials([jobs])
    assert {t["config"] for t in trials} == {"terminus-2:m", "terminus-2:m [snapshot]"}
    assert {t["variant"] for t in trials} == {"standard", "snapshot"}
    s = analyze.summarise(trials, test_set={"t1"})
    assert analyze.comparisons(s)["pairs"] == []  # a standard row is never paired with its snapshot arm
    assert analyze.ablation_arm(s, "terminus-2:m") is None  # and the snapshot arm is not the ops-only arm


def test_snapshot_decomposition_needs_the_snapshot_arm_and_pairs_by_identity():
    def row(variant, by_task):
        return {"complete": True, "variant": variant, "by_task": by_task, "pass@1": 0.5, "config_ids": ["x"]}

    tasks = {f"t{i}": 1.0 for i in range(4)}
    snap = {t: (1.0 if i < 2 else 0.0) for i, t in enumerate(tasks)}
    ops = {t: (1.0 if i < 1 else 0.0) for i, t in enumerate(tasks)}
    summary = {"a": row("standard", tasks), "a [snapshot]": row("snapshot", snap), "a [ops-only]": row("ablation", ops)}
    [x] = analyze.comparisons(summary)["snapshot_decomposition"]
    assert x["live_interaction"]["diff"] == 0.5 and x["snapshot_alone"]["diff"] == 0.25 and x["ops_only_arm"]
    gain = analyze.comparisons(summary)["evidence_gain"][0]["diff"]
    assert gain == pytest.approx(x["live_interaction"]["diff"] + x["snapshot_alone"]["diff"])  # they add up
    no_snap = {k: v for k, v in summary.items() if k != "a [snapshot]"}
    assert analyze.comparisons(no_snap)["snapshot_decomposition"] == []
    no_ops = {k: v for k, v in summary.items() if k != "a [ops-only]"}
    [y] = analyze.comparisons(no_ops)["snapshot_decomposition"]
    assert y["snapshot_alone"]["diff"] is None and y["live_interaction"]["diff"] == 0.5


def test_snapshot_section_appears_in_the_report_only_with_a_snapshot_arm(jobs):
    for i, (ns, r) in enumerate((("brokenml", 1.0), ("brokenml-snapshot", 1.0), ("brokenml-ablation", 0.0))):
        trial(jobs, "j1", f"a{i}", "t1", r, namespace=ns)
    s = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1"})
    text = analyze.markdown(s, {"utc": "t"})
    assert "report-and-logs snapshot" in text and "terminus-2:m [snapshot]" in text
    s.pop("terminus-2:m [snapshot]")
    assert "report-and-logs snapshot" not in analyze.markdown(s, {"utc": "t"})


def test_snapshot_decomposition_marks_tuning_models_and_splits_by_capture():
    def row(variant, by_task):
        return {"complete": True, "variant": variant, "by_task": by_task, "pass@1": 0.5, "config_ids": ["x"]}

    tasks = [f"t{i}" for i in range(4)]
    channels = {"t0": "errors", "t1": "stacks", "t2": "node-state", "t3": "storage"}
    full = dict.fromkeys(tasks, 1.0)
    snap = {"t0": 1.0, "t1": 1.0, "t2": 0.0, "t3": 0.0}
    ops = {"t0": 0.0, "t1": 1.0, "t2": 0.0, "t3": 0.0}
    summary = {"a": row("standard", full), "a [snapshot]": row("snapshot", snap), "a [ops-only]": row("ablation", ops)}
    [held] = analyze.snapshot_decomposition(summary, ["a"], channels)
    [tuned] = analyze.snapshot_decomposition(summary, ["b"], channels)
    [unknown] = analyze.snapshot_decomposition(summary, None, channels)
    assert held["note"] is None and tuned["note"] == "tuning model: tasks hardened against it (both arms)"
    assert "unknown" in unknown["note"]
    inside, outside = held["by_channel"]["inside"], held["by_channel"]["outside"]
    assert (inside["tasks"], outside["tasks"]) == (2, 2)
    assert inside["live_interaction"]["diff"] == 0.0 and inside["snapshot_alone"]["diff"] == 0.5
    assert outside["live_interaction"]["diff"] == 1.0 and outside["snapshot_alone"]["diff"] == 0.0
    for g in (inside, outside):  # the two add up to the live-access gain on the same tasks
        assert g["live_access_gain"]["diff"] == pytest.approx(
            g["live_interaction"]["diff"] + g["snapshot_alone"]["diff"]
        )
    assert analyze.capture_group("t0", channels) == "inside" and analyze.capture_group("zzz", channels) is None
    comp = analyze.comparisons(summary, ["b"])
    assert comp["snapshot_decomposition"][0]["note"] == analyze.TUNING_NOTE


def test_every_channel_is_inside_or_outside_the_capture():
    from bench.spec import CHANNELS

    outside = {"node-state", "service", "data", "storage"}
    assert analyze.INSIDE_CAPTURE | outside == set(CHANNELS) and not analyze.INSIDE_CAPTURE & outside


def test_a_timed_out_agent_is_graded_on_the_ops_it_left():
    from bench import outcomes

    timeout = {"exception_type": "AgentTimeoutError", "exception_message": "Agent execution timed out"}
    diag = {"failure": "none", "complete": 1.0}
    assert analyze.outcome(1.0, diag, timeout, 20, False) == outcomes.PASS  # the repair held: Harbor's convention
    assert analyze.outcome(0.0, {**diag, "failure": "agent"}, timeout, 20, False) == outcomes.AGENT
    assert analyze.outcome(None, {}, timeout, 20, False) == outcomes.AGENT  # no reward after real steps: its result
    assert analyze.outcome(None, {}, timeout, 0, False) == analyze.NOT_ATTEMPTED_OUTCOME  # never got going


def test_regradings_in_their_own_directories_follow_the_original_under_a_prefix(jobs):
    trial(jobs, "v1-scored-standard-m-1", "t1__a", "t1", None, infra=True, trial_id="orig-1", steps=5)
    trial(jobs, "regrade-20261103-120000", "t1__b", "t1", 1.0, source="orig-1")
    trial(jobs, "e2-pilot-standard-m-1", "t1__c", "t1", 0.0, steps=5)  # a pilot: not scored
    rows = analyze.load_trials([jobs], prefix="v1-scored")
    assert [(t["outcome"], t["reward"], t["gradings"]) for t in rows] == [("pass", 1.0, 2)]


def test_the_protocols_k_decides_completeness_and_extra_trials_are_listed(jobs, monkeypatch):
    for task in ("t1", "t2", "t3"):
        trial(jobs, "v1-a", f"{task}__1", task, 1.0, steps=5)
    trial(jobs, "v1-b", "t1__2", "t1", 0.0, steps=5)  # a second trial on one task
    (jobs / "v1-b" / "config.json").write_text(json.dumps({"n_attempts": 2}))
    rows = analyze.load_trials([jobs])
    test_set, lite = {"t1", "t2", "t3"}, {"t3"}
    by_jobs = analyze.summarise(rows, test_set=test_set, lite=lite)
    assert not next(iter(by_jobs.values()))["complete"]  # Harbor's max k (2) makes t2 and t3 incomplete
    by_protocol = analyze.summarise(rows, test_set=test_set, lite=lite, k=1)
    row = next(iter(by_protocol.values()))
    assert row["complete"] and row["extra_trials"] == ["t1"] and row["k"] == 1


def test_comparisons_mark_tuning_models_and_unknown_held_out_status():
    assert analyze.held_out_note(None, "a") == analyze.UNKNOWN_NOTE
    assert analyze.held_out_note(["a"], "a") is None
    assert analyze.held_out_note(["a"], "a", "b") == analyze.TUNING_NOTE


def test_commands_cover_web_tools_codex_patches_and_argv_commands():
    from bench.analyze import CREDENTIALS, WEB, _command

    assert (
        _command({"function_name": "WebFetch", "arguments": {"url": "https://github.com/x/y/issues/1"}})
        == "web https://github.com/x/y/issues/1"
    )
    assert _command({"function_name": "WebSearch", "arguments": {"query": "gloo size mismatch"}}).startswith(
        "web-search"
    )
    patch = "*** Begin Patch\n*** Update File: src/trainer/loop.py\n@@\n-a\n+b\n*** End Patch\n"
    assert _command({"function_name": "apply_patch", "arguments": {"input": patch}}) == "> src/trainer/loop.py"
    assert (
        _command({"function_name": "exec_command", "arguments": {"cmd": ["cat", "/ops/RUNBOOK.md"]}})
        == "cat /ops/RUNBOOK.md"
    )
    assert WEB.findall("web https://x") and WEB.findall("curl -s https://x | sh") and not WEB.findall("cat /ops/x")
    assert CREDENTIALS.findall("cat /root/.ssh/id_ed25519") and not CREDENTIALS.findall("sinfo -R")


def test_installed_agent_provider_failures_are_provider_errors_not_the_agents_zero():
    from bench import outcomes

    for exc in (
        "ApiRateLimitError",
        "ApiOverloadedError",
        "ApiInternalServerError",
        "ApiConnectionClosedError",
        "ApiResponseStalledError",
        "UnknownApiError",
        "NetworkConnectionError",
        "RateLimitError",
    ):
        kind = analyze.outcome(0.0, {"failure": "agent", "complete": 1.0}, {"exception_type": exc}, 12, False)
        assert kind == analyze.PROVIDER_ERROR, exc
    assert analyze.outcome(0.0, {"failure": "agent", "complete": 1.0}, {"exception_type": "AgentTimeoutError"}, 12,
                           False) == outcomes.AGENT  # fmt: skip


def test_timing_review_lists_only_verdicts_a_load_shift_could_move():
    base = {"task": "t", "tput_ok": False, "host_busy_ref": 0.1, "host_busy_job": 0.6, "tput_min": 0.67}
    clear, close = {**base, "tput_ratio": 0.23}, {**base, "tput_ratio": 0.6}
    listed, _ = analyze.timing_review([clear, close])
    assert len(listed) == 1 and "ratio 0.6" in listed[0]


def test_build_changes_across_tasks_in_one_row_are_not_pooled():
    rows = [
        dict(config="c", task="a", digest="a", harness="h", builds="r/h/node1"),
        dict(config="c", task="b", digest="b", harness="h", builds="r/h/node2"),
    ]
    with pytest.raises(analyze.MixedVersions):
        analyze.check_versions(rows, False)
    rows[0]["evaluation"] = {"runtime": "r1", "serve": "unknown"}
    rows[1]["evaluation"] = {"runtime": "r2", "serve": "unknown"}
    with pytest.raises(analyze.MixedVersions):
        analyze.check_versions(rows, False)  # an unknown role must not suppress a known build change


def test_a_registered_patched_grading_does_not_mix_the_rows_node_build():
    rows = [
        dict(config="c", task="a", digest="a", harness="h", builds="r/h/node1", evaluation={"cpu-node": "node1"}),
        dict(
            config="c",
            task="b",
            digest="b",
            harness="h",
            builds="r/h/patched",
            evaluation={"cpu-node": "patched"},
            patched_runtime="patched",
        ),
    ]
    assert analyze.check_versions(rows, False) == rows  # deviation ag: the patched twin's node build is its own
    assert analyze.row_evaluation(rows) == {"cpu-node": ["node1"]}  # the arm compares as one build
    rows[1].pop("patched_runtime")
    with pytest.raises(analyze.MixedVersions):
        analyze.check_versions(rows, False)  # the same build without the registration is another build in the row
    assert analyze.row_evaluation(rows) == {"cpu-node": ["node1", "patched"]}


def test_comparisons_reject_incomplete_arms_and_different_builds_and_handle_empty_overlap():
    def row(rate, variant="standard", complete=True, digest="d", build="h1"):
        return {
            "complete": complete,
            "variant": variant,
            "config_ids": ["x"],
            "by_task": {"t": rate},
            "task_digests": {"t": digest},
            "pass@1": rate,
            "evaluation": {"harness": [build]},
        }

    summary = {"a": row(1), "a [ops-only]": row(0, "ablation", complete=False)}
    assert analyze.comparisons(summary)["evidence_gain"] == []
    summary["a [ops-only]"] = row(0, "ablation", build="h2")
    assert analyze.comparisons(summary)["evidence_gain"] == []
    assert analyze.primary_problems(summary, ["a"])
    pair = analyze.comparisons({"a": row(1), "b": row(0, digest="other")})["pairs"][0]
    assert pair["tasks"] == 0 and pair["p_holm"] is None
    assert analyze.comparisons({"a": row(1), "b": row(0, build="h2")})["pairs"] == []


def test_serving_provenance_has_its_engine_and_no_inapplicable_node():
    value = analyze.execution_provenance(
        {"substrate": "serving", "runtime_build": "r", "harness_build": "h", "serve_build": "s"}
    )
    assert value == {"runtime": "r", "harness": "h", "serve": "s"}


def test_stale_labels_are_excluded_from_summary_and_replication(jobs, monkeypatch):
    task = "activation-oom"
    trial(jobs, "j", "a", task, 1)
    labels = {task: {"evidence": {"value": "runtime", "provisional": False, "digests": ["old"]}}}
    monkeypatch.setattr(analyze, "current_digest", lambda *a: "new")
    rows = analyze.load_trials([jobs])
    summary = analyze.summarise(rows, labels, test_set={task})
    assert summary["terminus-2:m"]["by_evidence"] == {"static (author)": [1.0, 1]}
    arm = {**summary["terminus-2:m"], "variant": "ablation"}
    summary["terminus-2:m [ops-only]"] = arm
    for row in summary.values():
        row["scored_protocol"] = True
    assert analyze.preregistered(summary, labels, ["terminus-2:m"])["measured_labels"] == 0


def test_regrade_keeps_original_timeout_and_execution_durations(jobs):
    trial(
        jobs,
        "original",
        "a",
        "t1",
        0.0,
        exception="AgentTimeoutError",
        steps=2,
        trial_id="origin",
        finished="2026-10-02T10:10:00Z",
    )
    trial(jobs, "regrade", "b", "t1", 1.0, source="origin", finished="2026-10-03T10:01:00Z")
    path = jobs / "original/a/result.json"
    value = json.loads(path.read_text())
    value.update(
        started_at="2026-10-02T10:00:00Z",
        agent_execution={"started_at": "2026-10-02T10:00:00Z", "finished_at": "2026-10-02T10:09:00Z"},
    )
    path.write_text(json.dumps(value))
    path = jobs / "regrade/b/result.json"
    value = json.loads(path.read_text())
    value["started_at"] = "2026-10-03T10:00:00Z"
    path.write_text(json.dumps(value))
    [result] = analyze.load_trials([jobs])
    assert result["reward"] == 1 and result["exception"] == "AgentTimeoutError"
    assert result["agent_s"] == 540 and result["wall_s"] == 600 and result["grading_wall_s"] == 60
    assert result["agent_steps"] == 2


def test_frozen_lite_repetition_targets_do_not_raise_every_tasks_target(jobs):
    for name, task in (("a", "t1"), ("b", "t2")):
        trial(jobs, "j", name, task, 1)
    manifest = {
        "protocol": "frozen",
        "protocol_k": 1,
        "required_attempts": {"t1": 1, "t2": 3},
        "tasks": {t: {"canonical": "c"} for t in ("t1", "t2")},
    }
    (jobs / "j/run-manifest.json").write_text(json.dumps(manifest))
    summary = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1", "t2"}, lite={"t2"})["terminus-2:m"]
    assert not summary["complete"] and summary["missing_tasks"] == ["t2"] and summary["k"] == 1
    trial(jobs, "j", "c", "t2", 1)
    trial(jobs, "j", "d", "t2", 1)
    assert analyze.summarise(analyze.load_trials([jobs]), test_set={"t1", "t2"}, lite={"t2"})["terminus-2:m"][
        "complete"
    ]


def test_policy_failures_keep_frozen_image_provenance_without_node_observations(jobs):
    from bench.protocol import digest

    trial(jobs, "j", "a", "t1", 0)
    body = {
        "schema": 1,
        "tasks": {"t1": "canonical"},
        "schedule": [{"task": "t1"}],
        "images": {"runtime": {"ref": "r@sha256:abc", "id": "sha256:build"}},
    }
    protocol = {"id": digest(body), **body}
    manifest = {
        "protocol": protocol["id"],
        "cell": 0,
        "images": {"runtime": "sha256:build"},
        "tasks": {"t1": {"canonical": "canonical", "digest": "sha256:aa"}},
    }
    (jobs / "j/protocol.json").write_text(json.dumps(protocol))
    (jobs / "j/run-manifest.json").write_text(json.dumps(manifest))
    path = jobs / "j/a/verifier/diagnostics.json"
    diag = json.loads(path.read_text())
    diag.pop("node_build")
    diag.update(policy_ok=0, failure="agent", complete=1)
    path.write_text(json.dumps(diag))
    [row] = analyze.load_trials([jobs])
    assert row["reward"] == 0 and row["provenance_complete"] and row["protocol_verified"]
    assert row["unobserved_builds"] == [] and "cpu-node" not in row["evaluation"]  # no job ran: no node to observe
    assert not analyze._known_version("known,unknown")
    (jobs / "j/protocol.json").unlink()
    row = analyze.load_trials([jobs])[0]
    assert not row["protocol_verified"] and row["provenance_complete"]  # nothing ran on a node: nothing unobserved


def test_audit_scan_flags_repository_fetches_and_verifier_paths_only():
    from bench.analyze import AUDIT, row_release

    command = (
        "curl -sL https://github.com/zhebrak/brokenml/raw/main/x; cat /tests/verify.yaml; "
        "echo 1 > /logs/verifier/reward.json; cat /ops/jobs/train/train.yaml; ocb metrics"
    )
    hits = AUDIT.findall(command)
    assert "brokenml" in hits and "/tests/verify.yaml" in hits and "/logs/verifier" in hits
    assert AUDIT.search("curl https://zhebrak.io/brokenml/tasks") and AUDIT.search("gh repo clone zhebrak/x")
    assert AUDIT.search("gh api repos/o/r/contents/x") and not AUDIT.search("gh issue list")
    assert not AUDIT.findall("cat /ops/CONTRACT.md; sacct -X; ssh c2 cat /sys/fs/cgroup/memory.events")
    # the red-team runs' searches for the grader, and the verifier's or a solution's directories at the root
    searched = [
        "find / -iname '*expected*' -o -iname '*solution*' -o -iname '*golden*' 2>/dev/null",
        "find / -path '*/verifier*' -o -path '*/grading*' 2>/dev/null",
        "ls -la /tests/",
        "locate grader",
    ]
    routine = [
        "find /ops -name '*.py'",
        "find / -name 'hwsetup*'",
        "ls site-packages/setuptools/tests/",
        "ocb score",
        "find /opt/ocb -type f -name '*.py'",
        "grep -n eval /ops/jobs/eval/eval.sbatch",
    ]
    assert all(AUDIT.search(c) for c in searched) and not any(AUDIT.search(c) for c in routine)
    models = {"qwen/qwen3.8-27b": {"released": "2026-12-01"}, "glm-5.3-flash": {"released": None}}
    dates = {"published": "2026-11-25", "models": models}
    released, flag = row_release("terminus-2:openrouter/qwen/qwen3.8-27b [hinted]", dates)
    assert released == "2026-12-01" and "after the dataset" in flag
    assert row_release("terminus-2:glm-5.3-flash", dates) == (None, "")
    assert row_release("terminus-2:unknown-model", {}) == (None, "")


def test_web_access_ignores_the_clusters_own_hosts_and_live_changes_ignore_read_only_tc():
    from bench.analyze import WEB, live_changes

    assert not WEB.findall("curl -s http://engine:8080/health") and not WEB.findall("curl http://objstore:8000/d/x")
    assert not WEB.findall("curl -s http://localhost:9100/metrics") and not WEB.findall("curl http://c1:29500")
    assert WEB.findall("gh repo clone o/r") and WEB.findall("gh api repos/o/r")
    assert WEB.findall("curl -s https://huggingface.co/x") and WEB.findall("wget http://example.com/f")
    assert live_changes("ssh c1 'tc qdisc show 2>&1'") == []
    assert live_changes("tc qdisc add dev eth0 root netem delay 5ms") == ["tc qdisc add"]


def test_family_clustered_ci_reads_the_bootstrap_record():
    from bench.analyze import FAMILIES, family_clustered_ci

    tasks = sorted(FAMILIES)[:6]
    per_task = {t: float(i % 2) for i, t in enumerate(tasks)}
    ci = family_clustered_ci(per_task)
    assert ci is not None and len(ci) == 2 and 0.0 <= ci[0] <= ci[1] <= 1.0
    assert family_clustered_ci({tasks[0]: 1.0}) is None  # one task: no interval
    assert family_clustered_ci({"not-a-task": 1.0, tasks[0]: 0.0}) is None  # unknown family: withheld


def test_sharding_bypass_flags_an_fsdp_config_whose_code_no_longer_shards(tmp_path):
    from bench.analyze import sharding_bypass

    def ops(mode: str, body: str):
        root = tmp_path / f"{mode}-{abs(hash(body))}"
        (root / "jobs" / "train").mkdir(parents=True)
        (root / "src" / "trainer").mkdir(parents=True)
        (root / "jobs" / "train" / "train.yaml").write_text(f"parallel: {mode}\n")
        (root / "src" / "trainer" / "parallel.py").write_text(body)
        return root

    shards = (
        "def wrap(model, cfg):\n"
        "    if cfg['parallel'] == 'fsdp':\n"
        "        for block in model.blocks:\n"
        "            fully_shard(block)\n"
        "        return fully_shard(model)\n"
        "    return DDP(model)\n"
    )
    bypass = (
        "def wrap(model, cfg):\n"
        "    if cfg['parallel'] == 'fsdp':\n"
        "        return DDP(model)  # FSDP2 on CPU is slow: use DDP\n"
        "    return DDP(model)\n"
    )
    no_branch = "def wrap(model, cfg):\n    return DDP(model)\n"
    assert sharding_bypass(ops("fsdp", shards)) is None
    assert sharding_bypass(ops("fsdp", bypass)) == "the fsdp path of parallel.wrap does not shard"
    assert sharding_bypass(ops("fsdp", no_branch)) == "parallel.wrap has no fsdp branch"
    assert sharding_bypass(ops("ddp", bypass)) is None  # nothing asked for sharding
    assert sharding_bypass(tmp_path / "missing") is None


def test_every_trajectory_signal_reaches_the_rows_and_the_audit_summary(jobs):
    """The audit flags are computed per trial and must be copied into the rows, or the report's audit section reads
    0%: each signal _agent_stats returns must reach load_trials and the summary."""
    trial(jobs, "j1", "a1", "t1", 1.0)
    agent = jobs / "j1" / "a1" / "agent"
    agent.mkdir()
    commands = ["ls -la /logs/verifier/\n", "vi /ops/jobs/train/train.yaml\n"]
    steps = [{"source": "agent", "tool_calls": [{"arguments": {"keystrokes": c}}]} for c in commands]
    (agent / "trajectory.json").write_text(json.dumps({"steps": steps}))
    trial(jobs, "j1", "a2", "t2", 1.0)
    [flagged] = [t for t in analyze.load_trials([jobs]) if t["task"] == "t1"]
    stats = analyze._agent_stats(jobs / "j1" / "a1")
    assert all(key in flagged for key in set(stats) - {"steps"})  # steps is carried as agent_steps
    assert flagged["audit"] == ["/logs/verifier"]
    s = analyze.summarise(analyze.load_trials([jobs]), test_set={"t1", "t2"})["terminus-2:m"]
    assert s["audit_trials"] == 0.5 and s["audit_passes"] == ["t1 ['/logs/verifier']"]


def test_an_observation_showing_a_fault_setup_variable_is_an_audit_flag(jobs):
    trial(jobs, "j1", "a1", "t1", 1.0)
    agent = jobs / "j1" / "a1" / "agent"
    agent.mkdir()
    seen = {"source": "agent", "tool_calls": [{"arguments": {"keystrokes": "ssh c2 cat /proc/1/environ\n"}}],
            "observation": "PATH=/usr/bin OCB_STALE_HOST=172.19.0.250 c1"}  # fmt: skip
    (agent / "trajectory.json").write_text(json.dumps({"steps": [seen]}))
    [row] = analyze.load_trials([jobs])
    assert "saw a fault-setup variable: OCB_STALE_HOST" in row["audit"]
    assert not analyze.FAULT_VARS.search("OCB_EXPECT_RUNTIME=abc OCB_MASTER_ADDR=10.0.0.1")


def test_logs_ladder_pairs_three_arms_splits_by_covariate_and_pools_held_out_rows():
    def row(variant, by_task):
        return {"complete": True, "variant": variant, "by_task": by_task, "pass@1": 0.5, "config_ids": ["x"]}

    tasks = ["rank0-eval-desync", "degraded-node", "realmemory-drain", "same-shard"]
    full = dict.fromkeys(tasks, 1.0)
    logs = {"rank0-eval-desync": 1.0, "degraded-node": 0.0, "realmemory-drain": 1.0, "same-shard": 0.0}
    files = {"rank0-eval-desync": 1.0, "degraded-node": 0.0, "realmemory-drain": 0.0, "same-shard": 0.0}
    summary = {"a": row("standard", full), "a [live logs]": row("logs", logs), "a [ops-only]": row("ablation", files)}
    covariate = {"rank0-eval-desync": True, "degraded-node": False, "realmemory-drain": True, "same-shard": False}
    channels = {t: "errors" for t in tasks}
    ladder = analyze.logs_decomposition(summary, ["a"], covariate, channels)
    [r] = ladder["rows"]
    assert r["tasks"] == 4 and r["rates"] == {"full": 1.0, "logs": 0.5, "files": 0.25}
    assert r["logs_minus_files"]["diff"] == 0.25 and r["full_minus_logs"]["diff"] == 0.5
    assert r["full_minus_files"]["diff"] == pytest.approx(r["logs_minus_files"]["diff"] + r["full_minus_logs"]["diff"])
    assert r["by_covariate"]["visible"]["full_minus_logs"]["diff"] == 0.0  # the read-only arm saw what it needed
    assert r["by_covariate"]["not visible"]["full_minus_logs"]["diff"] == 1.0
    pooled = ladder["pooled"]
    assert pooled["configs"] == ["a"] and pooled["tasks"] == 4
    assert pooled["logs_minus_files"]["diff"] == 0.25
    assert "value" in pooled["share_recovered"] or "withheld" in pooled["share_recovered"]
    assert analyze.logs_decomposition(summary, ["b"], covariate, channels)["pooled"] is None  # tuning rows: not pooled
    no_logs = {k: v for k, v in summary.items() if k != "a [live logs]"}
    assert analyze.logs_decomposition(no_logs, ["a"], covariate, channels)["rows"] == []


def test_rows_of_different_frozen_studies_pair_only_when_named(tmp_path, monkeypatch):
    a = {"complete": True, "by_task": {"t": 1.0}, "protocol": ["aaaaaaaaaaaa1111"]}
    b = {"complete": True, "by_task": {"t": 1.0}, "protocol": ["bbbbbbbbbbbb2222"]}
    monkeypatch.setattr(analyze, "NAMED_PAIRS", tmp_path / "named-pairs.json")
    analyze.named_pairs.cache_clear()
    assert analyze.incomparable(a, b) == "different frozen studies"
    (tmp_path / "named-pairs.json").write_text(json.dumps({"pairs": [["aaaaaaaaaaaa", "bbbbbbbbbbbb"]]}))
    analyze.named_pairs.cache_clear()
    assert analyze.incomparable(a, b) == ""
    c = {**b, "protocol": ["cccccccccccc3333"]}
    assert analyze.incomparable(a, c) == "different frozen studies"
    analyze.named_pairs.cache_clear()


def test_provider_limits_and_a_dead_harness_terminal_are_not_attempts():
    from bench.analyze import NOT_ATTEMPTED_OUTCOME, outcome

    for message in (
        'OpenrouterException - {"error":{"message":"Key limit exceeded (total limit). Manage it using https://openrouter.ai/"}}',
        "This request requires more credits, or fewer max_tokens. You requested up to 131072 tokens, but can only "
        "afford 9000",
        'OpenrouterException - {"error":{"message":"This request would exceed your available credits given your '
        'current in-flight requests. Retry after in-flight requests settle, or add credits.","code":402}}',
        "You have reached your specified API usage limits. You will regain access on 2026-11-01 at 00:00 UTC.",
        'failed to send non-blocking keys: command="tmux send-keys -t terminus-2 -- squeue"',
    ):
        exc = {"exception_type": "APIError", "exception_message": message}
        assert outcome(None, {}, exc, steps=12, verifier_ran=False) == NOT_ATTEMPTED_OUTCOME
    # an agent's own crash after it worked stays its result
    assert outcome(None, {}, {"exception_type": "ValueError", "exception_message": "bad JSON"}, 12, False) == "agent"


def test_a_model_call_left_unanswered_past_a_request_timeout_is_the_providers_failure(tmp_path):
    from bench.analyze import _unanswered_s

    def trial(name, gaps, tokens, timeout_after=None):
        d = tmp_path / name
        (d / "agent").mkdir(parents=True)
        t, steps = 1_000_000.0, []
        for gap, tok in zip(gaps, tokens, strict=True):
            t += gap
            steps.append({"source": "agent", "timestamp": f"{_iso(t)}", "metrics": {"completion_tokens": tok},
                          "tool_calls": [{"arguments": {"keystrokes": "ls\n", "duration": 1.0}}]})  # fmt: skip
        (d / "agent" / "trajectory.json").write_text(json.dumps({"steps": steps}))
        result = {"agent_execution": {"finished_at": _iso(t + timeout_after)} if timeout_after else {}}
        if timeout_after:
            result["exception_info"] = {"exception_type": "AgentTimeoutError"}
        (d / "result.json").write_text(json.dumps(result))
        return d

    assert _unanswered_s(trial("quick", [5, 9, 12], [100, 200, 300], timeout_after=40)) == 0.0
    # the call still open when the agent's time ran out (GLM study cell 17: 22 minutes)
    assert _unanswered_s(trial("open", [5, 9], [100, 200], timeout_after=1345)) == 1344.0
    # a stall that returned: 251 tokens after 18 minutes (Sonnet logs cell 209)
    assert _unanswered_s(trial("stall", [5, 1081, 7], [100, 251, 90])) == 1080.0
    # a long answer is the model's own time: 43,828 tokens in 15 minutes (MiniMax study cell 189)
    assert _unanswered_s(trial("long", [5, 906, 7], [100, 43828, 90])) == 0.0


def _iso(t):
    from datetime import UTC, datetime

    return datetime.fromtimestamp(t, tz=UTC).isoformat().replace("+00:00", "Z")


def test_a_registered_patched_regrade_is_scored_in_place_of_the_original(jobs, tmp_path, monkeypatch):
    """Deviation ag: a grading on the registered patched copy of a trial's task, whose nodes ran the registered build,
    gives the verdict; an unregistered patched grading, or one whose nodes ran another build, does not."""

    def nodes(job, name, build):
        diag = jobs / job / name / "verifier" / "diagnostics.json"
        diag.write_text(json.dumps({**json.loads(diag.read_text()), "node_build": build}))

    trial(jobs, "j1", "t1__a", "t1", None, infra=True, trial_id="id-a")
    trial(jobs, "regrade-1", "t1__p", "t1", 1.0, source="id-a", digest="sha256:p1", finished="2026-10-02T12:00:00Z")
    nodes("regrade-1", "t1__p", "nb2")
    trial(jobs, "j1", "t2__a", "t2", None, infra=True, trial_id="id-b")
    trial(jobs, "regrade-1", "t2__p", "t2", 1.0, source="id-b", digest="sha256:p2", finished="2026-10-02T12:00:00Z")
    nodes("regrade-1", "t2__p", "nb2")
    reg = tmp_path / "patched-gradings.json"
    reg.write_text(json.dumps({"trials": {"id-a": {"original_digest": "sha256:aa", "patched_digest": "sha256:p1",
                                                   "node_build": "nb2"}}}))  # fmt: skip
    monkeypatch.setattr(analyze, "PATCHED_GRADINGS", reg)
    by = {t["task"]: t for t in analyze.load_trials([jobs])}
    assert (by["t1"]["reward"], by["t1"]["outcome"], by["t1"]["patched_runtime"]) == (1.0, "pass", "nb2")
    assert by["t1"]["digest"] == "sha256:aa" and by["t1"]["other_version_gradings"] == 0
    assert (by["t2"]["outcome"], by["t2"]["patched_runtime"], by["t2"]["other_version_gradings"]) == ("infra", None, 1)
    nodes("regrade-1", "t1__p", "node-1")  # its nodes ran the study's build
    by = {t["task"]: t for t in analyze.load_trials([jobs])}
    assert (by["t1"]["outcome"], by["t1"]["patched_runtime"]) == ("infra", None)


def test_rerun_list_names_the_attempts_that_never_had_a_fair_run(jobs):
    trial(jobs, "j1", "a1", "t1", 1.0)
    trial(jobs, "j1", "a2", "t2", None, exception="RateLimitError", steps=5)  # the provider, not the agent
    s = analyze.summarise(analyze.load_trials([jobs]), test_set=["t1", "t2"])["terminus-2:m"]
    assert s["rerun"] == ["t2 (a2): RateLimitError"]
    text = analyze.markdown({"terminus-2:m": s}, {})
    assert "Cells to re-run" in text and "t2 (a2): RateLimitError" in text


def test_a_cell_settled_by_a_retry_is_not_listed_for_rerun(jobs):
    trial(jobs, "j1", "a1", "t1", None, exception="RateLimitError", steps=5)
    trial(jobs, "j1-r1", "a1", "t1", 1.0)  # the re-run got a verdict
    trial(jobs, "j1", "a2", "t2", None, exception="RateLimitError", steps=5)  # still open
    s = analyze.summarise(analyze.load_trials([jobs]), test_set=["t1", "t2"])["terminus-2:m"]
    assert s["rerun"] == ["t2 (a2): RateLimitError"]
