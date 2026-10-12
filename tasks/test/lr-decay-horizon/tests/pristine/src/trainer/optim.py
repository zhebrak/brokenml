"""Optimizer, learning-rate schedule and gradient clipping."""
from __future__ import annotations

import math

import torch
import torch.distributed as dist


def build(model: torch.nn.Module, cfg: dict) -> torch.optim.Optimizer:
    return torch.optim.AdamW(model.parameters(), lr=cfg["lr"], betas=tuple(cfg["betas"]), weight_decay=cfg["weight_decay"])


def lr_at(step: int, cfg: dict) -> float:
    """Linear warmup over warmup_steps, then cosine decay to min_lr_ratio * lr over decay_steps (default: the run)."""
    peak, warmup = cfg["lr"], cfg["warmup_steps"]
    total = (cfg["decay_steps"] or cfg["steps"]) // dist.get_world_size()
    if step < warmup:
        return peak * (step + 1) / warmup
    progress = min(1.0, (step - warmup) / max(1, total - warmup))
    floor = cfg["min_lr_ratio"]
    return peak * (floor + (1 - floor) * 0.5 * (1 + math.cos(math.pi * progress)))


def set_lr(opt: torch.optim.Optimizer, lr: float) -> None:
    for group in opt.param_groups:
        group["lr"] = lr


def clip(model: torch.nn.Module, max_norm: float, sharded: bool) -> float:
    """Clip gradients to a global norm. With FSDP each rank holds a shard, so the norm needs an all-reduce."""
    if max_norm <= 0:
        return 0.0
    grads = [p.grad for p in model.parameters() if p.grad is not None]
    local_sq = torch.stack([g.detach().float().pow(2).sum() for g in grads]).sum() if grads else torch.zeros(())
    if sharded:
        dist.all_reduce(local_sq)
    norm = float(local_sq.sqrt())
    if norm > max_norm:
        for g in grads:
            g.mul_(max_norm / (norm + 1e-6))
    return norm
