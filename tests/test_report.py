"""Reward is 1 only when the job-completion check ran and every check passed."""

import json

from harness.verify.report import Report


def reward(tmp_path, checks):
    r = Report()
    r.complete = True
    for name, ok in checks:
        r.check(name, ok)
    r.write(tmp_path)
    return json.loads((tmp_path / "reward.json").read_text())["reward"]


def test_all_pass_with_required_check(tmp_path):
    assert reward(tmp_path, [("policy", True), ("job completed before deadline", True), ("held-out loss", True)]) == 1.0


def test_crash_after_policy_scores_zero(tmp_path):
    # The verifier raised after the policy check: only "policy" and the error check exist.
    assert reward(tmp_path, [("policy", True), ("verifier error", False)]) == 0.0


def test_missing_required_check_scores_zero(tmp_path):
    assert reward(tmp_path, [("policy", True)]) == 0.0


def test_any_failure_scores_zero(tmp_path):
    assert reward(tmp_path, [("job completed before deadline", True), ("held-out loss", False)]) == 0.0


def test_ctrf_written(tmp_path):
    reward(tmp_path, [("job completed before deadline", True)])
    ctrf = json.loads((tmp_path / "ctrf.json").read_text())
    assert ctrf["results"]["summary"]["passed"] == 1


def test_reward_file_has_only_reward(tmp_path):
    r = Report()
    r.complete = True
    r.diag["loss"] = 1.5
    r.check("job completed before deadline", True)
    r.write(tmp_path)
    assert json.loads((tmp_path / "reward.json").read_text()) == {"reward": 1.0}
    assert json.loads((tmp_path / "diagnostics.json").read_text())["loss"] == 1.5


def test_infrastructure_failure_leaves_no_reward_file(tmp_path):
    (tmp_path / "reward.json").write_text('{"reward": 0}')  # what test.sh writes before the verifier starts
    r = Report()
    r.complete = True
    r.check("policy", True)
    r.check("reference run completed", False, "deadline", blame="infra")
    r.write(tmp_path)
    assert not (tmp_path / "reward.json").exists()
    diag = json.loads((tmp_path / "diagnostics.json").read_text())
    assert diag["failure"] == "infra" and diag["infra_error"] == 1.0


def test_first_failure_decides_the_attribution(tmp_path):
    r = Report()
    r.complete = True
    r.check("job completed before deadline", False, "deadline reached")  # the agent's
    r.check("held-out loss", False, "evaluation timed out", blame="infra")
    r.write(tmp_path)
    assert json.loads((tmp_path / "reward.json").read_text()) == {"reward": 0.0}
    assert json.loads((tmp_path / "diagnostics.json").read_text())["failure"] == "agent"


def test_an_agent_failure_decides_over_an_earlier_infrastructure_failure(tmp_path):
    r = Report()
    r.complete = True
    r.check("job completed before deadline", True)
    r.check("checkpoints written", False, "the object store's listing could not be read", blame="infra")
    r.check("throughput vs reference", False, "ratio 0.38 (min 0.6)")  # the agent's: not a free re-run
    r.write(tmp_path)
    assert json.loads((tmp_path / "reward.json").read_text()) == {"reward": 0.0}
    assert json.loads((tmp_path / "diagnostics.json").read_text())["failure"] == "agent"


def test_verifier_crash_scores_zero_and_is_flagged(tmp_path):
    r = Report()
    r.complete = True
    r.check("policy", True)
    r.check("verifier error", False, "Traceback ...", blame="verifier_bug")
    r.write(tmp_path)
    assert json.loads((tmp_path / "reward.json").read_text()) == {"reward": 0.0}
    assert json.loads((tmp_path / "diagnostics.json").read_text())["failure"] == "verifier_bug"


def test_a_placeholder_or_a_zero_without_a_failed_check_is_the_verifiers(tmp_path):
    early = Report()  # the start-up write, or a verifier killed before its last write
    early.write(tmp_path)
    diag = json.loads((tmp_path / "diagnostics.json").read_text())
    assert diag["failure"] == "verifier_bug" and diag["complete"] == 0.0
    silent = Report()
    silent.complete = True  # finished, reward 0, but nothing failed: a gap in the verifier, not the agent's 0
    silent.write(tmp_path)
    assert json.loads((tmp_path / "diagnostics.json").read_text())["failure"] == "verifier_bug"


def test_a_verifier_killed_mid_run_is_never_a_negative(tmp_path):
    """SIGKILL after the start-up write leaves reward 0 with complete=0, a verifier bug."""
    import os
    import signal
    import subprocess
    import sys
    import time

    from bench import outcomes

    code = ("from pathlib import Path; from harness.verify.report import Report; "
            f"Report().write(Path({str(tmp_path)!r})); import time; time.sleep(60)")  # fmt: skip
    proc = subprocess.Popen([sys.executable, "-c", code])
    try:
        deadline = time.time() + 20
        while not (tmp_path / "diagnostics.json").exists() and time.time() < deadline:
            time.sleep(0.05)
    finally:
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait()
    record = {**json.loads((tmp_path / "diagnostics.json").read_text()),
              "reward": json.loads((tmp_path / "reward.json").read_text())["reward"]}  # fmt: skip
    assert record["reward"] == 0.0 and outcomes.kind(record) == outcomes.BUG
