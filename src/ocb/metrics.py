"""Per-rank training metrics as JSON lines under /shared/metrics/<job id>/rank<r>.jsonl."""

from __future__ import annotations

import json
import os
import resource
import socket
import time
from pathlib import Path

ROOT = Path(os.environ.get("OCB_METRICS_ROOT", "/shared/metrics"))


class Metrics:
    def __init__(self, rank: int, job_id: str | None = None):
        job_id = job_id or os.environ.get("SLURM_JOB_ID", "local")
        self.path = ROOT / job_id / f"rank{rank}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.base = {"rank": rank, "host": socket.gethostname()}
        self._f = open(self.path, "a", buffering=1)  # noqa: SIM115 -- held for the process lifetime, line-buffered

    def log(self, **values) -> None:
        rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        self._f.write(
            json.dumps({"t": round(time.time(), 3), **self.base, "rss_mb": round(rss_mb, 1), **values}) + "\n"
        )
