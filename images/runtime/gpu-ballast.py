#!/usr/bin/env python3
"""Site GPU memory policy: each GPU of this node offers jobs a fixed budget (/etc/platform/gpu-budget.conf,
budget_gb=...). This service holds the rest of every visible GPU's memory for the node's lifetime, so jobs see the
same usable memory on any GPU model. Started by the node's init as the site account; restarted if it exits.
"""

from __future__ import annotations

import signal
import time
from pathlib import Path

import torch

CONF = Path("/etc/platform/gpu-budget.conf")
READY = Path("/run/gpu-ballast.ready")  # written once the memory is held (the node's health check waits for it)


def main() -> None:
    settings = dict(line.split("=", 1) for line in CONF.read_text().split() if "=" in line) if CONF.exists() else {}
    budget = int(float(settings.get("budget_gb", "0")) * 2**30)
    held = []
    if budget and torch.cuda.is_available():  # without GPUs or a budget there is nothing to hold, but stay up (one pid)
        for i in range(torch.cuda.device_count()):
            free, _total = torch.cuda.mem_get_info(i)
            extra = free - budget
            if extra > 0:
                held.append(torch.empty(extra, dtype=torch.uint8, device=f"cuda:{i}"))
        torch.cuda.synchronize()
        READY.write_text(" ".join(str(t.numel()) for t in held) + "\n")
    signal.signal(signal.SIGTERM, lambda *_: exit(0))
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
