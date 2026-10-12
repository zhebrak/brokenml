"""Verifier report: per-check results (CTRF), diagnostics, failure attribution and the binary reward.

Every failed check names whose failure it is:
  agent         the job, as configured in /ops, does not meet its spec          -> reward 0
  infra         something /ops cannot influence failed (provisioning, the       -> no reward file: Harbor records the
                reference run, a node's first-start setup, an eval timeout)        trial as errored, to be re-run
  verifier_bug  the verifier itself crashed                                     -> reward 0, flagged for review
An agent failure decides over any other; otherwise the first failure does. test.sh writes {"reward": 0} before the
verifier starts, so a crash anywhere leaves 0.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from harness.verify.rules import AGENT, INFRA, VERIFIER_BUG, Check

LOGS = Path("/logs/verifier")
REQUIRED = {"job completed before deadline"}


class Report:
    def __init__(self, required: set[str] | None = None) -> None:
        self.required = required or REQUIRED
        self.tests: list[dict] = []
        self.diag: dict[str, float | str] = {}
        self.failure: str | None = None
        self.complete = False  # set by the verifier's last write only: an earlier record is a placeholder
        self.t0 = self._last = time.time()

    def check(self, name: str, ok: bool, message: str = "", blame: str = AGENT) -> bool:
        assert blame in (AGENT, INFRA, VERIFIER_BUG), blame
        now = (
            time.time()
        )  # CTRF timing: the work since the previous check is this check's (a slow verifier shows where)
        test: dict[str, object] = {"name": name, "status": "passed" if ok else "failed", "message": message,
                                   "duration": int((now - self._last) * 1000), "start": int(self._last * 1000),
                                   "stop": int(now * 1000)}  # fmt: skip
        self._last = now
        if not ok:
            test["extra"] = {"blame": blame}
            # A later check the infrastructure failed (say, an unreadable store listing) must not turn a job that
            # already failed its spec into an errored trial that is re-run.
            if self.failure is None or blame == AGENT:
                self.failure = blame
        self.tests.append(test)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {message}" if message else ""), flush=True)
        return ok

    def add(self, c: Check) -> bool:
        return self.check(c.name, c.ok, c.message, c.blame)

    @property
    def reward(self) -> float:
        # Reward 1 needs the job-completion check to have run and passed, and every other check to pass.
        names = {t["name"] for t in self.tests if t["status"] == "passed"}
        return float(self.required <= names and all(t["status"] == "passed" for t in self.tests))

    def write(self, logs: Path = LOGS) -> None:
        reward = self.reward
        # A placeholder (written before grading, left by a killed verifier) or a 0 with no failed check is the
        # verifier's, never the agent's: bench.outcomes reads `complete` and `failure`.
        failure = self.failure or ("none" if reward == 1.0 else VERIFIER_BUG)
        if not self.complete:
            failure = VERIFIER_BUG
        self.diag.update(failure=failure, infra_error=float(failure == INFRA), complete=float(self.complete))
        logs.mkdir(parents=True, exist_ok=True)
        reward_file = logs / "reward.json"
        if failure == INFRA:
            reward_file.unlink(missing_ok=True)  # no reward: an infrastructure failure is not the agent's 0
        else:
            # reward.json holds only the reward: Harbor computes pass@k only for single-key rewards.
            reward_file.write_text(json.dumps({"reward": reward}))
        (logs / "diagnostics.json").write_text(json.dumps({"reward": reward, **self.diag}))
        passed = sum(t["status"] == "passed" for t in self.tests)
        ctrf = {
            "results": {
                "tool": {"name": "harness.verify"},
                "summary": {
                    "tests": len(self.tests),
                    "passed": passed,
                    "failed": len(self.tests) - passed,
                    "start": int(self.t0 * 1000),
                    "stop": int(time.time() * 1000),
                },
                "tests": self.tests,
                "extra": {"diagnostics": self.diag},
            }
        }
        (logs / "ctrf.json").write_text(json.dumps(ctrf, indent=1))
        shown = "none (infrastructure failure)" if failure == INFRA else reward
        print(f"reward={shown} {json.dumps(self.diag)}", flush=True)
