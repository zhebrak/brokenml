"""Memory margins of a memory-bound task, measured as outcomes under limits (release gate):

    uv run bench margins TASK [--factor 1.15] [--wrong NAME ...]

Runs the task's reference with every node limited to the task's limit divided by `factor` (it must still pass), and
its broken /ops with the limit multiplied by `factor` (it must still fail). memory.peak taken without a limit counts
page cache, which the kernel reclaims under a limit, so peaks overstate what a job needs; the outcome under a
limit does not. Every accepted alternative fix is held to the reference's bar: it must pass at limit / `factor`.
`--wrong NAME` also probes a wrong fix that is rejected only by memory (DDP where FSDP is needed): it must still be
OOM-killed at the limit multiplied by `factor`. Writes results/margins/<task>.json, stamped. The limits are each node's
in the spec (hardware.services.<node>.mem_limit), or the platform's default.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import tempfile
from pathlib import Path

import yaml

from bench import outcomes, patches, sweep
from bench.calibrate import run_once, sh
from bench.paths import ROOT, project_name
from bench.provenance import grader_digest, stamp, task_digest
from bench.spec import by_id, task_dir

OUT = ROOT / "results" / "margins"
REQUIRED_FACTOR = 1.15
DEFAULT_NODE_LIMIT = "1500m"  # bench.compose._node


def _mib(limit: str) -> int:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([mg])", str(limit).lower())
    if not m:
        raise ValueError(f"unsupported memory limit {limit!r} (use NNNNm or Ng)")
    return int(float(m.group(1)) * (1024 if m.group(2) == "g" else 1))


def node_limits(task: str) -> dict[str, int]:
    """Each node's memory limit in MiB, as the task's compose file gets it."""
    spec = by_id(task)
    return {n: _mib(spec.hardware.services.get(n, {}).get("mem_limit", DEFAULT_NODE_LIMIT)) for n in spec.nodes}


def _cap_realmemory(conf: Path, mib: int) -> None:
    """Lower every RealMemory above `mib` to `mib` (never raise one)."""
    if conf.exists():
        text = conf.read_text()
        conf.write_text(re.sub(r"RealMemory=(\d+)", lambda m: f"RealMemory={min(int(m.group(1)), mib)}", text))


def run_under(task: str, variant: str, limits_mib: dict[str, int]) -> dict:
    """One verification of the task's `variant` tree (pristine or reference) in a fresh cluster with these limits."""
    tests = task_dir(task) / "tests"
    project = project_name("mg", task, variant)
    tmp = Path(tempfile.mkdtemp())
    over: dict = {"main": {"build": {"context": str(tests)}, "command": ["sleep", "infinity"]}}
    for node, mib in limits_mib.items():
        over[node] = {"mem_limit": f"{mib}m", "memswap_limit": f"{mib}m"}
    (tmp / "o.yaml").write_text(yaml.safe_dump({"services": over}))
    compose = ["docker", "compose", "-p", project, "-f", str(tests / "docker-compose.yaml"), "-f", str(tmp / "o.yaml")]
    cfg = yaml.safe_load((tests / "verify.yaml").read_text())
    cfg["policy_skip"] = True
    if variant.startswith(("wrong:", "accepted:")):  # the broken /ops with that fix's files over it
        kind, name = variant.split(":", 1)
        files = patches.wrong_fix_files(by_id(task), name, kind)
        tree = patches.materialise(tests / "pristine")
        shutil.copytree(files, tree, dirs_exist_ok=True)
        shutil.rmtree(files)
    else:
        tree = patches.materialise(tests / variant)
    lowest = min(limits_mib.values())
    try:
        sh([*compose, "up", "-d", "--build"], timeout=1800)
        main = f"{project}-main-1"
        # A node below its configured RealMemory is drained by the health check, correctly; so a probe below the
        # task's limit lowers RealMemory with it, in the job's tree and the verifier's reference (jobs request none).
        _cap_realmemory(tree / "cluster" / "slurm.conf", lowest)
        sh(["docker", "exec", main, "sed", "-i", "-E", f"s/RealMemory=([0-9]+)/RealMemory={lowest}/",
            "/tests/reference/cluster/slurm.conf"], check=False)  # fmt: skip
        sh(["docker", "exec", "-i", main, "sh", "-c", "mkdir -p /logs/verifier && cat > /tests/verify-calibrate.yaml"],
           input=yaml.safe_dump(cfg))  # fmt: skip
        record, tail = run_once(main, tree, 3600)
        ooms = {}
        for node in limits_mib:
            events = ["docker", "exec", f"{project}-{node}-1", "cat", "/sys/fs/cgroup/memory.events"]
            ev = sh(events, check=False).stdout
            ooms[node] = int(next((line.split()[1] for line in ev.splitlines() if line.startswith("oom_kill ")), 0))
        failed = [line.strip() for line in tail.splitlines() if "[FAIL]" in line][:1]
        return {"variant": variant, "limits_mib": limits_mib, "reward": record.get("reward"), "oom_kills": ooms,
                "infra": outcomes.kind(record) == outcomes.INFRA, "kind": outcomes.kind(record),
                "failed": failed}  # fmt: skip
    finally:
        sh([*compose, "down", "-v"], check=False, timeout=600)
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tree, ignore_errors=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench margins", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("task")
    ap.add_argument("--factor", type=float, default=1.15)
    ap.add_argument("--wrong", action="append", default=[], help="a wrong fix rejected only by memory (repeatable)")
    args = ap.parse_args(argv)
    if not math.isfinite(args.factor) or args.factor < REQUIRED_FACTOR:
        ap.error(f"the margin factor must be at least {REQUIRED_FACTOR}")
    measured_inputs = sweep.inputs(args.task)
    limits = node_limits(args.task)
    tight = {n: int(v / args.factor) for n, v in limits.items()}
    below = run_under(args.task, "reference", tight)
    accepted = {
        n: run_under(args.task, f"accepted:{n}", tight) for n in patches.fix_patches(by_id(args.task), "accepted")
    }
    above = None  # the broken job must still be OOM-killed above the limit (only where the fault is the OOM)
    if by_id(args.task).metadata.fault_kind == "crash":
        above = run_under(args.task, "pristine", {n: int(v * args.factor) for n, v in limits.items()})
    wrong = {n: run_under(args.task, f"wrong:{n}", {k: int(v * args.factor) for k, v in limits.items()})
             for n in args.wrong}  # fmt: skip
    oomed = [above, *wrong.values()] if above else list(wrong.values())
    passing = [below, *accepted.values()]
    ok = all(r.get("kind", "pass" if r["reward"] == 1.0 else "") == outcomes.PASS for r in passing) and all(
        r.get("kind") == outcomes.AGENT and any(r["oom_kills"].values()) for r in oomed
    )
    infra = any(r["infra"] for r in [*passing, *oomed])  # says nothing about the margins: run again
    verdict = "PASS" if ok else ("INCONCLUSIVE" if infra else "FAIL")
    d = task_dir(args.task)
    record = {"task": args.task, "task_digest": task_digest(d), "grader_digest": grader_digest(d), "limits_mib": limits,
              "factor": args.factor, "reference_below": below, "accepted_below": accepted, "broken_above": above,
              "wrong_above": wrong, "inputs": measured_inputs,
              "pass": ok, "verdict": verdict, "stamp": stamp()}  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.task}.json").write_text(json.dumps(record, indent=1) + "\n")
    broken = "the fault is not an OOM"
    if above:
        broken = f"broken at limit*{args.factor}: {above['reward']}, oom_kills {above['oom_kills']}"
    alts = "".join(f"; accepted {n} at limit/{args.factor}: {r['reward']}" for n, r in accepted.items())
    print(f"{args.task}: {verdict} (reference at limit/{args.factor}: {below['reward']}{alts}; {broken})")
    if verdict != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
