"""Where tensors live and how matmuls run: CPU (Gloo) or one GPU per rank (NCCL); fp32, tf32 (fp32 with TensorFloat-32
matmuls) or bf16 autocast (with TF32 for what stays in fp32)."""
from __future__ import annotations

import contextlib
import os

import torch

_device = torch.device("cpu")
_precision = "fp32"


def setup(cfg: dict) -> torch.device:
    """Called once per rank before the process group is created."""
    global _device, _precision
    _precision = cfg["precision"]
    if cfg["device"] == "cuda":
        local = int(os.environ.get("LOCAL_RANK", "0"))
        torch.cuda.set_device(local)
        _device = torch.device("cuda", local)
        if _precision in ("tf32", "bf16"):  # fp32 matmuls on tensor cores (bf16: what autocast keeps in fp32)
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
    return _device


def get() -> torch.device:
    return _device


def backend() -> str:
    return "nccl" if _device.type == "cuda" else "gloo"


def put(t: torch.Tensor) -> torch.Tensor:
    return t.to(_device, non_blocking=True) if _device.type == "cuda" else t


def autocast():
    if _precision == "bf16":
        return torch.autocast(device_type=_device.type, dtype=torch.bfloat16)
    return contextlib.nullcontext()
