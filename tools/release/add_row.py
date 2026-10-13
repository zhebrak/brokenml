"""A leaderboard row added since launch: results/rows/<slug>/ from the Harbor job directories of its three runs.

    uv run python tools/release/add_row.py --jobs runs/jobs --prefix row-flash --slug qwen3.8-flash \
        --name "Qwen3.8 Flash" --source contributor --submitted-by <github handle> --archive <url>

The three runs (`bench run ... --variant standard`, `logs` and `ablation`, one configuration, one `--name`) are read
with `bench.analyze.load_trials`, the classifier the launch tables came from, so the row is counted as those rows
were: one verdict per task and condition, the earliest where a cell was run more than once (the later attempts stay
in the trial files as rerolled), re-runs where an attempt never had a fair run, every attempt kept. The tool refuses
a row that is not complete, that mixes configurations or is not the board's (Terminus 2 on Harbor 0.23.0 at high
effort, timeout multiplier 1, no extra hosts or tools, a pinned route, Harbor's own retry policy as `bench run` sets
it), whose jobs are not whole (a job renamed, or a trial the job reports without its directory), whose tasks are not
the dataset version's (each counted trial's lock digest against the dataset for the live cluster and against a fresh
render for the other two variants), whose images are not the launch images, that re-graded a scored verdict (an infra
cell may be re-graded twice, a throughput verdict timed on a busy host once), or that still has open reviews: an
infra cell without its re-grades, a throughput verdict timed on a busy host and not re-graded, or a pass with audit
hits that the row's review file (`review.yaml`: lists `zeroed` and `kept`, each entry `trial` and `reason`) does not
settle. It writes trials.jsonl and trials.csv (the launch dataset's columns, manifest empty), scoreboard.csv,
review.yaml and, last, row.yaml (what the row is, where it ran, what was counted). `make readme-table` draws every
row under results/rows/ next to the launch rows after re-checking it. docs/leaderboard.md has the rules;
CONTRIBUTING.md the pull request."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import tomllib
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_dataset as ds  # noqa: E402
from draw_leaderboard import BOARD, DATASET, ROWS, STUDY, board_models, norm_model  # noqa: E402

from bench import analyze, concurrency  # noqa: E402
from bench.run import SETUP_ERRORS  # noqa: E402

STUDY_IMAGES = ROOT / "images" / "study-images.json"
CONCURRENCY = ROOT / "results" / "concurrency.json"
SOURCES = ("maintainers", "contributor")
SLUG = re.compile(r"[a-z0-9][a-z0-9.-]*$")
REGRADES = 3  # gradings an infra or verifier_bug cell has had when its two allowed re-grades are spent
PIN_KEYS = {"order", "allow_fallbacks", "quantizations"}
# The board's trial configuration, as Harbor locks it (lock.json). Every field is compared; a field the board does
# not set is accepted only at its unset value, so a budget, resource or input Harbor adds later cannot pass unnoticed.
LOCK_DEFAULTS = {"install_only": False, "timeout_multiplier": 1.0, "skills": []}
LOCK_FREE = {"schema_version", "task", "bridge_inputs", "agent", "environment", "verifier"}  # identity, not settings
AGENT_DEFAULTS = {"name": BOARD["agent"], "skills": [], "resume_trajectory": False, "extra_allowed_hosts": [],
                  "mcp_servers": []}  # fmt: skip
AGENT_FREE = {"model_name", "kwargs"}  # the model, and the two options checked below
ENV_DEFAULTS = {"type": "docker", "force_build": False, "delete": True, "cpu_enforcement_policy": "auto",
                "memory_enforcement_policy": "auto", "extra_docker_compose": [], "kwargs": {},
                "extra_allowed_hosts": []}  # fmt: skip
VERIFIER_DEFAULTS = {"disable": False, "environment_mode": "separate"}
# The job as `bench run` launches it (the job's lock.json): Harbor itself, and the retry policy. Harbor deletes a
# retried attempt's directory, so a wider policy would re-roll trials unseen; this one retries only setup failures.
HARBOR_LOCK = {"version": BOARD["harbor"], "is_editable": False}
RETRY_MAX = 2
HARBOR_EXCLUDES = frozenset({
    "RewardFileNotFoundError", "ModelNotFoundError", "ApiUsageLimitError", "RewardFileEmptyError",
    "VerifierOutputParseError", "AgentTimeoutError", "AgentAuthenticationError", "VerifierTimeoutError",
    "AgentSafetyRefusalError",
})  # fmt: skip
HOST_RECORD_KEYS = {"safe_n", "host", "levels", "inputs", "tasks"}  # what bench concurrency writes


def dataset_tasks(path: Path = DATASET) -> tuple[str, dict[str, str]]:
    """(dataset version, {task: digest}) of the test split."""
    d = tomllib.loads(path.read_text())
    return d["dataset"]["version"], {t["name"].split("/")[-1]: t["digest"] for t in d["tasks"]}


def study_builds(path: Path = STUDY_IMAGES) -> dict[str, str]:
    """{role: BUILD id} of the launch images (runtime, harness, serve, runtime-getenvfix)."""
    return {role: img["build"] for role, img in json.loads(path.read_text())["images"].items()}


def expected_digest(tasks: dict[str, str]) -> Callable[[str, str], str]:
    """The digest a counted trial of (task, variant) must carry: the dataset's for the live cluster (the standard
    render), a fresh render's for the other variants. `bench run` renders each task under an opaque directory name,
    which does not enter the digest."""

    def expect(task: str, variant: str) -> str:
        return tasks[task] if variant == "standard" else analyze.current_digest(task, variant)

    return expect


def job_stamp(job: str) -> str:
    """The launch time at the end of a job directory name (YYYYMMDD-HHMMSS)."""
    return "-".join(job.rsplit("-", 2)[-2:])


def _unset(v: object) -> bool:
    """A field Harbor wrote but nobody set: null, false, or an empty list, dict or string. A number is a setting."""
    return v is None or v is False or (isinstance(v, (list, dict, str)) and not v)


def _diff(section: str, got: dict, want: dict, free: set[str]) -> list[str]:
    out = [f"{section} {k} is {json.dumps(got.get(k))[:60]} (the board is {json.dumps(v)})"
           for k, v in want.items() if got.get(k, v) != v]  # fmt: skip
    out += [f"{section} {k} is set: {json.dumps(v)[:60]}" for k, v in got.items()
            if k not in want and k not in free and not _unset(v)]  # fmt: skip
    return out


def lock_problems(lock: dict) -> list[str]:
    """What in a trial's lock.json is not the board's configuration."""
    agent = lock.get("agent") or {}
    kwargs = agent.get("kwargs") or {}
    out = _diff("lock", lock, LOCK_DEFAULTS, LOCK_FREE)
    out += _diff("agent", agent, AGENT_DEFAULTS, AGENT_FREE)
    if kwargs.get("reasoning_effort") != BOARD["effort"]:
        out.append(f"reasoning effort {kwargs.get('reasoning_effort')!r} (the board is {BOARD['effort']})")
    extra = sorted(set(kwargs) - {"reasoning_effort", "llm_call_kwargs"})
    if extra:
        out.append(f"agent options beyond the effort and the route pin: {', '.join(extra)}")
    llm = kwargs.get("llm_call_kwargs")
    routed = str(agent.get("model_name") or "").startswith("openrouter/")
    if routed and not llm:
        out.append("an OpenRouter model without a provider pin (bench run --provider SLUG[/QUANT])")
    elif not routed and llm:
        out.append("a vendor route carries no provider pin; llm_call_kwargs is set")
    elif llm:
        body = llm.get("extra_body") if isinstance(llm, dict) else None
        pin = (body or {}).get("provider") if isinstance(body, dict) else None
        if set(llm) != {"extra_body"} or set(body or {}) != {"provider"} or not isinstance(pin, dict):
            out.append("llm_call_kwargs carries more than the provider pin")
        elif (set(pin) - PIN_KEYS or pin.get("allow_fallbacks", True) is not False
              or len(pin.get("order") or []) != 1
              or ("quantizations" in pin and len(pin["quantizations"] or []) != 1)):  # fmt: skip
            out.append(f"provider pin is not a single provider at one precision with fallbacks off: {json.dumps(pin)}")
    out += _diff("environment", lock.get("environment") or {}, ENV_DEFAULTS, set())
    out += _diff("verifier", lock.get("verifier") or {}, VERIFIER_DEFAULTS, set())
    return out


def job_problems(job: Path, planned: int | None) -> list[str]:
    """What in a job directory is not a whole `bench run` job: Harbor or its retry policy other than the board's, a
    directory renamed, a trial the job's own result reports without its directory (a removed attempt), or, for the
    first job of an arm, fewer planned trials than the dataset has tasks (`planned`)."""
    lock, cfg, res = (analyze._json(job / f) for f in ("lock.json", "config.json", "result.json"))
    out = []
    if lock.get("harbor") != HARBOR_LOCK:
        out.append(f"Harbor {json.dumps(lock.get('harbor'))} (the board is {json.dumps(HARBOR_LOCK)})")
    retry = lock.get("retry") or {}
    wide = (int(retry.get("max_retries") or 0) > RETRY_MAX
            or not set(retry.get("include_exceptions") or []) <= set(SETUP_ERRORS)
            or not set(retry.get("exclude_exceptions") or []) >= HARBOR_EXCLUDES)  # fmt: skip
    if wide:
        out.append(f"retry policy {json.dumps(retry)[:120]} is wider than bench run's (setup failures only, at most "
                   f"{RETRY_MAX} retries)")  # fmt: skip
    if cfg.get("job_name") != job.name:
        out.append(f"job directory {job.name} was launched as {cfg.get('job_name')!r}")
    reported: set[str] = set()
    for ev in (res.get("stats") or {}).get("evals", {}).values():
        for names in (ev.get("reward_stats") or {}).get("reward", {}).values():
            reported.update(names)
        for names in (ev.get("exception_stats") or {}).values():
            reported.update(names)
    gone = sorted(n for n in reported if not (job / n).is_dir())
    if gone:
        out.append(f"attempts the job reports have no directory: {gone[:4]}{'...' if len(gone) > 4 else ''}")
    if planned is not None and len(lock.get("trials") or []) != planned:
        out.append(f"the first job of its arm planned {len(lock.get('trials') or [])} trials, not {planned} (one per "
                   "dataset task)")  # fmt: skip
    return out


def build_problems(t: dict, builds: dict[str, str]) -> list[str]:
    """A counted trial's image builds, as the verifier recorded them per role, against the launch images: the
    runtime and harness it graded with, the nodes' or the engine's build where a job ran. The patched runtime is
    accepted on the nodes only where a registered re-grade records it."""
    ev = t.get("evaluation") or {}
    out = []
    for role in ("runtime", "harness"):
        got = ev.get(role, "unknown")
        if got != builds[role] and not (got == "unknown" and t["outcome"] in analyze.RESIDUAL):
            out.append(f"{role} image build {got}, not the launch build {builds[role]} (make image-pull)")
    node = ev.get("cpu-node")
    if (
        node is not None
        and node != builds["runtime"]
        and not (t.get("patched_runtime") and node == builds.get("runtime-getenvfix"))
    ):
        out.append(f"nodes ran image build {node}, not the launch runtime")
    if ev.get("gpu-node") is not None:
        out.append("ran on GPU nodes; the board is the CPU benchmark")
    serve = ev.get("serve")
    if serve is not None and serve != builds.get("serve"):
        out.append(f"the engine ran image build {serve}, not the launch serve build {builds.get('serve')}")
    if not t.get("provenance_complete", True) and t.get("reward") == 1.0:  # a pass ran the job: every role is known
        out.append("image provenance incomplete on a pass: no build recorded for "
                   + ", ".join(t.get("unobserved_builds") or ["a role the grading used"]))  # fmt: skip
    return out


def grading_problem(t: dict) -> str | None:
    """A verdict is graded once. An infra or verifier_bug grading may be re-graded twice; a throughput verdict timed
    on a busy host (or across a load shift) once, on a quiet host; nothing else (docs/leaderboard.md, Re-grades)."""
    n = t.get("scored_gradings") or 1
    if n <= 1:
        return None
    first = t.get("first_outcome")
    if first in analyze.RESIDUAL:
        return None if n <= REGRADES else f"graded {n} times; an infra cell is re-graded at most twice"
    if t.get("first_busy"):
        return None if n <= 2 else f"graded {n} times; a busy-timed throughput verdict is re-graded once"
    return (
        f"re-graded a scored verdict (first grading: {first}); only infra cells and busy-timed throughput verdicts are"
    )


def timing_problem(t: dict) -> tuple[str | None, str | None]:
    """(problem, note) for a counted throughput verdict: a verdict timed with either run at BUSY_HIGH or more that
    was never re-graded is a problem (docs/leaderboard.md asks for a quiet-host re-grade); a verdict listed only for a
    load shift stands, since the verifier already turns a shift that favoured the verdict into an infra failure."""
    if t.get("tput_ok") is None:
        return None, None
    ref, job = t.get("host_busy_ref"), t.get("host_busy_job")
    if ref is None or job is None:
        return None, None
    ratio, floor = t.get("tput_ratio"), t.get("tput_min")
    close = ratio is None or floor is None or floor / analyze.TPUT_MARGIN <= ratio <= floor * analyze.TPUT_MARGIN
    if not close:
        return None, None
    verdict = "pass" if t["tput_ok"] else "fail"
    where = f"host busy {ref:.0%} during the reference, {job:.0%} during the job"
    if max(ref, job) >= analyze.BUSY_HIGH and (t.get("scored_gradings") or 1) <= 1:
        return (f"throughput {verdict} at ratio {ratio} timed on a busy host ({where}); re-grade it on a quiet host "
                f"(uv run bench regrade {t['dir']})", None)  # fmt: skip
    if abs(ref - job) >= analyze.BUSY_SHIFT:
        return None, f"throughput {verdict} at ratio {ratio} listed for a load shift ({where}); it stands"
    return None, None


def check_row(
    trials: list[dict],
    tasks: dict[str, str],
    *,
    expect: Callable[[str, str], str],
    builds: dict[str, str],
    review: dict[str, dict[str, str]],
    harbor: set[str | None],
) -> tuple[list[str], list[str]]:
    """(problems, notes): why these trials are not a complete leaderboard row, and what the tool settled itself (a cell
    run more than once keeps its earliest verdict; the later attempts are marked rerolled in place). `expect` gives
    the digest a counted trial must carry; `builds` the launch image builds; `review` the row's review file as
    {"zeroed": {trial: reason}, "kept": {trial: reason}}; `harbor` the jobs' Harbor versions."""  # fmt: skip
    problems: list[str] = []
    notes: list[str] = []
    ids = sorted({f"{t['label']} #{t['config_id']}" for t in trials})
    if len(ids) > 1:
        problems.append("more than one configuration: " + "; ".join(ids))
    for version in sorted({str(v) for v in harbor}):
        if version != BOARD["harbor"]:
            problems.append(f"Harbor {version} (the board is {BOARD['harbor']})")
    seen_lock: set[str] = set()
    for t in trials:
        for p in lock_problems(t.get("lock") or {}):
            if p not in seen_lock:
                seen_lock.add(p)
                problems.append(p)
    known = {t["trial"] for t in trials}
    for kind in ("zeroed", "kept"):
        for trial in sorted(set(review[kind]) - known):
            problems.append(f"review.yaml lists {trial} under {kind}, which is no trial of this row")
    for trial in sorted(set(review["zeroed"]) & set(review["kept"])):
        problems.append(f"review.yaml lists {trial} as both zeroed and kept")
    cells: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in trials:
        if t["variant"] not in ds.ARMS:
            problems.append(f"{t['job']}: variant {t['variant']} is not a leaderboard condition")
            continue
        cells[(t["task"], t["variant"])].append(t)
    for key, attempts in cells.items():
        counted = sorted((t for t in attempts if t.get("counted")),
                         key=lambda t: (str(t.get("started") or ""), t["trial"]))  # fmt: skip
        for t in counted[1:]:  # the earliest verdict counts; the later ones stay on record, never scored
            t.update(outcome=analyze.REROLLED, scored=False, counted=False)
            notes.append(f"{ds.ARMS[key[1]]}, {key[0]}: {t['trial']} ran after {counted[0]['trial']} had a verdict; "
                         "kept as rerolled")  # fmt: skip
    for t in trials:
        if not t.get("counted") or t["task"] not in tasks or t["variant"] not in ds.ARMS:
            continue
        cell = f"{ds.ARMS[t['variant']]}, {t['task']}"
        want = expect(t["task"], t["variant"])
        if t.get("digest") != want:
            problems.append(f"{cell}: task digest {str(t.get('digest'))[:19]} is not the dataset's {want[:19]} (an "
                            "edited task, or another dataset version)")  # fmt: skip
        problems.extend(f"{cell}: {p}" for p in build_problems(t, builds))
        if t.get("other_version_gradings") and not t.get("patched_runtime"):
            problems.append(f"{cell}: a grading on another task version exists but is not registered in "
                            "protocol/patched-gradings.json (bench regrade --runtime registers it; the pull request "
                            "carries the entry)")  # fmt: skip
        if problem := grading_problem(t):
            problems.append(f"{cell}: {problem}")
        if t["outcome"] in analyze.RESIDUAL and (t.get("scored_gradings") or 1) < REGRADES:
            problems.append(f"{cell}: {t['outcome']} after {t.get('scored_gradings') or 1} grading(s); re-grade it "
                            f"(uv run bench regrade {t['dir']})")  # fmt: skip
        problem, note = timing_problem(t)
        if problem:
            problems.append(f"{cell}: {problem}")
        if note:
            notes.append(f"{cell}: {note}")
        reviewed = t["trial"] in review["zeroed"] or t["trial"] in review["kept"]
        if t.get("reward") == 1.0 and t.get("audit") and not reviewed:
            problems.append(f"{cell}: pass {t['trial']} with audit hits ({'; '.join(t['audit'])[:120]}); read it and "
                            "list it in review.yaml under zeroed or kept")  # fmt: skip
    missing: dict[str, list[str]] = defaultdict(list)
    for variant, condition in ds.ARMS.items():
        for task in sorted(tasks):
            attempts = cells.get((task, variant), [])
            if any(t.get("counted") for t in attempts):
                continue
            why = "; ".join(f"{t['trial']}: {t.get('rerun_reason') or t['outcome']}" for t in attempts) or "not run"
            problems.append(f"{condition}, {task}: no verdict ({why})")
            missing[variant].append(task)
    if missing:
        model, route = ds.parse_label(trials[0]["label"]) if trials else ("<model>", "")
        pin = f" --provider {route}" if route and model.startswith("openrouter/") else ""
        prefix = trials[0]["job"].split("-" + trials[0]["variant"] + "-")[0] if trials else "<row>"
        for variant, names in missing.items():
            notes.append(f"re-run: uv run bench run {model} {' '.join(names)} --split test --variant {variant} "
                         f"--reasoning-effort high{pin} -n <measured> --env-file <keys> --name {prefix}")  # fmt: skip
    return problems, notes


def launch_inputs(tasks: list[str]) -> dict:
    """What `bench concurrency` records as its inputs when it runs on the launch images: the same computation as
    bench.concurrency.inputs, with the launch images' ids (images/study-images.json) in place of the local ones, so
    a record can be checked on a machine that has not pulled them."""
    available = {img["tag"]: img["id"] for img in json.loads(STUDY_IMAGES.read_text())["images"].values()}
    tests = concurrency.TASKS / "test"
    images = {ref: iid for t in tasks for ref, iid in concurrency.task_image_ids(tests / t, available).items()}
    if not images or not all(images.values()):
        raise ValueError("the measured tasks name images that are not the launch images")
    return {"tasks": {t: concurrency.grader_digest(tests / t) for t in tasks}, "images": images,
            "rule": concurrency.RULE_VERSION,
            "thresholds": [concurrency.RATIO_DRIFT, analyze.BUSY_HIGH, analyze.BUSY_SHIFT]}  # fmt: skip


def host_record_problem(measured: dict) -> str | None:
    """Why a concurrency record cannot stand for the run host: not a `bench concurrency` record (host signature,
    levels, inputs, measured tasks), no integer safe level, levels that do not support it without a gap, tasks other
    than the throughput-gated ones, or inputs other than the launch images and the current tasks under the current
    rule (what `bench run -n` checks, without the host signature: a maintainer rebuilding a row from an archive is not
    on the run host). The record is the submitter's own measurement; the verifier's timing review is the guard."""
    missing = sorted(HOST_RECORD_KEYS - set(measured))
    if missing:
        return f"not a bench concurrency record (missing {', '.join(missing)})"
    safe, tasks = measured.get("safe_n"), measured.get("tasks")
    if type(safe) is not int or safe < 0 or not (measured.get("host") or {}).get("cpu"):
        return "the concurrency record has no integer safe_n or no host signature"
    levels = measured.get("levels") or {}
    if any(not (levels.get(str(n)) or {}).get("safe") for n in range(1, safe + 1)):
        return f"the record's levels do not support safe_n {safe} without a gap"
    if not isinstance(tasks, list) or not all(isinstance(t, str) for t in tasks):
        return "the record names no measured tasks"
    if not set(concurrency.DEFAULT_TASKS) <= set(tasks) <= set(concurrency.throughput_tasks()):
        return "the record's measured tasks are not the throughput-gated tasks"
    try:
        if measured.get("inputs") != launch_inputs(tasks):
            return ("measurement stale: not measured on the launch images and the current tasks under the current "
                    "rule (make image-pull, then bench concurrency)")  # fmt: skip
    except ValueError as e:
        return f"cannot check the measurement: {e}"
    return None


def load_review(path: Path) -> dict[str, dict[str, str]]:
    """review.yaml: {"zeroed": {trial: reason}, "kept": {trial: reason}} (absent file: nothing reviewed). Every
    entry names its trial and gives a reason; a zeroed trial scores 0 by that reason."""
    d = (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}
    out: dict[str, dict[str, str]] = {}
    for k in ("zeroed", "kept"):
        out[k] = {}
        for e in d.get(k) or []:
            if not isinstance(e, dict) or not e.get("trial") or not str(e.get("reason") or "").strip():
                raise SystemExit(f"{path}: every entry under {k} names a trial and gives a reason: {e!r}")
            out[k][e["trial"]] = str(e["reason"]).strip()
    return out


def enrich(trials: list[dict], planned: int) -> tuple[set[str | None], int, int, list[str]]:
    """Attach each trial's lock.json and start time; check each job once (the first job of each arm must have
    planned every dataset task). Returns the jobs' Harbor versions, the largest concurrency any job ran at, Harbor's
    own retries (setup failures), and the job problems."""
    harbor: set[str | None] = set()
    concurrency_n, retries, problems = 0, 0, []
    jobs: dict[Path, str] = {}
    for t in trials:
        origin = Path(t["origin"])
        t["lock"] = analyze._json(origin / "lock.json")
        t["started"] = analyze._json(origin / "result.json").get("started_at") or job_stamp(t["job"])
        jobs.setdefault(origin.parent, t["variant"])
    first: dict[str, Path] = {}
    for job in sorted(jobs, key=lambda j: str(analyze._json(j / "result.json").get("started_at") or j.name)):
        first.setdefault(jobs[job], job)
    for job, variant in jobs.items():
        lock, cfg, res = (analyze._json(job / f) for f in ("lock.json", "config.json", "result.json"))
        harbor.add((lock.get("harbor") or {}).get("version"))
        concurrency_n = max(concurrency_n, int(cfg.get("n_concurrent_trials") or 1))
        retries += int((res.get("stats") or {}).get("n_retries") or 0)
        problems += [f"{job.name}: {p}" for p in job_problems(job, planned if first.get(variant) == job else None)]
    return harbor, concurrency_n, retries, problems


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--jobs", type=Path, nargs="+", required=True, help="directories of Harbor job directories")
    ap.add_argument("--prefix", required=True, help="the --name the runs were given (keeps those job directories)")
    ap.add_argument("--slug", required=True, help="the row's directory name under results/rows/, e.g. qwen3.8-flash")
    ap.add_argument("--name", required=True, help="the model's display name on the leaderboard")
    ap.add_argument("--added", default=dt.date.today().isoformat(), help="the date the row is added (ISO)")
    ap.add_argument("--source", choices=SOURCES, required=True, help="who ran it")
    ap.add_argument("--submitted-by", default="", help="GitHub handle (required for a contributor's row)")
    ap.add_argument("--archive", default="",
                    help="where the Harbor job directories, trajectories included, can be fetched (a contributor's "
                         "row)")  # fmt: skip
    ap.add_argument("--link", default="", help="the pull request (the maintainers set it when they merge)")
    ap.add_argument("--note", default="", help="one line a reader of the row should know")
    ap.add_argument("--review", type=Path,
                    help="the row's review.yaml (zeroed and kept trials); default: none reviewed")  # fmt: skip
    ap.add_argument("--host-record", type=Path, default=CONCURRENCY,
                    help="the run host's bench concurrency record (default results/concurrency.json; a maintainer "
                         "rebuilding a row passes the one archived with the jobs)")  # fmt: skip
    ap.add_argument("--out", type=Path, default=ROWS)
    ap.add_argument("--force", action="store_true", help="overwrite the row directory (a local re-run of the tool)")
    args = ap.parse_args()

    if not SLUG.match(args.slug):
        print(f"slug {args.slug!r}: use lower-case letters, digits, dots and dashes, e.g. qwen3.8-flash")
        return 1
    if args.source == "contributor" and not (args.submitted_by and args.archive):
        print("a contributor's row names its submitter and its archive: --submitted-by <github handle> --archive <url>")
        return 1
    version, tasks = dataset_tasks()
    if version != BOARD["dataset"]:
        print(f"this checkout is dataset {version}; the board is {BOARD['dataset']}, and rows are never pooled "
              "across versions")  # fmt: skip
        return 1
    trials = [t for t in analyze.load_trials([d.expanduser() for d in args.jobs], prefix=args.prefix)
              if t["task"] in tasks]  # fmt: skip
    if not trials:
        print(f"no trials of the test split under {', '.join(map(str, args.jobs))} with prefix {args.prefix!r}")
        return 1
    model, route = ds.parse_label(trials[0]["label"])
    taken = board_models(STUDY, args.out)
    if norm_model(model) in taken and taken[norm_model(model)] != args.slug:
        print(f"{model} is already on the board ({taken[norm_model(model)]}); the board has one row per model "
              "(CONTRIBUTING.md)")  # fmt: skip
        return 1
    released, late = analyze.row_release(trials[0]["label"], analyze.model_dates())
    if released is None:
        print(f"{model} has no release date in results/models.yaml; add it first (see the file's header)")
        return 1
    review = load_review(args.review) if args.review else {"zeroed": {}, "kept": {}}
    harbor, concurrency_n, retries, problems = enrich(trials, len(tasks))
    more, notes = check_row(trials, tasks, expect=expected_digest(tasks), builds=study_builds(), review=review,
                            harbor=harbor)  # fmt: skip
    problems += more
    for line in notes:
        print("note: " + line)
    if problems:
        print(f"not a complete row ({len(problems)} problems):")
        print("\n".join("  " + p for p in problems))
        return 1
    measured = json.loads(args.host_record.read_text()) if args.host_record.exists() else {}
    record_problem = host_record_problem(measured) if measured else "missing"
    if record_problem:
        print(f"{args.host_record}: {record_problem} (bench concurrency writes it on the run host; a maintainer "
              "rebuilding a row passes --host-record)")  # fmt: skip
        return 1
    if concurrency_n > int(measured["safe_n"]):
        print(f"the runs used -n {concurrency_n}, above the {measured['safe_n']} the host measured (bench concurrency)")
        return 1
    order = {v: i for i, v in enumerate(ds.ARMS)}
    trials.sort(key=lambda t: (order[t["variant"]], t["task"], str(t.get("started") or ""), t["trial"]))
    host = str((measured.get("host") or {}).get("cpu") or "unknown host")
    records, cell_of, attempt_of = [], {}, defaultdict(int)
    for t in trials:
        key = (t["variant"], t["task"])
        cell_of.setdefault(key, len(cell_of))
        records.append(ds.trial_record(t, Path(t["origin"]), Path(t["dir"]), host=host, zeroed=review["zeroed"],
                                       behaviour={}, cell=cell_of[key], attempt=attempt_of[key],
                                       not_reported=""))  # fmt: skip
        attempt_of[key] += 1
    board = ds.scoreboard(records)
    first = defaultdict(int)  # solved on first attempts only, an attempt without a verdict counting as a fail
    for r in records:
        if r["attempt"] == 0 and r["solved"]:
            first[r["condition"]] += 1
    unknown_cost = sum(1 for t in trials if t.get("counted") and t.get("cost") is None)
    stamps = sorted(str(t["started"])[:10].replace("-", "") for t in trials)
    out = args.out / args.slug
    if out.exists() and not args.force:
        print(f"{out} exists; --force overwrites it")
        return 1
    out.mkdir(parents=True, exist_ok=True)
    ds.write_csv(out / "trials.csv", records)
    with (out / "trials.jsonl").open("w") as fh:
        fh.write(json.dumps({"canary": ds.CANARY}) + "\n")
        fh.writelines(json.dumps(r) + "\n" for r in records)
    ds.write_csv(out / "scoreboard.csv", board)
    (out / "review.yaml").write_text(
        f"# {ds.CANARY}\n# Passing trials with audit hits, read by the maintainers: zeroed (the flagged content\n"
        "# reached /ops or ANALYSIS.md) or kept. Each entry: trial, reason.\n"
        + yaml.safe_dump({k: [{"trial": tr, "reason": why} for tr, why in v.items()] for k, v in review.items()},
                         sort_keys=False, allow_unicode=True))  # fmt: skip
    counted = [t for t in trials if t.get("counted")]
    row = {
        "slug": args.slug, "name": args.name, "model": model, "route": route or None,
        "label": trials[0]["label"], "config_id": trials[0]["config_id"],
        "agent": BOARD["agent"], "effort": BOARD["effort"], "harbor": BOARD["harbor"], "dataset": version,
        "builds": sorted({f"{role} {b}" for t in counted for role, b in (t.get("evaluation") or {}).items()
                          if role in ("runtime", "harness", "cpu-node", "serve")}),
        "host": {**(measured.get("host") or {}), "safe_n": measured.get("safe_n"), "record": measured.get("job"),
                 "measured": (measured.get("stamp") or {}).get("utc")},
        "concurrency": concurrency_n, "harbor_retries": retries,
        "runs": {"first": stamps[0], "last": stamps[-1]},
        "added": args.added, "source": args.source, "submitted_by": args.submitted_by or None,
        "archive": args.archive or None, "link": args.link or None, "note": args.note or None,
        "released": released, "released_after_publication": bool(late),
        "attempts": len(records), "counted": len(counted),
        "rerolled": sum(r["outcome"] == analyze.REROLLED for r in records),
        "residual": sum(t["outcome"] in analyze.RESIDUAL for t in counted),
        "regraded": sum((t.get("scored_gradings") or 1) > 1 for t in counted),
        "timing_review": analyze.timing_review(counted)[0],
        "zeroed": len(review["zeroed"]), "kept_after_review": len(review["kept"]),
        "solved": {b["condition"]: b["solved"] for b in board},
        "solved_first_attempt": {b["condition"]: first[b["condition"]] for b in board},
        "cost_recorded": None if unknown_cost else round(sum(r["cost_recorded"] for r in records), 4),
        "cost_unknown_trials": unknown_cost, "cutoff_responses": sum(r["cutoff_responses"] for r in records),
    }  # fmt: skip
    (out / "row.yaml").write_text(f"# {ds.CANARY}\n" + yaml.safe_dump(row, sort_keys=False, allow_unicode=True))
    solved = ", ".join(f"{b['condition']} {b['solved']}/{b['tasks']}" for b in board)
    cost = "cost unknown" if unknown_cost else f"${row['cost_recorded']:.2f} recorded"
    print(f"{out}: {len(records)} attempts, {len(counted)} counted; {solved}; {cost}")
    print("next: make readme-table, then open the pull request (CONTRIBUTING.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
