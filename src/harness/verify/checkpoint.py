"""Whether the checkpoints a job committed hold the model and optimizer state, run by the verifier as an
unprivileged subprocess:

    python3 -m harness.verify.checkpoint MODEL_JSON LISTING_JSON

LISTING_JSON maps each step to {"metadata": a copy of the step directory's DCP `.metadata`, "files": {name: bytes
allocated}, "dir": a copy of its files (only the checkpoints the verifier kept)} as the verifier saw them when the
step was committed (harness.verify.run.CheckpointWatch). Prints one JSON line, {step: ""} for a well-formed
checkpoint or {step: why not}.

Recoverable (kept checkpoints): every tensor the metadata declares is read from its byte range as the record DCP
wrote with torch.save, without unpickling anything: the record's single raw storage is taken from the zip archive and
viewed as the declared dtype; it must hold at least the chunk's values, all finite. The optimizer's per-parameter
`step` counters must all equal the checkpoint's step, so another step's checkpoint copied into place fails. Zeroed,
truncated or swapped shards fail. The process limits its own address space before reading anything.

Well formed: the metadata names every parameter of the platform model as `model.<name>` and both AdamW moments as
`optim.state.<name>.exp_avg[_sq]`, each in float32 with the parameter's shape and at least its bytes stored, and
every byte range it points at lies within the allocated part of a file of the step directory (so every rank's
shard is there, and is not a sparse placeholder). The metadata is a pickle the job wrote: it is read with an
unpickler that can construct DCP's metadata records and nothing else.
"""

from __future__ import annotations

import io
import json
import pickle
import re
import resource
import sys
import zipfile
from pathlib import Path

import torch
from torch.distributed.checkpoint._nested_dict import set_element  # pyright: ignore[reportPrivateImportUsage]
from torch.distributed.checkpoint.api import CheckpointException
from torch.distributed.checkpoint.default_planner import DefaultLoadPlanner
from torch.distributed.checkpoint.filesystem import FileSystemReader
from torch.distributed.checkpoint.metadata import Metadata, MetadataIndex, TensorStorageMetadata
from torch.distributed.checkpoint.state_dict import get_state_dict, set_state_dict
from torch.distributed.checkpoint.state_dict_loader import load as dcp_load

from ocb.model import GPT, GPTConfig

ALLOWED = {
    *(
        ("torch.distributed.checkpoint.metadata", name)
        for name in (
            "BytesStorageMetadata",
            "ChunkStorageMetadata",
            "Metadata",
            "MetadataIndex",
            "StorageMeta",
            "TensorProperties",
            "TensorStorageMetadata",
            "_MEM_FORMAT_ENCODING",
        )
    ),
    ("torch.distributed.checkpoint.filesystem", "_StorageInfo"),
    ("torch.serialization", "_get_layout"),
    ("torch", "Size"),
    ("pathlib", "PosixPath"),
}


class _MetadataUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if (module, name) in ALLOWED:
            return super().find_class(module, name)
        if module == "torch" and isinstance(getattr(torch, name, None), torch.dtype):
            return getattr(torch, name)
        raise pickle.UnpicklingError(f"{module}.{name} is not part of checkpoint metadata")


def read_metadata(data: bytes) -> Metadata:
    md = _MetadataUnpickler(io.BytesIO(data)).load()
    if not isinstance(md, Metadata):
        raise pickle.UnpicklingError(f"the metadata is a {type(md).__name__}")
    return md


def problem(md: Metadata, files: dict[str, int], params: dict[str, tuple[int, ...]]) -> str:
    """Why the checkpoint does not hold the model and optimizer state, or ""."""
    limit = 16 * (4 * len(params) + 64)  # every tensor and step counter, chunked across up to 16 ranks
    if len(md.storage_data) > limit or len(md.state_dict_metadata) > limit:
        return f"the metadata lists {len(md.storage_data)} items, more than the model's state can have"
    stored: dict[str, int] = {}
    for index, info in md.storage_data.items():
        size = files.get(info.relative_path)
        if size is None:
            return f"{info.relative_path} (holding {index.fqn}) is not in the checkpoint"
        if info.offset < 0 or info.length < 0 or info.offset + info.length > size:
            return f"{info.relative_path} is shorter than the {index.fqn} data it should hold"
        stored[index.fqn] = stored.get(index.fqn, 0) + info.length
    for name, shape in params.items():
        for key in (f"model.{name}", f"optim.state.{name}.exp_avg", f"optim.state.{name}.exp_avg_sq"):
            entry = md.state_dict_metadata.get(key)
            if not isinstance(entry, TensorStorageMetadata):
                return f"{key} is missing"
            if tuple(entry.size) != shape:
                return f"{key} has shape {tuple(entry.size)}, the model's is {shape}"
            if entry.properties.dtype != torch.float32:  # the platform trains in fp32: a cast copy is not the state
                return f"{key} is stored as {entry.properties.dtype}, not torch.float32"
            need = entry.size.numel() * 4
            if stored.get(key, 0) < need:
                return f"{key}: {stored.get(key, 0)} bytes stored, {need} needed"
        if not isinstance(md.state_dict_metadata.get(f"optim.state.{name}.step"), TensorStorageMetadata):
            return f"optim.state.{name}.step is missing"  # AdamW's step counter: which step the state belongs to
    return ""


ADDRESS_SPACE = 4 << 30  # this process's own limit: decoding job-written bytes never exhausts the verifier


def _tensor(raw: bytes, dtype: torch.dtype) -> torch.Tensor:
    """A tensor record DCP wrote with torch.save, read without unpickling: the zip archive's one raw storage."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        data = [i for i in z.infolist() if re.fullmatch(r"[^/]+/data/\d+", i.filename)]
        if len(data) != 1:
            raise ValueError(f"{len(data)} storages in one tensor record")
        if data[0].compress_type != zipfile.ZIP_STORED or data[0].file_size > len(raw):
            raise ValueError("the storage is compressed (torch.save stores it raw)")
        buf = z.read(data[0])
    if len(buf) % torch.empty((), dtype=dtype).element_size():
        raise ValueError("storage size is not a whole number of values")
    return torch.frombuffer(bytearray(buf), dtype=dtype) if buf else torch.empty(0, dtype=dtype)


def content_problem(md: Metadata, directory: Path, step: int) -> str:
    """Why a kept checkpoint's tensors cannot be recovered, or "" (see the module docstring)."""
    counters: set[float] = set()
    model_nonzero = False
    for index, info in md.storage_data.items():
        entry = md.state_dict_metadata.get(index.fqn)
        if not isinstance(entry, TensorStorageMetadata):  # bytes items (param groups) are never read
            continue
        path = directory / info.relative_path
        try:
            with path.open("rb") as f:
                f.seek(info.offset)
                raw = f.read(info.length)
            values = _tensor(raw, entry.properties.dtype)
        except Exception as exc:  # noqa: BLE001 -- whatever does not decode is the checkpoint's fault
            return f"{index.fqn}: its data does not decode ({type(exc).__name__}: {str(exc)[:80]})"
        chunk = next((c for c in entry.chunks if tuple(c.offsets) == tuple(index.offset or ())), entry.chunks[0])
        need = 1
        for n in chunk.sizes:
            need *= n
        if values.numel() < need:
            return f"{index.fqn}: {values.numel()} values stored, {need} declared"
        if values.is_floating_point() and not bool(torch.isfinite(values).all()):
            return f"{index.fqn}: non-finite values"
        if index.fqn.endswith(".exp_avg_sq") and bool((values < 0).any()):
            return f"{index.fqn}: negative second moments"
        if index.fqn.startswith("model.") and bool(values.any()):
            model_nonzero = True
        if index.fqn.startswith("optim.state.") and index.fqn.endswith(".step") and values.numel() >= 1:
            counters.add(float(values[0]))
    if not model_nonzero:
        return "the model's weights are all zero"
    if counters != {float(step)}:
        return f"optimizer step counters {sorted(counters)[:3]} do not match step {step}"
    return ""


def geometry_problem(md: Metadata, params: dict[str, tuple[int, ...]]) -> str:
    """Why the chunks declared for each required tensor cannot restore it: a chunk with the wrong rank or outside the
    tensor, two chunks that overlap, chunks that leave part of the tensor unwritten, a chunk whose shard location is
    missing or not a plain file name, or a payload far larger than the tensor it holds. DCP's loader enforces none
    of this (an overlap is written twice, a gap stays zero), so a decode that looks fine can still be no checkpoint."""
    for name in params:
        for key in (f"model.{name}", f"optim.state.{name}.exp_avg", f"optim.state.{name}.exp_avg_sq"):
            entry = md.state_dict_metadata.get(key)
            if not isinstance(entry, TensorStorageMetadata):
                return f"{key}: not a tensor"
            boxes: list[tuple[tuple[int, int], ...]] = []
            elements = 0
            for chunk in entry.chunks:
                offsets, sizes = tuple(chunk.offsets), tuple(chunk.sizes)
                if len(offsets) != len(entry.size) or len(sizes) != len(entry.size):
                    return f"{key}: a chunk of the wrong rank"
                if any(o < 0 or n <= 0 or o + n > lim for o, n, lim in zip(offsets, sizes, entry.size, strict=True)):
                    return f"{key}: a chunk outside the tensor"
                box = tuple((o, o + n) for o, n in zip(offsets, sizes, strict=True))
                if any(all(a < d and c < b for (a, b), (c, d) in zip(box, prev, strict=True)) for prev in boxes):
                    return f"{key}: overlapping chunks"
                boxes.append(box)
                info = md.storage_data.get(MetadataIndex(key, chunk.offsets))
                if info is None or Path(info.relative_path).name != info.relative_path:
                    return f"{key}: a chunk without a shard, or a shard outside the checkpoint directory"
                if info.length > chunk.sizes.numel() * entry.properties.dtype.itemsize + (1 << 20):
                    return f"{key}: a payload far larger than its tensor"
                elements += chunk.sizes.numel()
            if elements != entry.size.numel():
                return f"{key}: the chunks do not cover the tensor"
    return ""


def restore(md: Metadata, directory: Path, model_cfg: dict) -> None:
    """Restore the model and its AdamW state from the checkpoint the way the trainer would (DCP), so a checkpoint
    counts only if it loads: with the metadata already read by the restricted unpickler, and every byte payload
    (optimizer scalars and param groups) loaded with weights_only, which DCP's default planner does not do. Raises
    on anything that does not restore."""

    class CheckedReader(FileSystemReader):
        def read_metadata(self) -> Metadata:
            return md

    class CheckedPlanner(DefaultLoadPlanner):
        def load_bytes(self, read_item, value) -> None:  # DCP's signature
            loaded = torch.load(value, weights_only=True)
            if self.flatten_state_dict:
                set_element(self.original_state_dict, self.mappings[read_item.dest_index.fqn], loaded)
            else:
                self.state_dict[read_item.dest_index.fqn] = loaded

    model = GPT(GPTConfig(**model_cfg))
    optimizer = torch.optim.AdamW(model.parameters())
    model_sd, optim_sd = get_state_dict(model, optimizer)
    state = {"model": model_sd, "optim": optim_sd}
    dcp_load(state, storage_reader=CheckedReader(str(directory)), planner=CheckedPlanner())
    set_state_dict(model, optimizer, model_state_dict=state["model"], optim_state_dict=state["optim"])


def main(model_json: str, listing_json: str) -> None:
    resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_SPACE, ADDRESS_SPACE))
    torch.set_num_threads(1)
    with torch.device("meta"):
        model = GPT(GPTConfig(**json.loads(model_json)))
    params = {name: tuple(p.shape) for name, p in model.named_parameters()}
    out: dict[str, str] = {}
    for step, entry in json.loads(Path(listing_json).read_text()).items():
        try:
            md = read_metadata(Path(entry["metadata"]).read_bytes())
            out[step] = problem(md, entry["files"], params)
            if not out[step]:
                out[step] = geometry_problem(md, params)
            if not out[step] and entry.get("dir"):
                out[step] = content_problem(md, Path(entry["dir"]), int(step))
            if not out[step] and entry.get("dir"):  # the restore test: the trainer's own load path, hardened
                restore(md, Path(entry["dir"]), json.loads(model_json))
        except (Exception, CheckpointException) as exc:  # noqa: BLE001 -- what does not restore is the checkpoint's fault
            out[step] = f"checkpoint unreadable: {type(exc).__name__}: {str(exc)[:200]}"
    print(json.dumps(out))


if __name__ == "__main__":
    main(*sys.argv[1:3])
