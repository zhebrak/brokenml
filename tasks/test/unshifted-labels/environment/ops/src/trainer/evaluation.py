"""Loss and validation."""
from __future__ import annotations

import torch
import torch.distributed as dist
import torch.nn.functional as F

from . import data


def next_token_loss(model: torch.nn.Module, inputs: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    """Causal LM loss: `labels` are the token ids of the same sequence as `inputs`; the loss shifts them so the logits
    at position t score the token at t + 1."""
    logits = model(inputs[:, :-1])
    return F.cross_entropy(logits.reshape(-1, logits.shape[-1]), labels[:, 1:].reshape(-1))


def evaluate(model: torch.nn.Module, val: torch.Tensor, chunk: int = 16) -> float:
    """Validation loss averaged over ranks; each rank scores its slice of the validation set in chunks (collective)."""
    rank, world = dist.get_rank(), dist.get_world_size()
    part = val[rank::world]
    total = torch.zeros(())
    with torch.no_grad():
        for i in range(0, len(part), chunk):
            batch = part[i:i + chunk]
            inputs, labels = data.collate(batch)
            total = total + next_token_loss(model, inputs, labels) * len(batch)
    total = total / max(1, len(part))
    dist.all_reduce(total, op=dist.ReduceOp.SUM)
    return total.item() / world
