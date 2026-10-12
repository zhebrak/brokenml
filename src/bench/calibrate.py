"""Run a task's verifier on /ops variants, on one long-lived verifier cluster.

Each run is a full verification (fresh data, fresh job) with the policy check skipped, so legitimate variations that
differ from the contract can be measured too. It sets loss and throughput thresholds (calibration sets) and checks
that the fault, the wrong fixes and the reference fix separate (the sweep).

  bench calibrate TASK [--runs N] [--only VARIANT ...] [--jsonl FILE]
      variants: reference (the fix), pristine (the broken /ops), wrong:<name> (each scripted wrong fix)
  bench calibrate --set NAME [--runs N]
      a set from calibration/sets.yaml: the reference plus its legitimate variants and shortcuts, written with a
      provenance stamp to results/calibration/NAME.json

Every run is printed and, with --jsonl, appended as one JSON record as soon as it finishes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

import yaml

from bench import outcomes, patches
from bench.paths import RESULTS, ROOT, RUNS, project_name
from bench.provenance import calibration_digest, stamp, task_digest
from bench.spec import by_id, task_dir

DOCKER = os.environ.get("DOCKER", "docker").split()  # e.g. DOCKER="sudo -n docker" on a shared box
SETS = ROOT / "calibration" / "sets.yaml"
VARIANT_PATCHES = ROOT / "calibration" / "variants"


def sh(cmd: list[str], check: bool = True, timeout: float | None = None, **kw) -> subprocess.CompletedProcess:
    """Run a command; with check, a failure raises with the command's own error output (not just its exit code)."""
    if cmd[0] == "docker":
        cmd = [*DOCKER, *cmd[1:]]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout, **kw)
    if check and res.returncode:
        raise RuntimeError(f"{' '.join(cmd[:6])} ... exited {res.returncode}:\n{(res.stderr or res.stdout)[-3000:]}")
    return res


def separation_trees(task: str) -> dict[str, Path]:
    """reference, pristine, wrong:<name> and accepted:<name>, as scratch /ops trees (the caller removes them)."""
    tests = task_dir(task) / "tests"
    trees = {name: patches.materialise(tests / name) for name in ("reference", "pristine")}
    spec = by_id(task)
    for kind in ("wrong", "accepted"):
        for name in patches.fix_patches(spec, kind):
            files = patches.wrong_fix_files(spec, name, kind)
            tree = patches.materialise(tests / "pristine")
            shutil.copytree(files, tree, dirs_exist_ok=True)
            shutil.rmtree(files)
            trees[f"{kind}:{name}"] = tree
    return trees


def set_trees(cfg: dict) -> tuple[dict[str, Path], dict[str, str]]:
    """The reference plus each variant of a calibration set, and each variant's kind: legitimate, shortcut (rejected
    by 3x the legitimate spread) or must-fail (rejected, no margin asked; calibration/sets.yaml)."""
    # The trees come from the task's definition (template, ops patch, solution), as the sweeps' and the tests' do: the
    # rendered tests/reference carries a canary comment at the top of every file, which the variant patches' context
    # does not (the three sets whose variants touch a file's first lines failed to apply on the run host).
    broken, reference = patches.task_trees(by_id(cfg["task"]))
    shutil.rmtree(broken)
    trees = {"reference": reference}
    kinds = {"reference": "legitimate"}
    for kind, names in KINDS.items():
        for name in cfg.get(names, []):
            trees[name] = patches.materialise(reference, VARIANT_PATCHES / f"{name}.patch")
            kinds[name] = kind
    return trees, kinds


# kind -> sets.yaml key. A probe is measured and reported, never a gate (calibration/sets.yaml).
KINDS = {"legitimate": "legitimate", "shortcut": "shortcuts", "must-fail": "must_fail", "probe": "probes"}


def set_variants(cfg: dict) -> list[str]:
    return [name for key in KINDS.values() for name in cfg.get(key, [])]


def set_declaration(name: str) -> str | None:
    """A set's `shortcuts_rejected_by`: why its task needs no shortcut run for the loss bound (another verifier rule
    rejects a shorter run), stated for the task card and the validation table."""
    return (yaml.safe_load(SETS.read_text()).get(name) or {}).get("shortcuts_rejected_by")


def set_kinds(name: str) -> dict[str, str]:
    """Each variant's kind under the current sets.yaml (the reference is legitimate). QA reads a record's
    measurements through this, so relabelling a variant (shortcut -> probe) needs no new measurement."""
    cfg = yaml.safe_load(SETS.read_text())[name]
    kinds = {"reference": "legitimate"}
    for kind, key in KINDS.items():
        for variant in cfg.get(key, []):
            kinds[variant] = kind
    return kinds


def set_inputs(name: str) -> str:
    """A hash of what a calibration set measures: its task, run count and variants with their patches. The kinds
    and declarations are how QA reads the measurements, not inputs to them, so they are left out."""
    cfg = yaml.safe_load(SETS.read_text())[name]
    variants = sorted(set_variants(cfg))
    h = hashlib.sha256(json.dumps({"task": cfg["task"], "runs": cfg.get("runs"), "variants": variants},
                                  sort_keys=True).encode())  # fmt: skip
    for variant in variants:
        h.update((VARIANT_PATCHES / f"{variant}.patch").read_bytes())
    return h.hexdigest()[:16]


@contextmanager
def verifier_cluster(task: str, policy_skip: bool = True, throughput: bool = False) -> Iterator[str]:
    """The task's verifier compose, with `main` idling so variants can be run in it one after another. Calibration
    sets skip the policy check (they measure variants outside the contract); separation runs enforce it, as the
    verifier does, since some wrong fixes fail only by breaking the contract. `throughput` makes the verifier time a
    reference run beside every variant even when the task has no throughput rule, so a perf set measures ratios."""
    tests = task_dir(task) / "tests"
    project = project_name("cal", task)
    override = Path(tempfile.mkdtemp()) / "main.yaml"
    override.write_text(
        yaml.safe_dump({"services": {"main": {"build": {"context": str(tests)}, "command": ["sleep", "infinity"]}}})
    )
    compose = ["docker", "compose", "-p", project, "-f", str(tests / "docker-compose.yaml"), "-f", str(override)]
    cfg = yaml.safe_load((tests / "verify.yaml").read_text())
    cfg["policy_skip"] = policy_skip
    if throughput and not cfg.get("throughput"):
        cfg["throughput"] = {"ratio_min": 0.67}  # any bound: the ratio is what the set records
    try:
        sh([*compose, "up", "-d", "--build"], timeout=1800)
        main = f"{project}-main-1"
        sh(
            ["docker", "exec", "-i", main, "sh", "-c", "mkdir -p /logs/verifier && cat > /tests/verify-calibrate.yaml"],
            input=yaml.safe_dump(cfg),
        )
        yield main
    finally:
        sh([*compose, "down", "-v"], check=False, timeout=600)
        shutil.rmtree(override.parent, ignore_errors=True)


# A cluster reused across verifications must start each one from the reference cluster configuration. The previous
# run's /ops may have changed slurm.conf, and the health check drained nodes for it. The verifier's infra gate deploys
# the reference config but does not reconfigure the running daemons, which only matters in a reused cluster (Harbor
# grades in a fresh one). The gate's own reconfigure ships with the next harness image.
# Only a running controller with drained or down nodes is touched: reconfiguring a controller that is still starting
# took it down (every run of the task then failed "cluster up").
# A node the previous /ops drained by configuration (State=DRAIN in slurm.conf) stays drained after the reconfigure:
# Slurm keeps an administrative drain until the node is resumed, so the next verification's readiness gate would fail
# on it and blame the infrastructure (degraded-node's fewer-ranks after drain-c2).
SETTLE = (
    "from pathlib import Path\n"
    "from ocb import slurm\n"
    "if 'UP' in slurm.run(['scontrol', 'ping']).stdout and slurm.drained_nodes():\n"
    "    slurm.deploy_cluster_config(Path('/tests/reference'))\n"
    "    slurm.run(['scontrol', 'reconfigure'])\n"
    "    for node in slurm.drained_nodes():\n"
    "        slurm.run(['scontrol', 'update', f'NodeName={node}', 'State=RESUME'])\n"
)


def run_once(main: str, tree: Path, timeout_s: float, logs: Path | None = None) -> tuple[dict, str]:
    """One verification of `tree` as /ops; returns the diagnostics record and the verifier's output tail.

    A verifier that times out, exits non-zero or leaves no diagnostics is an infrastructure failure (reward None),
    never a 0: the placeholder reward written at start-up must not count as a result.
    """
    sh(["docker", "exec", main, "python3", "-c", SETTLE], check=False)
    sh(["docker", "exec", main, "sh", "-c",
        "find /ops -mindepth 1 -delete; rm -f /logs/verifier/diagnostics.json /logs/verifier/ctrf.json"])  # fmt: skip
    sh(["docker", "cp", f"{tree}/.", f"{main}:/ops"])
    t0 = time.time()
    try:
        run = sh(
            ["docker", "exec", main, "python3", "-m", "harness.verify", "/tests/verify-calibrate.yaml"],
            check=False,
            timeout=timeout_s,
        )
        output, code = run.stdout + run.stderr, run.returncode
    except subprocess.TimeoutExpired:
        sh(["docker", "exec", main, "pkill", "-KILL", "-f", "harness.verify"], check=False)
        output, code = f"verifier timed out after {timeout_s:.0f}s", -1
    diag = sh(["docker", "exec", main, "cat", "/logs/verifier/diagnostics.json"], check=False)
    try:
        record = json.loads(diag.stdout)
    except json.JSONDecodeError:
        record = {}
    if code != 0 or not record:
        record = {**record, "reward": None, "infra_error": 1.0, "error": f"verifier exit {code}"}
    ctrf = sh(["docker", "exec", main, "cat", "/logs/verifier/ctrf.json"], check=False)
    try:  # the checks that failed, by name: a wrong fix must fail the one it targets (bench.sweep)
        tests = json.loads(ctrf.stdout).get("results", {}).get("tests", [])
        failed = [t for t in tests if t.get("status") == "failed"]
        record["failed_checks"] = [t.get("name") for t in failed]
        record["failed_messages"] = {t.get("name"): str(t.get("message") or "")[:300] for t in failed}
    except (json.JSONDecodeError, AttributeError):
        record["failed_checks"], record["failed_messages"] = [], {}
    record["wall_s"] = round(time.time() - t0, 1)
    if logs:  # the verifier's own output and /logs, per run, so a failed variant can be read later
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "verifier.log").write_text(output)
        sh(["docker", "cp", f"{main}:/logs/verifier", str(logs / "verifier")], check=False)
    return record, "\n".join(output.strip().splitlines()[-12:])


def run_variants(
    task: str,
    trees: dict[str, Path],
    runs: int,
    jsonl: Path | None,
    policy_skip: bool = True,
    throughput: bool = False,
) -> dict[str, list[dict]]:
    """Every variant `runs` times on one verifier cluster. A run that ended inconclusively (a verifier timeout, an
    infrastructure error, a verifier bug) may have left ranks or jobs alive, so that cluster is torn down and the next
    run starts a fresh one: an unverified cluster is never reused. Each run's verifier output is kept under
    runs/calibration/<task>-<id>/<variant>-<n>/."""
    results: dict[str, list[dict]] = {}
    run_dir = RUNS / "calibration" / f"{task}-{uuid.uuid4().hex[:8]}"
    deadline = yaml.safe_load((task_dir(task) / "tests" / "verify.yaml").read_text()).get("deadline_s") or 600
    timeout_s = 3 * float(deadline) + 600  # reference + job + evaluation, with room for cluster start-up
    if jsonl:
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("a") as f:
            f.write(json.dumps({"task": task, "task_digest": task_digest(task_dir(task)), "stamp": stamp()}) + "\n")
    with ExitStack() as stack:
        main: str | None = None
        for name, tree in trees.items():
            for i in range(runs):
                for attempt in (1, 2):  # an inconclusive run on the shared cluster is retried once on a fresh one
                    if main is None:
                        main = stack.enter_context(verifier_cluster(task, policy_skip, throughput))
                    logs = run_dir / f"{name.replace(':', '-')}-{i + 1}{'' if attempt == 1 else '-retry'}"
                    record, tail = run_once(main, tree, timeout_s, logs)
                    if attempt == 2 or outcomes.kind(record) in (outcomes.PASS, outcomes.AGENT):
                        break
                    print(
                        f"{name:<24} run {i + 1}: inconclusive on the shared cluster ({json.dumps(record)[:120]}); "
                        "fresh cluster, one retry",
                        flush=True,
                    )
                    stack.close()
                    main = None
                results.setdefault(name, []).append(record)
                print(f"{name:<24} run {i + 1}: {json.dumps(record)}", flush=True)
                if record.get("reward") != 1.0:
                    print("  " + tail.replace("\n", "\n  "), flush=True)
                if jsonl:
                    with jsonl.open("a") as f:
                        f.write(json.dumps({"task": task, "variant": name, "run": i + 1, **record}) + "\n")
                        f.flush()
                        os.fsync(f.fileno())
                if outcomes.kind(record) not in (outcomes.PASS, outcomes.AGENT):
                    stack.close()  # the cluster may still run what the inconclusive verification left behind
                    main = None
    return results


def summary(results: dict[str, list[dict]]) -> str:
    def fmt(xs: list[float]) -> str:
        return f"{statistics.mean(xs):.4f} [{min(xs):.4f}, {max(xs):.4f}]" if xs else "-"

    lines = []
    for name, runs in results.items():
        passed = sum(r.get("reward") == 1.0 for r in runs)
        losses = [r["loss"] for r in runs if "loss" in r]
        elapsed = [r["elapsed_s"] for r in runs if "elapsed_s" in r]
        lines.append(f"{name:<24} reward {passed}/{len(runs)}  loss {fmt(losses)}  elapsed {fmt(elapsed)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench calibrate", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("task", nargs="?")
    ap.add_argument("--set", help="a calibration set from calibration/sets.yaml")
    ap.add_argument("--runs", type=int)
    ap.add_argument("--only", action="append", default=[], help="run only these variants")
    ap.add_argument("--jsonl", type=Path, help="append one JSON record per run to this file")
    args = ap.parse_args(argv)
    if bool(args.task) == bool(args.set):
        ap.error("give a TASK or --set NAME")

    if args.set:
        cfg = yaml.safe_load(SETS.read_text())[args.set]
        task, runs = cfg["task"], args.runs or cfg.get("runs", 3)
        trees, kinds = set_trees(cfg)
    else:
        task, runs, kinds = args.task, args.runs or 1, {}
        trees = separation_trees(task)
    if args.only:
        for name in set(trees) - set(args.only):
            shutil.rmtree(trees.pop(name))
    try:
        results = run_variants(task, trees, runs, args.jsonl, policy_skip=bool(args.set),
                               throughput=bool(args.set and cfg.get("throughput")))  # fmt: skip
    finally:
        for tree in trees.values():
            shutil.rmtree(tree, ignore_errors=True)

    if args.set:
        out = RESULTS / "calibration" / f"{args.set}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "set": args.set,
            "task": task,
            "task_digest": task_digest(task_dir(task)),
            "calibration_digest": calibration_digest(task_dir(task)),  # the task without its thresholds (qa)
            "inputs": set_inputs(args.set),
            "stamp": stamp(),
            "kinds": kinds,
            "results": results,
        }
        out.write_text(json.dumps(record, indent=1) + "\n")
        print(f"saved {out.relative_to(ROOT)}")
    print("\nsummary\n" + summary(results))


if __name__ == "__main__":
    main()
