"""Fault mechanisms in isolation, runnable on Gloo (CPU) and NCCL (GPU), for the fidelity table.

Each scenario is a minimal torchrun program with 2 ranks reproducing one benchmark mechanism. The driver
(run.py) runs every scenario under both backends and records each one's signature: exit status, time to
failure, first error line, NCCL watchdog / Flight Recorder evidence, and for the gather scenario whether the
outputs were right.

  torchrun --standalone --nproc-per-node=2 scenarios.py SCENARIO BACKEND
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import time

import torch
import torch.distributed as dist

TIMEOUT_S = 30
GATHER_MARK = "UNEVEN_GATHER_CHECK "  # a structured line the driver parses into the row


def setup(backend: str) -> tuple[int, torch.device]:
    device = torch.device("cuda", int(os.environ["LOCAL_RANK"])) if backend == "nccl" else torch.device("cpu")
    if backend == "nccl":
        torch.cuda.set_device(device)
    dist.init_process_group(backend, timeout=datetime.timedelta(seconds=TIMEOUT_S))
    rank = dist.get_rank()
    # The default group exists long before a fault in a real job (DDP's initial broadcast); NCCL creates its
    # communicator lazily, so warm it first and the fault hits an initialised communicator.
    dist.barrier()
    return rank, device


def healthy_control(backend: str) -> None:
    """Must pass on a backend before any fault row on it means anything."""
    rank, device = setup(backend)
    value = torch.tensor([float(rank + 1)], device=device)
    dist.all_reduce(value)
    assert value.item() == dist.get_world_size() * (dist.get_world_size() + 1) / 2
    sub = dist.new_group(ranks=[0, 1], timeout=datetime.timedelta(seconds=TIMEOUT_S))
    dist.all_reduce(value, group=sub)
    assert value.item() == 6
    print(f"rank {rank}: healthy control passed", flush=True)


def grads_allreduce(device: torch.device) -> None:
    """Stand-in for a DDP gradient bucket all-reduce."""
    bucket = torch.ones(50_000, device=device)
    dist.all_reduce(bucket)


def rank0_only_collective(backend: str) -> None:
    """rank0-eval-desync: rank 0 all-reduces a scalar while the others all-reduce a gradient bucket."""
    rank, device = setup(backend)
    for step in range(3):
        if rank == 0 and step == 1:
            dist.all_reduce(torch.ones(1, device=device))  # validation loss, rank 0 only
        grads_allreduce(device)


def cross_group_deadlock(backend: str) -> None:
    """subgroup-skip-deadlock with a warm subgroup: one member skips a subgroup collective the others issue, then
    everyone meets in a global one. Models a job whose subgroup already communicated (an eagerly bound NCCL
    communicator, as templates/ops-gpu binds with device_id)."""
    rank, device = setup(backend)
    sub = dist.new_group(ranks=[0, 1], timeout=datetime.timedelta(seconds=TIMEOUT_S))
    dist.all_reduce(torch.ones(1, device=device), group=sub)
    dist.barrier()
    print(f"rank {rank}: subgroup warmup complete; entering fault", flush=True)
    if rank == 0:
        dist.all_reduce(torch.ones(1, device=device), group=sub)  # rank 1 skipped it (node-local flag)
    dist.all_reduce(torch.ones(1, device=device))  # global validation all-reduce


def cross_group_deadlock_cold(backend: str) -> None:
    """subgroup-skip-deadlock as the task has it: the subgroup's first collective is the one rank 1 skips. In a lazily
    initialised NCCL job (the trainer adapted to NCCL, no device_id) rank 0 then waits inside communicator creation,
    not in a collective; the same 30 s timeout as the warm row, so the two rows differ only in warmth."""
    rank, device = setup(backend)
    sub = dist.new_group(ranks=[0, 1], timeout=datetime.timedelta(seconds=TIMEOUT_S))
    print(f"rank {rank}: entering fault with a cold subgroup", flush=True)
    if rank == 0:
        dist.all_reduce(torch.ones(1, device=device), group=sub)
    dist.all_reduce(torch.ones(1, device=device))


def rank_stuck_outside(backend: str) -> None:
    """prefetch-thread-dies: one rank never reaches the collective (blocked waiting for data)."""
    rank, device = setup(backend)
    if rank == 1:
        time.sleep(10 * TIMEOUT_S)  # stands in for queue.get() on a dead producer
    grads_allreduce(device)


def gather_report(out: list[torch.Tensor], lengths: list[int]) -> dict:
    """What an all_gather of unequal slices returned, against what a correct gather would hold: each rank r sent
    `lengths[r]` copies of r + 1 into buffers the receivers sized like their own slice (as the task does) and prefilled
    with NaN. `outputs_valid` needs every buffer to carry the sender's values over the sender's true length;
    `corrupt_elements` counts positions in those prefixes that hold anything else (NaN included)."""
    corrupt, shapes = 0, [list(t.shape) for t in out]
    for r, (buf, length) in enumerate(zip(out, lengths, strict=True)):
        prefix = buf[: min(length, buf.numel())].float()
        corrupt += int((prefix != float(r + 1)).sum().item())  # NaN != anything, so NaN counts as corrupt
        corrupt += max(0, length - buf.numel())  # values the buffer had no room for
    return {"shapes": shapes, "expected_lengths": lengths, "corrupt_elements": corrupt, "outputs_valid": corrupt == 0}


def uneven_all_gather(backend: str) -> None:
    """uneven-val-gather: ranks all-gather tensors of different lengths (uneven validation slices). No assertion: the
    exit status stays the backend's; what the buffers hold is reported on a structured line the driver records."""
    rank, device = setup(backend)
    world = dist.get_world_size()
    lengths = [128 - r for r in range(world)]
    local = torch.full((lengths[rank],), float(rank + 1), device=device)
    out = [torch.full_like(local, float("nan")) for _ in range(world)]
    dist.all_gather(out, local)
    if backend == "nccl":
        torch.cuda.synchronize()
    report = gather_report([t.cpu() for t in out], lengths)
    print(GATHER_MARK + json.dumps({"rank": rank, **report}), flush=True)


def timeout_below_stall(backend: str) -> None:
    """pg-timeout-below-checkpoint: rank 0 spends longer than the collective timeout in a legitimate stall."""
    rank, device = setup(backend)
    grads_allreduce(device)
    if rank == 0:
        time.sleep(TIMEOUT_S * 1.5)  # slow checkpoint commit
    dist.barrier()


def replication_oom(backend: str) -> None:
    """ddp-replication-oom: replicated weights + grads + Adam state exceed device (or cgroup) memory."""
    _rank, device = setup(backend)
    total = torch.cuda.get_device_properties(device).total_memory if backend == "nccl" else 2 * 1024**3
    n = int(total / 4 / 5)  # 5 fp32 copies (weights, grads, bucket, two Adam moments) ~ the whole memory
    params = [torch.zeros(n, device=device, requires_grad=True) for _ in range(2)]
    opt = torch.optim.Adam(params)
    for p in params:
        p.grad = torch.ones_like(p)
    opt.step()
    grads_allreduce(device)


SCENARIOS = {
    f.__name__: f
    for f in (
        healthy_control,
        rank0_only_collective,
        cross_group_deadlock,
        cross_group_deadlock_cold,
        rank_stuck_outside,
        uneven_all_gather,
        timeout_below_stall,
        replication_oom,
    )
}

if __name__ == "__main__":
    SCENARIOS[sys.argv[1]](sys.argv[2])
    if sys.argv[2] == "nccl":
        # NCCL ops are asynchronous; a training loop next blocks on a sync (loss.item()) while the watchdog runs.
        # Tearing the communicator down instead would block in ncclCommDestroy and hide the watchdog.
        torch.cuda.synchronize()
    dist.destroy_process_group()
    os._exit(0)
