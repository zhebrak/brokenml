"""Job configuration.

A job's YAML file is merged over DEFAULTS, so every key the trainer understands is listed here with its
default. Unknown keys are reported (they are usually typos) but do not stop the job.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

DEFAULTS: dict = {
    # model and data
    "model": {"vocab": 32, "ctx": 64, "d_model": 128, "n_layer": 2, "n_head": 4},
    "data": "/shared/data/corpus.safetensors",  # train / val sequences (ctx + 1 tokens each), prepared by the data team
    "train_seqs": 16384,
    "val_seqs": 512,
    "prefetch": 2,                 # batches prepared ahead by a background thread per rank (0: inline)
    # optimisation
    "seed": 0,
    "steps": 500,
    "micro_batch": 16,             # sequences per rank per micro-step
    "grad_accum": 1,               # micro-steps per optimizer step
    "lr": 3e-3,
    "warmup_steps": 50,
    "decay_steps": None,           # cosine horizon in steps; None: the whole run (`steps`)
    "min_lr_ratio": 0.1,           # cosine decays to this fraction of lr at the end of the horizon
    "weight_decay": 0.0,
    "betas": [0.9, 0.95],
    "grad_clip": 0.0,              # max global grad norm; 0 disables clipping
    "replica_check_every": 100,    # steps between logged replica consistency checks
    # parallelism and communication
    "parallel": "ddp",             # ddp | fsdp | manual (bucketed all-reduce in parallel.sync_grads)
    "bucket_cap_mb": 25,           # DDP gradient bucket size
    "pg_timeout_s": 120,           # collective timeout of the default process group
    # evaluation, monitoring, checkpoints
    "eval_every": 100,
    "log_every": 10,               # cluster-wide throughput aggregate, logged by rank 0
    "ckpt_every": 0,               # 0 disables periodic checkpoints
    "ckpt_keep": 0,                # keep only the newest N checkpoints; 0 keeps all
    "ckpt_dir": "/shared/ckpt/train",
    "resume_from": None,           # a checkpoint directory, or a run directory (its newest checkpoint)
    "resume_key_map": None,        # {current name or prefix: name in the checkpoint}, see ocb.ckpt.load
    "export": "/shared/out/model.safetensors",
}


def load(path: str | Path) -> dict:
    user = yaml.safe_load(Path(path).read_text()) or {}
    unknown = sorted(set(user) - set(DEFAULTS))
    if unknown:
        print(f"config {path}: unknown keys {unknown} (ignored by the trainer)", file=sys.stderr, flush=True)
    cfg = {**DEFAULTS, **user}
    cfg["model"] = {**DEFAULTS["model"], **(user.get("model") or {})}
    if cfg["parallel"] not in ("ddp", "fsdp", "manual"):
        raise ValueError(f"parallel must be ddp, fsdp or manual, not {cfg['parallel']!r}")
    return cfg
