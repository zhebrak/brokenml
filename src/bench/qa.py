"""Stage-1 quality gate for a rendered task.

  bench qa TASK [--release] [--oracle N] [--nop N] [--no-wrong] [-n CONCURRENCY]

Checks:
  static       canary in every file, no solution/tests in the agent image, no network fetches in test.sh, named
               volumes only, only /ops crosses to the verifier, images pinned by digest (release)
  isolation    the agent's containers hold the platform only; the harness image runs only in sidecars
  calibration  loss_max clears legitimate runs and rejects shortcuts, each by 3x the legitimate spread, measured on
               the current images (results/calibration/<set>.json)
  oracle       the reference fix scores 1 on every run (also the flakiness check)
  nop          doing nothing scores 0, and provisioning observed the intended symptom
  wrong        every scripted wrong fix scores 0, and every accepted alternative fix scores 1

Writes runs/qa/<task>.md and .json (results/qa/ in release mode), stamped; bench validation reads the JSON.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import yaml

from bench import outcomes, patches, sweep
from bench.calibrate import set_declaration, set_inputs, set_kinds
from bench.constants import CANARY_GUID
from bench.paths import RESULTS, RUNS
from bench.provenance import (
    calibration_digest,
    describe,
    image_ids,
    image_tags,
    images_match,
    stamp,
    task_digest,
    task_image_ids,
)
from bench.spec import by_id, task_dir

HARBOR = os.environ.get("HARBOR", "harbor").split()  # e.g. HARBOR="sudo -n env PATH=$PATH harbor" on a shared box
HARBOR_TIMEOUT_S = 7200
Row = tuple[str, bool, str]
# The rows a release record measured with trials (bench qa --regrade reuses them; every other row is re-evaluated).
TRIAL_ROW = re.compile(
    r"(oracle \d+/\d+|nop \d+/\d+ score 0|symptom observed at bootstrap|(wrong|accepted) fix '.+' scores [01])"
)


def _image_refs(task: Path) -> list[str]:
    refs = [line.split()[1] for f in task.rglob("Dockerfile*") for line in f.read_text().splitlines()
            if line.startswith("FROM ")]  # fmt: skip
    for compose in (task / "environment" / "docker-compose.yaml", task / "tests" / "docker-compose.yaml"):
        refs += [svc["image"] for svc in yaml.safe_load(compose.read_text())["services"].values() if "image" in svc]
    return sorted(set(refs))


def static_checks(task: Path) -> list[Row]:
    out: list[Row] = []
    missing = [
        str(p.relative_to(task))
        for p in task.rglob("*")
        if p.is_file()
        and p.suffix in (".md", ".toml", ".sh")
        and p.name != "ANALYSIS.md"
        and p.parent.name != "files"
        and "ops" not in p.relative_to(task).parts
        and "pristine" not in p.parts
        and "reference" not in p.parts
        and CANARY_GUID not in p.read_text()
    ]
    out.append(("canary in task files", not missing, ", ".join(missing)))
    refs = _image_refs(task)
    locked = set(image_tags().values())
    unpinned = [r for r in refs if "@sha256:" not in r or r not in locked]
    # A [bundle] row is settled when the release bundle is made: registry digests exist once the images are pushed
    # (a release pins digests in images.toml), while the scored study pins image IDs in its manifest
    # (docs/scored-runs.md).
    out.append(("[bundle] every image pinned to the digests in images/images.toml", not unpinned, ", ".join(unpinned)))
    out.append(("every image is one of images/images.toml", set(refs) <= locked, ", ".join(sorted(set(refs) - locked))))
    env_files = [
        p.relative_to(task / "environment").as_posix() for p in (task / "environment").rglob("*") if p.is_file()
    ]
    leaked = [f for f in env_files if f.startswith(("tests/", "solution/")) or "verify" in f]
    out.append(("no tests or solution in the agent image", not leaked, ", ".join(leaked)))
    test_sh = (task / "tests" / "test.sh").read_text()
    fetch = re.findall(r"\b(curl|wget|pip install|uv pip|apt-get|dnf)\b", test_sh)
    out.append(("no network fetches in test.sh", not fetch, ", ".join(fetch)))
    binds = []
    for compose in (task / "environment" / "docker-compose.yaml", task / "tests" / "docker-compose.yaml"):
        for name, svc in yaml.safe_load(compose.read_text())["services"].items():
            binds += [
                f"{compose.parent.name}:{name}:{v}"
                for v in svc.get("volumes", [])
                if str(v).startswith(("/", ".", "~"))
            ]
    out.append(("named volumes only (no host binds)", not binds, ", ".join(binds)))
    toml = (task / "task.toml").read_text()
    sources = re.findall(r'source\s*=\s*"([^"]+)"', toml)
    out.append(("only /ops crosses to the verifier (artifacts)", sources == ["/ops"], ", ".join(sources)))
    out += isolation_checks(task)
    return out


def isolation_checks(task: Path) -> list[Row]:
    """The agent's reach (workstation, controller, nodes) holds the platform only; setup and grading live elsewhere."""
    out: list[Row] = []
    tags = image_tags()
    runtime, harness = tags["runtime"], tags["harness"]
    env = task / "environment"
    main_df = (env / "Dockerfile").read_text()
    copies = [line for line in main_df.splitlines() if line.startswith(("COPY", "ADD"))]
    out.append(("workstation image copies nothing task-specific", not copies, "; ".join(copies)))
    froms = [line.split()[1] for line in main_df.splitlines() if line.startswith("FROM")]
    out.append(("workstation image is the runtime image", froms == [runtime], ", ".join(froms)))
    compose = yaml.safe_load((env / "docker-compose.yaml").read_text())
    services = compose["services"]
    allowed_harness = {"provision", "objstore"}
    wrong = [n for n, svc in services.items() if svc.get("image") == harness and n not in allowed_harness]
    if "provision" in services:
        prov_df = (env / services["provision"]["build"].get("dockerfile", "Dockerfile")).read_text()
        if f"FROM {harness}" not in prov_df:
            wrong.append("provision is not built from the harness image")
    out.append(("harness image only for provision / objstore", not wrong, ", ".join(wrong)))
    privileged = [n for n, svc in services.items() if svc.get("privileged")]
    out.append(("no privileged containers", not privileged, ", ".join(privileged)))
    nets = compose.get("networks") or {}
    internal = (
        bool(nets)
        and all(cfg.get("internal") for cfg in nets.values())
        # a service with no network at all (the keys service) cannot egress either
        and all(svc.get("networks") or svc.get("network_mode") == "none" for svc in services.values())
    )
    out.append(("agent cluster on an internal network (no egress)", internal, f"networks: {nets}"))
    shells = [
        n for n in allowed_harness & set(services) if services[n].get("command") not in (["provision"], ["objstore"])
    ]
    out.append(("harness sidecars run only their service (no shell)", not shells, ", ".join(shells)))
    return out


def loss_window(verify: dict, record: dict, declaration: str | None = None) -> Row:
    """loss_max must clear legitimate runs and fail shortcut runs, each by 3x the legitimate spread. A `must_fail`
    variant (a milder shortcut, e.g. 20% fewer steps) has to land above loss_max in every run, with no margin asked:
    the margin rule is pre-registered for the 50% shortcuts, and the milder probe is reported with its measured gap.
    A set without shortcut runs is acceptable when the task is throughput-gated or when the set declares which other
    verifier rule rejects a shorter run (`shortcuts_rejected_by`); its `probes` are measured and reported, not gates."""
    name = "loss threshold calibrated"
    if problem := calibration_problem(record, "loss"):
        return name, False, f"{record.get('set')}: {problem}"
    kinds, results = record["kinds"], record["results"]
    losses = {k: [r["loss"] for r in runs if "loss" in r] for k, runs in results.items()}
    legit = [x for k, v in losses.items() if kinds.get(k) == "legitimate" for x in v]
    short = [x for k, v in losses.items() if kinds.get(k) == "shortcut" for x in v]
    must = {k: v for k, v in losses.items() if kinds.get(k) == "must-fail"}
    probes = {k: v for k, v in losses.items() if kinds.get(k) == "probe"}
    no_loss = [k for k, runs in results.items() for r in runs if "loss" not in r]
    if no_loss:
        return (name, False, f"{record.get('set')}: runs without a loss in {sorted(set(no_loss))}")
    if len(legit) < 3:
        return (name, False, f"{record.get('set')}: {len(legit)} legitimate runs (need at least 3 for a spread)")
    spread = max(legit) - min(legit)
    lo = max(legit) + 3 * spread
    legit_txt = f"legit {min(legit):.4f}-{max(legit):.4f} n={len(legit)}"
    under = sorted(k for k, v in must.items() if min(v) <= verify["loss_max"])
    must_txt = "".join(f"; must fail {k} >= {min(v):.4f}" + (" NOT REJECTED" if k in under else "")
                       for k, v in sorted(must.items()))  # fmt: skip
    must_txt += "".join(f"; probe {k} {min(v):.4f}-{max(v):.4f} (" + ("rejected" if min(v) > verify["loss_max"]
                        else "not rejected by loss_max") + ")" for k, v in sorted(probes.items()))  # fmt: skip
    if not short:
        # Without shortcut runs the bound only has to clear legitimate runs: a throughput gate catches shortcuts
        # (e.g. checkpoint resume), or the set names the verifier rule that does (e.g. step coverage).
        if "throughput" in verify:
            why = "throughput-gated"
        else:
            why = f"shortcuts rejected by {declaration}" if declaration else "no shortcut runs and no other gate"
        ok = ("throughput" in verify or bool(declaration)) and lo <= verify["loss_max"] and not under
        return (name, ok, f"loss_max {verify['loss_max']} >= {lo:.4f} ({legit_txt}; {why}){must_txt}")
    hi = min(short) - 3 * spread
    ok = lo <= verify["loss_max"] <= hi and not under
    return (name, ok, f"loss_max {verify['loss_max']} in [{lo:.4f}, {hi:.4f}] ({legit_txt}, "
            f"shortcuts >= {min(short):.4f} n={len(short)}){must_txt}")  # fmt: skip


def calibration_problem(record: dict, metric: str) -> str:
    """Why a calibration record cannot set a threshold for `metric`: a variant with no runs, fewer than three
    legitimate runs (no spread), or a run that was inconclusive (verifier timeout, infrastructure, verifier bug) or
    carries no finite value of the metric. Shortcut runs may fail the verifier's own check (that is their point) but
    must still have run to a verdict."""
    results, kinds = record.get("results", {}), record.get("kinds", {})
    missing = [k for k in kinds if not results.get(k)]
    if kinds.get("reference") != "legitimate" or missing or set(results) != set(kinds):
        return f"missing calibration variants: {missing or ['reference']}"
    for variant, runs in results.items():
        if kinds.get(variant) == "legitimate" and len(runs) < 3:
            return f"{variant}: {len(runs)} legitimate runs (need at least 3 for a spread)"
        for run in runs:
            value = run.get(metric)
            if outcomes.kind(run) not in (outcomes.PASS, outcomes.AGENT):
                return f"{variant}: an inconclusive run (infrastructure error or verifier bug)"
            try:
                finite = isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                return f"{variant}: a run without a finite {metric}"
    return ""


def throughput_window(verify: dict, record: dict) -> Row:
    """ratio_min must sit at least 3 noise units below the slowest legitimate run and, where the set has shortcut
    runs, 3 above the fastest shortcut. The noise unit is the run-to-run spread within one configuration (the largest
    over the set's variants), not the spread across variants as for loss: a throughput set's legitimate variants are
    deliberately slower correct configurations (FSDP2 runs at about 0.8 of DDP), so the across-variant spread is the
    design's gap, not measurement noise, and no bound could clear three of it."""
    name = "throughput threshold calibrated"
    if problem := calibration_problem(record, "tput_ratio"):
        return name, False, f"{record.get('set')}: {problem}"
    kinds, results = record["kinds"], record["results"]
    ratios = {k: [r["tput_ratio"] for r in runs] for k, runs in results.items()}
    legit = [x for k, v in ratios.items() if kinds.get(k) == "legitimate" for x in v]
    short = [x for k, v in ratios.items() if kinds.get(k) == "shortcut" for x in v]
    noise = max(max(v) - min(v) for k, v in ratios.items() if kinds.get(k) == "legitimate" and len(v) >= 2)
    hi = min(legit) - 3 * noise
    lo = max(short) + 3 * noise if short else 0.0
    threshold = verify["throughput"]["ratio_min"]
    return (name, lo <= threshold <= hi, f"ratio_min {threshold} in [{lo:.3f}, {hi:.3f}] (legit "
            f"{min(legit):.3f}-{max(legit):.3f} n={len(legit)}, run-to-run noise {noise:.3f})")  # fmt: skip


def _calibration_set(verify: dict, set_name: str, metric: str) -> list[Row]:
    path = RESULTS / "calibration" / f"{set_name}.json"
    if not path.exists():
        return [(f"[release] {metric} threshold calibrated", False,
                 f"not measured yet: {path.relative_to(RESULTS.parent)}")]  # fmt: skip
    record = json.loads(path.read_text())
    # The measurements are read through the current set definition: today's kinds, and only today's variants.
    kinds = set_kinds(set_name)
    view = {**record, "kinds": kinds, "results": {k: v for k, v in record.get("results", {}).items() if k in kinds}}
    rows = [loss_window(verify, view, set_declaration(set_name)) if metric == "loss"
            else throughput_window(verify, view)]  # fmt: skip
    measured = record.get("stamp", {}).get("images", {})
    current = task_image_ids(task_dir(record["task"]), image_ids())
    same_images = images_match(measured, current)
    # A record measures losses and ratios; the thresholds set from them are not its inputs (calibration_digest).
    # Records written before that digest existed compare the whole task digest.
    if "calibration_digest" in record:
        same_task = record["calibration_digest"] == calibration_digest(task_dir(record["task"]))
    else:
        same_task = record.get("task_digest") == task_digest(task_dir(record["task"]))
    same_set = record.get("inputs") == set_inputs(set_name)
    rows.append(("[release] calibration measured on the current images, task and variants",
                 same_images and same_task and same_set,
                 f"{set_name}: images {'ok' if same_images else 'differ'}, task {'ok' if same_task else 'changed'}, "
                 f"variants {'ok' if same_set else 'changed'}; {describe(record.get('stamp', {}))}"))  # fmt: skip
    return rows


def calibration_checks(task: Path) -> list[Row]:
    """The loss bound against its calibration set (verify.calibration, default base-job) and, for a training task with
    a throughput rule, ratio_min against the perf set of its link (perf-link over the emulated link, perf without)."""
    verify = yaml.safe_load((task / "tests" / "verify.yaml").read_text())
    rows: list[Row] = []
    if "loss_max" in verify:
        rows += _calibration_set(verify, verify.get("calibration") or "base-job", "loss")
    else:
        rows.append(("loss threshold calibrated", True, "no loss check"))
    if verify.get("throughput") and verify.get("substrate", "slurm") == "slurm":
        rows += _calibration_set(verify, "perf-link" if by_id(task.name).hardware.network else "perf", "throughput")
    return rows


def read_trials(job_dir: Path) -> list[dict]:
    """The trials of one Harbor job directory. The reward comes only from Harbor's verifier result: after a verifier
    timeout or an infrastructure failure there is none, and the placeholder the verifier wrote at start-up must not
    count as a 0."""
    trials = []
    for result in sorted(job_dir.glob("*/result.json")):
        r = json.loads(result.read_text())
        reward = ((r.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        diag_file = result.parent / "verifier" / "diagnostics.json"
        diag = json.loads(diag_file.read_text()) if diag_file.exists() else {}
        exc = r.get("exception_info")
        symptom = next(result.parent.glob("artifacts/**/symptom.json"), None)
        trials.append({
            "task": (r.get("task_name") or "").split("/")[-1],
            "reward": reward,
            "rewards": {**diag, "reward": reward},
            "error": exc and exc.get("exception_type"),
            "infra": bool(diag.get("infra_error")),
            "symptom": json.loads(symptom.read_text()) if symptom else None,
            "dir": str(result.parent),
        })  # fmt: skip
    return trials


def harbor(
    task_path: Path, agent: str, k: int, n: int, label: str, artifacts: tuple[str, ...] = ()
) -> tuple[list[dict], str]:
    """Run Harbor; returns the trials and, if Harbor itself failed, why. `artifacts` are collected for this job only
    (QA reads the bootstrap's symptom.json from nop runs; tasks themselves export only /ops)."""
    job = f"qa-{task_path.name}-{label}-{int(time.time())}"
    jobs = RUNS / "jobs"
    cmd = [*HARBOR, "run", "-p", str(task_path), "-a", agent, "-k", str(k), "-n", str(n), "-o", str(jobs), "-y",
           "--job-name", job, "-q"]  # fmt: skip
    for a in artifacts:
        cmd += ["--artifact", a]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=HARBOR_TIMEOUT_S, check=False)
        problem = "" if res.returncode == 0 else f"harbor exited {res.returncode}: {res.stderr.strip()[-300:]}"
    except subprocess.TimeoutExpired:
        problem = f"harbor timed out after {HARBOR_TIMEOUT_S}s"
    return read_trials(jobs / job), problem


def wrong_fix_task(task: Path, name: str, kind: str = "wrong") -> Path:
    """A copy of the task whose oracle applies a wrong (or accepted) fix instead of the reference fix."""
    tmp = patches.scratch(f"qa-{task.name}-") / task.name
    shutil.copytree(task, tmp)
    shutil.rmtree(tmp / "solution" / "files")
    files = patches.wrong_fix_files(by_id(task.name), name, kind)
    shutil.copytree(files, tmp / "solution" / "files")
    shutil.rmtree(files)
    return tmp


def scored(t: dict, reward: float) -> bool:
    """A trial that ran to a complete verdict of the expected type: reward 1 with nothing failed, or reward 0 failed
    by the job itself (bench.outcomes). A Harbor error, an infrastructure failure or a verifier bug is neither."""
    if t["error"] is not None or t["infra"]:
        return False
    want = outcomes.PASS if reward == 1.0 else outcomes.AGENT
    return outcomes.kind({**(t.get("rewards") or {}), "reward": t["reward"]}) == want


def _detail(trials: list[dict], problem: str) -> str:
    return "; ".join([problem] * bool(problem) + [json.dumps(t["rewards"] or {"error": t["error"]}) for t in trials])


def oracle_history(previous: Path, inputs: dict, passed: int, runs: int) -> list[dict]:
    """Every oracle run recorded against the same inputs (grader digest, wrong fixes, images), the new one appended:
    a flake seen in one run and gone in the next stays in the record, so the release bundle's pooled flake bound counts
    it. Inputs that changed start the history over."""
    history: list[dict] = []
    try:
        old = json.loads(previous.read_text())
        if old.get("inputs") == inputs:
            history = [h for h in old.get("oracle_history") or [] if isinstance(h, dict)]
            if not history and old.get("oracle"):  # a record from before histories existed: its own oracle line
                for check in old.get("checks", []):
                    m = re.match(r"oracle (\d+)/(\d+)", str(check.get("check", "")))
                    if m:
                        history = [{"passed": int(m.group(1)), "runs": int(m.group(2)), "stamp": old.get("stamp")}]
    except (OSError, ValueError):
        pass
    return [*history, {"passed": passed, "runs": runs, "stamp": stamp()}] if runs else history


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench qa", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("task")
    ap.add_argument("--release", action="store_true", help="release gate: oracle 10, nop 3, pinned images required")
    ap.add_argument("--oracle", type=int)
    ap.add_argument("--nop", type=int)
    ap.add_argument("--no-wrong", action="store_true")
    ap.add_argument("-n", type=int, default=1, help="concurrent trials (at most one per 8 physical cores)")
    ap.add_argument("--regrade", action="store_true", help="release records only: re-evaluate the static and "
                    "calibration rows against today's records and reuse the trial rows of the existing record, which "
                    "must have been made on the same inputs (task, fixes, images); runs no trial")  # fmt: skip
    args = ap.parse_args(argv)
    args.oracle = args.oracle if args.oracle is not None else (10 if args.release else 2)
    args.nop = args.nop if args.nop is not None else (3 if args.release else 1)
    if args.oracle < 0 or args.nop < 0 or args.n < 1:
        ap.error("trial counts must be non-negative and concurrency positive")
    if args.release and (args.oracle < 10 or args.nop < 3 or args.no_wrong):
        ap.error("the release gate needs at least 10 oracle runs, 3 nop runs and every wrong fix (docs/leaderboard.md)")

    task = task_dir(args.task)
    spec = by_id(args.task)
    oracle_passed = 0
    rows: list[Row] = static_checks(task) + calibration_checks(task)
    previous = (RESULTS if args.release else RUNS) / "qa" / f"{args.task}.json"
    regraded_from = None
    if args.regrade:
        # The calibration rows read records that may be measured after the trials (a new host measures its calibration
        # sets while the QA runs); the trials depend only on the task, its fixes and the images (bench.sweep.inputs).
        if not args.release:
            ap.error("--regrade applies to release records")
        try:
            old = json.loads(previous.read_text())
        except (OSError, ValueError):
            raise SystemExit(f"bench qa: no release record to regrade for {args.task}") from None
        if old.get("mode") != "release" or old.get("inputs") != sweep.inputs(args.task):
            raise SystemExit(f"bench qa: the record of {args.task} was made on other inputs (task, fixes or images); "
                             "run its trials again")  # fmt: skip
        rows += [(c["check"], bool(c["ok"]), str(c.get("detail", ""))) for c in old.get("checks", [])
                 if TRIAL_ROW.fullmatch(str(c.get("check", "")))]  # fmt: skip
        regraded_from = old.get("stamp")
    if args.oracle and not args.regrade:
        trials, problem = harbor(task, "oracle", args.oracle, args.n, "oracle")
        ok = len(trials) == args.oracle and all(scored(t, 1.0) for t in trials)
        oracle_passed = sum(scored(t, 1.0) for t in trials)
        rows.append((f"oracle {oracle_passed}/{args.oracle}", ok, _detail(trials, problem)))
    if args.nop and not args.regrade:
        trials, problem = harbor(task, "nop", args.nop, args.n, "nop", ("/shared/evidence/symptom.json",))
        ok = len(trials) == args.nop and all(scored(t, 0.0) for t in trials)
        rows.append((f"nop {sum(scored(t, 0.0) for t in trials)}/{args.nop} score 0", ok, _detail(trials, problem)))
        observed = [bool(t["symptom"] and t["symptom"].get("observed")) for t in trials]
        rows.append(("symptom observed at bootstrap", bool(trials) and all(observed),
                     "; ".join(json.dumps(t["symptom"]) for t in trials)))  # fmt: skip
    if not args.no_wrong and not args.regrade:
        for kind, want in (("wrong", 0.0), ("accepted", 1.0)):
            for name in patches.fix_patches(spec, kind):
                tmp = wrong_fix_task(task, name, kind)
                trials, problem = harbor(tmp, "oracle", 1, 1, f"{kind}-{name}")
                ok = bool(trials) and all(scored(t, want) for t in trials)
                rows.append((f"{kind} fix '{name}' scores {want:.0f}", ok, _detail(trials, problem)))
                shutil.rmtree(tmp.parent)

    mode = "release" if args.release else "dev"
    lines = [f"# QA: {args.task}", "", f"Mode: {mode} (oracle x{args.oracle}, nop x{args.nop}). {describe(stamp())}",
             "", "| Check | Result | Detail |", "|---|---|---|"]  # fmt: skip
    for name, ok, detail in rows:
        if ok:
            result = "PASS"
        elif name.startswith("[bundle]"):
            result = "BUNDLE"  # decided at release-bundle time, never part of Stage 1
        else:
            result = "SKIP (dev)" if name.startswith("[release]") and not args.release else "FAIL"
        lines.append(f"| {name} | {result} | {detail.replace('|', '/')[:300]} |")
    decides = [(ok, name) for name, ok, _ in rows if not name.startswith("[bundle]")]
    verdict = all(ok for ok, name in decides if args.release or not name.startswith("[release]"))
    lines += ["", f"**Stage 1 ({mode}): {'PASS' if verdict else 'FAIL'}**", ""]
    if regraded_from:
        lines += [f"Regraded: the trial rows are those of the record of {regraded_from.get('utc')} (same inputs); the "
                  "static and calibration rows were re-evaluated.", ""]  # fmt: skip
    out = (RESULTS if args.release else RUNS) / "qa" / f"{args.task}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    inputs = sweep.inputs(args.task)
    record = {"task": args.task, "mode": mode, "oracle": args.oracle, "nop": args.nop, "pass": verdict,
              "inputs": inputs, "stamp": stamp(),
              "checks": [{"check": name, "ok": ok, "detail": detail[:300]} for name, ok, detail in rows],
              "oracle_history": (json.loads(previous.read_text()).get("oracle_history") or [] if regraded_from
                                 else oracle_history(out.with_suffix(".json"), inputs, oracle_passed, args.oracle)),
              **({"regraded_from": regraded_from} if regraded_from else {})}  # fmt: skip
    out.with_suffix(".json").write_text(json.dumps(record, indent=1) + "\n")
    print("\n".join(lines))
    if not verdict:  # scriptable: a failed gate fails the command
        raise SystemExit(1)


if __name__ == "__main__":
    main()
