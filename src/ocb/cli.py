"""`ocb`: the workstation's helper CLI. Every command is a thin wrapper over standard tools
(squeue/scontrol, ssh, py-spy, the metrics files), so an agent can always fall back to those.

  ocb status                 queue, node states, drain reasons
  ocb submit [JOB]           run /ops/jobs/JOB/submit.sh as svc-train (default JOB=train)
  ocb logs JOBID [-n N] [--head H]   tail (and head) the job's log files
  ocb metrics JOBID          per-rank progress: steps, loss, step time, tokens/s, RSS
  ocb dump JOBID             py-spy stacks + Flight Recorder traces from every rank
  ocb nodes                  per-node cgroup memory/CPU counters
  ocb cluster apply          push /ops/cluster/{slurm,cgroup}.conf to the cluster and reconfigure
  ocb score [JOB]            held-out loss of the job's export, computed as the verifier does
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import time
from pathlib import Path

from ocb import slurm

OPS = Path("/ops")
SHARED = Path("/shared")
FR_DIR = SHARED / "evidence" / "fr"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR"]


def ssh(host: str, command: str, timeout: float = 20) -> str:
    res = slurm.run([*SSH, f"root@{host}", command], timeout=timeout)
    return (res.stdout + res.stderr).strip()


def status() -> str:
    parts = [slurm.run(["squeue", "-l"]).stdout, slurm.run(["sinfo"]).stdout]
    drained = slurm.run(["sinfo", "-R", "-h"]).stdout.strip()
    parts.append("Drained/down nodes:\n" + (drained or "(none)"))
    return "\n".join(parts)


def logs(job_id: str, n: int = 80, head: int = 0) -> str:
    """The first `head` and last `n` lines of each log file of the job."""
    files = sorted((SHARED / "logs").glob(f"*-{job_id}.out"))
    if not files:
        return f"no log files for job {job_id} under /shared/logs"
    out = []
    for f in files:
        lines = f.read_text(errors="replace").splitlines()
        if head and len(lines) > head + n:
            out.append(f"==> {f} (first {head} and last {n} of {len(lines)} lines) <==")
            out.extend([*lines[:head], "[...]", *lines[-n:]])
        else:
            out.append(f"==> {f} ({len(lines)} lines) <==")
            out.extend(lines[-max(n, head + n) :])
    return "\n".join(out)


def metrics_summary(job_id: str) -> str:
    root = SHARED / "metrics" / job_id
    files = sorted(root.glob("rank*.jsonl"))
    if not files:
        return f"no metrics for job {job_id} under {root}"
    rows = ["rank host     steps  last_loss  med_step_s  tok/s     rss_mb  last_update_s_ago"]
    now = time.time()
    for f in files:
        recs = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
        steps = [r for r in recs if "step_s" in r]  # training-step records (not validation or done events)
        if not steps:
            rows.append(f"{f.stem}: no steps logged")
            continue
        last = steps[-1]
        step_s = [r["step_s"] for r in steps[-50:] if "step_s" in r]
        med = statistics.median(step_s) if step_s else float("nan")
        tok_s = last.get("tokens", 0) / med if step_s and med > 0 else float("nan")
        rows.append(
            f"{last['rank']:<4} {last['host']:<8} {last['step']:<6} {last.get('loss', float('nan')):<10.4f} "
            f"{med:<11.4f} {tok_s:<9.0f} {last.get('rss_mb', 0):<7.0f} {now - last['t']:.0f}"
        )
    return "\n".join(rows)


def dump(job_id: str, out_dir: Path | None = None) -> str:
    """Stacks of every training process plus Flight Recorder traces, saved under /shared/evidence."""
    job = slurm.job(job_id)
    hosts = slurm.hostnames(job.nodes) if job else []
    hosts = hosts or sorted(slurm.nodes())
    out_dir = out_dir or SHARED / "evidence" / "dumps" / f"{job_id}-{int(time.time())}"
    out_dir.mkdir(parents=True, exist_ok=True)
    FR_DIR.mkdir(parents=True, exist_ok=True)
    (FR_DIR / "TRIGGER").write_text(str(time.time()))
    time.sleep(3)
    report = []
    for host in hosts:
        pids = ssh(host, "pgrep -f -u svc-train 'python.*\\.py' || true").split()
        for pid in pids:
            stack = ssh(host, f"py-spy dump --pid {pid} 2>&1 || true")
            (out_dir / f"stack-{host}-{pid}.txt").write_text(stack + "\n")
            report.append(f"## {host} pid {pid}\n{stack}\n")
    # The NCCL watchdog writes its own dumps when a collective times out (<host>-nccl-rank<r>), also after the job died.
    watchdog = sorted(p for p in FR_DIR.glob("*-nccl-rank*") if p.is_file())
    if not report and not watchdog:
        shutil.rmtree(out_dir, ignore_errors=True)
        return f"no live training processes for job {job_id} on {', '.join(hosts)} (nothing to dump)"
    traces = sorted(FR_DIR.glob("*.json"))
    for trace in traces:
        (out_dir / f"fr-{trace.name}").write_bytes(trace.read_bytes())
    for trace in watchdog:
        (out_dir / f"fr-watchdog-{trace.name}").write_bytes(trace.read_bytes())
    if traces:
        report.append(f"Flight Recorder traces: {out_dir}/fr-*.json (analyse with `torchfrtrace`)")
    if watchdog:
        report.append(f"NCCL watchdog dumps (written at its timeout): {out_dir}/fr-watchdog-* (`torchfrtrace`)")
    (out_dir / "stacks.md").write_text("\n".join(report))
    return "\n".join(report) + f"\nSaved under {out_dir}"


def node_stats() -> str:
    out = []
    for host in sorted(slurm.nodes()):
        stats = ssh(
            host,
            "cd /sys/fs/cgroup && for f in memory.events memory.peak memory.max cpu.max cpu.stat; do "
            'echo "--- $f"; cat $f 2>/dev/null; done; '
            'echo "--- memory.stat"; grep -E "^(anon|file|shmem|kernel) " memory.stat 2>/dev/null; '
            'echo "--- filesystems"; df -h /shared /shared/ckpt /scratch /var/tmp /tmp /dev/shm 2>/dev/null | uniq',
        )
        out.append(f"=== {host}\n{stats}")
    return "\n".join(out)


GPU_QUERY = "index,uuid,name,memory.used,memory.total,utilization.gpu,clocks.sm,power.draw,temperature.gpu"
# Which processes hold each GPU, from their open device files (nvidia-smi cannot name them inside a container).
GPU_HOLDERS = (
    "for p in /proc/[0-9]*; do for f in $p/fd/*; do t=$(readlink $f 2>/dev/null); case $t in /dev/nvidia[0-9]*) "
    "echo \"${t#/dev/} pid=${p#/proc/} user=$(stat -c %U $p) $(tr '\\0' ' ' < $p/cmdline | cut -c1-80)\";; esac; "
    "done; done | sort -u"
)


def gpu_stats() -> str:
    out = []
    for host in sorted(slurm.nodes()):
        info = ssh(host, f"nvidia-smi --query-gpu={GPU_QUERY} --format=csv 2>/dev/null || echo no-gpus")
        if "no-gpus" in info:
            continue
        holders = ssh(host, GPU_HOLDERS)
        out.append(f"=== {host}\n{info}\n--- processes holding a GPU device\n{holders or '(none)'}")
    return "\n".join(out) or "no node has GPUs"


def cluster_apply() -> str:
    slurm.deploy_cluster_config(OPS)
    res = slurm.run(["scontrol", "reconfigure"])
    return (res.stdout + res.stderr).strip() or "reconfigured"


HELDOUT = Path("/shared/data/heldout.safetensors")


def score(job: str) -> str:
    """Held-out loss of the job's export, computed the way the evaluation does (positions 2+, held-out sequences)."""
    import json

    import yaml

    cfg = yaml.safe_load((OPS / "jobs" / job / "train.yaml").read_text())
    data = HELDOUT  # the cluster's held-out split (fresh sequences from the dataset's definition)
    export = Path(cfg["export"])
    if not export.exists():
        return f"no export at {export}: run the job to completion first"
    res = slurm.run([sys.executable, "-m", "ocb.score", str(export), str(data), json.dumps(cfg["model"])], timeout=600)
    try:
        out = json.loads(res.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return f"scoring failed:\n{(res.stderr or res.stdout)[-1500:]}"
    return (
        f"held-out loss {out['loss']:.4f} on the corpus's held-out split (positions 2+).\n"
        "The evaluation computes the same metric on its own fresh data and held-out set."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ocb", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("submit")
    p.add_argument("job", nargs="?", default="train")
    p = sub.add_parser("logs")
    p.add_argument("job_id")
    p.add_argument("-n", type=int, default=80)
    p.add_argument("--head", type=int, default=0, help="also show the first HEAD lines")
    p = sub.add_parser("metrics")
    p.add_argument("job_id")
    p = sub.add_parser("dump")
    p.add_argument("job_id")
    sub.add_parser("nodes")
    sub.add_parser("gpus", help="per-GPU memory, utilisation, clocks and power, and the processes holding each GPU")
    p = sub.add_parser("cluster")
    p.add_argument("action", choices=["apply"])
    p = sub.add_parser("score", help="held-out loss of the job's export, computed as the evaluation computes it")
    p.add_argument("job", nargs="?", default="train")
    p = sub.add_parser("ckpt", help="a committed checkpoint: step, files, stored names, AdamW step counters")
    p.add_argument("path", help="a step directory, or a run directory (its `latest` pointer is followed)")
    args = ap.parse_args(argv)
    try:
        return _run(args)
    except slurm.SlurmError as exc:
        print(f"ocb: {exc}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace) -> int:

    if args.cmd == "status":
        print(status())
    elif args.cmd == "submit":
        ids, output = slurm.submit(OPS, args.job)
        print(output.strip())
        print("submitted job ids:", " ".join(ids) or "(none)")
    elif args.cmd == "logs":
        print(logs(args.job_id, args.n, args.head))
    elif args.cmd == "metrics":
        print(metrics_summary(args.job_id))
    elif args.cmd == "dump":
        print(dump(args.job_id))
    elif args.cmd == "nodes":
        print(node_stats())
    elif args.cmd == "gpus":
        print(gpu_stats())
    elif args.cmd == "cluster":
        print(cluster_apply())
    elif args.cmd == "score":
        print(score(args.job))
    elif args.cmd == "ckpt":
        from ocb import ckpt  # torch: imported only for this command

        print(ckpt.inspect(args.path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
