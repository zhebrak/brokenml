"""check-baselines: the trivial baselines must cover every task of the split, each with a typed verdict."""

from __future__ import annotations

from bench.baselines import problems


def _t(task, reward, failure):
    return {"task": task, "reward": reward, "error": None, "infra": False, "dir": task,
            "rewards": {"failure": failure, "complete": 1.0}}  # fmt: skip


def test_missing_tasks_and_verifier_bugs_are_problems():
    oracle, nop = [_t("a", 1.0, "none")], [_t("a", 0.0, "verifier_bug")]
    found = problems(oracle, nop, expected={"a", "b"})
    assert any("oracle: no trial of ['b']" in p for p in found) and any("nop a" in p for p in found)
