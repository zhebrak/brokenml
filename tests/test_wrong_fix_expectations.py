"""Every wrong fix of the test and dev splits declares the check it must fail (wrong_fixes/<name>.expect), so the
sweep can tell a fix rejected for the intended reason from one rejected by a crash, a deadline or the policy."""

from __future__ import annotations

import re

import pytest

from bench import patches
from bench.spec import load_specs

CHECKS = {
    "policy", "cluster usable under /ops/cluster config", "cluster runs the platform's protected settings",
    "job's processes stopped", "site services kept running", "job completed before deadline", "no node drained",
    "final model exported", "all ranks trained", "validation logged", "every step trained once the run is stitched "
    "together", "ranks placed as required", "eval exports written", "checkpoints written", "held-out loss",
    "export loads into the platform model", "throughput vs reference", "engine ready", "all requests served",
    "p95 time to first token", "greedy outputs match the reference", "every GPU of the node used",
}  # fmt: skip


@pytest.mark.parametrize("spec", [s for s in load_specs() if s.split in ("test", "dev")], ids=lambda s: s.id)
def test_every_wrong_fix_names_known_checks_it_must_fail(spec):
    for name, path in patches.wrong_fix_patches(spec).items():
        expect = path.with_suffix(".expect")
        assert expect.exists(), f"{spec.id}: wrong fix {name} has no .expect"
        lines = [x.strip() for x in expect.read_text().splitlines() if x.strip() and not x.strip().startswith("#")]
        assert lines, f"{spec.id}: {name}.expect is empty"
        checks = [x.partition(": ")[0] for x in lines]
        unknown = [x for x in checks if x not in CHECKS and not re.fullmatch(r"\w+ logged", x)]
        assert not unknown, f"{spec.id}: {name}.expect names unknown checks {unknown}"


def test_an_expected_reason_must_appear_in_the_checks_message():
    from bench.outcomes import failed_for

    base = {"reward": 0.0, "failure": "agent", "complete": 1.0, "failed_checks": ["job completed before deadline"]}
    deadline = {**base, "failed_messages": {"job completed before deadline": "deadline reached"}}
    crash = {**base, "failed_messages": {"job completed before deadline": "a job did not complete"}}
    want = ["job completed before deadline: deadline reached"]
    assert failed_for(deadline, want) and not failed_for(crash, want)
    assert failed_for(crash, ["job completed before deadline"])  # a bare name accepts any reason
    assert not failed_for(base, want)  # no recorded message: the reason cannot be confirmed
