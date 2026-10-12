"""What a verifier record says, typed. Every gate (sweep, qa, margins, check-baselines) and the analysis read a verdict
through `kind`, so an infrastructure failure or a grader that crashed or was killed is never counted as a result:

  pass          reward 1, nothing failed
  agent         reward 0 because the job as configured in /ops failed a check
  infra         no verdict for reasons /ops cannot cause (no reward, or the verifier blamed infrastructure)
  verifier_bug  the verifier did not finish (start-up placeholder still in place), crashed, or scored 0 without a
                failed check: never evidence, never the agent's 0

A negative control (broken job, wrong fix, nop) counts only as `agent`; a positive one only as `pass`.
"""

from __future__ import annotations

PASS, AGENT, INFRA, BUG = "pass", "agent", "infra", "verifier_bug"


def kind(record: dict | None) -> str:
    """The type of a verifier record (diagnostics.json plus `reward`)."""
    record = record or {}
    reward = record.get("reward")
    if reward is None or record.get("infra_error") or record.get("failure") == "infra":
        return INFRA
    if record.get("complete", 1.0) != 1.0:  # verifiers before 2026-10-02 did not record completion
        return BUG
    failure = record.get("failure")
    if reward == 1.0 and failure in (None, "none"):
        return PASS
    if reward == 0.0 and failure in ("agent", None):  # no failure field: records older than typed failures
        return AGENT
    return BUG


def failed_for(record: dict | None, expected: list[str]) -> bool:
    """Whether a negative control failed for one of the expected reasons: a check name (or `policy`), optionally with
    the reason its message must contain (`job completed before deadline: deadline reached`), so a crash cannot stand
    in for the intended failure of the same check."""
    record = record or {}
    if kind(record) != AGENT:
        return False
    failed, messages = set(record.get("failed_checks") or []), record.get("failed_messages") or {}
    for want in expected:
        name, _, reason = want.partition(": ")
        if name in failed and (not reason or reason in messages.get(name, "")):
            return True
    return False
