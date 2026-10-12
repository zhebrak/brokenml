"""The verifier records how busy the host was while it timed each run (a diagnostic, never a rule)."""

from __future__ import annotations

from harness.verify.run import busy_share, host_cpu


def test_busy_share_is_the_busy_fraction_of_the_interval() -> None:
    assert busy_share((100, 1000), (400, 1600)) == 0.5
    assert busy_share(None, (1, 2)) is None
    assert busy_share((5, 10), (5, 10)) is None  # no time passed
    now = host_cpu()
    assert now is None or 0 <= now[0] <= now[1]


def test_load_shift_is_zero_when_either_run_was_not_measured():
    from harness.verify.run import LOAD_SHIFT, load_shift

    assert load_shift(0.3, 0.6) == 0.3 >= LOAD_SHIFT
    assert load_shift(None, 0.9) == 0.0 and load_shift(0.5, 0.55) < LOAD_SHIFT


def test_a_shifted_pair_is_infrastructures_only_when_the_shift_could_have_decided_a_close_verdict():
    from harness.verify import rules
    from harness.verify.report import Report

    close_pass, ratio = rules.throughput(30.0, 36.0, 0.67)  # ratio 0.83: within TPUT_MARGIN of the minimum
    assert close_pass.ok
    # A busier reference run inflates the ratio: a close pass under it is the shift's, re-graded as infra.
    verdict = rules.timed(close_pass, ratio, 0.67, ref_busy=0.75, job_busy=0.30)
    assert not verdict.ok and verdict.blame == rules.INFRA
    # The same pass with the busier job run stands: load worked against it.
    assert rules.timed(close_pass, ratio, 0.67, ref_busy=0.30, job_busy=0.75) is close_pass
    close_fail, ratio = rules.throughput(30.0, 50.0, 0.67)  # ratio 0.6
    assert not close_fail.ok
    assert rules.timed(close_fail, ratio, 0.67, ref_busy=0.30, job_busy=0.75).blame == rules.INFRA
    assert rules.timed(close_fail, ratio, 0.67, ref_busy=0.75, job_busy=0.30) is close_fail  # the agent's failure
    decisive, ratio = rules.throughput(30.0, 22.0, 0.67)  # ratio 1.36: no shift can have decided it
    assert rules.timed(decisive, ratio, 0.67, ref_busy=0.75, job_busy=0.30) is decisive
    assert rules.timed(close_pass, 0.83, 0.67, ref_busy=0.60, job_busy=0.65) is close_pass  # comparable load
    report = Report()
    report.check("held-out loss", False)
    report.add(rules.timed(close_pass, 0.83, 0.67, ref_busy=0.75, job_busy=0.30))
    assert report.failure == "agent"  # contention never buys an already broken job another chance


def test_analyze_and_the_verifier_agree_on_the_load_shift_threshold() -> None:
    from bench.analyze import BUSY_SHIFT
    from harness.verify.run import LOAD_SHIFT

    assert BUSY_SHIFT == LOAD_SHIFT
