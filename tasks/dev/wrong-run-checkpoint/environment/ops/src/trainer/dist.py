"""Process group setup and the collective helpers the rest of the trainer uses."""
from __future__ import annotations

import datetime
import os

import torch
import torch.distributed as dist

from ocb import frdump


def init(timeout_s: float) -> tuple[int, int]:
    """Join the job's process group (rendezvous via torchrun's environment). Returns (rank, world size)."""
    frdump.install()
    dist.init_process_group("gloo", timeout=datetime.timedelta(seconds=timeout_s))
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "1")))
    return dist.get_rank(), dist.get_world_size()


def rank() -> int:
    return dist.get_rank()


def world() -> int:
    return dist.get_world_size()


def is_main() -> bool:
    return dist.get_rank() == 0


def local_rank() -> int:
    return int(os.environ.get("LOCAL_RANK", "0"))


def mean(value: torch.Tensor) -> torch.Tensor:
    """Average a tensor over all ranks (collective)."""
    out = value.detach().clone()
    dist.all_reduce(out, op=dist.ReduceOp.SUM)
    return out / dist.get_world_size()


def reduce_stats(stats: dict[str, float], op: str = "sum") -> dict[str, float]:
    """Reduce a dict of scalars over all ranks in one collective (collective; keys in sorted order on every rank)."""
    keys = sorted(stats)
    t = torch.tensor([float(stats[k]) for k in keys], dtype=torch.float64)
    dist.all_reduce(t, op={"sum": dist.ReduceOp.SUM, "max": dist.ReduceOp.MAX, "min": dist.ReduceOp.MIN}[op])
    return dict(zip(keys, t.tolist()))


def barrier() -> None:
    dist.barrier()


def shutdown() -> None:
    if dist.is_initialized():
        dist.destroy_process_group()
