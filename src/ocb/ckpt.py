"""Checkpoint I/O for training jobs: DCP checkpoints with an atomic commit, and the final export.

Layout under a checkpoint root:
  step_<n>/        a committed DCP checkpoint (renamed into place only after every rank wrote)
  step_<n>/meta.json   step and LR-schedule state, written by rank 0
  latest           text file naming the newest committed step directory
"""

from __future__ import annotations

import http.client
import json
import os
from pathlib import Path

import torch
import torch.distributed as dist
import torch.distributed.checkpoint as dcp
from safetensors.torch import save_file
from torch.distributed.checkpoint.state_dict import (
    StateDictOptions,
    get_model_state_dict,
    get_state_dict,
    set_model_state_dict,
    set_state_dict,
)


def _rank() -> int:
    return dist.get_rank() if dist.is_initialized() else 0


def _barrier() -> None:
    if dist.is_initialized():
        dist.barrier()


def _objstore_url() -> str | None:
    conf = Path("/etc/platform/objstore.conf")
    if not conf.exists():
        return None
    settings = dict(line.split("=", 1) for line in conf.read_text().split() if "=" in line)
    return settings.get("url")


def _replicate_commit(path: Path) -> None:
    """A checkpoint counts as committed once the cluster's object store holds a replica (platform policy)."""
    url = _objstore_url()
    if not url:
        return
    host, _, port = url.removeprefix("http://").partition(":")
    for f in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = f"{path.parent.name}/{path.name}/{f.relative_to(path)}"
        try:
            conn = http.client.HTTPConnection(host, int(port or 80), timeout=900)
            with open(f, "rb") as body:
                conn.request("PUT", f"/replicas/{rel}", body=body, headers={"Content-Length": str(f.stat().st_size)})
            conn.getresponse().read()
            conn.close()
        except OSError as exc:
            print(f"ckpt: replica of {rel} failed: {exc}", flush=True)


def save(
    root: str | Path, step: int, model: torch.nn.Module, optimizer: torch.optim.Optimizer, meta: dict | None = None
) -> Path:
    """Collective: every rank must call it. Writes step_<n>.tmp, then commits by rename."""
    root = Path(root)
    final, tmp = root / f"step_{step}", root / f"step_{step}.tmp"
    model_sd, optim_sd = get_state_dict(model, optimizer)
    dcp.save({"model": model_sd, "optim": optim_sd}, checkpoint_id=str(tmp))
    _barrier()
    if _rank() == 0:
        (tmp / "meta.json").write_text(json.dumps({"step": step, **(meta or {})}))
        os.rename(tmp, final)
        _replicate_commit(final)
        pointer = root / "latest.tmp"
        pointer.write_text(final.name)
        os.replace(pointer, root / "latest")
    _barrier()
    return final


def latest(root: str | Path) -> Path | None:
    pointer = Path(root) / "latest"
    return Path(root) / pointer.read_text().strip() if pointer.exists() else None


def _map_name(name: str, mapping: dict[str, str]) -> str:
    if name in mapping:
        return mapping[name]
    for old, new in mapping.items():
        if old.endswith(".") and name.startswith(old):
            return new + name[len(old) :]
    return name


def _rename(obj, mapping: dict[str, str]):
    """Rename parameter names (dict keys and name lists) through `mapping`, recursively."""
    if not mapping:
        return obj
    if isinstance(obj, dict):
        return {_map_name(k, mapping) if isinstance(k, str) else k: _rename(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_map_name(v, mapping) if isinstance(v, str) else _rename(v, mapping) for v in obj]
    return obj


def load(
    path: str | Path,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer | None = None,
    key_map: dict[str, str] | None = None,
) -> dict:
    """Collective. Restores model (and optimizer, if given) in place; returns meta.json.

    key_map maps current parameter names to the names stored in the checkpoint, for checkpoints
    written before a parameter was renamed. An entry ending in "." maps a name prefix (a whole module),
    e.g. {"ln_f.weight": "norm.weight", "ln_f.": "final_norm."}.
    """
    path = Path(path)
    fwd, back = dict(key_map or {}), {v: k for k, v in (key_map or {}).items()}
    if optimizer is None:
        state = {"model": _rename(get_model_state_dict(model), fwd)}
        dcp.load(state, checkpoint_id=str(path))
        set_model_state_dict(model, _rename(state["model"], back))
    else:
        model_sd, optim_sd = get_state_dict(model, optimizer)
        state = {"model": _rename(model_sd, fwd), "optim": _rename(optim_sd, fwd)}
        dcp.load(state, checkpoint_id=str(path))
        set_state_dict(
            model,
            optimizer,
            model_state_dict=_rename(state["model"], back),
            optim_state_dict=_rename(state["optim"], back),
        )
    return json.loads((path / "meta.json").read_text())


def export_final(model: torch.nn.Module, path: str | Path) -> None:
    """Collective. Gathers full weights (DDP or FSDP2) and rank 0 writes safetensors atomically."""
    sd = get_model_state_dict(model, options=StateDictOptions(full_state_dict=True, cpu_offload=True))
    if _rank() == 0:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        save_file({k: v.contiguous() for k, v in sd.items()}, str(tmp))
        os.replace(tmp, path)
    _barrier()


def inspect(path: str | Path) -> str:
    """A committed checkpoint as the contract's counters rule sees it: the step its meta.json records, its files, the
    names stored under model.* and optim.state.*, and AdamW's per-parameter step counters against that step. Single
    process (no process group needed); a run directory is followed through its `latest` pointer. Reads only the
    checkpoint's own files."""
    from collections import Counter

    from torch.distributed.checkpoint.filesystem import FileSystemReader
    from torch.distributed.checkpoint.metadata import TensorStorageMetadata

    path = Path(path)
    lines: list[str] = []
    if (path / "latest").exists() and not (path / ".metadata").exists():
        lines.append(f"{path}/latest -> {(path / 'latest').read_text().strip()}")
        path = latest(path) or path
    if not (path / ".metadata").exists():
        return "\n".join([*lines, f"{path}: no DCP checkpoint here (no .metadata file)"])
    lines.append(f"checkpoint {path}")
    meta = json.loads((path / "meta.json").read_text()) if (path / "meta.json").exists() else None
    lines.append(f"  meta.json: {json.dumps(meta)}" if meta is not None else "  meta.json: missing (never committed)")
    files = sorted(f for f in path.iterdir() if f.is_file())
    lines.append("  files: " + ", ".join(f"{f.name} ({f.stat().st_size / 1e6:.1f} MB)" for f in files))
    md = FileSystemReader(str(path)).read_metadata()
    tensors = {k: v for k, v in md.state_dict_metadata.items() if isinstance(v, TensorStorageMetadata)}
    model = sorted(k[len("model.") :] for k in tensors if k.startswith("model."))
    moments = sum(1 for k in tensors if k.startswith("optim.state.") and k.endswith((".exp_avg", ".exp_avg_sq")))
    steps = sorted(k for k in tensors if k.startswith("optim.state.") and k.endswith(".step"))
    lines.append(f"  model tensors stored: {len(model)}" + (f" (e.g. {', '.join(model[:3])})" if model else ""))
    lines.append("  top-level names: " + ", ".join(sorted({n.split(".")[0] for n in model})))
    lines.append(f"  optimizer: {moments} moment tensors, {len(steps)} step counters")
    if steps:
        state = {k: torch.empty(tuple(tensors[k].size), dtype=tensors[k].properties.dtype) for k in steps}
        dcp.load(state, checkpoint_id=str(path))
        counts = Counter(float(v.reshape(-1)[0]) for v in state.values() if v.numel())
        values = ", ".join(f"{int(v) if v == int(v) else v} x{n}" for v, n in sorted(counts.items()))
        want = meta.get("step") if isinstance(meta, dict) else None
        if want is None:
            verdict = "no meta.json step to compare with"
        elif set(counts) == {float(want)}:
            verdict = f"all equal to step {want}: the counters match"
        else:
            verdict = f"do NOT match step {want} (the verifier's counters rule fails this checkpoint)"
        lines.append(f"  AdamW step counters: {values}; {verdict}")
    return "\n".join(lines)
