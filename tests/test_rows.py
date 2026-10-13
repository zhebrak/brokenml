"""Leaderboard rows added since launch (tools/release/add_row.py, drawn by tools/release/draw_leaderboard.py)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "release"))

import add_row
import build_dataset as ds
import draw_leaderboard

ROOT = Path(__file__).resolve().parents[1]
TASKS = {"alpha": "sha256:a", "beta": "sha256:b"}
LABEL = "terminus-2:openrouter/qwen/qwen3.8-flash @alibaba"
BUILDS = {"runtime": "rt1", "harness": "hn1", "serve": "sv1", "runtime-getenvfix": "rtfix"}
PIN = {"extra_body": {"provider": {"order": ["alibaba"], "allow_fallbacks": False}}}
LOCK = {
    "schema_version": "1", "task": {"digest": "x"}, "install_only": False, "timeout_multiplier": 1.0,
    "bridge_inputs": {}, "skills": [],
    "agent": {"name": "terminus-2", "model_name": "openrouter/qwen/qwen3.8-flash", "skills": [],
              "resume_trajectory": False, "extra_allowed_hosts": [], "mcp_servers": [],
              "kwargs": {"reasoning_effort": "high", "llm_call_kwargs": PIN}},
    "environment": {"type": "docker", "force_build": False, "delete": True, "cpu_enforcement_policy": "auto",
                    "memory_enforcement_policy": "auto", "extra_docker_compose": [], "kwargs": {},
                    "extra_allowed_hosts": []},
    "verifier": {"disable": False, "environment_mode": "separate"},
}  # fmt: skip
EVAL = {"runtime": "rt1", "harness": "hn1", "cpu-node": "rt1"}
NO_REVIEW = {"zeroed": {}, "kept": {}}


def expect(task: str, variant: str) -> str:
    return TASKS[task] + ("" if variant == "standard" else f"-{variant}")


def trial(
    task: str,
    variant: str,
    *,
    counted: bool = True,
    label: str = LABEL,
    digest: str | None = None,
    outcome: str = "agent",
    rerun_reason: str | None = None,
    reward: float = 0.0,
    started: str = "2026-10-13T06:00:00Z",
    audit: list[str] | None = None,
    evaluation: dict | None = None,
    lock: dict | None = None,
    config_id: str = "abc123",
    trial_id: str | None = None,
    **extra,
) -> dict:
    return {"task": task, "variant": variant, "counted": counted, "label": label, "config_id": config_id,
            "digest": digest or expect(task, variant), "outcome": outcome, "rerun_reason": rerun_reason,
            "reward": reward, "audit": audit or [], "scored_gradings": 1, "first_outcome": outcome,
            "first_busy": False, "builds": "rt1/hn1/rt1", "evaluation": EVAL if evaluation is None else evaluation,
            "lock": LOCK if lock is None else lock, "started": started,
            "trial": trial_id or f"t-{task}-{variant}-{'c' if counted else 'u'}",
            "job": f"row-x-{variant}-20261013-060000", "dir": f"/runs/row-x-{variant}-20261013-060000/t-{task}",
            "tput_ok": None, **extra}  # fmt: skip


def full_row(**kw) -> list[dict]:
    return [trial(task, variant, **kw) for task in TASKS for variant in ("standard", "logs", "ablation")]


def check(trials: list[dict], **kw) -> tuple[list[str], list[str]]:
    kw.setdefault("review", NO_REVIEW)
    kw.setdefault("harbor", {"0.23.0"})
    return add_row.check_row(trials, TASKS, expect=expect, builds=BUILDS, **kw)


def with_agent(**changes) -> dict:
    return {**LOCK, "agent": {**LOCK["agent"], **changes}}


def test_a_verdict_in_every_cell_on_the_board_s_configuration_is_a_complete_row():
    assert check(full_row()) == ([], [])


def test_a_cell_without_a_verdict_names_the_attempt_and_prints_the_re_run_command():
    trials = [t for t in full_row() if not (t["task"] == "beta" and t["variant"] == "logs")]
    trials.append(trial("beta", "logs", counted=False, outcome="provider error",
                        rerun_reason="a model call unanswered for 640 s"))  # fmt: skip
    problems, notes = check(trials)
    assert problems == ["live logs + files, beta: no verdict (t-beta-logs-u: a model call unanswered for 640 s)"]
    assert notes == ["re-run: uv run bench run openrouter/qwen/qwen3.8-flash beta --split test --variant logs "
                     "--reasoning-effort high --provider alibaba -n <measured> --env-file <keys> "
                     "--name row-x"]  # fmt: skip


def test_a_cell_with_two_verdicts_keeps_the_earliest_by_start_time_and_marks_the_later_rerolled():
    later = trial("alpha", "standard", reward=1.0, started="2026-10-13T09:00:00Z", trial_id="t-alpha-again")
    trials = [later, *full_row()]  # listed first, started later
    problems, notes = check(trials)
    assert problems == []
    assert notes == ["live cluster, alpha: t-alpha-again ran after t-alpha-standard-c had a verdict; kept as rerolled"]
    assert later["counted"] is False and later["outcome"] == "rerolled"


def test_mixed_configurations_wrong_harbor_and_edited_tasks_are_refused():
    trials = full_row()
    trials[0] = dict(trials[0], config_id="other", digest="sha256:edited")
    problems, _ = check(trials, harbor={"0.23.0", "0.24.0"})
    assert any(p.startswith("more than one configuration") for p in problems)
    assert "Harbor 0.24.0 (the board is 0.23.0)" in problems
    assert any("alpha: task digest sha256:edited" in p for p in problems)


def test_a_variant_rendered_task_is_checked_against_its_own_render():
    trials = full_row()
    trials[1] = dict(trials[1], digest=TASKS["alpha"])  # the logs trial carries the standard digest
    problems, _ = check(trials)
    assert len(problems) == 1 and problems[0].startswith("live logs + files, alpha: task digest")


@pytest.mark.parametrize(("lock", "words"), [
    (with_agent(name="codex"), 'agent name is "codex"'),
    (with_agent(kwargs={"reasoning_effort": "medium", "llm_call_kwargs": PIN}), "reasoning effort 'medium'"),
    ({**LOCK, "timeout_multiplier": 2.0}, "lock timeout_multiplier is 2.0"),
    ({**LOCK, "agent_timeout_multiplier": 2}, "lock agent_timeout_multiplier is set: 2"),
    ({**LOCK, "override_cpus": 1}, "lock override_cpus is set: 1"),
    ({**LOCK, "override_gpus": 0}, "lock override_gpus is set: 0"),
    ({**LOCK, "something": True}, "lock something is set: true"),
    (with_agent(override_timeout_sec=3600), "agent override_timeout_sec is set: 3600"),
    (with_agent(resume_trajectory=True), "agent resume_trajectory is true"),
    (with_agent(extra_allowed_hosts=["github.com"]), "agent extra_allowed_hosts is"),
    ({**LOCK, "environment": {**LOCK["environment"], "kwargs": {"cpus": 16}}}, "environment kwargs is"),
    ({**LOCK, "environment": {**LOCK["environment"], "extra_docker_compose": ["x.yaml"]}}, "extra_docker_compose is"),
    ({**LOCK, "verifier": {"disable": False, "environment_mode": "shared"}}, "verifier environment_mode is"),
    (with_agent(kwargs={"reasoning_effort": "high", "llm_call_kwargs": {"extra_body": {
        "provider": {"order": ["alibaba"], "allow_fallbacks": False}, "plugins": [{"id": "web"}]}}}),
     "more than the provider pin"),
    (with_agent(kwargs={"reasoning_effort": "high", "llm_call_kwargs": {"extra_body": {
        "provider": {"order": ["alibaba"]}}}}), "fallbacks off"),
    (with_agent(kwargs={"reasoning_effort": "high", "llm_call_kwargs": {"extra_body": {
        "provider": {"order": ["alibaba", "qwen"], "allow_fallbacks": False}}}}), "single provider"),
    (with_agent(kwargs={"reasoning_effort": "high", "llm_call_kwargs": {"extra_body": {
        "provider": {"order": ["parasail"], "allow_fallbacks": False, "quantizations": ["fp4", "bf16"]}}}}),
     "one precision"),
    (with_agent(kwargs={"reasoning_effort": "high"}), "OpenRouter model without a provider pin"),
    (with_agent(model_name="anthropic/claude-sonnet-5-5"), "vendor route carries no provider pin"),
])  # fmt: skip
def test_a_lock_outside_the_board_s_configuration_is_refused(lock: dict, words: str):
    problems, _ = check(full_row(lock=lock))
    assert len(problems) == 1 and words in problems[0], problems


def test_a_vendor_route_without_a_pin_is_the_board_s_configuration():
    lock = with_agent(model_name="anthropic/claude-sonnet-5-5", kwargs={"reasoning_effort": "high"})
    assert check(full_row(lock=lock)) == ([], [])


def test_images_other_than_the_launch_builds_are_refused_and_the_patched_runtime_is_allowed_where_recorded():
    trials = full_row()
    trials[0] = dict(trials[0], evaluation={"runtime": "rt1", "harness": "hn9", "cpu-node": "rt1"})
    trials[1] = dict(trials[1], evaluation={"runtime": "rt1", "harness": "hn1", "cpu-node": "rtfix"})
    trials[2] = dict(trials[2], evaluation={"runtime": "rt1", "harness": "hn1", "cpu-node": "rtfix"},
                     patched_runtime="rtfix")  # fmt: skip
    trials[3] = dict(trials[3], evaluation={"runtime": "rt1", "harness": "hn1", "serve": "sv9"})
    trials[4] = dict(trials[4], evaluation={"runtime": "rt1", "harness": "hn1", "serve": "sv1"})
    problems, _ = check(trials)
    assert [p.split(": ", 1)[1][:30] for p in problems] == [
        "harness image build hn9, not t",
        "nodes ran image build rtfix, n",
        "the engine ran image build sv9",
    ]


def test_missing_image_provenance_on_a_pass_is_refused_and_on_a_job_that_never_ran_is_not():
    trials = full_row()
    trials[0] = dict(trials[0], reward=1.0, evaluation={"runtime": "rt1", "harness": "hn1"},
                     provenance_complete=False, unobserved_builds=["serve"])  # fmt: skip
    trials[1] = dict(
        trials[1],
        reward=0.0,
        evaluation={"runtime": "rt1", "harness": "hn1"},
        provenance_complete=False,
        unobserved_builds=["cpu-node"],
    )  # a drained node: no job ran
    problems, _ = check(trials)
    assert len(problems) == 1 and "image provenance incomplete on a pass: no build recorded for serve" in problems[0]


def test_a_re_grading_on_another_task_version_must_be_registered():
    trials = full_row()
    trials[0] = dict(trials[0], other_version_gradings=1)
    trials[1] = dict(trials[1], other_version_gradings=1, patched_runtime="rtfix",
                     evaluation={"runtime": "rt1", "harness": "hn1", "cpu-node": "rtfix"})  # fmt: skip
    problems, _ = check(trials)
    assert len(problems) == 1 and "not registered in protocol/patched-gradings.json" in problems[0]


def test_only_infra_cells_and_busy_timed_verdicts_may_be_re_graded_and_only_so_often():
    trials = full_row()
    trials[0] = dict(trials[0], reward=1.0, scored_gradings=2, first_outcome="agent")  # a fail re-graded to a pass
    trials[1] = dict(trials[1], scored_gradings=3, first_outcome="infra")  # an infra cell re-graded twice
    trials[2] = dict(trials[2], scored_gradings=4, first_outcome="infra")
    trials[3] = dict(trials[3], reward=1.0, scored_gradings=2, first_outcome="agent", first_busy=True, tput_ok=True)
    trials[4] = dict(trials[4], scored_gradings=3, first_outcome="agent", first_busy=True)
    problems, _ = check(trials)
    assert [p.split(": ", 1)[1][:40] for p in problems] == [
        "re-graded a scored verdict (first gradin",
        "graded 4 times; an infra cell is re-grad",
        "graded 3 times; a busy-timed throughput ",
    ]


def test_an_infra_cell_is_refused_until_its_two_re_grades_are_spent():
    trials = full_row()
    trials[0] = dict(trials[0], outcome="infra", first_outcome="infra", scored_gradings=1)
    problems, _ = check(trials)
    assert len(problems) == 1 and "infra after 1 grading(s); re-grade it (uv run bench regrade /runs/" in problems[0]
    trials[0] = dict(trials[0], scored_gradings=3)
    assert check(trials) == ([], [])


def test_a_throughput_verdict_timed_on_a_busy_host_blocks_and_one_listed_for_a_shift_stands():
    busy = trial("alpha", "standard", reward=1.0, tput_ok=True, tput_ratio=0.82, tput_min=0.8, host_busy_ref=0.6,
                 host_busy_job=0.1)  # fmt: skip
    shift = trial("beta", "standard", reward=0.0, tput_ok=False, tput_ratio=0.665, tput_min=0.8,
                  host_busy_ref=0.29, host_busy_job=0.1)  # fmt: skip
    trials = [busy, shift, *[t for t in full_row() if t["variant"] != "standard"]]
    problems, notes = check(trials)
    assert len(problems) == 1
    assert problems[0].startswith("live cluster, alpha: throughput pass at ratio 0.82 timed on a busy host")
    assert notes == ["live cluster, beta: throughput fail at ratio 0.665 listed for a load shift (host busy 29% during "
                     "the reference, 10% during the job); it stands"]  # fmt: skip
    busy.update(scored_gradings=2, first_busy=True)  # re-graded on a quiet host
    problems, _ = check(trials)
    assert problems == []


def test_open_audit_reviews_block_a_row_until_settled_in_the_review_file():
    trials = full_row()
    trials[1] = dict(trials[1], reward=1.0, audit=["sharding bypass: no fully_shard call"])
    problems, _ = check(trials)
    assert len(problems) == 1 and "pass t-alpha-logs-c with audit hits (sharding bypass" in problems[0]
    assert check(trials, review={"zeroed": {"t-alpha-logs-c": "bypass confirmed"}, "kept": {}}) == ([], [])
    assert check(trials, review={"zeroed": {}, "kept": {"t-alpha-logs-c": "find in /logs, nothing used"}}) == ([], [])


def test_review_entries_must_name_trials_of_the_row_and_one_list_only():
    trials = full_row()
    problems, _ = check(trials, review={"zeroed": {"t-nope": "x", "t-alpha-logs-c": "y"},
                                        "kept": {"t-alpha-logs-c": "z"}})  # fmt: skip
    assert problems == ["review.yaml lists t-nope under zeroed, which is no trial of this row",
                        "review.yaml lists t-alpha-logs-c as both zeroed and kept"]  # fmt: skip


def test_a_review_entry_without_a_reason_is_refused(tmp_path: Path):
    f = tmp_path / "review.yaml"
    f.write_text(yaml.safe_dump({"zeroed": [{"trial": "t-1"}], "kept": []}))
    with pytest.raises(SystemExit, match="names a trial and gives a reason"):
        add_row.load_review(f)
    f.write_text(yaml.safe_dump({"zeroed": [{"trial": "t-1", "reason": " bypass "}], "kept": None}))
    assert add_row.load_review(f) == {"zeroed": {"t-1": "bypass"}, "kept": {}}


def test_an_attempt_outside_the_three_conditions_is_refused():
    problems, _ = check([*full_row(), trial("alpha", "net")])
    assert problems == ["row-x-net-20261013-060000: variant net is not a leaderboard condition"]


def test_slug_rules():
    assert (
        add_row.SLUG.match("qwen3.8-flash")
        and not add_row.SLUG.match("openrouter/qwen")
        and not add_row.SLUG.match("Qwen")
    )


# --- jobs: whole, as bench run launched them


def job_dir(
    root: Path,
    name: str,
    *,
    trials: list[str],
    reported: list[str] | None = None,
    planned: int = 2,
    harbor: dict | None = None,
    retry: dict | None = None,
    job_name: str | None = None,
) -> Path:
    d = root / name
    d.mkdir(parents=True)
    retry = retry or {"max_retries": 2, "include_exceptions": list(add_row.SETUP_ERRORS),
                      "exclude_exceptions": sorted(add_row.HARBOR_EXCLUDES)}  # fmt: skip
    d.joinpath("lock.json").write_text(json.dumps({
        "harbor": harbor or add_row.HARBOR_LOCK, "retry": retry,
        "trials": [{"task": {"name": f"t-{i}"}} for i in range(planned)]}))  # fmt: skip
    d.joinpath("config.json").write_text(json.dumps({"job_name": job_name or name, "n_concurrent_trials": 8}))
    d.joinpath("result.json").write_text(json.dumps({"started_at": "2026-10-13T05:37:28Z", "stats": {
        "n_retries": 0, "evals": {"x": {"reward_stats": {"reward": {"0.0": reported or trials}},
                                        "exception_stats": {}}}}}))  # fmt: skip
    for t in trials:
        d.joinpath(t).mkdir()
    return d


def test_a_whole_job_as_bench_run_launched_it_has_no_problems(tmp_path: Path):
    d = job_dir(tmp_path, "row-x-standard-20261013-060000", trials=["t-a", "t-b"])
    assert add_row.job_problems(d, planned=2) == []
    assert add_row.job_problems(d, planned=None) == []


@pytest.mark.parametrize(("kw", "words"), [
    ({"harbor": {"version": "0.23.0", "is_editable": True}}, "Harbor"),
    ({"retry": {"max_retries": 5, "include_exceptions": [], "exclude_exceptions": ["VerifierTimeoutError"]}},
     "retry policy"),
    ({"retry": {"max_retries": 2, "include_exceptions": ["AgentTimeoutError"], "exclude_exceptions": []}},
     "retry policy"),
    ({"job_name": "row-x-standard-20261013-010000"}, "was launched as 'row-x-standard-20261013-010000'"),
    ({"reported": ["t-a", "t-b", "t-gone"]}, "attempts the job reports have no directory: ['t-gone']"),
    ({"planned": 1}, "planned 1 trials, not 2"),
])  # fmt: skip
def test_a_job_that_is_not_whole_is_refused(tmp_path: Path, kw: dict, words: str):
    d = job_dir(tmp_path, "row-x-standard-20261013-060000", trials=["t-a", "t-b"], **kw)
    problems = add_row.job_problems(d, planned=2)
    assert len(problems) == 1 and words in problems[0], problems


def test_a_later_job_of_an_arm_may_plan_fewer_trials(tmp_path: Path):
    d = job_dir(tmp_path, "row-x-standard-20261013-090000", trials=["t-a"], planned=1)
    assert add_row.job_problems(d, planned=None) == []


def test_a_concurrency_record_needs_its_measurement_not_only_a_number():
    host = {"cpu": "AMD EPYC 9R14"}
    tasks = list(add_row.concurrency.DEFAULT_TASKS)
    assert add_row.host_record_problem({"safe_n": 8}) == (
        "not a bench concurrency record (missing host, inputs, levels, tasks)"
    )
    base = {"safe_n": 8, "host": host, "inputs": {}, "tasks": tasks}
    assert add_row.host_record_problem({**base, "host": {}, "levels": {}})
    levels = {str(n): {"safe": n != 2} for n in range(1, 9)}  # a failed 2 beside a safe 3 to 8: no support for 8
    assert add_row.host_record_problem({**base, "levels": levels}) == (
        "the record's levels do not support safe_n 8 without a gap"
    )
    levels["2"] = {"safe": True}
    assert (
        add_row.host_record_problem({**base, "levels": levels, "tasks": None}) == "the record names no measured tasks"
    )
    assert add_row.host_record_problem({**base, "levels": levels, "tasks": ["not-a-task"]}) == (
        "the record's measured tasks are not the throughput-gated tasks"
    )
    real = json.loads((ROOT / "results" / "concurrency.json").read_text())
    stale = add_row.host_record_problem({**real, "inputs": {**real["inputs"], "rule": "other"}})
    assert stale is not None and stale.startswith(("measurement stale", "cannot check the measurement"))
    assert add_row.host_record_problem(real) is None  # the launch host's record, on the launch images


# --- drawing: a row directory is re-checked before it joins the board

CELLS = {f"task{i:02d}" for i in range(46)}
DATES = {"published": "2026-10-12", "models": {"qwen/qwen3.8-flash": {"released": "2026-08-26"},
                                                "a/b": {"released": "2026-01-01"}, "x/y": {"released": "2026-01-01"},
                                                "minimax-m3": {"released": "2026-05-31"},
                                                "minimax-m3.5": {"released": "2026-11-02"}}}  # fmt: skip


def board_csv(model: str, solved: tuple[int, int, int], tasks: int = 46) -> str:
    lines = ["# canary", "model,condition,tasks,solved,pass_rate"]
    for cond, n in zip(("files only", "live logs + files", "live cluster"), solved, strict=True):
        lines.append(f"{model},{cond},{tasks},{n},{n / tasks:.4f}")
    return "\n".join(lines) + "\n"


def row_dir(
    root: Path,
    slug: str,
    model: str,
    solved: tuple[int, int, int],
    *,
    tasks: int = 46,
    meta: dict | None = None,
    tamper: bool = False,
    extra: list[dict] | None = None,
) -> Path:
    """A row directory as add_row.py writes it: trials.jsonl with one counted trial per cell, and the scoreboard
    rebuilt from it (or, with tamper, a flattering one)."""
    d = root / slug
    d.mkdir(parents=True)
    records = []
    for cond, n in zip(("files only", "live logs + files", "live cluster"), solved, strict=True):
        for i in range(tasks):
            records.append({"model": model, "condition": cond, "task": f"task{i:02d}", "counted": True,
                            "reward": 1.0 if i < n else 0.0, "zeroed": "", "not_reported": "", "cost_recorded": 0.01,
                            "trial": f"t-{cond[:4]}-{i}"})  # fmt: skip
    records += extra or []
    with (d / "trials.jsonl").open("w") as fh:
        fh.write(json.dumps({"canary": "x"}) + "\n")
        fh.writelines(json.dumps(r) + "\n" for r in records)
    ds.write_csv(d / "scoreboard.csv", ds.scoreboard(records))
    if tamper:
        d.joinpath("scoreboard.csv").write_text(board_csv(model, (46, 46, 46)))
    row = {
        **draw_leaderboard.BOARD,
        "model": model,
        "name": slug.title(),
        "label": f"terminus-2:{model}",
        "released": "2026-01-01",
        "released_after_publication": False,
        "added": "2026-10-13",
        **(meta or {}),
    }
    d.joinpath("row.yaml").write_text(yaml.safe_dump(row))
    return d


@pytest.fixture
def dates(monkeypatch):
    from bench import analyze

    monkeypatch.setattr(analyze, "model_dates", lambda: DATES)


def test_a_rebuilt_row_joins_the_board_and_the_launch_rows_keep_their_order(tmp_path: Path, dates):
    study = tmp_path / "scoreboard.csv"
    study.write_text(board_csv("anthropic/claude-sonnet-5-5", (32, 43, 45)))
    row_dir(tmp_path / "rows", "flash", "openrouter/qwen/qwen3.8-flash", (10, 20, 30), meta={"released": "2026-08-26"})
    board = draw_leaderboard.load(study)
    names, added = draw_leaderboard.load_rows(tmp_path / "rows", board, CELLS)
    assert set(board) == {"anthropic/claude-sonnet-5-5", "openrouter/qwen/qwen3.8-flash"}
    assert names == {"openrouter/qwen/qwen3.8-flash": "Flash"} and added == {}
    svg = draw_leaderboard.draw(board, "light", names, added)
    assert svg.index("Claude Sonnet 5.5") < svg.index(">Flash<")  # ordered by live-cluster solves
    assert "added" not in svg and "2026-10-13" not in svg


def test_a_model_released_after_publication_is_marked_from_the_model_list_not_the_row_file(tmp_path: Path, dates):
    (tmp_path / "scoreboard.csv").write_text(board_csv("x/y", (1, 2, 3)))
    row_dir(tmp_path / "rows", "new", "openrouter/minimax/minimax-m3.5", (1, 2, 3),
            meta={"released": "2026-11-02", "released_after_publication": True})  # fmt: skip
    board = draw_leaderboard.load(tmp_path / "scoreboard.csv")
    names, added = draw_leaderboard.load_rows(tmp_path / "rows", board, CELLS)
    assert added == {"openrouter/minimax/minimax-m3.5": "model released after publication"}
    assert "model released after publication" in draw_leaderboard.draw(board, "light", names, added)


def test_a_row_file_whose_flag_disagrees_with_the_model_list_is_refused(tmp_path: Path, dates):
    (tmp_path / "scoreboard.csv").write_text(board_csv("x/y", (1, 2, 3)))
    row_dir(
        tmp_path / "rows",
        "new",
        "openrouter/minimax/minimax-m3.5",
        (1, 2, 3),
        meta={"released": "2026-05-31", "released_after_publication": False},
    )  # the predecessor's date
    board = draw_leaderboard.load(tmp_path / "scoreboard.csv")
    with pytest.raises(SystemExit, match=r"release date or contamination flag is not what results/models\.yaml gives"):
        draw_leaderboard.load_rows(tmp_path / "rows", board, CELLS)


DUP = {"model": "a/b", "condition": "live cluster", "task": "task00", "counted": True, "reward": 1.0, "zeroed": "",
       "not_reported": "", "cost_recorded": 0.01, "trial": "t-live-again"}  # fmt: skip
INVENTED = {**DUP, "task": "task99", "trial": "t-live-99"}
EXCLUDED = {**DUP, "task": "task01", "reward": 0.0, "not_reported": "cut", "trial": "t-live-1x"}


@pytest.mark.parametrize(("kw", "words"), [
    ({"tamper": True}, "scoreboard.csv is not what trials.jsonl gives"),
    ({"meta": {"effort": "medium"}}, "effort 'medium' is not the board's 'high'"),
    ({"meta": {"dataset": "0.2.0"}}, "dataset '0.2.0' is not the board's '0.1.0'"),
    ({"tasks": 45}, "45 counted cells; missing ['task45']"),
    ({"meta": {"model": "someone/else"}}, "row.yaml says 'someone/else'"),
    ({"extra": [DUP]}, "more than one counted trial in a cell: ['live cluster, task00']"),
    ({"extra": [INVENTED]}, "not in the dataset ['task99']"),
    ({"extra": [EXCLUDED]}, "marked not_reported ['t-live-1x']"),
])  # fmt: skip
def test_a_row_directory_that_fails_its_re_check_is_refused(tmp_path: Path, dates, kw: dict, words: str):
    (tmp_path / "scoreboard.csv").write_text(board_csv("x/y", (1, 2, 3)))
    row_dir(tmp_path / "rows", "new", "a/b", (1, 2, 3), **kw)
    board = draw_leaderboard.load(tmp_path / "scoreboard.csv")
    with pytest.raises(SystemExit) as e:
        draw_leaderboard.load_rows(tmp_path / "rows", board, CELLS)
    assert words in str(e.value)


def test_the_same_model_through_another_router_or_variant_is_the_same_row(tmp_path: Path, dates):
    (tmp_path / "scoreboard.csv").write_text(board_csv("x/y", (1, 2, 3)))
    row_dir(tmp_path / "rows", "dup", "openrouter/x/y:nitro", (4, 5, 6))
    board = draw_leaderboard.load(tmp_path / "scoreboard.csv")
    with pytest.raises(SystemExit, match="already on the board as x/y"):
        draw_leaderboard.load_rows(tmp_path / "rows", board, CELLS)
    assert draw_leaderboard.board_models(tmp_path / "scoreboard.csv", tmp_path / "rows") == {"x/y": "dup"}
    assert draw_leaderboard.norm_model("openrouter/openai/gpt-6.1-sol") == "openai/gpt-6.1-sol"


def test_a_display_name_already_on_the_board_is_refused(tmp_path: Path, dates):
    (tmp_path / "scoreboard.csv").write_text(board_csv("anthropic/claude-sonnet-5-5", (1, 2, 3)))
    row_dir(tmp_path / "rows", "new", "a/b", (1, 2, 3), meta={"name": "claude sonnet 5.5"})
    board = draw_leaderboard.load(tmp_path / "scoreboard.csv")
    with pytest.raises(SystemExit, match=r"name 'claude sonnet 5\.5' is already on the board"):
        draw_leaderboard.load_rows(tmp_path / "rows", board, CELLS)


def test_the_committed_rows_pass_their_re_check():
    """Every row under results/rows/ rebuilds from its trials, is one verdict per dataset task and condition, carries
    the release date the model list gives, and is the board's configuration (what make readme-table checks)."""
    board = draw_leaderboard.load(draw_leaderboard.STUDY)
    names, added = draw_leaderboard.load_rows(draw_leaderboard.ROWS, board)
    assert set(added) <= set(names)
