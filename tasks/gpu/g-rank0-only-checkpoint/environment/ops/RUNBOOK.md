# Runbook: GPU training node

## Layout
- Versions: Python 3.12, PyTorch 2.14.1 (CUDA 13.0 build), Slurm 26.05.2.
- Workstation (`main`): Slurm submit host. You are root here.
- `slurmctld`: Slurm controller. Compute node: `g1`, with its GPUs as Slurm GRES (`sinfo -o '%N %G'`; ssh as root:
  `ssh g1`).
- `/ops` (this repo) is mounted read-only on every node: jobs read their code and config from it.
- `/shared` is shared by all nodes: `logs/` (job stdout/stderr), `metrics/<jobid>/rank*.jsonl` (per-step metrics),
  `out/` (exported model), `ckpt/` (checkpoints: a filesystem of its own with a fixed capacity, see `df`), `data/`
  (datasets), `evidence/` (reports and dumps).
- Object store `http://objstore:8000` (S3-like, run by the storage team): checkpoint replicas (`ocb.ckpt` uploads
  every committed checkpoint) and datasets (`GET /datasets/<name>`). It may limit each client host's request rate:
  beyond the budget it answers `503 SlowDown`, and every request counts against the budget, rejected ones included.

## Jobs
- Submit: `ocb submit train` (runs `jobs/train/submit.sh` as `svc-train`). Cancel: `scancel <jobid>`.
- Watch: `squeue`, `sinfo -R`, `scontrol show job <jobid>`, `ocb status`, `ocb logs <jobid>`, `ocb metrics <jobid>`.
- Stacks and Flight Recorder traces of every rank: `ocb dump <jobid>` (py-spy over ssh; traces for `torchfrtrace`).
- Score the exported model the way the evaluation does: `ocb score` (held-out loss, positions 2+, fresh sequences).
- Inspect a committed checkpoint (step, files, stored names, AdamW step counters): `ocb ckpt <dir>` (a step
  directory, or a run directory to follow its `latest`).
- Node counters (cgroup memory/CPU, filesystems): `ocb nodes`. GPUs (memory, utilisation, clocks, power, which
  processes hold each device): `ocb gpus`. On the node (as root): `nvidia-smi`, `py-spy`, `ss`, `lsof`, `nsys`,
  and the PyTorch profiler.
- NCCL: the node's site settings are in `/etc/nccl.conf`; `NCCL_DEBUG=INFO` in a job's environment logs the
  transports and algorithms each communicator chose. A rank stuck in a collective is reported by the NCCL watchdog
  at the process group's timeout, with a Flight Recorder dump per rank (`ocb dump`, `torchfrtrace`).

## Cluster config
- `cluster/slurm.conf`, `cluster/nodes/<node>.env` (extra task environment per node, applied by the TaskProlog).
- Apply changes to the running cluster: `ocb cluster apply`.

## Debug knobs
- `TORCH_DISTRIBUTED_DEBUG=DETAIL` checks that ranks issue matching collectives (slow; for diagnosis).
- `kill -USR1 <pid>` on a node makes a rank print all Python thread stacks to its log.
