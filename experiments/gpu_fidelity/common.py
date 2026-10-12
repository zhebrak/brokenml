"""Run directories, provenance, device ownership and subprocess cleanup for the GPU fidelity experiments.

Provenance builds on bench.provenance.stamp, device locks follow the shared pod's convention (blocking
/tmp/gpu<N>.lock per physical index) besides the per-UUID guard, a failed launcher's peers get a grace period so their
watchdog and Flight Recorder dumps land, and rows never carry a non-finite number.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

GRACE_S = 45.0  # after one launcher fails, how long its peers may keep running to write their dumps
# NCCL settings the rented containers needed (NVLS multicast cannot bind there); applied unless the caller set them,
# and recorded in every manifest, so a run never silently differs from the archived table.
NCCL_DEFAULTS = {"NCCL_NVLS_ENABLE": "0", "NCCL_DEBUG": "WARN"}


def digest_tree(path: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(path.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
            h.update(f.relative_to(path).as_posix().encode() + b"\0" + f.read_bytes())
    return h.hexdigest()


def run_dir(parent: Path, label: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"{label}-", dir=parent.resolve()))


def command(*args: str) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, check=False, timeout=20)
        return p.stdout.strip() if p.returncode == 0 else f"unavailable: {p.stderr.strip()}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"


def nccl_env(env: dict[str, str]) -> dict[str, str]:
    """`env` with NCCL_DEFAULTS filled in where the caller set nothing."""
    return {**NCCL_DEFAULTS, **env}


def provenance(backend: str) -> dict:
    """What a run ran on: the repository stamp every other record carries (commit, dirty tree, host, CPU, time) plus
    the GPU side (torch, CUDA, NCCL, driver inventory, topology) and the hashes of the experiment and platform code."""
    import torch

    from bench.provenance import stamp

    nccl = torch.cuda.nccl.version() if torch.cuda.is_available() else None
    return {
        **stamp(),
        "python": sys.version,
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "nccl": nccl,
        "backend": backend,
        "adapter_sha256": digest_tree(HERE),
        "platform_sha256": digest_tree(ROOT / "src" / "ocb"),
        "harness_sha256": digest_tree(ROOT / "src" / "harness"),
        "gpu_inventory": command(
            "nvidia-smi", "--query-gpu=index,uuid,name,memory.total,driver_version", "--format=csv"
        ),
        "topology": command("nvidia-smi", "topo", "-m"),
        "environment": {
            k: v
            for k, v in os.environ.items()
            if k.startswith(("NCCL_", "TORCH_NCCL_", "TORCH_FR_"))
            or k in ("CUDA_VISIBLE_DEVICES", "OMP_NUM_THREADS", "PYTHONHASHSEED")
        },
    }


def visible_devices(count: int) -> tuple[list[str], list[str]]:
    """The first `count` entries of the inherited CUDA_VISIBLE_DEVICES mask (never overridden: on a shared pod the mask
    is the allocation) and the UUIDs behind them."""
    import torch

    available = torch.cuda.device_count()
    if available < count:
        raise ValueError(f"need {count} visible GPUs, found {available}; CUDA_VISIBLE_DEVICES is preserved")
    mask = os.environ.get("CUDA_VISIBLE_DEVICES")
    tokens = mask.split(",") if mask is not None else [str(i) for i in range(available)]
    selected = [t.strip() for t in tokens[:count]]
    if len(selected) != count or len(set(selected)) != count or not all(selected):
        raise ValueError("invalid or duplicate CUDA_VISIBLE_DEVICES entries")
    uuids = [str(torch.cuda.get_device_properties(i).uuid) for i in range(count)]
    return selected, uuids


@contextmanager
def devices(backend: str, count: int):
    """Hold the GPUs for one run. Two locks per device: the shared pod's convention, `/tmp/gpu<index>.lock` taken
    blocking (the other users of the pod queue on the same files, so runs wait instead of colliding), and a
    non-blocking per-UUID lock that refuses a second runner of ours on the same card whatever mask it uses."""
    selected, uuids = visible_devices(count) if backend == "nccl" else ([], [])
    with ExitStack() as stack:
        # Lock in physical order, regardless of the caller's CUDA mapping. Reversed masks must not deadlock.
        for token in sorted(selected, key=lambda t: (not t.isdigit(), int(t) if t.isdigit() else t)):
            if token.isdigit():
                f = stack.enter_context(open(Path(tempfile.gettempdir()) / f"gpu{token}.lock", "a"))
                fcntl.flock(f, fcntl.LOCK_EX)
        for uuid in sorted(uuids):
            f = stack.enter_context(open(Path(tempfile.gettempdir()) / f"bench-gpu-{uuid}.lock", "a"))
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield selected, uuids


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def process_identity(pid: int) -> str | None:
    """The process's start time from /proc, so a recorded PID is never killed after the kernel reused it."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def kill_tree(pid: int, identity: str | None) -> None:
    """Stop the process before walking its children (no forking while we look), then kill them and it."""
    if identity is None or process_identity(pid) != identity:
        return
    try:
        os.kill(pid, signal.SIGSTOP)
        children = command("ps", "-o", "pid=", "--ppid", str(pid))
        for child in children.split():
            if child.isdigit():
                kill_tree(int(child), process_identity(int(child)))
        if process_identity(pid) == identity:
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def execute(commands: list[tuple[list[str], dict, Path]], limit: float) -> tuple[list[int], bool, float]:
    """Run the launchers together. Ends when all exit, at `limit`, or GRACE_S after the first failure (its peers can
    only time out, but their watchdog and Flight Recorder dumps are the evidence, so they get that long to write
    them). Returns (exit codes, whether the limit ended it, elapsed seconds)."""
    procs, logs = [], []
    started, timed_out, first_failure = time.monotonic(), False, None
    try:
        for argv, env, path in commands:
            log = path.open("w")
            logs.append(log)
            p = subprocess.Popen(argv, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            procs.append((p, process_identity(p.pid)))
        while any(p.poll() is None for p, _ in procs):
            now = time.monotonic()
            if now - started >= limit:
                timed_out = True
                break
            if first_failure is None and any(p.poll() not in (None, 0) for p, _ in procs):
                first_failure = now
            if first_failure is not None and now - first_failure >= GRACE_S:
                break
            time.sleep(0.2)
    finally:
        for p, identity in procs:
            if p.poll() is None:
                kill_tree(p.pid, identity)
            p.wait()
        for log in logs:
            log.close()
    return [p.returncode for p, _ in procs], timed_out, time.monotonic() - started


def finite(value):
    """`value` with every non-finite float replaced by None, recursively: a NaN loss is a finding, not a crash."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [finite(v) for v in value]
    return value


def append_row(path: Path, row: dict) -> None:
    """One JSON line per run, written under a lock and fsynced, so a killed driver loses nothing already measured."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(finite(row), allow_nan=False)
    with path.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(text + "\n")
        f.flush()
        os.fsync(f.fileno())
    print(text, flush=True)
