"""templates/ops-gpu is templates/ops plus a device path and a one-node GPU layout. Every other file must stay
identical, so a platform fix to the CPU trainer reaches the GPU track too (and GPU twins, which reuse CPU fault
patches through `twin_of`, keep applying)."""

from __future__ import annotations

from bench.paths import ROOT

CPU, GPU = ROOT / "templates" / "ops", ROOT / "templates" / "ops-gpu"
# Files that may differ: the device path, and the GPU node's jobs, cluster config and runbook.
ALLOWED = {
    "src/trainer/config.py", "src/trainer/dist.py", "src/trainer/loop.py", "src/trainer/evaluation.py",
    "src/trainer/optim.py", "src/trainer/parallel.py", "src/trainer/monitor.py", "src/trainer/device.py",
    "jobs/train/launch.sbatch", "jobs/train/train.yaml", "jobs/train/CONTRACT.md", "jobs/finetune/launch.sbatch",
    "jobs/finetune/train.yaml", "jobs/eval/eval.sbatch", "cluster/slurm.conf", "cluster/nodes/c1.env",
    "cluster/nodes/c2.env", "cluster/nodes/g1.env", "RUNBOOK.md",
}  # fmt: skip


def _files(root):
    return {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def test_gpu_template_differs_only_where_allowed():
    cpu, gpu = _files(CPU), _files(GPU)
    drift = sorted(rel for rel in (cpu.keys() | gpu.keys()) - ALLOWED
                   if rel not in cpu or rel not in gpu or cpu[rel].read_bytes() != gpu[rel].read_bytes())  # fmt: skip
    assert not drift, f"templates/ops-gpu drifted from templates/ops (copy the change, or allow it here): {drift}"
