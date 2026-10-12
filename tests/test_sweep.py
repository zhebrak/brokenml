from bench import sweep


def test_separating_task_passes():
    rows = {"reference": {"reward": 1.0}, "pristine": {"reward": 0.0}, "wrong:a": {"reward": 0.0}}
    assert sweep.verdict(rows) == (sweep.PASS, "ok")


def test_wrong_fix_that_passes_fails_the_task():
    rows = {"reference": {"reward": 1.0}, "pristine": {"reward": 0.0}, "wrong:skip-save": {"reward": 1.0}}
    state, why = sweep.verdict(rows)
    assert state == sweep.FAIL and "wrong:skip-save passes" in why


def test_missing_runs_and_broken_pass_are_reported():
    state, why = sweep.verdict({"pristine": {"reward": 1.0}})
    assert state == sweep.FAIL and "broken job passes" in why and "not run: reference" in why


def test_infrastructure_errors_are_inconclusive_not_passes():
    # A throughput task whose reference run failed: every variant "scores 0", which proves nothing.
    rows = {
        "reference": {"reward": 0.0, "infra_error": 1.0},
        "pristine": {"reward": 0.0, "infra_error": 1.0},
        "wrong:a": {"reward": 0.0, "infra_error": 1.0},
    }
    state, why = sweep.verdict(rows)
    assert state == sweep.INCONCLUSIVE and "infrastructure error" in why


def test_verifier_crash_without_diagnostics_is_inconclusive():
    rows = {"reference": {"reward": 1.0}, "pristine": {"reward": None, "infra_error": 1.0}}
    assert sweep.verdict(rows)[0] == sweep.INCONCLUSIVE


def test_read_records_takes_the_header_and_last_run(tmp_path):
    log = tmp_path / "x.jsonl"
    log.write_text(
        '{"task": "t", "task_digest": "sha256:ab", "stamp": {"git_sha": "1"}}\n'
        '{"task": "t", "variant": "reference", "run": 1, "reward": 0.0}\n'
        '{"task": "t", "variant": "reference", "run": 2, "reward": 1.0, "loss": 1.5}\n'
        "not json\n"
    )
    header, rows = sweep.read_records(log)
    assert header["task_digest"] == "sha256:ab"
    assert rows == {"reference": {"reward": 1.0, "loss": 1.5}}


def test_wrong_fixes_that_never_ran_make_the_task_inconclusive():
    rows = {"reference": {"reward": 1.0}, "pristine": {"reward": 0.0}}
    state, why = sweep.verdict(rows, ["reference", "pristine", "wrong:skip-save"])
    assert state == sweep.INCONCLUSIVE and "wrong:skip-save" in why


def test_an_outright_failure_beats_missing_runs():
    rows = {"reference": {"reward": 0.0}}
    assert sweep.verdict(rows, ["reference", "pristine"])[0] == sweep.FAIL


def test_expected_variants_include_every_wrong_fix():
    names = sweep.expected_variants("degraded-node")
    assert names[:2] == ["reference", "pristine"] and "wrong:clone-reference-job" in names


TOML = '[task]\nname = "brokenml/t"\nversion = "{v}"\n[metadata]\ncategory = "{cat}"\n[verifier]\ntimeout_sec = {t}\n'


def _task(tmp_path):
    d = tmp_path / "t"
    (d / "environment" / "ops").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "task.toml").write_text(TOML.format(v="0.1.0", cat="memory", t=600))
    (d / "instruction.md").write_text("Fix the job.\n")
    (d / "environment" / "ops" / "RUNBOOK.md").write_text("Tools.\n")
    (d / "environment" / "ops" / "train.yaml").write_text("steps: 500\n")
    (d / "tests" / "verify.yaml").write_text("loss_max: 1.5\n")
    (d / "environment" / "bootstrap.yaml").write_text("spec: Train it.\nsymptom: {kind: failed}\n")
    return d


def test_grader_digest_ignores_text_and_metadata_but_not_grading_inputs(tmp_path):
    from bench.provenance import grader_digest, task_digest

    d = _task(tmp_path)
    g, t = grader_digest(d), task_digest(d)
    (d / "instruction.md").write_text("Fix the job, please.\n")
    (d / "environment" / "ops" / "RUNBOOK.md").write_text("Tools and versions.\n")
    (d / "environment" / "bootstrap.yaml").write_text("spec: Train it well.\nsymptom: {kind: failed}\n")
    (d / "task.toml").write_text(TOML.format(v="0.2.0", cat="state", t=600))  # relabel and version bump
    assert grader_digest(d) == g and task_digest(d) != t
    (d / "task.toml").write_text(TOML.format(v="0.2.0", cat="state", t=900))
    assert grader_digest(d) != g
    g = grader_digest(d)
    (d / "task.toml").write_text(TOML.format(v="0.2.0", cat="state", t=900) + "[agent]\ntimeout_sec = 1800.0\n")
    assert grader_digest(d) == g and task_digest(d) != t  # the agent's time budget is a row attribute, not grading
    (d / "environment" / "ops" / "train.yaml").write_text("steps: 250\n")
    assert grader_digest(d) != g
    g = grader_digest(d)
    (d / "environment" / "bootstrap.yaml").write_text("spec: Train it well.\nsymptom: {kind: completed}\n")
    assert grader_digest(d) != g


def test_calibration_digest_ignores_the_thresholds_a_set_exists_to_set(tmp_path):
    from bench.provenance import calibration_digest, grader_digest

    d = _task(tmp_path)
    (d / "tests" / "verify.yaml").write_text("loss_max: 1.5\nthroughput: {ratio_min: 0.67}\nttft_p95_max_s: 3\n")
    c, g = calibration_digest(d), grader_digest(d)
    (d / "tests" / "verify.yaml").write_text("loss_max: 1.43\nthroughput: {ratio_min: 0.7}\nttft_p95_max_s: 2\n")
    assert calibration_digest(d) == c and grader_digest(d) != g  # retuned thresholds: the measurements still hold
    (d / "tests" / "verify.yaml").write_text("loss_max: 1.43\nttft_p95_max_s: 2\n")
    assert calibration_digest(d) != c  # whether a throughput rule exists decides what gets measured: an input
    (d / "tests" / "verify.yaml").write_text(
        "loss_max: 1.43\nthroughput: {ratio_min: 0.7}\nttft_p95_max_s: 2\ndeadline_s: 900\n"
    )
    assert calibration_digest(d) != c  # anything else in the verifier's rules is an input
    c = calibration_digest(d)
    (d / "environment" / "ops" / "train.yaml").write_text("steps: 250\n")
    assert calibration_digest(d) != c


def test_fresh_uses_the_grader_digest_and_falls_back_for_legacy_rows():
    now = {"task_digest": "t2", "grader_digest": "g1", "wrong_fixes": "w", "images": {"r": "1"}}
    assert sweep.fresh({**now, "task_digest": "t1"}, now)  # wording changed, grading did not
    assert not sweep.fresh({**now, "task_digest": "t1", "grader_digest": "g0"}, now)  # grading changed
    assert sweep.fresh({**now, "grader_digest": "g0"}, now)  # byte-identical task: only the digest's definition moved
    assert not sweep.fresh({**now, "images": {"r": "2"}}, now)
    legacy = {"task_digest": "t1", "wrong_fixes": "w", "images": {"r": "1"}}
    assert not sweep.fresh(legacy, now) and sweep.fresh({**legacy, "task_digest": "t2"}, now)
    assert not sweep.fresh(None, now)


def test_adopting_grader_digests_only_migrates_rows_that_are_current(monkeypatch, tmp_path):
    now = {"task_digest": "t1", "grader_digest": "g1", "wrong_fixes": "w", "images": {}}
    monkeypatch.setattr(sweep, "inputs", lambda task: now)

    def task_dir(task):
        if task == "retired":
            raise KeyError(task)
        return tmp_path

    monkeypatch.setattr(sweep, "task_dir", task_dir)
    table = {"tasks": {"a": {"inputs": {"task_digest": "t1", "wrong_fixes": "w", "images": {}}},
                       "b": {"inputs": {"task_digest": "t0", "wrong_fixes": "w", "images": {}}},
                       "retired": {"inputs": {"task_digest": "t1", "wrong_fixes": "w", "images": {}}}}}  # fmt: skip
    assert sweep.adopt_grader_digests(table) == ["a"]
    assert table["tasks"]["a"]["inputs"]["grader_digest"] == "g1"
    assert "grader_digest" not in table["tasks"]["b"]["inputs"]


def test_accepted_fixes_must_pass_and_change_only_their_own_rows_inputs():
    rows = {"reference": {"reward": 1.0}, "pristine": {"reward": 0.0}, "accepted:alt": {"reward": 0.0}}
    state, why = sweep.verdict(rows, ["reference", "pristine", "accepted:alt"])
    assert state == sweep.FAIL and "accepted:alt fails" in why
    rows["accepted:alt"] = {"reward": 1.0}
    assert sweep.verdict(rows, ["reference", "pristine", "accepted:alt"])[0] == sweep.PASS
    now = {"grader_digest": "g", "wrong_fixes": "w", "images": {}}
    assert sweep.fresh(dict(now), now)  # a task without accepted fixes: rows recorded before the key stay fresh
    assert not sweep.fresh(dict(now), {**now, "accepted_fixes": "a"})  # a task that gains them must run them


def test_a_crashed_or_killed_grader_is_never_a_negative_control():
    ref = {"reward": 1.0, "failure": "none", "complete": 1.0}
    bug = {"reward": 0.0, "failure": "verifier_bug", "complete": 1.0}
    killed = {"reward": 0.0, "failure": "verifier_bug", "complete": 0.0}  # start-up placeholder left behind
    for broken in (bug, killed):
        state, why = sweep.verdict({"reference": ref, "pristine": broken})
        assert state == sweep.FAIL and "verifier bug" in why


def test_a_wrong_fix_must_fail_on_the_check_it_declares():
    ref = {"reward": 1.0, "failure": "none", "complete": 1.0}
    broken = {"reward": 0.0, "failure": "agent", "complete": 1.0, "failed_checks": ["job completed before deadline"]}
    shortcut = {"reward": 0.0, "failure": "agent", "complete": 1.0, "failed_checks": ["policy"]}
    rows = {"reference": ref, "pristine": broken, "wrong:skip-eval": shortcut}
    state, why = sweep.verdict(rows, None, {"wrong:skip-eval": ["validation logged"]})
    assert state == sweep.FAIL and "failed on policy, not on validation logged" in why
    assert sweep.verdict(rows, None, {"wrong:skip-eval": ["policy"]})[0] == sweep.PASS  # a declared contract shortcut
