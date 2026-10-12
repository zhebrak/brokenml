"""Placement is measured on the nodes: declared ranks and CPU-busy processes must both show the contract's shape, and
the completion check's reason names what the verifier saw."""

from __future__ import annotations

from harness.verify.rules import placement
from harness.verify.run import RunResult, busy_share, process_sample


def sample(node, ticks, now, rows):
    text = "CLK 100\n" + "\n".join(f"{pid} {t} {ws} {rank}" for pid, t, ws, rank in rows)
    return process_sample(node, text, now, ticks, 0.3)


def test_busy_processes_need_cpu_time_between_two_samples_and_ranks_need_world_size():
    ticks: dict = {}
    first = sample("c1", ticks, 10.0, [(11, 1000, 1, "0"), (12, 1000, 1, "1"), (13, 50, 0, "x")])
    assert first == (2, 0)  # no interval yet
    second = sample("c1", ticks, 12.0, [(11, 1190, 1, "0"), (12, 1195, 1, "1"), (13, 52, 0, "x")])
    assert second == (2, 2)  # ranks burned ~0.95 CPU each; the launcher (pid 13) ~0.01
    # A faked rank (an idle process that declares RANK and WORLD_SIZE) counts as a rank but not as busy.
    third = sample("c2", ticks, 14.0, [(21, 10, 1, "2"), (22, 10, 1, "3")])
    fourth = sample("c2", ticks, 16.0, [(21, 10, 1, "2"), (22, 10, 1, "3")])
    assert third == (2, 0) and fourth == (2, 0)
    assert ("c1", 13) in ticks
    sample("c1", ticks, 18.0, [(11, 1300, 1, "0"), (12, 1300, 1, "1")])
    assert ("c1", 13) not in ticks  # gone processes are forgotten, so a reused pid starts a fresh interval


def test_placement_needs_declared_ranks_and_busy_processes_in_the_contracts_shape():
    assert placement({"c1": 2, "c2": 2}, 2, 2, {"c1": 2, "c2": 2}).ok
    assert placement({"c1": 2, "c2": 2}, 2, 2).ok  # GPU tasks: no busy count
    # Four real ranks on c1 with two of them hidden, and two idle fakes declared on c2: the RANK counts look right.
    faked = placement({"c1": 2, "c2": 2}, 2, 2, {"c1": 4, "c2": 0})
    assert not faked.ok and "busy processes c1: 4" in faked.message
    one_node = placement({"c1": 4}, 2, 2, {"c1": 4})
    assert not one_node.ok and "need 2 on each of 2 nodes" in one_node.message
    assert not placement({}, 2, 2, {}).ok


def test_the_completion_reason_names_what_the_verifier_saw():
    base = dict(cluster_ok=True, submitted=True, drained={}, elapsed_s=1.0)
    assert RunResult(finished=True, completed=True, **base).incomplete_reason() == ""
    slow = RunResult(finished=False, completed=False, why="deadline reached", **base)
    assert slow.incomplete_reason() == "deadline reached"
    rejected = RunResult(finished=False, completed=False, why="no job accepted", **base)
    assert rejected.incomplete_reason() == "no job accepted"
    timed_out = RunResult(finished=True, completed=False, states={"7": "TIMEOUT(TimeLimit)", "8": "COMPLETED"}, **base)
    assert timed_out.incomplete_reason() == "a job did not complete: TIMEOUT(TimeLimit)"
    assert RunResult(finished=True, completed=False, **base).incomplete_reason() == "a job did not complete: no job ran"


def test_host_busy_subtracts_the_clusters_own_cpu():
    assert busy_share((100, 1000), (400, 1600)) == 0.5
    assert busy_share((100, 1000), (400, 1600), own_usec=2_000_000) == 0.167  # 200 of the 300 busy ticks were the job
    assert busy_share((100, 1000), (400, 1600), own_usec=9_000_000) == 0.0  # never negative
