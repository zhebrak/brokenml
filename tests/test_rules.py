"""The verifier's checks as pure functions over the records a job wrote."""

from __future__ import annotations

import math

from harness.verify import rules


def recs(*steps, loss=2.0, **extra):
    return [{"step": s, "loss": loss, **extra} for s in steps]


def test_uncovered_is_at_least_every_n():
    assert rules.uncovered({100, 200}, 100, 1, 300) == [300]
    assert rules.uncovered({95, 190, 290}, 100, 1, 300) == []  # within each window, not exact multiples
    assert rules.uncovered(set(), 100, 250, 300) == [300]  # a resumed run is checked from where it started


def test_trained_ignores_malformed_records():
    records = rules.parse_metrics(
        ['{"step": 1, "loss": 2.0}', '"val_loss"', "not json", '{"step": true, "loss": 1.0}',
         '{"step": 2, "loss": NaN}', '{"step": "3", "loss": 1.0}', "[1, 2]", '{"step": 4, "loss": 1.5}']
    )  # fmt: skip
    assert [r["step"] for r in rules.trained(records)] == [1, 4]
    assert all(isinstance(r, dict) for r in records)


def test_validation_cadence():
    rank0 = [*recs(*range(1, 301)), {"step": 100, "val_loss": 2.0}, {"step": 200, "val_loss": 1.9}]
    check = rules.logged_every(rank0, "val_loss", 100, 1, 300, "validation logged", "val_loss")
    assert not check.ok and "[300]" in check.message and check.blame == rules.AGENT


def test_cadence_starts_where_the_verifier_says_not_where_the_records_start():
    # A job that logs only from step 301 on does not shrink the requirement: `first` is the verifier's.
    late = [*recs(*range(301, 1001)), {"step": 1000, "val_loss": 1.5}]
    assert not rules.logged_every(late, "val_loss", 100, 1, 1000, "validation logged", "val_loss").ok
    assert not rules.eval_exports({}, 10, 1, 20).ok
    assert not rules.checkpoints_written({}, {}, {}, 100, 1, 500, "/shared/ckpt").ok


def _ckpts(*steps):
    """Hashes as the verifier saw the checkpoints committed, and identical replicas."""
    hashes = {s: {"__0_0.distcp": f"h{s}", ".metadata": f"m{s}"} for s in steps}
    return hashes, {s: dict(files) for s, files in hashes.items()}


def test_checkpoints_for_a_resumed_run_start_after_the_resume_point():
    hashes, replicas = _ckpts(300, 400, 500)
    good = dict.fromkeys(hashes, "")
    assert rules.checkpoints_written(good, replicas, hashes, 100, 201, 500, "/shared/ckpt").ok
    two = {300: "", 500: ""}
    assert not rules.checkpoints_written(two, replicas, hashes, 100, 201, 500, "/shared/ckpt").ok


def test_a_checkpoint_counts_only_when_well_formed_and_replicated_in_full():
    hashes, replicas = _ckpts(100, 200)
    malformed = rules.checkpoints_written({100: "", 200: "optim.state.head.weight.exp_avg is missing"}, replicas,
                                          hashes, 100, 1, 200, "/shared/ckpt")  # fmt: skip
    assert not malformed.ok and "exp_avg is missing" in malformed.message and malformed.blame == rules.AGENT
    partial = {100: replicas[100], 200: {".metadata": "m200"}}  # one shard never reached the store
    check = rules.checkpoints_written({100: "", 200: ""}, partial, hashes, 100, 1, 200, "/shared/ckpt")
    assert not check.ok and "not replicated to the object store in full" in check.message
    other = {100: replicas[100], 200: {"__0_0.distcp": "something else", ".metadata": "m200"}}  # different bytes
    assert not rules.checkpoints_written({100: "", 200: ""}, other, hashes, 100, 1, 200, "/shared/ckpt").ok
    unknown = rules.checkpoints_written({100: "", 200: ""}, None, hashes, 100, 1, 200, "/shared/ckpt")
    assert not unknown.ok and unknown.blame == rules.INFRA


def test_step_coverage_needs_every_step_and_continuous_loss():
    first = recs(*range(1, 51), loss=2.0)
    second = recs(*range(51, 101), loss=2.1)
    assert rules.step_coverage([("1", first), ("2", second)], 100).ok
    assert not rules.step_coverage([("1", first)], 100).ok  # steps 51-100 never trained
    restarted = recs(*range(51, 101), loss=3.5)  # weights not carried over: loss jumps back up
    check = rules.step_coverage([("1", first), ("2", restarted)], 100)
    assert not check.ok and "starts at loss 3.50" in check.message


def test_all_ranks_trained_needs_a_trained_step_inside_the_run_from_every_rank():
    good = {r: recs(1, 2) for r in range(4)}
    assert rules.all_ranks_trained(good, 4, 1, 500).ok
    assert not rules.all_ranks_trained({0: recs(1), 2: recs(1)}, 4, 1, 500).ok
    empty = {0: recs(1), 1: [], 2: [], 3: []}  # rank files without records
    assert not rules.all_ranks_trained(empty, 4, 1, 500).ok
    late = {r: recs(501, 502) for r in range(4)}  # steps shifted past the end of the run
    assert not rules.all_ranks_trained(late, 4, 1, 500).ok


def test_heldout_attributes_each_failure():
    assert rules.heldout({"loss": 1.4, "floor": 1.3}, 1.5).ok
    assert not rules.heldout({"loss": 1.6, "floor": 1.3}, 1.5).ok
    load = rules.heldout({"error": "Missing key(s) in state_dict", "stage": "load"}, 1.5)
    assert load.name == "export loads into the platform model" and load.blame == rules.AGENT
    assert rules.heldout({"error": "slow", "timeout": True}, 1.5).blame == rules.INFRA
    assert rules.heldout({"error": "Traceback"}, 1.5).blame == rules.VERIFIER_BUG


def test_throughput_ratio():
    check, ratio = rules.throughput(40.0, 50.0, 0.67)
    assert check.ok and math.isclose(ratio, 0.8)
    assert not rules.throughput(40.0, 80.0, 0.67)[0].ok


def test_eval_exports_need_every_multiple_and_must_load():
    assert rules.eval_exports({10: "", 20: ""}, 10, 1, 20).ok
    missing = rules.eval_exports({10: ""}, 10, 1, 20)
    assert not missing.ok and "[20]" in missing.message
    broken = rules.eval_exports({10: "", 20: "Missing key(s)"}, 10, 1, 20)
    assert not broken.ok and "Missing key" in broken.message


def test_logged_every_ignores_non_finite_non_numeric_and_out_of_range_records():
    good = [{"step": s, "val_loss": 1.5} for s in (100, 200)]
    assert rules.logged_every(good, "val_loss", 100, 1, 200, "validation logged", "validation").ok
    for bad in ({"step": 200, "val_loss": float("nan")}, {"step": 200, "val_loss": "1.5"},
                {"step": True, "val_loss": 1.5}, {"step": 900, "val_loss": 1.5}):  # fmt: skip
        records = [good[0], bad]
        assert not rules.logged_every(records, "val_loss", 100, 1, 200, "validation logged", "validation").ok, bad


def test_parse_metrics_survives_oversized_integers_and_deep_nesting():
    # json raises ValueError (not JSONDecodeError) past the integer digit limit and RecursionError on deep nesting:
    # either would have crashed the verifier (a verifier bug, so a free re-grade for the job that wrote the record)
    assert rules.parse_metrics(['{"step": ' + "9" * 5000 + "}", "[" * 2000 + "]" * 2000, '{"step": 1}']) == [
        {"step": 1}
    ]


def test_numeric_metrics_reject_huge_json_integers_and_booleans():
    from harness.verify.rules import logged_every, trained

    for loss in (10**400, True, float("nan"), float("inf"), "2.0", None):
        assert trained([{"step": 1, "loss": loss}]) == []
        assert not logged_every([{"step": 1, "val_loss": loss}], "val_loss", 1, 1, 1, "eval", "loss").ok
    assert trained([{"step": 1, "loss": 2}]) == [{"step": 1, "loss": 2}]
