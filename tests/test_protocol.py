"""A scored schedule is frozen before launches, runs at the measured concurrency, reads each cell's state from its
jobs, and never repeats a cell on its own."""

from __future__ import annotations

import json

import pytest

from bench import protocol, run


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
        "max_trials": 8,
        "configurations": [{"model": "anthropic/model", "reasoning_effort": "high"}],
    }
    return settings, inputs


@pytest.fixture
def scheduler(frozen, tmp_path, monkeypatch):
    """A frozen manifest on disk, with launches, cell states, spend and the host's concurrency under test control."""
    settings, _ = frozen
    path = tmp_path / "manifest.json"
    manifest = protocol.freeze(settings)
    path.write_text(json.dumps(manifest))
    state = {"status": dict.fromkeys(range(len(manifest["schedule"])), "pending"), "launches": [], "spent": 0.0,
             "codes": {}, "measured": 1}  # fmt: skip

    def launch(args):
        index = int(args[args.index("--cell") + 1])
        state["launches"].append((index, args[args.index("--name") + 1]))
        state["status"][index] = "done"
        return state["codes"].get(index, 0)

    monkeypatch.setattr(protocol, "launch", launch)
    monkeypatch.setattr(protocol, "statuses", lambda manifest_id, cells: dict(state["status"]))
    monkeypatch.setattr(protocol, "spent", lambda manifest_id: state["spent"])
    monkeypatch.setattr(protocol.concurrency, "measured", lambda: state["measured"])
    monkeypatch.setattr(run, "routed_through", lambda env: [])
    return path, manifest, state


def test_freeze_has_reproducible_complete_schedule_and_explicit_limit(frozen):
    settings, _ = frozen
    first = protocol.freeze(settings)
    assert first == protocol.freeze(settings)
    assert len(first["schedule"]) == 8
    assert sum(c["task"] == "task-b" for c in first["schedule"]) == 6
    assert protocol.freeze({**settings, "seed": 8})["schedule"] != first["schedule"]
    with pytest.raises(ValueError, match="above max_trials"):
        protocol.freeze({**settings, "max_trials": 7})
    with pytest.raises(ValueError, match="reasoning_effort"):
        protocol.freeze({**settings, "configurations": [{"model": "anthropic/model"}]})
    with pytest.raises(ValueError, match="study decisions"):
        protocol.freeze({k: v for k, v in settings.items() if k != "k"})  # no default k: the count is a decision
    with pytest.raises(ValueError, match="budget_usd"):
        protocol.freeze({**settings, "budget_usd": -1})
    assert protocol.freeze({**settings, "budget_usd": 120})["budget_usd"] == 120


def test_manifest_rejects_changed_inputs_unbuilt_images_and_unqualified_tasks(frozen, monkeypatch):
    settings, inputs = frozen
    manifest = protocol.freeze(settings)
    protocol.validate(manifest)
    with pytest.raises(ValueError, match="changed after freezing"):
        protocol.validate({**manifest, "seed": 10})
    monkeypatch.setattr(protocol.validation, "build", lambda: {"task-a": {"green": False}})
    with pytest.raises(ValueError, match="not qualified"):
        protocol.validate(manifest)
    inputs["images"]["runtime"]["id"] = ""
    with pytest.raises(ValueError, match="built here"):
        protocol.freeze(settings)


def test_schedule_launches_pending_cells_in_order_and_lists_the_unscored(scheduler, capsys):
    path, manifest, state = scheduler
    state["status"].update({0: "done", 2: "unscored"})
    protocol.run_schedule(path, "unused.env")
    assert [i for i, _ in state["launches"]] == [1, 3, 4, 5, 6, 7]  # the frozen order, nothing repeated
    assert all(name == protocol.cell_name(manifest["id"], i) for i, name in state["launches"])
    out = capsys.readouterr().out
    assert "unscored [2]" in out and "--retry-cell 2" in out
    progress = json.loads(path.with_suffix(".progress.json").read_text())
    assert progress["running"] == [] and progress["id"] == manifest["id"]


def test_an_interrupted_launch_blocks_the_schedule_until_retried_as_a_numbered_attempt(scheduler):
    path, manifest, state = scheduler
    path.with_suffix(".progress.json").write_text(json.dumps({"id": manifest["id"], "running": [3], "attempts": {}}))
    with pytest.raises(ValueError, match="interrupted launches \\[3\\]"):
        protocol.run_schedule(path, "unused.env")
    assert state["launches"] == []
    state["status"][3] = "unscored"
    protocol.run_schedule(path, "unused.env", retry=[3])
    assert state["launches"] == [(3, protocol.cell_name(manifest["id"], 3, attempt=1))]
    progress = json.loads(path.with_suffix(".progress.json").read_text())
    assert progress["attempts"] == {"3": 1} and progress["running"] == []
    protocol.run_schedule(path, "unused.env")  # the schedule continues once the interruption is resolved
    assert sorted(i for i, _ in state["launches"]) == [0, 1, 2, 3, 4, 5, 6, 7]


def test_a_configuration_block_runs_only_its_cells_in_the_frozen_order(frozen, tmp_path, monkeypatch, scheduler):
    path, manifest, state = scheduler
    two = protocol.freeze({**{k: v for k, v in manifest.items() if k != "id"}, "max_trials": 16, "configurations": [
        {"model": "openrouter/qwen/qwen3.8-27b", "provider": "parasail/fp8", "reasoning_effort": "high"},
        {"model": "anthropic/claude-sonnet-5-5", "reasoning_effort": "high"}]})  # fmt: skip
    path.write_text(json.dumps(two))
    state["status"] = dict.fromkeys(range(len(two["schedule"])), "pending")
    protocol.run_schedule(path, "unused.env", configurations=["qwen"])
    launched = [i for i, _ in state["launches"]]
    assert launched and all(two["schedule"][i]["configuration"] == 0 for i in launched)
    assert launched == sorted(launched)  # the frozen order within the block
    assert len(launched) == len(two["schedule"]) // 2
    with pytest.raises(ValueError, match="no configuration matches"):
        protocol.run_schedule(path, "unused.env", configurations=["gemini"])


def test_retry_refuses_a_cell_with_a_counted_trial_or_never_launched(scheduler):
    path, _, state = scheduler
    state["status"][1] = "done"
    with pytest.raises(ValueError, match="already holds a counted trial"):
        protocol.run_schedule(path, "unused.env", retry=[1])
    with pytest.raises(ValueError, match="never launched"):
        protocol.run_schedule(path, "unused.env", retry=[2])
    assert state["launches"] == []


def test_dry_schedule_does_not_launch_or_write_progress(scheduler, capsys):
    path, _, state = scheduler
    protocol.run_schedule(path, "unused.env", dry_run=True)
    assert state["launches"] == [] and not path.with_suffix(".progress.json").exists()
    assert "8 launches, 1 at a time" in capsys.readouterr().out


def test_workers_are_bounded_by_the_measured_concurrency(scheduler):
    path, _, state = scheduler
    state["measured"] = None
    with pytest.raises(ValueError, match="no current concurrency measurement"):
        protocol.run_schedule(path, "unused.env")
    state["measured"] = 0
    with pytest.raises(ValueError, match="no current concurrency measurement"):
        protocol.run_schedule(path, "unused.env")
    state["measured"] = 2
    with pytest.raises(ValueError, match="between 1 and the measured concurrency, 2"):
        protocol.run_schedule(path, "unused.env", workers=3)
    assert state["launches"] == []
    protocol.run_schedule(path, "unused.env", workers=2)
    assert sorted(i for i, _ in state["launches"]) == list(range(8))


def test_budget_and_repeated_launch_failures_stop_dispatching(scheduler):
    path, _, state = scheduler
    state["spent"] = 150.0
    manifest = json.loads(path.read_text())
    budgeted = protocol.freeze({**{k: v for k, v in manifest.items() if k != "id"}, "budget_usd": 100})
    path.write_text(json.dumps(budgeted))
    with pytest.raises(ValueError, match="budget reached"):
        protocol.run_schedule(path, "unused.env")
    assert state["launches"] == []
    state["spent"] = 0.0
    state["codes"] = dict.fromkeys(range(8), 1)  # Harbor itself keeps exiting nonzero: the host, not the cells
    with pytest.raises(ValueError, match="consecutive launches exited nonzero"):
        protocol.run_schedule(path, "unused.env")
    assert len(state["launches"]) == protocol.FAILED_LAUNCHES_MAX


def test_archived_protocol_integrity_is_checked_without_current_host_dependencies(frozen, monkeypatch):
    from bench.analyze import protocol_matches

    settings, _ = frozen
    manifest = protocol.freeze(settings)
    task = manifest["schedule"][0]["task"]
    run_record = {
        "protocol": manifest["id"],
        "cell": 0,
        "tasks": {task: {"canonical": manifest["tasks"][task]}},
        "images": {role: value["id"] for role, value in manifest["images"].items()},
    }
    monkeypatch.setattr(protocol, "evaluation_inputs", lambda: pytest.fail("offline analysis consulted the host"))
    assert protocol_matches(run_record, manifest)
    assert not protocol_matches(run_record, {**manifest, "seed": 99})
    assert not protocol_matches({**run_record, "images": {}}, manifest)


def test_unpinned_precision_and_missing_qualification_are_rejected(frozen, monkeypatch):
    settings, _ = frozen
    with pytest.raises(ValueError, match="provider/precision"):
        protocol.freeze(
            {
                **settings,
                "configurations": [
                    {"model": "openrouter/example/model", "provider": "vendor", "reasoning_effort": "high"}
                ],
            }
        )
    vendor = protocol.freeze({**settings, "configurations": [
        {"model": "openrouter/openai/gpt-6.1-sol", "provider": "openai", "reasoning_effort": "high"}]})  # fmt: skip
    assert vendor["configurations"][0]["provider"] == "openai"  # a vendor serving its own model needs no precision
    manifest = protocol.freeze(settings)
    monkeypatch.setattr(protocol.validation, "build", lambda: {})
    with pytest.raises(ValueError, match="not qualified"):
        protocol.validate(manifest)


def test_cells_are_read_from_job_directories(tmp_path, monkeypatch):
    prefix = protocol.job_prefix("abcdef123456ffff")
    jobs = tmp_path / "jobs"
    for name in (f"{prefix}00000-standard-m-1", f"{prefix}00002-standard-m-1", f"{prefix}00002-r1-standard-m-2"):
        (jobs / name).mkdir(parents=True)
    monkeypatch.setattr(protocol, "RUNS", tmp_path)
    trials = [{"job": f"{prefix}00000-standard-m-1", "counted": False}, {"job": f"{prefix}00002-r1-standard-m-2",
                                                                         "counted": True}]  # fmt: skip
    monkeypatch.setattr(protocol.analyze, "load_trials", lambda dirs, prefix="": trials)
    assert protocol.statuses("abcdef123456ffff", 4) == {0: "unscored", 1: "pending", 2: "done", 3: "pending"}


def test_a_vendor_endpoint_under_another_provider_name_needs_no_precision():
    from bench.protocol import VENDOR_ENDPOINTS

    assert "alibaba" in VENDOR_ENDPOINTS["qwen"] and "qwen" in VENDOR_ENDPOINTS["qwen"]


def _two_rows(path, manifest, state, **extra):
    two = protocol.freeze({**{k: v for k, v in manifest.items() if k != "id"}, "max_trials": 16, "configurations": [
        {"model": "openrouter/qwen/qwen3.8-27b", "provider": "parasail/fp8", "reasoning_effort": "high"},
        {"model": "anthropic/claude-sonnet-5-5", "reasoning_effort": "high"}], **extra})  # fmt: skip
    path.write_text(json.dumps(two))
    state["status"] = dict.fromkeys(range(len(two["schedule"])), "pending")
    return two


def test_a_row_at_its_cap_launches_no_more_cells_and_the_other_rows_go_on(scheduler, monkeypatch, capsys):
    path, manifest, state = scheduler
    two = _two_rows(path, manifest, state, row_budget_usd=10)
    assert two["row_budget_usd"] == 10 and protocol.validate(two) == []

    def row_spend(manifest):  # $6 a trial on the first row, nothing on the second
        rows = [manifest["schedule"][i]["configuration"] for i, _ in state["launches"]]
        return {0: (6.0 * rows.count(0), rows.count(0)), 1: (0.0, rows.count(1))}

    monkeypatch.setattr(protocol, "row_spend", row_spend)
    protocol.run_schedule(path, "unused.env")
    rows = [two["schedule"][i]["configuration"] for i, _ in state["launches"]]
    assert rows.count(0) == 2 and rows.count(1) == len(two["schedule"]) // 2  # paused at $12 = 1.2x; row 1 whole
    out = capsys.readouterr().out
    assert "row paused: openrouter/qwen/qwen3.8-27b: $12.00 spent, more than 20% over the row budget $10.00" in out
    state["launches"].clear()
    protocol.run_schedule(path, "unused.env", row_cap=100)  # a decision raises the cap: the row's cells go on
    assert {two["schedule"][i]["configuration"] for i, _ in state["launches"]} == {0}
    with pytest.raises(ValueError, match="row-budget-usd must be positive"):
        protocol.run_schedule(path, "unused.env", row_cap=0)


def test_a_row_projected_past_its_cap_pauses_once_enough_cells_are_counted(scheduler, monkeypatch):
    path, manifest, state = scheduler
    two = _two_rows(path, manifest, state, row_budget_usd=3.5)
    per_row = len(two["schedule"]) // 2  # 8 cells a row here
    monkeypatch.setattr(protocol, "ROW_PROJECTION_AFTER", 3)
    # both rows are under 1.2x their budget so far; only the row with enough counted cells is projected
    monkeypatch.setattr(protocol, "row_spend", lambda m: {0: (1.5, 2), 1: (2.0, 3)})
    paused = protocol.paused_rows(two, 3.5)
    assert list(paused) == [1] and f"projects ${2.0 / 3 * per_row:.2f} for its {per_row}" in paused[1]
    assert protocol.paused_rows(two, 5) == {}  # $5.33 projected is within 1.2x of $5
    assert protocol.paused_rows(two, None) == {}


def test_row_spend_sums_each_rows_trials_from_its_cells(monkeypatch, frozen):
    settings, _ = frozen
    rows = [{"model": "anthropic/a", "reasoning_effort": "high"}, {"model": "anthropic/b", "reasoning_effort": "high"}]
    manifest = protocol.freeze({**settings, "max_trials": 16, "configurations": rows})
    prefix = protocol.job_prefix(manifest["id"])
    row_of = {i: c["configuration"] for i, c in enumerate(manifest["schedule"])}
    first = next(i for i, r in row_of.items() if r == 0)
    second = next(i for i, r in row_of.items() if r == 1)
    trials = [{"job": f"{prefix}{first:05d}-standard-m-1", "cost": 1.5, "counted": False},
              {"job": f"{prefix}{first:05d}-r1-standard-m-2", "cost": 2.0, "counted": True},
              {"job": f"{prefix}{second:05d}-standard-m-1", "cost": None, "counted": True},
              {"job": "scored-elsewhere-00001-standard-m-1", "cost": 9.0, "counted": True}]  # fmt: skip
    monkeypatch.setattr(
        protocol.analyze, "load_trials", lambda dirs, prefix="": [t for t in trials if t["job"].startswith(prefix)]
    )
    assert protocol.row_spend(manifest) == {0: (3.5, 1), 1: (0.0, 1)}
    with pytest.raises(ValueError, match="row_budget_usd must be positive"):
        protocol.freeze({**settings, "row_budget_usd": 0})


def test_variants_default_to_the_studys_two_arms_and_keep_their_manifest_ids(frozen, monkeypatch):
    """A schedule names its arms; the default (standard and ablation) leaves the manifest body as it was, so the
    study's frozen manifests keep their ids; the logs arm pins its renders, which are made at launch."""
    settings, _ = frozen
    default = protocol.freeze(settings)
    assert "variants" not in default and {c["variant"] for c in default["schedule"]} == {"standard", "ablation"}
    assert protocol.freeze({**settings, "variants": ["standard", "ablation"]}) == default
    monkeypatch.setattr(
        protocol, "variant_digests", lambda variant: {"task-a": f"{variant}-a", "task-b": f"{variant}-b"}
    )
    monkeypatch.setattr(protocol, "readonly_unqualified", lambda digests: ["task-b"])
    with pytest.raises(ValueError, match=r"read-only probe .* task-b"):
        protocol.freeze({**settings, "variants": ["logs"]})  # isolation is qualified per render, before freezing
    monkeypatch.setattr(protocol, "readonly_unqualified", lambda digests: [])
    logs = protocol.freeze({**settings, "variants": ["logs"]})
    assert {c["variant"] for c in logs["schedule"]} == {"logs"} and len(logs["schedule"]) == 4  # k=1, lite_k=3
    assert logs["variants"] == ["logs"] and logs["variant_digests"] == {
        "logs": {"task-a": "logs-a", "task-b": "logs-b"}
    }
    assert logs["id"] != default["id"]
    monkeypatch.setattr(protocol, "variant_digests", lambda variant: {"task-a": "changed", "task-b": "logs-b"})
    with pytest.raises(ValueError, match="differ"):
        protocol.validate(logs)  # a change to the variant's code after freezing stops the schedule
    for bad in (["net"], ["logs", "logs"], []):
        with pytest.raises(ValueError, match="variants"):
            protocol.freeze({**settings, "variants": bad})


def test_a_logs_trial_must_have_run_the_render_its_manifest_pinned(frozen, monkeypatch):
    from bench.analyze import protocol_matches

    settings, _ = frozen
    monkeypatch.setattr(protocol, "variant_digests", lambda variant: {"task-a": "logs-a", "task-b": "logs-b"})
    monkeypatch.setattr(protocol, "readonly_unqualified", lambda digests: [])
    manifest = protocol.freeze({**settings, "variants": ["logs"]})
    task = manifest["schedule"][0]["task"]
    record = {"protocol": manifest["id"], "cell": 0,
              "tasks": {task: {"canonical": manifest["tasks"][task], "digest": f"logs-{task[-1]}"}},
              "images": {role: value["id"] for role, value in manifest["images"].items()}}  # fmt: skip
    assert protocol_matches(record, manifest)
    record["tasks"][task]["digest"] = "a render the manifest never pinned"
    assert not protocol_matches(record, manifest)


def test_readonly_qualification_reads_the_probe_records_at_the_render_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, "ROOT", tmp_path)
    (tmp_path / "results").mkdir()
    rows = {"a": {"ok": True, "task_digest": "d-a", "evidence_visible": True},
            "b": {"ok": True, "task_digest": "old", "evidence_visible": False},
            "c": {"ok": False, "task_digest": "d-c", "evidence_visible": True}}  # fmt: skip
    (tmp_path / "results" / "readonly-probe.json").write_text(json.dumps(rows))
    assert protocol.readonly_unqualified({"a": "d-a", "b": "d-b", "c": "d-c", "d": "d-d"}) == ["b", "c", "d"]


def test_allow_unqualified_warns_lists_the_tasks_and_records_the_run_as_not_qualified(scheduler, monkeypatch, capsys):
    path, manifest, state = scheduler
    monkeypatch.setattr(protocol.validation, "build", lambda: {"task-a": {"green": True}, "task-b": {"green": False}})
    with pytest.raises(ValueError, match="not qualified: task-b"):
        protocol.run_schedule(path, "unused.env")
    assert state["launches"] == [] and not path.with_suffix(".progress.json").exists()
    assert protocol.validate(manifest, allow_unqualified=True) == ["task-b"]
    protocol.run_schedule(path, "unused.env", allow_unqualified=True)
    out = capsys.readouterr().out
    assert "warning" in out and "task-b" in out and "not qualified" in out
    assert len(state["launches"]) == len(manifest["schedule"])  # every cell ran despite the unqualified task
    progress = json.loads(path.with_suffix(".progress.json").read_text())
    assert progress["qualified"] is False and progress["id"] == manifest["id"]


def test_a_qualified_run_records_no_qualified_key(scheduler):
    path, _, _ = scheduler
    protocol.run_schedule(path, "unused.env", allow_unqualified=True)
    assert "qualified" not in json.loads(path.with_suffix(".progress.json").read_text())


def test_the_run_command_takes_allow_unqualified(scheduler, monkeypatch):
    path, _, _ = scheduler
    seen = {}
    monkeypatch.setattr(protocol, "run_schedule", lambda *a, **kw: seen.update(kw))
    protocol.main(["run", str(path), "--allow-unqualified", "--dry-run"])
    assert seen["allow_unqualified"] is True
    protocol.main(["run", str(path), "--dry-run"])
    assert seen["allow_unqualified"] is False
