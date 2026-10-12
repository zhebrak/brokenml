"""Debug hooks every training rank installs before init_process_group.

- SIGUSR1: faulthandler writes all Python thread stacks to stderr (works while blocked in C++).
- Flight Recorder: recording is enabled through TORCH_FR_BUFFER_SIZE. Gloo has no watchdog that
  dumps on timeout, so a daemon thread watches for /shared/evidence/fr/TRIGGER and writes this
  rank's trace to /shared/evidence/fr/<host>-rank<r>.json. A thread is used because Python signal
  handlers do not run while the main thread is blocked inside a collective. On NCCL the watchdog
  also dumps by itself when a collective times out, to /shared/evidence/fr/<host>-nccl-rank<r>.
"""

from __future__ import annotations

import faulthandler
import os
import signal
import socket
import threading
import time
from pathlib import Path

FR_DIR = Path(os.environ.get("OCB_FR_DIR", "/shared/evidence/fr"))


def install() -> None:
    os.environ.setdefault("TORCH_FR_BUFFER_SIZE", "2000")
    os.environ.setdefault("TORCH_NCCL_DUMP_ON_TIMEOUT", "1")  # NCCL's watchdog: dump every rank's trace on timeout
    os.environ.setdefault("TORCH_NCCL_DEBUG_INFO_TEMP_FILE", str(FR_DIR / f"{socket.gethostname()}-nccl-rank"))
    faulthandler.register(signal.SIGUSR1, all_threads=True)
    threading.Thread(target=_watch, daemon=True, name="ocb-frdump").start()


def _watch() -> None:
    trigger = FR_DIR / "TRIGGER"
    seen = 0.0
    while True:
        time.sleep(1.0)
        try:
            mtime = trigger.stat().st_mtime
        except FileNotFoundError:
            continue
        if mtime > seen:
            seen = mtime
            _dump()


def _dump() -> None:
    import torch._C._distributed_c10d as c10d
    import torch.distributed as dist

    rank = os.environ.get("RANK", "x")
    try:
        # ProcessGroupNCCL keeps its own recorder; the generic one holds only backends without native support (Gloo).
        nccl = dist.is_initialized() and dist.get_backend() == "nccl"
        dump = getattr(c10d, "_dump_nccl_trace_json", None) if nccl else None
        trace = (dump or c10d._dump_fr_trace_json)(includeCollectives=True, onlyActive=False)
    except Exception as exc:  # noqa: BLE001 -- a dump hook must never raise: recording off, no process group yet
        trace = f'{{"error": "{type(exc).__name__}: {exc}"}}'.encode()
    out = FR_DIR / f"{socket.gethostname()}-rank{rank}.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(trace)
    os.replace(tmp, out)
