"""The release bundle's flake bound and its reading of QA records."""

from __future__ import annotations

from bench.release_bundle import flake_bound, oracle_runs


def test_flake_bound_is_the_one_sided_95_percent_bound_when_nothing_failed():
    assert flake_bound(460, 460)["upper95"] == round(1 - 0.05 ** (1 / 460), 4)  # about 0.65%
    assert flake_bound(459, 460) == {"runs": 460, "failures": 1, "upper95": None}
    assert flake_bound(0, 0)["upper95"] is None


def test_oracle_runs_come_from_the_release_qa_check():
    record = {"checks": [{"check": "nop 3/3 score 0"}, {"check": "oracle 10/10 score 1"}]}
    assert oracle_runs(record) == (10, 10) and oracle_runs(None) == (0, 0)


def test_oracle_runs_pool_the_history_and_ignore_stale_records():
    inputs = {"grader_digest": "g1", "images": {"a": "1"}}
    record = {"inputs": inputs, "checks": [{"check": "oracle 10/10"}],
              "oracle_history": [{"passed": 9, "runs": 10}, {"passed": 10, "runs": 10}]}  # fmt: skip
    assert oracle_runs(record) == (19, 20)  # the flake that a re-run then passed stays counted
    assert oracle_runs(record, inputs) == (19, 20)
    assert oracle_runs(record, {**inputs, "grader_digest": "g2"}) == (0, 0)  # stale: proves nothing about what ships
    assert oracle_runs({"checks": [{"check": "oracle 10/10 ok"}]}) == (10, 10)  # a record from before histories
