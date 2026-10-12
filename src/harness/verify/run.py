"""How the verifier runs a job: which configuration, as which user, and what is cleaned up between runs.

Agent code runs in the verifier only through the job's submit.sh and the Slurm jobs it creates, as `svc-train`.
Nothing about the reference may be reachable from there:
  - /tests (reference fix, pristine tree, verifier config, the verifier's store) is root-only;
  - the reference configuration runs as a different account (`svc-ci`), and slurm.conf's PrivateData hides one
    account's jobs and scripts from the other; the job-completion log is emptied and made private between runs;
  - after each run every process of its account is killed, here and on every node, its node-local files are
    removed, and the shared run directories are recreated;
  - the export and metrics of the agent's run are copied to a root-only snapshot as soon as its jobs end, and every
    check reads the snapshot.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import stat
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path

from harness.cluster import apply_site
from harness.config import VerifyConfig
from harness.verify import gpus
from harness.verify.rules import LOAD_SHIFT, load_shift, parse_metrics  # noqa: F401 -- re-exported for callers
from ocb import cli, slurm

OPS = Path("/ops")
TESTS = Path("/tests")
SHARED = Path("/shared")
EXPORT = SHARED / "out" / "model.safetensors"
EVAL_EXPORTS = SHARED / "out" / "eval"  # step_<N>.safetensors: weights for the eval team (require_eval_exports_every)
JOBCOMP = SHARED / "slurm" / "jobcomp.log"
SNAPSHOT = Path("/var/lib/verify/snapshot")
RUN_DIRS = ("out", "metrics", "ckpt", "logs", "evidence/fr")  # recreated, owned by the run's account, before each run
JOB_USER = slurm.JOB_USER  # the agent's job
REF_USER = "svc-ci"  # the platform's reference configuration
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
OBJSTORE = "http://objstore:8000"
LOGS_KEPT_BYTES = 200_000
METRICS_MAX_BYTES = 50_000_000  # per rank; a 500-step run writes a few hundred kB


def lock_tests() -> None:
    """Make /tests root-only. Only the directory: copies made from it (the reference run's /ops) keep their modes."""
    os.chown(TESTS, 0, 0)
    TESTS.chmod(0o700)


def _readable(tree: Path) -> None:
    for path in [tree, *tree.rglob("*")]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | (0o555 if path.is_dir() else 0o444))


def _replace_tree(dst: Path, src: Path) -> None:
    for child in dst.iterdir():
        shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
    shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True)
    _readable(dst)


@contextmanager
def ops_swapped(src: Path) -> Iterator[None]:
    """Temporarily replace /ops (a volume the nodes read) with another tree."""
    backup = Path(tempfile.mkdtemp(prefix="agent-ops-"))  # 0700, root
    shutil.copytree(OPS, backup, dirs_exist_ok=True, symlinks=True)
    try:
        _replace_tree(OPS, src)
        yield
    finally:
        _replace_tree(OPS, backup)
        shutil.rmtree(backup, ignore_errors=True)


def reset_run_dirs(owner: str) -> None:
    for name in RUN_DIRS:
        path = SHARED / name
        if path.is_mount():  # a volume of its own (e.g. the size-limited checkpoint volume): emptied, not removed
            for child in path.iterdir():
                shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
        else:
            shutil.rmtree(path, ignore_errors=True)
            path.mkdir(parents=True)
        shutil.chown(path, owner, owner)


def seal_jobcomp() -> None:
    """Empty the job-completion log and make it private, so no account reads another run's job records."""
    if JOBCOMP.exists():
        JOBCOMP.write_text("")
        JOBCOMP.chmod(0o600)


def kill_local(user: str, attempts: int = 20) -> bool:
    """Kill every process `user` owns in this container; True once none is left."""
    for _ in range(attempts):
        slurm.run(["runuser", "-u", user, "--", "kill", "-KILL", "-1"])  # one call reaches every process it owns
        if slurm.run(["pgrep", "-u", user]).returncode != 0:
            return True
        time.sleep(0.2)
    return False


def node_build() -> str:
    """The build ID of the image the nodes run (their /opt/ocb/BUILD), which the verifier's own image need not share
    (GPU nodes run runtime-cuda); several IDs are joined, an unreadable node is `unknown`."""
    builds = set()
    for node in slurm.nodes():
        res = slurm.run([*SSH, f"root@{node}", "cat", "/opt/ocb/BUILD"], timeout=30)
        builds.add(res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else "unknown")
    return ",".join(sorted(builds)) or "unknown"


LIVE_STATES = "RSDTtIW"  # not Z or X: a zombie cannot run or write; its parent reaps it


def clean_nodes(user: str) -> tuple[list[str], list[str]]:
    """Kill `user`'s processes on every node until none is left, then remove its node-local files. Returns
    (survivors, unreachable): nodes where processes of the account outlived twenty kills (exit 3: the job's doing,
    like survivors on the verifier), and nodes that did not answer or whose process table could not be read (exit 2:
    the host's). A process left behind would run beside the next timed run and move its ratio."""
    script = (
        f"i=0; while [ $i -lt 20 ]; do pkill -KILL -u {user}; "
        f"pgrep -u {user} --runstates {LIVE_STATES} >/dev/null; st=$?; [ $st -eq 1 ] && break; "
        "[ $st -ne 0 ] && exit 2; i=$((i + 1)); sleep 0.2; done; "
        f"pgrep -u {user} --runstates {LIVE_STATES} >/dev/null; st=$?; [ $st -eq 1 ] || exit $(( st == 0 ? 3 : 2 )); "
        f"for d in /tmp /var/tmp /dev/shm /scratch; do find $d -xdev -user {user} -delete 2>/dev/null; done; "
        f"find /home/{user} -mindepth 1 -delete 2>/dev/null; true"
    )
    survivors, unreachable = [], []
    for node in slurm.nodes():
        try:
            code = slurm.run([*SSH, f"root@{node}", script], timeout=30).returncode
        except slurm.SlurmError:
            code = 2
        if code == 3:
            survivors.append(f"processes of {user} survive on {node}")
        elif code != 0:
            unreachable.append(f"node {node} did not answer or its cleanup could not be verified")
    return survivors, unreachable


GPU_NODE = "g1"


def gpu_state() -> list[gpus.GPU] | None:
    """The GPU node's GPUs as root reads them, or None when the node does not answer."""
    res = slurm.run([*SSH, f"root@{GPU_NODE}", gpus.COMMAND], timeout=30)
    try:
        return gpus.parse(res.stdout) if res.returncode == 0 else None
    except ValueError:
        return None


SITE_ACCOUNT = "metrics"  # runs the site's node services, started by every node's init (images/runtime/entrypoint.sh)


def site_services() -> dict[str, str]:
    """Each node's site service processes (pids), to compare before and after a run: a job that crashes one (e.g. to
    take its port) changes them. A node that does not answer maps to ""."""
    out = {}
    for node in slurm.nodes():
        res = slurm.run([*SSH, f"root@{node}", f"pgrep -u {SITE_ACCOUNT} | sort -n | tr '\\n' ' '"], timeout=30)
        out[node] = res.stdout.strip()
    return out


def stop_account(user: str, seal: Callable[[], None] | None = None) -> tuple[list[str], list[str]]:
    """Cancel the account's jobs and kill its processes everywhere. Returns (survivors, unreachable): processes that
    outlived every kill, and nodes that could not be cleaned. `seal` records what the run left before the shared run
    directories become root's, so nothing the account left behind can change what is read from them."""
    unreachable: list[str] = []
    try:
        if slurm.run(["scancel", "-u", user]).returncode:
            unreachable.append(f"could not cancel {user}'s jobs")
    except slurm.SlurmError as exc:
        unreachable.append(str(exc))
    try:
        survivors = [] if kill_local(user) else [f"processes of {user} survive on the verifier"]
    except slurm.SlurmError as exc:
        survivors = [str(exc)]
    try:
        node_survivors, node_unreachable = clean_nodes(user)
        survivors += node_survivors
        unreachable += node_unreachable
    except slurm.SlurmError as exc:
        unreachable.append(str(exc))
    if seal:
        seal()
    for name in RUN_DIRS:
        try:
            if slurm.run(["chown", "-R", "root:root", str(SHARED / name)]).returncode:
                unreachable.append(f"could not seal {name}")
        except slurm.SlurmError as exc:
            unreachable.append(str(exc))
    return survivors, unreachable


PROTECTED = {"PrivateData": "jobs,usage", "JobCompLoc": "/shared/slurm/jobcomp.log"}


def protected_settings() -> list[str]:
    """Protected settings the running controller does not have (whatever slurm.conf seemed to say)."""
    try:
        config = slurm.query(["scontrol", "show", "config"])
    except slurm.SlurmError as exc:
        return [str(exc)]
    effective = {}
    for line in config.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            effective[key.strip()] = value.strip()
    return [f"{k} = {effective.get(k)!r}, not {v!r}" for k, v in PROTECTED.items() if effective.get(k) != v]


def checkpoint_bytes_max(model_cfg: dict) -> int:
    """An upper bound on one platform checkpoint of `model_cfg`: fp32 weights and both AdamW moments, twice over for
    DCP's per-record overhead, plus 16 MiB; 1 GiB when the config does not say."""
    try:
        d, layers, vocab, ctx = (int(model_cfg[k]) for k in ("d_model", "n_layer", "vocab", "ctx"))
    except (KeyError, TypeError, ValueError):
        return 1 << 30
    params = layers * (12 * d * d + 13 * d) + 2 * vocab * d + ctx * d + 2 * d  # ocb.model.GPT
    return 2 * 3 * 4 * params + (16 << 20)


class CheckpointWatch:
    """Committed checkpoints as the verifier sees them appear during the run (polled as root by Observer), so a
    checkpoint that retention deletes later still counts. A step directory is committed once renamed into place with
    its DCP `.metadata` (ocb.ckpt.save). At first sight the verifier copies the checkpoint (root-only) and records the
    allocated size and sha256 of every file; it then keeps only the newest checkpoint of each cadence window and the
    last one (at most steps / every + 1, so a checkpoint every step stays legal) and forgets the others. Only what it
    kept can count: harness.verify.checkpoint decodes every kept copy after the run, and its hashes are compared with
    the object store's replicas. Each step's copy is bounded by `max_bytes` (checkpoint_bytes_max); a file that is not
    a regular, dense, singly linked file, or does not fit, is not copied, so its step cannot count."""

    METADATA_MAX = 4 << 20  # a platform checkpoint's metadata is tens of KiB
    FILES_MAX = 256  # files per step directory (a platform checkpoint has one per rank, the metadata and meta.json)

    def __init__(
        self, root: Path, every: int | None = None, steps: int | None = None, max_bytes: int = 1 << 30
    ) -> None:
        self.root, self.every, self.steps, self.max_bytes = root, every, steps, max_bytes
        self.store = Path(tempfile.mkdtemp(prefix="ckpt-watch-"))  # root-only (0700)
        self.seen: dict[int, dict[str, int]] = {}  # kept step -> {file name: bytes allocated}
        self.hashes: dict[int, dict[str, str]] = {}  # kept step -> {file name: sha256, "" if not copied}
        self.done: set[int] = set()  # every step looked at, kept or not

    @property
    def kept(self) -> set[int]:
        return set(self.seen)

    def poll(self) -> None:
        if not self.root.is_dir() or self.root.is_symlink():
            return
        for d in islice(self.root.iterdir(), (self.steps or 1024) + 16):
            step, meta = d.name[5:], d / ".metadata"
            if (
                not step.isdecimal()
                or len(step) > len(str(self.steps or 1024))
                or d.name != f"step_{int(step)}"
                or int(step) in self.done
                or d.is_symlink()
                or meta.is_symlink()
            ):
                continue
            if self.steps is not None and not 1 <= int(step) <= self.steps:
                self.done.add(int(step))  # outside the run: can never count, not worth a byte of the verifier's disk
                continue
            copy = self.store / str(int(step))
            try:
                if not meta.is_file() or meta.stat().st_size > self.METADATA_MAX:
                    continue
                files = {
                    f.name: _allocated(f)
                    for f in islice(d.iterdir(), self.FILES_MAX + 1)
                    if f.is_file() and not f.is_symlink()
                }
                copy.mkdir()
                hashes, budget = {}, self.max_bytes
                for name in sorted(files) if len(files) <= self.FILES_MAX else []:
                    hashes[name], used = _copy_hashed(d / name, copy / name, budget)
                    budget -= used
                hashes = {name: hashes.get(name, "") for name in files}
            except OSError:  # deleted by retention between the listing and the copy
                shutil.rmtree(copy, ignore_errors=True)
                continue
            self.done.add(int(step))
            if not hashes.get(".metadata"):  # not a regular, dense file: nothing to inspect, so it cannot count
                shutil.rmtree(copy, ignore_errors=True)
                continue
            self.seen[int(step)], self.hashes[int(step)] = files, hashes
            self._prune()

    def _prune(self) -> None:
        """Keep the newest checkpoint per cadence window, and the last one; forget the others."""
        if not self.every:
            return
        newest: dict[int, int] = {}
        for s in self.seen:
            window = -(-s // self.every)
            newest[window] = max(newest.get(window, 0), s)
        last = max(self.seen)
        for s in list(self.seen):
            if s != newest[-(-s // self.every)] and s != last:
                shutil.rmtree(self.store / str(s), ignore_errors=True)
                del self.seen[s], self.hashes[s]

    def close(self) -> None:
        shutil.rmtree(self.store, ignore_errors=True)


SPARSE_MIN = 64 << 10  # below this, file systems may store data inline with no blocks allocated


def _copy_hashed(src: Path, dst: Path, limit: int) -> tuple[str, int]:
    """Copy a regular, dense, singly linked file to `dst` in chunks, reading at most `limit` bytes; returns its sha256
    and size, or ("", 0) and no copy for anything else (a symlink, FIFO or device, a sparse or hard-linked file, one
    larger than `limit` or growing past it)."""
    try:
        fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        if isinstance(exc, FileNotFoundError):
            raise
        return "", 0
    with os.fdopen(fd, "rb") as fin:
        st = os.fstat(fin.fileno())
        sparse = st.st_size > SPARSE_MIN and st.st_blocks * 512 < st.st_size
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or sparse or st.st_size > limit:
            return "", 0
        digest, n = hashlib.sha256(), 0
        with dst.open("wb") as fout:
            while chunk := fin.read(min(1 << 20, limit + 1 - n)):
                n += len(chunk)
                if n > limit:
                    break
                digest.update(chunk)
                fout.write(chunk)
    if n > limit:
        dst.unlink(missing_ok=True)
        return "", 0
    return digest.hexdigest(), n


def _allocated(f: Path) -> int:
    """A file's bytes as far as they are really stored (a sparse file's holes do not count)."""
    st = f.stat()
    return min(st.st_size, st.st_blocks * 512)


class EvalExportWatch:
    """When each eval export (`step_<N>.safetensors`) first appeared, whether the final export already existed by
    then, and what each looked like the last time it was seen before the final export existed (polled as root by
    Observer). An export written during training precedes the final one and is not touched afterwards; a copy made
    after the run, or a mid-run file overwritten later, is not an export of that step."""

    def __init__(self, root: Path = EVAL_EXPORTS, final: Path = EXPORT, steps: int = 1024) -> None:
        self.root, self.final, self.steps = root, final, steps
        self.after_final: dict[int, bool] = {}  # step -> the final export already existed when it first appeared
        self.signature: dict[int, tuple[int, int, int]] = {}  # step -> (inode, size, ctime) before the final export
        self.final_seen = False  # sticky: deleting and re-creating the final export does not reopen the window
        self.sealed: dict[int, tuple[int, int, int]] | None = None  # at the run's end, before the verifier's chown

    def poll(self) -> None:
        if not self.root.is_dir() or self.root.is_symlink():
            return
        self.final_seen = self.final_seen or self.final.exists()  # read first: files below appeared no later
        seen: dict[int, tuple[int, int, int]] = {}
        for f in islice(self.root.iterdir(), self.steps + 1):
            step = f.name.removeprefix("step_").removesuffix(".safetensors")
            if (
                step.isdecimal()
                and len(step) <= len(str(self.steps))
                and 1 <= int(step) <= self.steps
                and f.name == f"step_{int(step)}.safetensors"
                and not f.is_symlink()
            ):
                self.after_final.setdefault(int(step), self.final_seen)
                with contextlib.suppress(OSError):
                    seen[int(step)] = _signature(f)
        if not (self.final_seen or self.final.exists()):  # nothing below may be recorded once the final export exists
            self.signature.update(seen)

    def seal(self) -> None:
        """Record every export as the run left it: once the job's processes are gone and before the verifier makes
        the run directories root's (a chown moves every ctime)."""
        self.sealed = {}
        if self.root.is_dir() and not self.root.is_symlink():
            for f in islice(self.root.iterdir(), self.steps + 1):
                step = f.name.removeprefix("step_").removesuffix(".safetensors")
                if (
                    step.isdecimal()
                    and len(step) <= len(str(self.steps))
                    and 1 <= int(step) <= self.steps
                    and f.name == f"step_{int(step)}.safetensors"
                    and not f.is_symlink()
                ):
                    with contextlib.suppress(OSError):
                        self.sealed[int(step)] = _signature(f)

    def rewritten(self, step: int) -> bool:
        """Whether the export of `step` changed after it was last seen during training (ctime moves on every write
        and cannot be set back by the job's account, so restoring the mtime does not hide a rewrite)."""
        if self.sealed is not None:
            return self.sealed.get(step) != self.signature.get(step)
        try:
            return _signature(self.root / f"step_{step}.safetensors") != self.signature.get(step)
        except OSError:
            return True


def _signature(path: Path) -> tuple[int, int, int]:
    st = path.lstat()
    return st.st_ino, st.st_size, st.st_ctime_ns


class Observer:
    """What the verifier watches while the agent's job runs, each in a thread of its own: committed checkpoints every
    0.2 s (a checkpoint that retention removes a second later is still seen), every 2 s the job's account's processes
    on each node (read as root over ssh: CPU ticks from /proc/<pid>/stat, and RANK and WORLD_SIZE from its
    environment), and when each eval export first appears. Two placement signals come out of the process samples:
    the distinct RANK values of processes that carry WORLD_SIZE (the env:// workers torchrun or a plain srun launch
    starts), which job code could fake, and the number of processes that burned at least BUSY_SHARE of a CPU since
    the previous sample, which it cannot fake without doing the work there."""

    # pid, utime+stime ticks (after "pid (comm) ": state ppid pgrp session tty tpgid flags minflt cminflt majflt
    # cmajflt utime stime), whether WORLD_SIZE is set, and RANK (x when unset); the node's clock ticks per second first
    PROCS = (
        "echo CLK $(getconf CLK_TCK); for p in $(pgrep -u {user}); do "
        "s=$(sed 's/^[^)]*) //' /proc/$p/stat 2>/dev/null) || continue; set -- $s; t=$(( ${{12}} + ${{13}} )); "
        "e=$(tr '\\0' '\\n' < /proc/$p/environ 2>/dev/null); w=$(printf '%s\\n' \"$e\" | grep -c '^WORLD_SIZE='); "
        "r=$(printf '%s\\n' \"$e\" | grep -m1 '^RANK=' | cut -d= -f2); echo \"$p $t $w ${{r:-x}}\"; done"
    )
    BUSY_SHARE = 0.3  # of one CPU between two samples: a training rank runs near 1.0, launchers and monitors near 0

    def __init__(
        self,
        user: str,
        watch: CheckpointWatch | None,
        placement: bool,
        gpu_idle: dict[str, int] | None = None,
        evals: EvalExportWatch | None = None,
    ) -> None:
        self.user, self.watch, self.placement, self.evals = user, watch, placement, evals
        self.ranks: dict[str, int] = {}  # node -> most distinct ranks seen at once
        self.busy: dict[str, int] = {}  # node -> most CPU-busy processes of the account seen at once
        self._ticks: dict[tuple[str, int], tuple[int, float]] = {}  # (node, pid) -> (ticks, sampled at)
        self.gpu_idle = gpu_idle  # GPU tasks: uuid -> memory used at idle (the ballast)
        self.gpus_used: set[str] = set()  # GPUs seen holding clearly more than at idle during the run
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def __enter__(self) -> Observer:
        if self.watch:
            self._threads.append(threading.Thread(target=self._every, args=(0.2, self.watch.poll), daemon=True))
        if self.evals:
            self._threads.append(threading.Thread(target=self._every, args=(0.5, self.evals.poll), daemon=True))
        if self.placement:
            self._threads.append(threading.Thread(target=self._every, args=(2.0, self._sample_ranks), daemon=True))
        if self.gpu_idle is not None:
            self._threads.append(threading.Thread(target=self._every, args=(2.0, self._sample_gpus), daemon=True))
        for th in self._threads:
            th.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        for th in self._threads:
            th.join(timeout=60)
        if self.watch:
            self.watch.poll()

    def seal(self) -> None:
        if self.evals:
            self.evals.seal()

    def _every(self, interval: float, fn) -> None:
        while not self._stop.is_set():
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 -- an observation error must not end the observation
                print(f"observer: {exc}", flush=True)
            self._stop.wait(interval)

    def _sample_gpus(self) -> None:
        state = gpu_state()
        if state is not None and self.gpu_idle is not None:
            self.gpus_used |= gpus.busy(state, self.gpu_idle)

    def _sample_ranks(self) -> None:
        for node in slurm.nodes():
            res = slurm.run([*SSH, f"root@{node}", self.PROCS.format(user=self.user)], timeout=20)
            if res.returncode == 0:
                ranks, busy = process_sample(node, res.stdout, time.monotonic(), self._ticks, self.BUSY_SHARE)
                self.ranks[node] = max(ranks, self.ranks.get(node, 0))
                self.busy[node] = max(busy, self.busy.get(node, 0))


def process_sample(
    node: str, text: str, now: float, ticks: dict[tuple[str, int], tuple[int, float]], busy_share: float
) -> tuple[int, int]:
    """(distinct RANK values among WORLD_SIZE processes, processes busy since their previous sample) from one PROCS
    output; `ticks` keeps each pid's last (ticks, time) and is updated in place. A pid seen for the first time is not
    busy yet (no interval), so the count needs two samples: the observer samples every 2 s for the whole run."""
    clk, ranks, busy, seen = 100, set(), 0, set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "CLK" and parts[1].isdigit():
            clk = int(parts[1]) or 100
            continue
        if len(parts) != 4 or not (parts[0].isdigit() and parts[1].isdigit()):
            continue
        pid, t, has_ws, rank = int(parts[0]), int(parts[1]), parts[2] != "0", parts[3]
        seen.add((node, pid))
        if has_ws and rank != "x":
            ranks.add(rank)
        prev = ticks.get((node, pid))
        if prev is not None and now > prev[1] and (t - prev[0]) / clk / (now - prev[1]) >= busy_share:
            busy += 1
        ticks[(node, pid)] = (t, now)
    for key in [k for k in ticks if k[0] == node and k not in seen]:
        del ticks[key]  # the process is gone; a new one with the same pid starts a fresh interval
    return len(ranks), busy


def replicated(root_name: str, since: float, until: float | None = None) -> dict[int, dict[str, str]] | None:
    """Checkpoint files the object store received completely within the job's run [since, until]: step -> {file name:
    sha256}; None if the store could not be asked."""
    try:
        with urllib.request.urlopen(f"{OBJSTORE}/replicas/", timeout=10) as resp:
            uploads = json.loads(resp.read())
    except (OSError, ValueError):
        return None
    out: dict[int, dict[str, str]] = {}
    for u in uploads:
        parts = str(u.get("key", "")).split("/")
        t = u.get("t", 0)
        if t < since or (until is not None and t > until) or len(parts) < 3 or parts[0] != root_name:
            continue
        if parts[1].startswith("step_") and parts[1][5:].isdigit():
            out.setdefault(int(parts[1][5:]), {})["/".join(parts[2:])] = str(u.get("sha256", ""))
    return out


@dataclass
class RunResult:
    cluster_ok: bool
    submitted: bool
    finished: bool
    completed: bool
    drained: dict[str, str]  # node -> "state: reason" (ocb.slurm.drained_nodes)
    elapsed_s: float
    job_ids: list[str] = field(default_factory=list)
    detail: str = ""
    settings: list[str] = field(default_factory=list)  # protected settings the running cluster does not have
    survivors: list[str] = field(default_factory=list)  # the account's processes that outlived every kill
    unreachable: list[str] = field(default_factory=list)  # nodes that could not be cleaned
    started: float = 0.0  # when the job was submitted (the object store's uploads after this belong to it)
    # Share of the host's CPU time busy with other work while the job ran: the cluster's own CPU (the nodes' cgroups)
    # is subtracted, so a slow job does not read as a quiet host and a fast one as a busy one. Timing only.
    host_busy: float | None = None
    why: str = ""  # why polling stopped before every job finished (deadline reached, no job accepted, ...)
    states: dict[str, str] = field(default_factory=dict)  # job id -> final state (STATE(reason) unless COMPLETED)

    def incomplete_reason(self) -> str:
        """Why the job did not complete: what stopped the polling (deadline reached, no job accepted, dependency
        never satisfied, pending on unavailable nodes) or, when every job finished, the Slurm states of those that
        did not complete (TIMEOUT, FAILED, OUT_OF_MEMORY, ...), so a negative control's expectation can name the
        failure it intends and a crash cannot stand in for a job that was too slow."""
        if self.completed:
            return ""
        if not self.finished:
            return self.why or "deadline reached"
        states = sorted({st for st in self.states.values() if st != "COMPLETED"}) or ["no job ran"]
        return "a job did not complete: " + ", ".join(states)


def host_cpu() -> tuple[int, int] | None:
    """(busy, total) CPU ticks of the whole host from /proc/stat, which a container shares with its host. Timing
    rules compare two runs on one host; a busy share near 1 says another workload may have slowed one of them."""
    try:
        ticks = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]  # guest is in user
    except (OSError, ValueError, IndexError):
        return None
    idle = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)  # idle + iowait
    return sum(ticks) - idle, sum(ticks)


def busy_share(start: tuple[int, int] | None, end: tuple[int, int] | None, own_usec: int | None = None) -> float | None:
    """The host's busy share between two host_cpu() readings, less the cluster's own CPU time (`own_usec`, from the
    nodes' cgroups) when it is known; /proc/stat ticks are USER_HZ (100 per second) on Linux."""
    if start is None or end is None or end[1] <= start[1]:
        return None
    busy = end[0] - start[0]
    if own_usec is not None:
        busy = max(0, busy - own_usec // 10_000)
    return round(busy / (end[1] - start[1]), 3)


def cluster_cpu_usec() -> int | None:
    """CPU time the cluster's nodes have used so far (the sum of usage_usec of each node container's cgroup, read as
    root over ssh); None when any node did not answer, so the subtraction is all or nothing."""
    total = 0
    try:
        nodes = slurm.nodes()
    except slurm.SlurmError:
        return None
    for node in nodes:
        res = slurm.run([*SSH, f"root@{node}", "grep ^usage_usec /sys/fs/cgroup/cpu.stat"], timeout=10)
        parts = res.stdout.split()
        if res.returncode != 0 or len(parts) != 2 or not parts[1].isdigit():
            return None
        total += int(parts[1])
    return total + own_cpu_usec()


def own_cpu_usec() -> int:
    """This container's CPU time (its cgroup): the submission script, the watches and the hashing run here, and are
    the trial's own work, not host load. 0 where the cgroup is not readable (then it counts as load, as before)."""
    try:
        for line in Path("/sys/fs/cgroup/cpu.stat").read_text().splitlines():
            if line.startswith("usage_usec "):
                return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return 0


# Completion is seen within this long: the run's elapsed time is quantised by it, so it must be small against the
# shortest timed run (about 20 s). A 2 s poll made a reference look 5-10% slower than itself.
POLL_S = 0.25


def _poll_until_done(cfg: VerifyConfig, user: str, before: int, t0: float) -> tuple[bool, list[slurm.Job], str]:
    """(every job finished, the jobs, why polling stopped if they did not): the reason names what the verifier saw,
    so a negative control's expectation can tell a job that was too slow from one that was never accepted."""
    deadline = cfg.deadline_s or 600
    window: list[slurm.Job] = []
    empty_polls = errors = 0
    stuck_since: float | None = None
    while time.time() - t0 < deadline:
        try:
            polled = slurm.jobs()
        except slurm.SlurmError:  # a busy controller is not evidence of an empty queue
            errors += 1
            time.sleep(2)
            continue
        window = [j for j in polled if j.user == user and int(j.id) > before]
        if window and all(j.state in slurm.TERMINAL for j in window):
            return True, window, ""
        empty_polls = 0 if window else empty_polls + 1
        if empty_polls >= 5 and time.time() - t0 > 30:  # the scheduler accepted nothing
            return False, window, "no job accepted"
        waiting = [j for j in window if j.state not in slurm.TERMINAL]
        if waiting and all(j.state == "PENDING" and j.reason == "DependencyNeverSatisfied" for j in waiting):
            return False, window, "dependency never satisfied"  # can never start: a dependency failed
        # Pending on nodes that are drained or down: nothing in the run will bring them back, so after a minute the
        # outcome is known (a job pending behind a drained node once held a verifier for 25 minutes).
        unavailable = waiting and all(j.state == "PENDING" and "ReqNodeNotAvail" in j.reason for j in waiting)
        stuck_since = (stuck_since or time.time()) if unavailable else None
        if stuck_since is not None and time.time() - stuck_since > 60:
            return False, window, "pending on unavailable nodes"
        time.sleep(POLL_S)
    return False, window, "deadline reached"


def save_job_logs(label: str, logs_dir: Path) -> None:
    dest = logs_dir / "job-logs" / label
    dest.mkdir(parents=True, exist_ok=True)
    for log in sorted((SHARED / "logs").glob("*.out")):
        if not stat.S_ISREG(log.lstat().st_mode):  # a symlink or a FIFO is the job's doing: nothing to keep
            continue
        with log.open("rb") as stream:  # never the whole file: a log can be as large as the job wants
            data = stream.read(LOGS_KEPT_BYTES)
            if stream.read(1):
                stream.seek(-(LOGS_KEPT_BYTES // 2), os.SEEK_END)
                data = data[: LOGS_KEPT_BYTES // 2] + b"\n[... truncated ...]\n" + stream.read(LOGS_KEPT_BYTES // 2)
        (dest / log.name).write_bytes(data)


def run_job(cfg: VerifyConfig, label: str, user: str, logs_dir: Path, observer: Observer | None = None) -> RunResult:
    """_run_job, with the account stopped whatever raised in between (a submission or polling error must not leave
    the job running into the next timed run or the verifier's own checks)."""
    try:
        return _run_job(cfg, label, user, logs_dir, observer)
    except BaseException:
        stop_account(user)
        raise


def _run_job(cfg: VerifyConfig, label: str, user: str, logs_dir: Path, observer: Observer | None = None) -> RunResult:
    """Deploy /ops's cluster config, submit /ops's job as `user`, and wait until every job it created is terminal or
    the deadline passes. The account is stopped everywhere before this returns."""
    deployed = slurm.deploy_cluster_config(OPS)
    slurm.run(["scontrol", "reconfigure"])
    cluster_ok = slurm.wait_for_cluster(cfg.min_nodes, timeout_s=180, since=deployed)
    if not cluster_ok:
        try:
            reasons = slurm.query(["sinfo", "-R", "-h", "-o", "%N: %E"]).strip()
        except slurm.SlurmError as exc:
            reasons = str(exc)
        return RunResult(False, False, False, False, {}, 0.0, detail=reasons or "controller or nodes not up")
    settings = protected_settings()
    reset_run_dirs(user)
    seal_jobcomp()
    if cfg.store_refill_s:  # the previous run's dataset requests must not throttle this one
        time.sleep(cfg.store_refill_s)
    try:
        apply_site(cfg.site)
    except RuntimeError as exc:  # the site's reservations or jobs could not be created under /ops's cluster config
        detail = f"site state not applicable under /ops/cluster config: {exc}"
        return RunResult(False, False, False, False, {}, 0.0, detail=detail)
    before = max((int(j.id) for j in slurm.jobs()), default=0)
    with observer or contextlib.nullcontext():
        # submit.sh may wait for its jobs: observations must cover that work too.
        t0, cpu0, own0 = time.time(), host_cpu(), cluster_cpu_usec()
        ids, output = slurm.submit(OPS, cfg.job, user=user)
        kill_local(user)  # nothing submit.sh started survives outside Slurm
        print(f"[{label}] submit as {user}: jobs {ids or '(none)'}\n{output.strip()}", flush=True)
        finished, window, why = _poll_until_done(cfg, user, before, t0)
        # timed when completion is seen, not after the observer winds down (an ssh sample in flight takes seconds)
        elapsed, cpu1 = time.time() - t0, host_cpu()
    own1 = cluster_cpu_usec()
    busy = busy_share(cpu0, cpu1, own1 - own0 if own0 is not None and own1 is not None else None)
    survivors, unreachable = stop_account(user, seal=observer.seal if observer else None)
    problems = survivors + unreachable
    try:
        window = [j for j in slurm.jobs() if j.user == user and int(j.id) > before] or window
        drained = slurm.drained_nodes()
    except slurm.SlurmError as exc:
        problems.append(str(exc))
        drained = {}
    states = {j.id: j.state if j.state == "COMPLETED" else f"{j.state}({j.reason})" for j in window}
    completed = finished and bool(window) and all(j.state == "COMPLETED" for j in window)
    print(f"[{label}] jobs: {states} elapsed={elapsed:.1f}s host_busy={busy} drained={drained or 'none'}", flush=True)
    if problems:
        print(f"[{label}] cleanup: {'; '.join(problems)}", flush=True)
    save_job_logs(label, logs_dir)
    if not completed:
        for j in window:
            print(f"[{label}] --- job {j.id} log (head and tail) ---\n{cli.logs(j.id, n=40, head=20)}", flush=True)
            print(f"[{label}] --- job {j.id} metrics ---\n{cli.metrics_summary(j.id)}", flush=True)
    return RunResult(True, bool(ids), finished, completed, drained, elapsed, [j.id for j in window],
                     settings=settings, survivors=survivors, unreachable=unreachable, started=t0,
                     host_busy=busy, why=why, states=states)  # fmt: skip


def _copy_bounded(src: Path, dst: Path, budget: int) -> bool:
    """Copy at most `budget` bytes; False (and no file) when the source holds more, whatever its stat said."""
    copied = 0
    with open(src, "rb") as f, open(dst, "wb") as out:
        while chunk := f.read(1 << 20):
            copied += len(chunk)
            if copied > budget:
                out.close()
                dst.unlink(missing_ok=True)
                return False
            out.write(chunk)
    return True


@dataclass
class Snapshot:
    """What the agent's run left behind, copied root-only the moment its jobs ended."""

    export: Path | None
    metrics: dict[str, dict[int, list[dict]]]  # job id -> rank -> records
    eval_exports: dict[int, Path] = field(default_factory=dict)  # step -> copy of step_<N>.safetensors
    errors: list[str] = field(default_factory=list)


def snapshot(
    job_ids: list[str], model_cfg: dict | None = None, *, world: int = 8, steps: int = 1024, eval_every: int = 1
) -> Snapshot:
    """Read bounded, regular artifacts after account cleanup. Keep at most one export per cadence window.
    Invalid files are submission errors, never unbounded reads or verifier failures."""
    shutil.rmtree(SNAPSHOT, ignore_errors=True)
    SNAPSHOT.mkdir(parents=True)
    SNAPSHOT.chmod(0o700)
    errors: list[str] = []
    max_bytes = checkpoint_bytes_max(model_cfg or {})

    def regular(path: Path, budget: int) -> bool:
        info = path.lstat()
        return stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= budget

    def copy_export(src: Path, dst: Path) -> bool:
        if not regular(src, max_bytes) or not _copy_bounded(src, dst, max_bytes):
            errors.append(f"invalid or oversized export: {src.name}")
            return False
        return True

    export = None
    if EXPORT.exists() or EXPORT.is_symlink():
        dest = SNAPSHOT / "model.safetensors"
        if EXPORT.parent.is_symlink():
            errors.append("export directory is a symlink")
        elif copy_export(EXPORT, dest):
            export = dest
    metrics: dict[str, dict[int, list[dict]]] = {}
    remaining = min(100_000_000, METRICS_MAX_BYTES * world)
    files = 0
    for job_id in job_ids:
        directory = SHARED / "metrics" / job_id
        if directory.parent.is_symlink() or directory.is_symlink() or not directory.is_dir():
            continue
        for f in directory.iterdir():
            files += 1
            if files > world * max(1, len(job_ids)):
                errors.append("too many metric files")
                break
            rank = f.stem.removeprefix("rank")
            if not f.name.startswith("rank") or f.suffix != ".jsonl" or not rank.isdecimal() or len(rank) > 6:
                continue  # not a rank's metrics (the platform writes rank<r>.jsonl only); counted, never read
            if not regular(f, min(remaining, METRICS_MAX_BYTES)):
                errors.append(f"invalid or oversized metrics: {f.name}")
                continue
            remaining -= f.stat().st_size
            metrics.setdefault(job_id, {})[int(rank)] = parse_metrics(f.read_text(errors="replace").splitlines())
        if files > world * max(1, len(job_ids)):
            break
    selected: dict[int, tuple[int, Path]] = {}
    if EVAL_EXPORTS.is_dir() and not EVAL_EXPORTS.is_symlink():
        for count, f in enumerate(EVAL_EXPORTS.iterdir(), 1):
            if count > steps:
                errors.append("too many evaluation exports")
                break
            step_text = f.name.removeprefix("step_").removesuffix(".safetensors")
            if (
                not step_text.isdecimal()
                or len(step_text) > len(str(steps))
                or not 1 <= int(step_text) <= steps
                or f.name != f"step_{int(step_text)}.safetensors"
            ):
                continue  # not an export of a step of this run: never counts (rules.eval_exports), never read
            if not regular(f, max_bytes):
                errors.append(f"invalid or oversized export: {f.name}")
                continue
            step = int(step_text)
            window = (step - 1) // max(1, eval_every)
            if window not in selected or selected[window][0] < step:
                selected[window] = (step, f)
    evals = {}
    for step, f in selected.values():
        dest = SNAPSHOT / f"eval-{step}.safetensors"
        if copy_export(f, dest):
            evals[step] = dest
    return Snapshot(export, metrics, evals, errors)
