"""The dispatcher runs the frozen schedule from one queue: numbered re-runs first, then pending cells in the frozen
order, under per-model caps, a control file read before every launch, and the same stops as bench.protocol; it adopts
cells a previous scheduler left running (bench.dispatch)."""

from __future__ import annotations

import json
import threading
import time

import pytest

from bench import dispatch, protocol, run


@pytest.fixture
def frozen(monkeypatch):
    inputs = {
        "tasks": {"task-a": "a", "task-b": "b"},
        "images": {"runtime": {"ref": "runtime:dev", "id": "sha256:build"}},
    }
    monkeypatch.setattr(protocol, "evaluation_inputs", lambda: inputs)
    monkeypatch.setattr(protocol, "image_tags", lambda: {"runtime": "runtime:dev"})
    monkeypatch.setattr(protocol.validation, "build", lambda: {t: {"green": True} for t in inputs["tasks"]})
    monkeypatch.setattr(run, "lite_tasks", lambda: ["task-b"])
    settings = {
        "seed": 7,
        "k": 1,
        "lite_k": 3,
        "max_trials": 16,
        "configurations": [
            {"model": "openrouter/qwen/qwen3.8-27b", "provider": "parasail/fp8", "reasoning_effort": "high"},
            {"model": "openrouter/z-ai/glm-5.3-flash", "provider": "baseten/fp8", "reasoning_effort": "high"},
        ],
    }
    return protocol.freeze(settings)


@pytest.fixture
def host(frozen, tmp_path, monkeypatch):
    """A frozen manifest and control file on disk, with launches (each holds its slot for `hold` seconds), cell
    states, spend, the host's concurrency and running processes under test control."""
    path, control = tmp_path / "manifest.json", tmp_path / "control.json"
    path.write_text(json.dumps(frozen))
    control.write_text(json.dumps({"workers": 4}))
    state = {"status": dict.fromkeys(range(len(frozen["schedule"])), "pending"), "launches": [], "spent": 0.0,
             "codes": {}, "measured": 8, "hold": 0.0, "inflight": {}, "peak": {}, "procs": {},
             "on_launch": None, "argv": {}}  # fmt: skip
    lock = threading.Lock()

    def launch(args):
        index = int(args[args.index("--cell") + 1])
        model = frozen["configurations"][frozen["schedule"][index]["configuration"]]["model"]
        with lock:
            state["launches"].append((index, args[args.index("--name") + 1]))
            state["argv"][index] = list(args)
            state["inflight"][model] = state["inflight"].get(model, 0) + 1
            state["peak"][model] = max(state["peak"].get(model, 0), state["inflight"][model])
            if state["on_launch"]:
                state["on_launch"](index)
        time.sleep(state["hold"])
        with lock:
            state["inflight"][model] -= 1
            state["status"][index] = "done"
        return state["codes"].get(index, 0)

    monkeypatch.setattr(protocol, "launch", launch)
    monkeypatch.setattr(protocol, "statuses", lambda manifest_id, cells: dict(state["status"]))
    monkeypatch.setattr(protocol, "spent", lambda manifest_id: state["spent"])
    monkeypatch.setattr(protocol, "paused_rows", lambda manifest, cap: {})
    monkeypatch.setattr(protocol.concurrency, "measured", lambda: state["measured"])
    monkeypatch.setattr(run, "routed_through", lambda env: [])
    monkeypatch.setattr(dispatch, "cell_process", lambda manifest, index, attempt: state["procs"].get(index))
    monkeypatch.setattr(dispatch, "_alive", lambda pid: pid in state["procs"].values())
    return path, control, frozen, state


def _go(path, control, poll=0.005):
    dispatch.dispatch(path, "unused.env", control, poll=poll)


def test_re_runs_go_first_then_pending_cells_in_the_frozen_order(host):
    path, control, manifest, state = host
    state["status"].update({0: "done", 5: "unscored"})
    control.write_text(json.dumps({"workers": 1, "retry": {"5": 1}}))
    _go(path, control)
    order = [i for i, _ in state["launches"]]
    assert order[0] == 5 and state["launches"][0][1] == protocol.cell_name(manifest["id"], 5, attempt=1)
    assert order[1:] == [i for i in range(len(manifest["schedule"])) if i not in (0, 5)]
    progress = json.loads(path.with_suffix(".progress.json").read_text())
    assert progress["attempts"] == {"5": 1} and progress["running"] == []


def test_a_re_run_already_launched_is_not_repeated(host):
    path, control, manifest, state = host
    state["status"] = dict.fromkeys(state["status"], "done")
    state["status"][3] = "unscored"
    path.with_suffix(".progress.json").write_text(
        json.dumps({"id": manifest["id"], "running": [], "attempts": {"3": 1}})
    )
    control.write_text(json.dumps({"workers": 2, "retry": {"3": 1}}))
    _go(path, control)
    assert state["launches"] == []  # attempt 1 ran before; attempt 2 needs its own listing
    control.write_text(json.dumps({"workers": 2, "retry": {"3": 2}}))
    _go(path, control)
    assert state["launches"] == [(3, protocol.cell_name(manifest["id"], 3, attempt=2))]


def test_a_cap_keeps_a_model_to_one_cell_while_the_others_fill_the_slots(host):
    path, control, manifest, state = host
    state["hold"] = 0.03
    control.write_text(json.dumps({"workers": 4, "caps": {"glm": 1}}))
    _go(path, control)
    assert len(state["launches"]) == len(manifest["schedule"])
    assert state["peak"]["openrouter/z-ai/glm-5.3-flash"] == 1
    assert state["peak"]["openrouter/qwen/qwen3.8-27b"] > 1


def test_the_control_file_is_read_before_every_launch(host):
    path, control, manifest, state = host
    glm = [i for i, c in enumerate(manifest["schedule"]) if c["configuration"] == 1]
    control.write_text(json.dumps({"workers": 1, "configurations": ["qwen"]}))

    def widen(index):  # after the first launch, the operator adds GLM's configuration
        if len(state["launches"]) == 1:
            control.write_text(json.dumps({"workers": 1, "configurations": ["qwen", "glm"]}))

    state["on_launch"] = widen
    _go(path, control)
    assert sorted(i for i, _ in state["launches"]) == list(range(len(manifest["schedule"])))
    assert state["launches"][0][0] not in glm


def test_stop_launches_nothing_more_and_the_running_cells_finish(host):
    path, control, _manifest, state = host
    state["hold"] = 0.02
    control.write_text(json.dumps({"workers": 2}))

    def stop(index):
        if len(state["launches"]) == 2:
            control.write_text(json.dumps({"workers": 2, "stop": True}))

    state["on_launch"] = stop
    _go(path, control)
    assert len(state["launches"]) == 2
    assert all(state["status"][i] == "done" for i, _ in state["launches"])


def test_cells_a_previous_scheduler_left_running_are_adopted_and_hold_their_slots(host):
    path, control, manifest, state = host
    path.with_suffix(".progress.json").write_text(json.dumps({"id": manifest["id"], "running": [3, 4], "attempts": {}}))
    state["procs"] = {3: 9001}  # 3 still runs; 4 has no process and no counted trial: an interrupted launch
    state["status"].update({3: "unscored", 4: "unscored"})  # a launched cell reads unscored until its trial counts
    control.write_text(json.dumps({"workers": 1}))

    def end_adopted():
        time.sleep(0.05)
        state["status"][3] = "done"
        state["procs"].clear()

    threading.Thread(target=end_adopted).start()
    started = time.monotonic()
    _go(path, control)
    assert state["launches"] and time.monotonic() - started >= 0.05  # the one slot waited for the adopted cell
    assert 3 not in [i for i, _ in state["launches"]] and 4 not in [i for i, _ in state["launches"]]
    progress = json.loads(path.with_suffix(".progress.json").read_text())
    assert progress["running"] == [4]  # still listed, for the protocol's dry run, until a numbered re-run


def test_budget_concurrency_and_repeated_launch_failures_stop_dispatching(host):
    path, control, manifest, state = host
    state["spent"] = 1e9
    manifest_budget = json.loads(path.read_text()).get("budget_usd")
    if manifest_budget is not None:
        with pytest.raises(ValueError, match="budget reached"):
            _go(path, control)
    state["spent"], state["measured"] = 0.0, 2
    control.write_text(json.dumps({"workers": 4}))
    with pytest.raises(ValueError, match="concurrency record"):
        _go(path, control)
    assert state["launches"] == []
    state["measured"] = 8
    state["codes"] = dict.fromkeys(range(len(manifest["schedule"])), 1)
    control.write_text(json.dumps({"workers": 1}))
    with pytest.raises(ValueError, match="consecutive launches exited nonzero"):
        _go(path, control)
    assert len(state["launches"]) == protocol.FAILED_LAUNCHES_MAX


def test_the_control_file_sets_the_total_budget_in_place_of_the_manifests(host):
    path, control, _manifest, state = host
    state["spent"] = 50.0
    control.write_text(json.dumps({"workers": 1, "budget_usd": 40}))
    with pytest.raises(ValueError, match=r"budget reached: \$50\.00 of \$40\.00"):
        _go(path, control)
    assert state["launches"] == []
    state["spent"] = 1e9  # far past any manifest budget: the control file's decides
    control.write_text(json.dumps({"workers": 1, "budget_usd": 1e10}))
    _go(path, control)
    assert state["launches"]


def test_an_unreadable_control_file_stops_dispatching(host):
    path, control, _manifest, state = host
    control.write_text("{not json")
    _go(path, control)
    assert state["launches"] == []


def test_add_retries_lists_each_unscored_cells_next_attempt(host):
    path, control, manifest, state = host
    state["status"].update({2: "unscored", 6: "unscored", 1: "done"})
    path.with_suffix(".progress.json").write_text(
        json.dumps({"id": manifest["id"], "running": [], "attempts": {"6": 1}})
    )
    assert dispatch.add_retries(path, control, [2, 6])["retry"] == {"2": 1, "6": 2}
    with pytest.raises(ValueError, match="only unscored cells re-run"):
        dispatch.add_retries(path, control, [1])


def test_cell_process_finds_a_cells_bench_run_by_its_name(tmp_path, frozen):
    name = protocol.cell_name(frozen["id"], 7, attempt=1)
    for pid, argv in {"123": ["python", "-m", "bench.run", "m", "t", "--name", name], "124": ["sleep", "1"]}.items():
        (tmp_path / pid).mkdir()
        (tmp_path / pid / "cmdline").write_bytes("\0".join(argv).encode() + b"\0")
    (tmp_path / "self").mkdir()
    assert dispatch.cell_process(frozen, 7, 1, proc=tmp_path) == 123
    assert dispatch.cell_process(frozen, 7, 0, proc=tmp_path) is None


def test_a_zombie_counts_as_ended(tmp_path, monkeypatch):
    import os

    monkeypatch.setattr(os, "kill", lambda pid, sig: None)
    for pid, state in {"5": "State:\tS (sleeping)", "6": "State:\tZ (zombie)"}.items():
        (tmp_path / pid).mkdir()
        (tmp_path / pid / "status").write_text(f"Name:\tpython\n{state}\n")
    assert dispatch._alive(5, proc=tmp_path) and not dispatch._alive(6, proc=tmp_path)
    assert not dispatch._alive(7, proc=tmp_path)  # no status: gone


def test_a_row_paused_by_its_budget_resumes_when_the_control_file_raises_it(host, monkeypatch):
    path, control, manifest, state = host
    monkeypatch.setattr(protocol, "paused_rows", lambda m, cap: {0: "over budget"} if (cap or 0) < 50 else {})
    control.write_text(json.dumps({"workers": 1, "row_budget_usd": 30}))
    qwen = [i for i, c in enumerate(manifest["schedule"]) if c["configuration"] == 0]

    def raise_budget(index):
        if len(state["launches"]) == 2:
            control.write_text(json.dumps({"workers": 1, "row_budget_usd": 60}))

    state["on_launch"] = raise_budget
    _go(path, control)
    order = [i for i, _ in state["launches"]]
    assert sorted(order) == list(range(len(manifest["schedule"])))  # every cell ran once the row resumed
    assert not set(order[:2]) & set(qwen)  # while paused, only the other row launched


def test_the_control_file_routes_a_models_cells_through_another_provider(host):
    path, control, manifest, state = host
    control.write_text(json.dumps({"workers": 2, "provider": {"glm": "z-ai/fp8"}}))
    _go(path, control)
    assert len(state["argv"]) == len(manifest["schedule"])
    for index, args in state["argv"].items():  # GLM's frozen pin is replaced; Qwen keeps its own
        glm = manifest["schedule"][index]["configuration"] == 1
        assert args.count("--provider") == 1
        assert args[args.index("--provider") + 1] == ("z-ai/fp8" if glm else "parasail/fp8")
    # a configuration pinned in code (no provider in the manifest) gets the route added
    unpinned = protocol.freeze({"seed": 7, "k": 1, "lite_k": 3, "max_trials": 16, "configurations": [
        {"model": "openrouter/qwen/qwen3.8-27b", "reasoning_effort": "high"}]})  # fmt: skip
    other = path.with_name("unpinned.json")
    other.write_text(json.dumps(unpinned))
    state["status"] = dict.fromkeys(range(len(unpinned["schedule"])), "pending")
    state["argv"].clear()
    control.write_text(json.dumps({"workers": 1, "provider": {"qwen": "deepinfra/bf16"}}))
    _go(other, control)
    assert len(state["argv"]) == len(unpinned["schedule"])
    assert all(
        a.count("--provider") == 1 and a[-2:] == ["--provider", "deepinfra/bf16"] for a in state["argv"].values()
    )
