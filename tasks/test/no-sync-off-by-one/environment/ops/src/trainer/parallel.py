"""Data parallelism: DDP (replicated parameters) or FSDP2 (sharded parameters, gradients and optimizer state)."""
from __future__ import annotations

from contextlib import nullcontext

import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP


def wrap(model: torch.nn.Module, cfg: dict) -> torch.nn.Module:
    if cfg["parallel"] == "manual":
        return model  # gradients are averaged by sync_grads (the gradient-compression experiment hooks in there)
    if cfg["parallel"] == "fsdp":
        from torch.distributed.fsdp import fully_shard

        for block in model.blocks:  # one FSDP unit per transformer block, plus the root
            fully_shard(block)
        return fully_shard(model)
    return DDP(model, bucket_cap_mb=cfg["bucket_cap_mb"])


def sync_grads(model: torch.nn.Module) -> None:
    """parallel: manual. Average gradients across ranks with one flat all-reduce per top-level module."""
    world = dist.get_world_size()
    modules = sorted({name.split(".")[0] for name, _ in model.named_parameters()})
    for module in modules:
        grads = [p.grad for name, p in model.named_parameters() if name.split(".")[0] == module and p.grad is not None]
        flat = torch.cat([g.flatten() for g in grads])
        dist.all_reduce(flat)
        flat /= world
        offset = 0
        for g in grads:
            g.copy_(flat[offset:offset + g.numel()].view_as(g))
            offset += g.numel()


def unwrap(model: torch.nn.Module) -> torch.nn.Module:
    return model.module if isinstance(model, DDP) else model


def sync_context(model: torch.nn.Module, micro: int, accum: int):
    """Gradient accumulation: DDP all-reduces gradients only on the last micro-step of an optimizer step."""
    if isinstance(model, DDP) and micro > 0:
        return model.no_sync()
    return nullcontext()
