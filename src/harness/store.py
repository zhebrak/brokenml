"""Build a task's checkpoint store at image-build time (checkpoint-resume tasks).

  python3 -m harness.store STORE_YAML OUT_DIR

STORE_YAML:
  teacher_seed: 1234            # differs between the agent image and the verifier image
  runs:
    - name: train-2026-09-28    # directory under OUT_DIR/runs/
      steps: 800                # train this many steps, checkpointing every ckpt_every
      ckpt_every: 100
      model: {...}              # optional GPTConfig override (default: the job's model)
      corrupt: [half-written-latest | rename-key:OLD->NEW | latest-points-to:REL | mixed-shards:STEP_DIR]   # optional

The trainer mirrors the job's trainer package (templates/ops/src/trainer: same model, AdamW settings, schedule,
batches and checkpoint format; tests/test_store.py checks the settings), so the job's resume path can load what it
writes. It runs as 4 ranks over Gloo on localhost (torchrun --standalone), which also gives the DCP files a 4-rank
layout.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

JOB_MODEL = {"vocab": 32, "ctx": 64, "d_model": 128, "n_layer": 2, "n_head": 4}
# The job's training settings (templates/ops/src/trainer/config.py DEFAULTS; tests/test_store.py keeps them equal).
LR, WARMUP, MIN_LR_RATIO, BETAS, WEIGHT_DECAY = 3e-3, 50, 0.1, (0.9, 0.95), 0.0
MICRO_BATCH, TRAIN_SEQS = 16, 16384


def lr_at(step: int, total: int) -> float:
    """The job's schedule (trainer.optim.lr_at): linear warmup, then cosine decay to MIN_LR_RATIO over `total`."""
    if step < WARMUP:
        return LR * (step + 1) / WARMUP
    progress = min(1.0, (step - WARMUP) / max(1, total - WARMUP))
    return LR * (MIN_LR_RATIO + (1 - MIN_LR_RATIO) * 0.5 * (1 + math.cos(math.pi * progress)))


def _worker(run_json: str) -> None:
    import datetime

    import torch
    import torch.distributed as dist
    import torch.nn.functional as F
    from torch.nn.parallel import DistributedDataParallel as DDP

    from harness.teacher import Teacher
    from ocb import ckpt
    from ocb.model import GPT, GPTConfig

    run = json.loads(run_json)
    dist.init_process_group("gloo", timeout=datetime.timedelta(seconds=300))
    rank, world = dist.get_rank(), dist.get_world_size()
    torch.set_num_threads(1)
    torch.manual_seed(0)
    teacher = Teacher.load(run["teacher"])
    mcfg = GPTConfig(**run["model"])
    data = teacher.sample(TRAIN_SEQS, mcfg.ctx + 1, seed=teacher.seed + 1)
    model = DDP(GPT(mcfg))
    opt = torch.optim.AdamW(model.parameters(), lr=LR, betas=BETAS, weight_decay=WEIGHT_DECAY)
    shard = data[rank::world]
    total = run["schedule_steps"]
    step, epoch, i = 0, 0, 0
    order = torch.randperm(len(shard), generator=torch.Generator().manual_seed(epoch))
    while step < run["steps"]:
        if i + MICRO_BATCH > len(order):
            epoch, i = epoch + 1, 0
            order = torch.randperm(len(shard), generator=torch.Generator().manual_seed(epoch))
        tokens = shard[order[i : i + MICRO_BATCH]]
        i += MICRO_BATCH
        lr = lr_at(step, total)
        for g in opt.param_groups:
            g["lr"] = lr
        logits = model(tokens[:, :-1])
        loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), tokens[:, 1:].reshape(-1))
        loss.backward()
        opt.step()
        opt.zero_grad(set_to_none=True)
        step += 1
        if step % run["ckpt_every"] == 0:
            ckpt.save(run["dir"], step, model, opt, meta={"lr": lr, "model": run["model"]})
    dist.destroy_process_group()


def _corrupt(run_dir: Path, how: str) -> None:
    latest = run_dir / (run_dir / "latest").read_text().strip()
    if how == "half-written-latest":
        # The store is a mirror filled by a sync job that copies the `latest` pointer before the data and was
        # interrupted while copying the newest checkpoint: its metadata, meta.json and one rank's shard are missing.
        for name in (".metadata", "meta.json"):
            (latest / name).unlink()
        shards = sorted(latest.glob("*.distcp"))
        if shards:
            shards[-1].unlink()
    elif how.startswith("rename-key:"):
        # The whole run was written by an older model version whose parameter had another name.
        import pickle

        old, new = how.split(":", 1)[1].split("->")
        for meta_path in run_dir.glob("step_*/.metadata"):
            with open(meta_path, "rb") as f:
                md = pickle.load(f)  # trusted: written by this build step, never by an agent
            md.state_dict_metadata = {k.replace(old, new): v for k, v in md.state_dict_metadata.items()}
            md.storage_data = {
                type(idx)(idx.fqn.replace(old, new), idx.offset, idx.index): v for idx, v in md.storage_data.items()
            }
            with open(meta_path, "wb") as f:
                pickle.dump(md, f)
    elif how.startswith("mixed-shards:"):
        # An in-place mirror sync interrupted half-way: the newest checkpoint's metadata and the first half of its
        # shards are the new step's, the other shards still hold the older step's files (same names and layout), so
        # the checkpoint loads and carries two steps' parameters and optimizer states.
        older = run_dir / how.split(":", 1)[1]
        shards = sorted(latest.glob("*.distcp"))
        for shard in shards[len(shards) // 2 :]:
            shutil.copy2(older / shard.name, shard)
    elif how.startswith("latest-points-to:"):
        # A sync mix-up: this run's `latest` pointer names a checkpoint of another run (a path relative to the run
        # directory, e.g. ../train-wide/step_800), whose own files are intact.
        (run_dir / "latest").write_text(how.split(":", 1)[1])
    else:
        raise ValueError(f"unknown corruption {how}")


def build(spec_path: str, out: str) -> None:
    from harness.teacher import Teacher

    spec = yaml.safe_load(Path(spec_path).read_text())
    out_dir = Path(out)
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)
    teacher = Teacher(seed=spec["teacher_seed"])
    teacher.save(out_dir / "teacher.json")
    for run in spec["runs"]:
        run_dir = out_dir / "runs" / run["name"]
        cfg = {
            "teacher": str(out_dir / "teacher.json"),
            "dir": str(run_dir),
            "steps": run["steps"],
            "ckpt_every": run["ckpt_every"],
            "schedule_steps": run.get("schedule_steps", run["steps"]),
            "model": {**JOB_MODEL, **run.get("model", {})},
        }
        env = {**os.environ, "OMP_NUM_THREADS": "1"}  # PYTHONPATH from the image: /opt/ocb:/opt/harness
        subprocess.run(
            ["torchrun", "--standalone", "--nproc-per-node=4", "-m", "harness.store", "--worker", json.dumps(cfg)],
            check=True,
            env=env,
        )
        for how in run.get("corrupt", []):
            _corrupt(run_dir, how)
        for tmp in run_dir.glob("*.tmp"):
            shutil.rmtree(tmp) if tmp.is_dir() else tmp.unlink()
    _sync_log(out_dir, spec)
    for path in out_dir.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)


def _sync_log(out_dir: Path, spec: dict) -> None:
    """The store is a mirror of the training cluster's checkpoints; record the sync job's progress like its log
    would (pointer first, then data), ending mid-copy for a run whose newest checkpoint was cut off."""
    lines, t = ["ckpt-sync: mirroring /scratch/ckpt -> /shared/ckpt-store"], 0
    for run in spec["runs"]:
        run_dir = out_dir / "runs" / run["name"]
        steps = sorted((d for d in run_dir.glob("step_*") if d.is_dir()), key=lambda d: int(d.name.split("_")[1]))
        newest = (run_dir / "latest").read_text().strip() if (run_dir / "latest").exists() else None
        if newest:
            t += 2
            lines.append(f"00:{t // 60:02d}:{t % 60:02d} copied runs/{run['name']}/latest -> {newest}")
        for d in steps:
            t += 7
            stamp = f"00:{t // 60:02d}:{t % 60:02d}"
            if (d / ".metadata").exists():
                lines.append(f"{stamp} copied runs/{run['name']}/{d.name} ({len(list(d.glob('*.distcp')))} shards)")
            else:
                lines.append(f"{stamp} copying runs/{run['name']}/{d.name} ...")
                break
    (out_dir / "SYNC.log").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "--worker":
        _worker(sys.argv[2])
    else:
        build(sys.argv[1], sys.argv[2])
