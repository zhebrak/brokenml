"""The training corpus: sequences materialised from a dataset definition (harness.teacher).

Jobs read /shared/data/corpus.safetensors (`train` and `val`, int64, ctx + 1 tokens per sequence); the generator
itself stays with the harness. The agent's cluster also gets /shared/data/heldout.safetensors for `ocb score`; the
verifier keeps its held-out data private, so the corpus file itself is the same in both clusters.

Dataset properties a task can set (harness.config.Data), the same in the agent's and the verifier's cluster:
- `shards`: the corpus lives only in the object store's dataset volume, as `train-NNNNN.safetensors` objects plus
  `val.safetensors` and `index.json` (DATASETS/corpus/).
- `remap`: `rows` train sequences, in `blocks` runs of consecutive rows at independent random positions, went through
  a fixed permutation of the token ids (shards written with another tokenizer's ids); validation and held-out data
  are clean.
- `train_rows`: the corpus holds this many train sequences (the data team's full set; the job uses the first
  train_seqs).
- `val_rows`: the corpus holds this many validation sequences (the job slices the first val_seqs of them).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import torch
from safetensors.torch import save_file

from harness import config
from harness.config import Data
from harness.teacher import Teacher

DATASETS = Path(config.DATASETS)  # mounted by provisioning (or the verifier) and the store only
REMAP_SEED = 20240917  # the other tokenizer's id order: fixed, so the permutation is the same in every draw


def remapped(train: torch.Tensor, rows: int, vocab: int, blocks: int = 1, seed: int | None = None) -> torch.Tensor:
    """`rows` sequences in `blocks` equal runs of consecutive rows at independent random positions (not overlapping),
    with every token id permuted (no id maps to itself). `seed` fixes the positions (the verifier records it, so a
    replay re-grades the same corpus); without it they are drawn fresh."""
    g = torch.Generator().manual_seed(REMAP_SEED)
    perm = torch.randperm(vocab, generator=g)
    while bool((perm == torch.arange(vocab)).any()):
        perm = torch.randperm(vocab, generator=g)
    size = rows // blocks
    free = len(train) - size * blocks  # rows outside the blocks, distributed at random between them
    rng = torch.Generator().manual_seed(int.from_bytes(os.urandom(4), "little") if seed is None else seed)
    cuts = torch.randint(0, free + 1, (blocks,), generator=rng).sort().values.tolist()
    out = train.clone()
    for i, cut in enumerate(cuts):
        start = cut + i * size
        out[start : start + size] = perm[train[start : start + size]]
    return out


def shard_manifest(rows: int, world: int, mode: str) -> torch.Tensor:
    """One [start, end) row range per rank over the first `rows` train sequences: `disjoint` (consecutive quarters, as
    the data pipeline documents) or `identical` (rank 0's range repeated: the pipeline bug same-shard reproduces)."""
    n = rows // world
    if mode == "identical":
        return torch.tensor([[0, n]] * world, dtype=torch.int64)
    return torch.tensor([[i * n, (i + 1) * n] for i in range(world)], dtype=torch.int64)


def _save(tensors: dict[str, torch.Tensor], path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    save_file({k: v.contiguous() for k, v in tensors.items()}, str(tmp))
    os.replace(tmp, path)
    path.chmod(0o644)


def write(
    teacher: Teacher,
    path: str | Path,
    train: int,
    val: int,
    length: int,
    heldout: int = 0,
    data: Data | None = None,
    data_seed: int | None = None,
    world: int = 4,
) -> Path:
    """The corpus at `path` (one file), or, for a sharded dataset, under DATASETS/corpus/ with the held-out split
    (if any) at `path`'s directory / heldout.safetensors. Returns where the job reads it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    job_rows = train  # the rows the job trains on (train_seqs); a manifest's ranges cover these
    if data and data.train_rows:
        train = max(train, data.train_rows)
    if data and data.val_rows:
        val = data.val_rows
    splits = {
        "train": teacher.sample(train, length, seed=teacher.seed + 1),
        "val": teacher.sample(val, length, seed=teacher.seed + 2),
    }
    if data and data.shard_manifest:
        splits["shards"] = shard_manifest(job_rows, world, data.shard_manifest)
    if data and data.remap:
        splits["train"] = remapped(splits["train"], data.remap.rows, teacher.vocab, data.remap.blocks, seed=data_seed)
    held = teacher.sample(heldout, length, seed=int.from_bytes(os.urandom(4), "little")) if heldout else None
    if held is not None:  # the agent's held-out split for `ocb score`: its own file, so the corpus has the same splits
        _save({"heldout": held}, path.parent / "heldout.safetensors")  # in both clusters (the verifier keeps its own)
    if not (data and data.shards):
        _save(splits, path)
        return path
    root = DATASETS / "corpus"
    root.mkdir(parents=True, exist_ok=True)
    names = []
    for i, part in enumerate(torch.tensor_split(splits["train"], data.shards)):
        names.append(f"train-{i:05d}.safetensors")
        _save({"train": part}, root / names[-1])
    _save({"val": splits["val"]}, root / "val.safetensors")
    (root / "index.json").write_text(json.dumps({"train": names, "val": "val.safetensors", "sequences": train}))
    return root
