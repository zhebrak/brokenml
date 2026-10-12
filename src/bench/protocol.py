"""Freeze and execute an explicit scored-run schedule (docs/scored-runs.md).

  bench protocol freeze SETTINGS.json --out MANIFEST.json
  bench protocol run MANIFEST.json [--env-file PATH] [--workers N] [--dry-run]
  bench protocol run MANIFEST.json --retry-cell N [N ...]

Settings name the configurations (model, agent, reasoning_effort, optional provider and agent_version), k, lite_k, seed,
max_trials, an optional budget_usd for the study and an optional row_budget_usd for each configuration, an approximate
budget: a row whose spend, or projected spend, passes it by more than ROW_OVERRUN launches no more cells until a
decision (--row-budget-usd); the other rows go on. Freeze records the current task digests, the built images and the
tools, and shuffles the complete schedule (every test task, both arms, k or lite_k attempts) with the seed. Run
dispatches cells in that order, as many at a time as this host's measured concurrency allows (`bench concurrency`), one
Harbor job per cell. A cell is done when its job holds a counted trial (pass or agent, or a residual infra or
verifier_bug); a cell whose job holds none (a provider error, a setup failure, an interrupted launch:
docs/leaderboard.md, Errors) is never repeated on its own. It is listed, and --retry-cell launches it again under the
same cell as a numbered attempt. Progress is read from the job directories, so an interrupted scheduler loses nothing;
the cells it was running are reported and wait for --retry-cell. A frozen cell is one trial: `bench analyze` scores the
earliest counted trial of a cell and lists any later one as rerolled.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import random
import subprocess
import sys
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path

from bench import analyze, concurrency, validation
from bench.paths import ROOT, RUNS
from bench.provenance import image_ids, image_tags, task_digest, task_image_refs
from bench.spec import load_specs, task_dir

EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "default")  # Terminus 2's reasoning_effort
CONFIG_KEYS = {"agent", "model", "reasoning_effort", "provider", "agent_version"}
# A vendor's own endpoint where OpenRouter names the provider differently from the model's author: Alibaba serves Qwen
# (the Qwen team's cloud), and its endpoints report no precision.
VENDOR_ENDPOINTS = {"qwen": {"qwen", "alibaba"}}
# The arms a schedule may hold: the study's two (the default) and live read-only access (docs/variants.md, Live logs),
# which runs as its own frozen arm from its own checkout (docs/study-rules.md).
DEFAULT_VARIANTS = ["standard", "ablation"]
SCORED_VARIANTS = ("standard", "ablation", "logs")
FAILED_LAUNCHES_MAX = 3  # consecutive Harbor exits with a nonzero status that stop dispatching: the host, not a cell
ROW_PROJECTION_AFTER = 10  # counted cells of a row before its spend per cell can project it past its budget
# A row's budget is approximate: it pauses past 1.2x (not a hard cap, but not significantly more).
ROW_OVERRUN = 1.2


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def evaluation_inputs() -> dict:
    """What a trial's execution depends on: task digests, image identities, Harbor's version and the launcher's own
    source. Analysis code is not here: an analysis fix is a logged deviation (docs/study-rules.md) and
    must not stop a running schedule."""
    tasks = {s.id: task_digest(task_dir(s)) for s in load_specs() if s.split == "test"}
    roles = {role: ref for task in tasks for role, ref in task_image_refs(task_dir(task)).items()}
    available = image_ids()
    from bench.run import HARBOR

    version = subprocess.run(
        [*HARBOR, "--version"], capture_output=True, text=True, check=True, timeout=30
    ).stdout.strip()
    source = hashlib.sha256()
    for name in ("run.py", "protocol.py", "provenance.py", "concurrency.py"):
        source.update((Path(__file__).parent / name).read_bytes())
    source.update((ROOT / "uv.lock").read_bytes())
    return {
        "tasks": tasks,
        "images": {role: {"ref": ref, "id": available.get(ref, "")} for role, ref in roles.items()},
        "tools": {"harbor": version, "runner_source": source.hexdigest()},
    }


def variant_digests(variant: str) -> dict[str, str]:
    """The digest of every test task as `variant` renders it (rendered at launch, so pinned here)."""
    import shutil
    import tempfile

    from bench.render import render

    work = Path(tempfile.mkdtemp(prefix="bench-freeze-"))
    try:
        return {s.id: task_digest(render(s, work, variant)) for s in load_specs() if s.split == "test"}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def readonly_unqualified(digests: dict[str, str]) -> list[str]:
    """Tasks whose logs render has no passing read-only probe record at exactly this digest, with its evidence probes
    recorded (results/readonly-probe.json, `bench readonly-probe`): the arm's isolation is qualified per render."""
    path = ROOT / "results" / "readonly-probe.json"
    rows = json.loads(path.read_text()) if path.exists() else {}
    return sorted(t for t, d in digests.items() if not (rows.get(t, {}).get("ok") and rows[t].get("task_digest") == d
                                                         and "evidence_visible" in rows[t]))  # fmt: skip


def freeze(settings: dict) -> dict:
    from bench.run import lite_tasks, provider_kwargs

    k, lite_k, seed, maximum = (settings.get(key) for key in ("k", "lite_k", "seed", "max_trials"))
    if any(type(v) is not int for v in (k, lite_k, seed, maximum)):
        raise ValueError("k, lite_k, seed and max_trials are study decisions: give each as an integer "
                         "(docs/study-rules.md)")  # fmt: skip
    assert isinstance(k, int) and isinstance(lite_k, int) and isinstance(seed, int) and isinstance(maximum, int)
    if k < 1 or lite_k < k or maximum < 1:
        raise ValueError("counts must be positive and lite_k >= k")
    budget, row_budget = settings.get("budget_usd"), settings.get("row_budget_usd")
    if any(b is not None and (type(b) not in (int, float) or not b > 0) for b in (budget, row_budget)):
        raise ValueError("budget_usd and row_budget_usd must be positive numbers when given")
    configs = settings.get("configurations", [])
    if not configs or any(not c.get("model") or not c.get("reasoning_effort") for c in configs):
        raise ValueError("name every model and its reasoning_effort explicitly")
    configs = [{"agent": "terminus-2", **c} for c in configs]
    for c in configs:
        if set(c) - CONFIG_KEYS or c["agent"] != "terminus-2":
            raise ValueError("the scored full/ops-only protocol supports Terminus 2 configurations only")
        if c["reasoning_effort"] not in EFFORTS:
            raise ValueError("unsupported reasoning_effort for pinned Harbor")
        options = provider_kwargs(c["model"], c.get("provider"), c["agent"])
        if options:
            routing = json.loads(options[1].split("=", 1)[1])["extra_body"]["provider"]
            vendor = c["model"].removeprefix("openrouter/").split("/")[0]
            own = VENDOR_ENDPOINTS.get(vendor, {vendor})
            if not routing.get("quantizations") and routing["order"][0] not in own:
                raise ValueError("scored OpenRouter configurations require provider/precision (a vendor's own "
                                 "endpoint, e.g. openai for openai/..., needs no precision)")  # fmt: skip
    if len({digest(c) for c in configs}) != len(configs):
        raise ValueError("duplicate configurations")
    variants = settings.get("variants", DEFAULT_VARIANTS)
    if not variants or len(set(variants)) != len(variants) or any(v not in SCORED_VARIANTS for v in variants):
        raise ValueError(f"variants: a list of distinct arms from {', '.join(SCORED_VARIANTS)}")
    inputs = evaluation_inputs()
    if "logs" in variants:  # rendered at launch from code no other input pins
        inputs["variant_digests"] = {"logs": variant_digests("logs")}
        if unqualified := readonly_unqualified(inputs["variant_digests"]["logs"]):
            raise ValueError("the logs arm needs a passing read-only probe at each task's current render (bench "
                             f"readonly-probe): {', '.join(unqualified)}")  # fmt: skip
    if not inputs["images"] or any(not value["id"] for value in inputs["images"].values()):
        raise ValueError("freeze requires every image the tasks use to be built here: its full ID is the pin (a "
                         "registry digest, once the images are published, goes in the release bundle)")  # fmt: skip
    lite = set(lite_tasks())
    schedule = [
        {"configuration": i, "task": task, "variant": variant, "attempt": attempt}
        for i in range(len(configs))
        for task in sorted(inputs["tasks"])
        for variant in variants
        for attempt in range(1, (lite_k if task in lite else k) + 1)
    ]
    if len(schedule) > maximum:
        raise ValueError(
            f"schedule needs {len(schedule)} trials, above max_trials={maximum}; revise settings before freeze"
        )
    random.Random(seed).shuffle(schedule)
    body = {
        "schema": 1,
        "k": k,
        "lite_k": lite_k,
        "seed": seed,
        "max_trials": maximum,
        "budget_usd": budget,
        **({"row_budget_usd": row_budget} if row_budget is not None else {}),
        **({"variants": variants} if variants != DEFAULT_VARIANTS else {}),  # the study's manifests keep their ids
        "configurations": configs,
        "schedule": schedule,
        **inputs,
    }
    return {"id": digest(body), **body}


def validate(manifest: dict, *, allow_unqualified: bool = False) -> list[str]:
    """Refuse a manifest whose inputs changed since the freeze or whose tasks are not all green in `bench validation`.
    With `allow_unqualified` the second refusal is not raised: the tasks that are not green are returned instead, for
    the caller to warn about and record (a rebuilt-image host where release QA has not been re-run)."""
    if manifest.get("schema") != 1 or manifest.get("id") != digest({k: v for k, v in manifest.items() if k != "id"}):
        raise ValueError("manifest is invalid or changed after freezing")
    expected = freeze(manifest)
    if manifest != expected:
        raise ValueError("frozen schedule, tasks or images differ from current inputs")
    refs = image_tags()
    if any(refs.get(role) != value["ref"] for role, value in manifest["images"].items()):
        raise ValueError("image lock differs from the frozen manifest")
    rows = validation.build()
    unqualified = [task for task in manifest["tasks"] if not rows.get(task, {}).get("green")]
    if unqualified and not allow_unqualified:
        raise ValueError("tasks not qualified: " + ", ".join(unqualified) + " (--allow-unqualified runs them anyway, "
                         "recorded as not qualified)")  # fmt: skip
    return unqualified


def job_prefix(manifest_id: str) -> str:
    return f"scored-{manifest_id[:12]}-"


def cell_name(manifest_id: str, index: int, attempt: int = 0) -> str:
    """The --name of a cell's launch; bench run appends the variant, model and launch time."""
    return f"{job_prefix(manifest_id)}{index:05d}" + (f"-r{attempt}" if attempt else "")


def cell_args(manifest: dict, index: int, env_file: str, manifest_path: Path, attempt: int = 0) -> list[str]:
    cell = manifest["schedule"][index]
    config = manifest["configurations"][cell["configuration"]]
    args = [
        config["model"], cell["task"], "--agent", config["agent"], "--variant", cell["variant"],
        "--reasoning-effort", config["reasoning_effort"], "--env-file", env_file,
        "--name", cell_name(manifest["id"], index, attempt), "--held-out",
        "--protocol", str(manifest_path), "--cell", str(index),
    ]  # fmt: skip
    for key in ("provider", "agent_version"):
        if config.get(key):
            args += ["--" + key.replace("_", "-"), config[key]]
    return args


def launch(args: list[str]) -> int:
    """One cell as its own `bench run` process (so nothing shares this process's environment): Harbor's exit code."""
    return subprocess.run([sys.executable, "-m", "bench.run", *args], check=False).returncode


def _cell_of(job_name: str, prefix: str) -> int | None:
    index = job_name[len(prefix) :].split("-")[0] if job_name.startswith(prefix) else ""
    return int(index) if index.isdigit() else None


def statuses(manifest_id: str, cells: int) -> dict[int, str]:
    """Each cell from its job directories: pending (never launched), done (a counted trial exists), or unscored (jobs
    exist but none holds a counted trial: a provider error, a setup failure or an interrupted launch)."""
    prefix = job_prefix(manifest_id)
    out = {i: "pending" for i in range(cells)}
    for job in (RUNS / "jobs").glob(f"{prefix}*"):
        index = _cell_of(job.name, prefix)
        if index in out and job.is_dir():
            out[index] = "unscored"
    for t in analyze.load_trials([RUNS / "jobs"], prefix=prefix):
        index = _cell_of(t["job"], prefix)
        if index in out and t.get("counted"):
            out[index] = "done"
    return out


def spent(manifest_id: str) -> float:
    """Dollars the study's trials have reported so far (a trial without a cost counts nothing, and is not free)."""
    return sum(t.get("cost") or 0.0 for t in analyze.load_trials([RUNS / "jobs"], prefix=job_prefix(manifest_id)))


def row_spend(manifest: dict) -> dict[int, tuple[float, int]]:
    """Each configuration's reported dollars (every trial, counted or not) and counted cells so far."""
    prefix = job_prefix(manifest["id"])
    out: dict[int, tuple[float, int]] = {}
    for t in analyze.load_trials([RUNS / "jobs"], prefix=prefix):
        index = _cell_of(t["job"], prefix)
        if index is None or not 0 <= index < len(manifest["schedule"]):
            continue
        row = manifest["schedule"][index]["configuration"]
        dollars, counted = out.get(row, (0.0, 0))
        out[row] = (dollars + (t.get("cost") or 0.0), counted + bool(t.get("counted")))
    return out


def paused_rows(manifest: dict, cap: float | None) -> dict[int, str]:
    """The rows past their budget by more than ROW_OVERRUN (docs/study-rules.md), with the reason: their
    spend, or, once ROW_PROJECTION_AFTER of a row's cells are counted, its spend per counted cell over all its cells."""
    if cap is None:
        return {}
    limit, over = cap * ROW_OVERRUN, f"more than {ROW_OVERRUN - 1:.0%} over the row budget ${cap:.2f}"
    cells: dict[int, int] = {}
    for cell in manifest["schedule"]:
        cells[cell["configuration"]] = cells.get(cell["configuration"], 0) + 1
    out = {}
    for row, (dollars, counted) in row_spend(manifest).items():
        projected = dollars / counted * cells[row] if counted >= ROW_PROJECTION_AFTER else 0.0
        if dollars >= limit:
            out[row] = f"${dollars:.2f} spent, {over}"
        elif projected > limit:
            pace = f"${dollars:.2f} over {counted} counted cells projects ${projected:.2f} for its {cells[row]}"
            out[row] = f"{pace}, {over}"
    return out


def pause_note(manifest: dict, row: int, why: str) -> str:
    return (f"row paused: {manifest['configurations'][row]['model']}: {why}; its cells wait for a decision "
            "(--row-budget-usd; docs/study-rules.md)")  # fmt: skip


def configuration_indices(manifest: dict, wanted: list[str] | None) -> set[int]:
    """The configurations named by index or by a substring of their model (e.g. "qwen"); all when none are named."""
    configs = manifest["configurations"]
    if not wanted:
        return set(range(len(configs)))
    out: set[int] = set()
    for w in wanted:
        hits = (
            {int(w)} if w.isdigit() and int(w) < len(configs) else {i for i, c in enumerate(configs) if w in c["model"]}
        )
        if not hits:
            raise ValueError(f"no configuration matches {w!r}: {[c['model'] for c in configs]}")
        out |= hits
    return out


def run_schedule(
    path: Path, env_file: str, *, dry_run: bool = False, workers: int | None = None, retry: list[int] | None = None,
    configurations: list[str] | None = None, row_cap: float | None = None, allow_unqualified: bool = False,
) -> None:  # fmt: skip
    from bench import run

    manifest = json.loads(path.read_text())
    unqualified = validate(manifest, allow_unqualified=allow_unqualified)
    if unqualified:
        print(f"warning: {len(unqualified)} tasks are not qualified (--allow-unqualified); the run is recorded as "
              f"not qualified: {', '.join(unqualified)}", flush=True)  # fmt: skip
    if not dry_run:
        overrides = run.routed_through(env_file)
        if overrides:
            raise ValueError("endpoint overrides are not a scored route: " + ", ".join(overrides))
    limit = concurrency.measured()
    if not limit:  # None: no current record for this host; 0: measured, and no trial is safe
        raise ValueError("no current concurrency measurement for this host, or it permits no trials: run "
                         "`bench concurrency` on the idle host first (docs/leaderboard.md, Concurrency)")  # fmt: skip
    workers = limit if workers is None else workers
    if not 1 <= workers <= limit:
        raise ValueError(f"--workers must be between 1 and the measured concurrency, {limit}")
    cells = len(manifest["schedule"])
    retry = list(retry or [])
    if row_cap is not None and not row_cap > 0:
        raise ValueError("--row-budget-usd must be positive")
    cap = row_cap if row_cap is not None else manifest.get("row_budget_usd")
    # The lock is held across launches: two schedulers cannot run the same cell or exceed the measured concurrency.
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = path.with_suffix(".progress.json")
        state = (
            json.loads(state_path.read_text())
            if state_path.exists()
            else {"id": manifest["id"], "running": [], "attempts": {}}
        )
        if state.get("id") != manifest["id"]:
            raise ValueError(f"{state_path} belongs to another manifest")
        if unqualified and not dry_run:
            state["qualified"] = False  # sticky: a later launch with every task green does not clear it
        status = statuses(manifest["id"], cells)
        interrupted = sorted(i for i in state.get("running", []) if status.get(i) != "done")
        for i in retry:
            if not 0 <= i < cells:
                raise ValueError(f"no cell {i} in the schedule")
            if status[i] == "done":
                raise ValueError(f"cell {i} already holds a counted trial: a scored cell is one trial")
            if status[i] == "pending":
                raise ValueError(f"cell {i} was never launched; the schedule launches it")
        if retry:
            todo = retry
        elif interrupted:
            raise ValueError(
                f"interrupted launches {interrupted}: inspect their jobs under {RUNS / 'jobs'}/"
                f"{job_prefix(manifest['id'])}<cell>-*, then `bench protocol run --retry-cell N` for each"
            )
        else:
            # A block of configurations (`--configurations`) runs in the frozen order within the block; which blocks run
            # first is a budget decision, logged with the study rules, and the manifest's other rows stay pending.
            chosen = configuration_indices(manifest, configurations)
            todo = [i for i in range(cells) if status[i] == "pending"
                    and manifest["schedule"][i]["configuration"] in chosen]  # fmt: skip
        paused = paused_rows(manifest, cap)
        for row, why in sorted(paused.items()):
            print(pause_note(manifest, row, why))
        todo = [i for i in todo if manifest["schedule"][i]["configuration"] not in paused]
        attempts = {i: state["attempts"].get(str(i), 0) + (1 if retry else 0) for i in todo}
        if dry_run:
            for i in todo:
                print(f"{i}: " + " ".join(cell_args(manifest, i, env_file, path, attempts[i])))
            counts = {s: sum(1 for v in status.values() if v == s) for s in ("done", "unscored", "pending")}
            print(f"{len(todo)} launches, {workers} at a time; cells {counts}")
            return
        for i in todo:
            state["running"] = sorted(set(state["running"]) - {i})
            state["attempts"][str(i)] = attempts[i]
        _dispatch(path, manifest, todo, attempts, workers, env_file, state, state_path, cap, paused, allow_unqualified)
        status = statuses(manifest["id"], cells)
        unscored = sorted(i for i, s in status.items() if s == "unscored")
        done = sum(1 for s in status.values() if s == "done")
        print(f"cells done {done}/{cells}; unscored {unscored or 'none'}")
        if unscored:
            print(f"a cell without a counted trial is re-run by hand (docs/leaderboard.md, Errors): bench protocol run "
                  f"{path} --retry-cell {' '.join(map(str, unscored))}")  # fmt: skip


def _dispatch(
    path: Path, manifest: dict, todo: list[int], attempts: dict[int, int], workers: int, env_file: str,
    state: dict, state_path: Path, cap: float | None = None, paused: dict[int, str] | None = None,
    allow_unqualified: bool = False,
) -> None:  # fmt: skip
    """Launch the cells in order, `workers` at a time. Dispatching stops (running cells finish) when the budget is
    reached, when the inputs changed since the freeze, when the host's concurrency record no longer covers the workers,
    or after FAILED_LAUNCHES_MAX consecutive launches that exited nonzero; the cells not launched stay pending. A row
    that reaches its cap during the run launches no more cells, and the other rows go on."""
    budget = manifest.get("budget_usd")
    queue = list(todo)
    paused = dict(paused or {})
    failures = 0
    stop: Exception | None = None

    def save() -> None:
        state_path.write_text(json.dumps(state, indent=2) + "\n")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        running: dict[Future, int] = {}
        try:
            while queue or running:
                while queue and len(running) < workers and stop is None:
                    try:
                        if budget is not None and (cost := spent(manifest["id"])) >= budget:
                            raise ValueError(f"budget reached: ${cost:.2f} of ${budget:.2f} spent")
                        validate(
                            manifest, allow_unqualified=allow_unqualified
                        )  # inputs that changed since the freeze stop the rest of the schedule
                        if (concurrency.measured() or 0) < workers:
                            raise ValueError("the host's concurrency record no longer covers the running workers")
                    except ValueError as exc:
                        stop = exc
                        break
                    for row, why in sorted(paused_rows(manifest, cap).items()):
                        if row not in paused:
                            paused[row] = why
                            print(pause_note(manifest, row, why), flush=True)
                    queue = [i for i in queue if manifest["schedule"][i]["configuration"] not in paused]
                    if not queue:
                        break
                    index = queue.pop(0)
                    state["running"] = sorted(set(state["running"]) | {index})
                    save()
                    running[pool.submit(launch, cell_args(manifest, index, env_file, path, attempts[index]))] = index
                if not running:
                    break
                finished, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in finished:
                    index = running.pop(future)
                    code = future.result()
                    state["running"] = sorted(set(state["running"]) - {index})
                    save()
                    failures = failures + 1 if code else 0
                    if failures >= FAILED_LAUNCHES_MAX and stop is None:
                        stop = ValueError(f"{failures} consecutive launches exited nonzero; the host needs attention")
        finally:
            pool.shutdown(wait=True)  # a cell still running is interrupted only with the scheduler itself
    if stop is not None:
        raise stop


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench protocol", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    create = sub.add_parser("freeze")
    create.add_argument("settings", type=Path)
    create.add_argument("--out", type=Path, required=True)
    execute = sub.add_parser("run")
    execute.add_argument("manifest", type=Path)
    execute.add_argument("--env-file", default=str(ROOT / ".env"))
    execute.add_argument("--workers", type=int, help="cells at a time (default and maximum: the measured concurrency)")
    execute.add_argument("--retry-cell", type=int, nargs="+", help="launch these unscored cells again, as new attempts")
    execute.add_argument("--configurations", nargs="+", metavar="MODEL|INDEX",
                         help="run only these configurations' pending cells, a block, in the frozen order")  # fmt: skip
    execute.add_argument("--row-budget-usd", type=float, metavar="USD",
                         help="the per-row budget for this launch, in place of the manifest's row_budget_usd (a "
                         "budget decision, logged in docs/study-rules.md)")  # fmt: skip
    execute.add_argument("--allow-unqualified", action="store_true",
                         help="run tasks that are not green in `bench validation` (a host whose release QA has not "
                         "been re-run): a warning lists them, and the progress file records "
                         "qualified: false")  # fmt: skip
    execute.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.command == "freeze":
            manifest = freeze(json.loads(args.settings.read_text()))
            # Never overwrite a frozen schedule that may already have observations attached to it.
            with args.out.open("x") as output:
                output.write(json.dumps(manifest, indent=2) + "\n")
            print(f"frozen {len(manifest['schedule'])} trials: {args.out}")
        else:
            run_schedule(args.manifest, args.env_file, dry_run=args.dry_run, workers=args.workers,
                         retry=args.retry_cell, configurations=args.configurations,
                         row_cap=args.row_budget_usd, allow_unqualified=args.allow_unqualified)  # fmt: skip
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        ap.error(str(exc))


if __name__ == "__main__":
    main()
