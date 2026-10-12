"""Run supported benchmark jobs on two logical nodes (NCCL, or Gloo for a CPU smoke), for the fidelity study.

  python experiments/gpu_fidelity/jobs.py TASK [TASK ...] [--variants broken,fixed] [--gpus-per-node 2]

The default is 2 ranks per logical node (4 GPUs), the benchmark's world size and global batch. --gpus-per-node 1 is a
different global batch and is refused for tasks whose mechanism needs two ranks on each node. Each task's /ops is
assembled from the template and its patches exactly as the renderer does (bench.patches.task_trees); a checked adapter
then switches the modular trainer to NCCL and moves tensors to the device. Each logical node gets the task environment
TaskProlog would build for it (the site's job.env from the spec's node_setup, then the ops node env file), so
node-scoped faults keep their meaning. This runner measures GPU fidelity: it reproduces neither Slurm, nor CPU memory
limits, nor object-store or network throttling, and says so in every manifest.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

import yaml
from common import ROOT, append_row, devices, digest_tree, execute, free_port, nccl_env, provenance, run_dir

from bench import patches
from bench.spec import TaskSpec, by_id

# Mechanisms this runner supports, with the ranks per logical node each needs. A task outside the list may depend
# on a platform service this runner does not provide, so it is refused rather than run with the fault missing.
SUPPORTED = {
    "rank0-eval-desync": 1,
    "rank0-only-checkpoint": 1,
    "prefetch-thread-dies": 1,
    "hash-ordered-buckets": 1,
    "no-sync-off-by-one": 1,
    "same-shard": 1,
    "unshifted-labels": 1,
    "lr-decay-horizon": 1,
    "tiny-ddp-buckets": 1,
    "redundant-param-broadcast": 1,
    "fsdp-fine-wrapping": 1,
    "uneven-val-gather": 2,
    "bad-token-ids": 1,
    "subgroup-skip-deadlock": 2,
    "node-thread-oversubscription": 1,
}
LOG_EXCERPT_BYTES = 100_000  # from each end of each node log: the failure is at the end, the setup at the start


def validate(task: str, ranks_per_node: int) -> None:
    if task not in SUPPORTED:
        raise ValueError(f"{task}: unsupported here; supported tasks: {', '.join(sorted(SUPPORTED))}")
    spec = by_id(task)
    if ranks_per_node < SUPPORTED[task]:
        raise ValueError(f"{task} needs at least {SUPPORTED[task]} ranks per logical node")
    if spec.substrate != "slurm" or spec.store or spec.hardware.objstore or spec.hardware.services:
        raise ValueError(f"{task}: needs services or hardware this runner does not reproduce")
    if spec.data and spec.data.shards:
        raise ValueError(f"{task}: needs the sharded object-store dataset")
    if spec.site:
        raise ValueError(f"{task}: needs site state (reservations) this runner does not reproduce")
    for node, setup in spec.hardware.node_setup.items():
        if setup.stale_host or setup.loopback_self or setup.metrics_port or setup.nccl_conf:
            raise ValueError(f"{task}: node {node} needs host, exporter or NCCL state this runner does not reproduce")


def assemble(task: str, variant: str, work: Path) -> Path:
    """The task's /ops as the agent (broken) or the reference fix (fixed) has it, by the renderer's own assembly."""
    if variant not in ("broken", "fixed"):
        raise ValueError(f"unknown variant: {variant}")
    broken, fixed = patches.task_trees(by_id(task))
    try:
        ops = work / "ops"
        shutil.copytree(fixed if variant == "fixed" else broken, ops)
        return ops
    finally:
        shutil.rmtree(broken)
        shutil.rmtree(fixed)


def port(ops: Path) -> None:
    """Small, checked edits to the modular trainer (each anchor must occur exactly once); fault patches stay applied.
    The process group is initialised without device_id, so NCCL communicators form lazily, as in the CPU trainer."""
    edits = {
        "dist.py": [
            (
                '    dist.init_process_group("gloo",',
                '    if os.environ.get("OCB_BACKEND") == "nccl":\n'
                '        torch.cuda.set_device(int(os.environ["LOCAL_RANK"]))\n'
                '        torch.set_default_device("cuda")\n'
                '    dist.init_process_group(os.environ.get("OCB_BACKEND", "gloo"),',
            )
        ],
        "data.py": [
            ("generator=g)", 'generator=g, device="cpu")'),
            (
                '    corpus = load_file(cfg["data"])',
                '    corpus = load_file(cfg["data"])\n    corpus["val"] = corpus["val"].to(torch.get_default_device())',
            ),
        ],
        "evaluation.py": [
            (  # the loss takes one tensor (the template) or inputs and labels (unshifted-labels' collator cut): either
                [
                    "def next_token_loss(model: torch.nn.Module, tokens: torch.Tensor) -> torch.Tensor:\n",
                    "    logits = model(inputs[:, :-1])\n",
                ],
                [
                    "def next_token_loss(model: torch.nn.Module, tokens: torch.Tensor) -> torch.Tensor:\n"
                    "    tokens = tokens.to(torch.get_default_device())\n",
                    "    device = torch.get_default_device()\n"
                    "    inputs, labels = inputs.to(device), labels.to(device)\n"
                    "    logits = model(inputs[:, :-1])\n",
                ],
            )
        ],
    }
    for module, replacements in edits.items():
        path = ops / "src" / "trainer" / module
        source = path.read_text()
        for before, after in replacements:
            options = list(zip(before, after, strict=True)) if isinstance(before, list) else [(before, after)]
            hit = [(b, a) for b, a in options if source.count(b) == 1]
            if len(hit) != 1:
                raise ValueError(f"GPU adapter expected exactly one of {[b for b, _ in options]!r} in {module}")
            source = source.replace(hit[0][0], hit[0][1], 1)
        compile(source, str(path), "exec")
        path.write_text(source)


def config(ops: Path) -> dict:
    module_spec = importlib.util.spec_from_file_location("job_config", ops / "src/trainer/config.py")
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module.load(ops / "jobs/train/train.yaml")


def _assignments(lines: list[str]) -> dict[str, str]:
    env = {}
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if "=" in line and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", line):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def node_env(ops: Path, node: str, spec: TaskSpec | None = None) -> dict[str, str]:
    """The task environment TaskProlog builds on `node`: the site's job.env (LC_ALL, then the node's `site_job_env`
    from the spec's hardware.node_setup, where the site-state faults live), then the ops node env file; later wins."""
    setup = spec.hardware.node_setup.get(node) if spec else None
    site = ["LC_ALL=C.UTF-8", *(setup.site_job_env if setup else [])]
    path = ops / "cluster/nodes" / f"{node}.env"
    return {**_assignments(site), **_assignments(path.read_text().splitlines() if path.exists() else [])}


def excerpt(path: Path) -> str:
    """The head and the tail of a node log (the failure is at the end; the whole file could be anything)."""
    with path.open("rb") as log:
        head = log.read(LOG_EXCERPT_BYTES)
        if not log.read(1):
            return head.decode(errors="replace")
        log.seek(-LOG_EXCERPT_BYTES, os.SEEK_END)
        return head.decode(errors="replace") + "\n[... truncated ...]\n" + log.read().decode(errors="replace")


def run(
    task: str,
    variant: str,
    ranks_per_node: int,
    limit: float,
    overrides: dict,
    parent: Path,
    backend: str = "nccl",
    seed: int = 7,
    heldout_seed: int = 424242,
    data_seed: int = 20240917,
) -> dict:
    from harness import corpus
    from harness.teacher import Teacher

    validate(task, ranks_per_node)
    spec = by_id(task)
    work = run_dir(parent, f"{task}-{variant}-{backend}")
    row = {
        "task": task,
        "variant": variant,
        "backend": backend,
        "run_dir": str(work),
        "status": "runner-error",
        "teacher_seed": seed,
        "heldout_seed": heldout_seed,
        "data_seed": data_seed,
        "overrides": overrides,
        "world_size": 2 * ranks_per_node,
    }
    (work / "manifest.json").write_text(json.dumps(row, indent=2))
    try:
        with devices(backend, 2 * ranks_per_node) as (selected, uuids):
            ops = assemble(task, variant, work)
            cfg = config(ops)
            invalid = (set(overrides) - set(cfg)) | (set(overrides) & {"data", "ckpt_dir", "export", "resume_from"})
            if invalid:
                raise ValueError(f"unknown or runner-managed overrides: {sorted(invalid)}")
            cfg.update(overrides)
            noise = spec.data.noise.model_dump() if spec.data and spec.data.noise else None
            manifest = {
                **provenance(backend),
                "task": task,
                "variant": variant,
                "spec": spec.model_dump(),
                "canonical_ops_sha256": digest_tree(ops),
                "overrides": overrides,
                "teacher_seed": seed,
                "heldout_seed": heldout_seed,
                "data_seed": data_seed,
                "gpu_uuids": uuids,
                "world_size": 2 * ranks_per_node,
                "global_batch": 2 * ranks_per_node * cfg["micro_batch"] * cfg["grad_accum"],
                "differences": [
                    "two logical nodes on one host",
                    "no Slurm, object-store replication, CPU memory limit or dataset throttling",
                    "native GPU link, no emulated inter-node network",
                    "CUDA default device and batch transfers",
                    "NCCL communicators initialised lazily (no device_id), unlike templates/ops-gpu",
                ],
            }
            (work / "manifest.json").write_text(json.dumps(manifest, indent=2))
            teacher = Teacher(seed=seed, noise=noise)
            teacher.save(work / "teacher.json")
            corpus.write(
                teacher,
                work / "corpus.safetensors",
                cfg["train_seqs"],
                cfg["val_seqs"],
                cfg["model"]["ctx"] + 1,
                data=spec.data,
                data_seed=data_seed,
            )
            cfg.update(
                data=str(work / "corpus.safetensors"),
                ckpt_dir=str(work / "ckpt"),
                export=str(work / "out/model.safetensors"),
            )
            (work / "train.yaml").write_text(yaml.safe_dump(cfg))
            port(ops)
            manifest["adapted_ops_sha256"] = digest_tree(ops)
            (work / "fr").mkdir()
            commands = []
            port_no = free_port()
            for n in range(2):
                node = f"c{n + 1}"
                env = nccl_env({
                    **os.environ,
                    "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "4"),
                    **node_env(ops, node, spec),
                    "OCB_BACKEND": backend,
                    "SLURM_JOB_ID": "job",
                    "OCB_METRICS_ROOT": str(work / "metrics"),
                    "OCB_FR_DIR": str(work / "fr"),
                    "PYTHONPATH": str(ROOT / "src"),
                    "TORCH_FR_BUFFER_SIZE": "2000",
                    "TORCH_NCCL_TRACE_BUFFER_SIZE": "2000",
                    "TORCH_NCCL_DUMP_ON_TIMEOUT": "1",
                    "TORCH_NCCL_DEBUG_INFO_TEMP_FILE": str(work / "fr/nccl_trace_rank_"),
                })  # fmt: skip
                env["CUDA_VISIBLE_DEVICES"] = ",".join(selected[n * ranks_per_node : (n + 1) * ranks_per_node])
                manifest.setdefault("node_environment", {})[node] = {
                    k: v
                    for k, v in env.items()
                    if k.startswith(("OCB_", "NCCL_", "TORCH_"))
                    or k in ("OMP_NUM_THREADS", "PYTHONHASHSEED", "CUDA_VISIBLE_DEVICES", "LC_ALL")
                    or k in node_env(ops, node, spec)
                }
                argv = [
                    sys.executable,
                    "-m",
                    "torch.distributed.run",
                    "--nnodes=2",
                    f"--nproc-per-node={ranks_per_node}",
                    f"--node-rank={n}",
                    "--rdzv-backend=static",
                    "--master-addr=127.0.0.1",
                    f"--master-port={port_no}",
                    str(ops / "src/train.py"),
                    "--config",
                    str(work / "train.yaml"),
                ]
                commands.append((argv, env, work / f"node{n + 1}.log"))
            (work / "manifest.json").write_text(json.dumps(manifest, indent=2))
            codes, timed_out, elapsed = execute(commands, limit)
            row.update(
                status="hung" if timed_out else "failed" if any(codes) else "completed",
                exit=codes,
                elapsed_s=round(elapsed, 3),
            )
            rank0 = work / "metrics/job/rank0.jsonl"
            records = [json.loads(line) for line in rank0.read_text().splitlines()] if rank0.exists() else []
            times = [r["step_s"] for r in records if "step_s" in r]
            row.update(steps=len(times), median_step_s=statistics.median(times) if times else None)
            text = "\n".join(excerpt(work / f"node{n + 1}.log") for n in range(2))
            errors = [
                line.strip()
                for line in text.splitlines()
                if re.search(r"Error|error:|Watchdog|timed out|Timeout|mismatch|SIGKILL|SIGABRT", line)
                and "Traceback" not in line
            ]
            row.update(first_errors=errors[:3], watchdog="watchdog" in text.lower())
            if Path(cfg["export"]).is_file() and row["status"] == "completed":
                try:
                    res = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "harness.verify.evaluate",
                            cfg["export"],
                            str(work / "teacher.json"),
                            json.dumps(cfg["model"]),
                            str(heldout_seed),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=300,
                        check=False,
                        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "CUDA_VISIBLE_DEVICES": ""},
                    )
                    (work / "evaluation.log").write_text(res.stdout + res.stderr)
                    row["evaluation"] = json.loads(res.stdout.strip().splitlines()[-1])
                    row["loss"] = row["evaluation"].get("loss")
                    if res.returncode or "loss" not in row["evaluation"]:
                        row["status"] = "evaluation-error"
                except (subprocess.TimeoutExpired, IndexError, ValueError) as exc:
                    row.update(status="evaluation-error", error=str(exc))
            row["fr_dumps"] = len(list((work / "fr").glob("*")))
    except Exception as exc:  # noqa: BLE001 -- failed runs also get durable records
        row["error"] = f"{type(exc).__name__}: {exc}"
    (work / "result.json").write_text(json.dumps(row, indent=2))
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tasks", nargs="+")
    ap.add_argument("--variants", default="broken,fixed")
    ap.add_argument("--gpus-per-node", type=int, default=2)
    ap.add_argument("--backend", choices=("gloo", "nccl"), default="nccl")
    ap.add_argument("--limit", type=float, default=400)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=YAML")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--heldout-seed", type=int, default=424242)
    ap.add_argument("--data-seed", type=int, default=20240917)
    ap.add_argument("--runs-dir", type=Path, default=ROOT / "runs/gpu")
    ap.add_argument("--out", type=Path, default=ROOT / "runs/gpu/jobs.jsonl")
    args = ap.parse_args()
    try:
        if args.gpus_per_node < 1 or args.limit <= 0:
            raise ValueError("ranks per node and limit must be positive")
        variants = args.variants.split(",")
        if not set(variants) <= {"broken", "fixed"}:
            raise ValueError("variants must be broken or fixed")
        for task in args.tasks:
            validate(task, args.gpus_per_node)
        overrides = {k: yaml.safe_load(v) for k, v in (s.split("=", 1) for s in args.set)}
    except (ValueError, KeyError) as exc:
        ap.error(str(exc))
    from run import run as run_scenario

    control = run_scenario("healthy_control", args.backend, min(args.limit, 180), args.runs_dir)
    append_row(args.out.with_suffix(".controls.jsonl"), control)
    if control["status"] != "completed":
        sys.exit("healthy distributed control failed; inspect its log before interpreting task failures")
    failed = False
    for task in args.tasks:
        for variant in variants:
            row = run(
                task,
                variant,
                args.gpus_per_node,
                args.limit,
                overrides,
                args.runs_dir,
                args.backend,
                args.seed,
                args.heldout_seed,
                args.data_seed,
            )
            append_row(args.out, row)
            failed |= row["status"] in ("runner-error", "evaluation-error") or (
                variant == "fixed" and row["status"] != "completed"
            )
    sys.exit(int(failed))


if __name__ == "__main__":
    main()
