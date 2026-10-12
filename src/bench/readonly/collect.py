#!/usr/bin/env python3
"""The logs variant's observer: complete read-only views of the live cluster, copied into /obs every few seconds.

Runs as the `obs` sidecar (runtime image, this project's cluster keys) and takes no input from anyone: the agent's
workstation has no network at all and mounts /obs read-only. It starts once provisioning has written
/shared/evidence/READY (or SETUP_FAILED), so the evidence is collected exactly as in the standard variant; the daemon
logs it copies are whole files, so they hold everything the daemons recorded since the cluster booted, provisioning's
submissions and node updates included, as a node's own /var/log/slurm does in the standard variant. Each view is
written atomically (a temporary file renamed over the old one), except daemon logs, whose new bytes are appended in
place with the node's own modification time (so `tail -f` and `ls -lt` behave as on a node); /obs/SNAPSHOT_AT, written
last, says when the cycle ended, and /obs/CYCLES keeps one line per cycle (its duration and any view that failed).

    slurm/*.json     squeue and sinfo with every field (squeue-fields, sinfo-fields: the workstation's commands
                     render any format from these), and the usual outputs of squeue, sinfo, scontrol show, sacct,
                     sdiag, ... with their exit status
    logs/HOST/       the daemon logs of the controller and of every node (/var/log/slurm), whole files
    nodes/           `ocb nodes` and `ocb gpus` as they print (.txt), and with their exit status (.json)
    store/           the object store's replica listing (GET /replicas/) as served, and its HTTP status
    engine/          the serving engine's /health, /slots, /metrics and /props as served, each with its HTTP status
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(os.environ.get("OBS_DIR", "/obs"))
EVIDENCE = Path(os.environ.get("OBS_EVIDENCE", "/shared/evidence"))
INTERVAL_S = float(os.environ.get("OBS_INTERVAL_S", "10"))
SUBSTRATE = os.environ.get("OBS_SUBSTRATE", "slurm")
MAX_FILE = 256 * 2**20  # far above any daemon log seen; a runaway log keeps its newest bytes
SEP = "\x1f"
SQUEUE_LETTERS = "aAbBcCdDeEfFgGhHiIjJkKlLmMnNoOpPqQrRSTtuUvVwWxXyYzZ"
SINFO_LETTERS = "aAbBcCdDeEfFgGhHIlLmMnNoOpPrRsStTuUwXYZz"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR"]

# The usual outputs, run as root (who sees every user's jobs) with their arguments fixed here: nothing chooses them.
SLURM_COMMANDS: dict[str, list[str]] = {
    "squeue": ["squeue"],
    "squeue-l": ["squeue", "-l"],
    "squeue-start": ["squeue", "--start"],
    "squeue-s": ["squeue", "-s"],
    "scontrol-job": ["scontrol", "show", "job"],
    "scontrol-job-d": ["scontrol", "-d", "show", "job"],
    "scontrol-node": ["scontrol", "show", "node"],
    "scontrol-partition": ["scontrol", "show", "partition"],
    "scontrol-reservation": ["scontrol", "show", "reservation"],
    "scontrol-step": ["scontrol", "show", "step"],
    "scontrol-config": ["scontrol", "show", "config"],
    "scontrol-ping": ["scontrol", "ping"],
    "scontrol-version": ["scontrol", "version"],
    "sacct": ["sacct"],
    "sdiag": ["sdiag"],
    "sprio": ["sprio"],
    "sshare": ["sshare"],
}
# sinfo's usual forms, each with and without its header (sinfo-Nel: sinfo -N -e -l; sinfo-noheader: sinfo -h).
SINFO_FORMS = ("", "l", "R", "Rl", "s", "N", "Nl", "Nel", "e", "el", "T")


def sinfo_view(form: str, no_header: bool) -> str:
    return "sinfo" + (f"-{form}" if form else "") + ("-noheader" if no_header else "")


for _form in SINFO_FORMS:
    _flags = [f"-{c}" for c in _form]
    SLURM_COMMANDS[sinfo_view(_form, False)] = ["sinfo", *_flags]
    SLURM_COMMANDS[sinfo_view(_form, True)] = ["sinfo", *_flags, "-h"]


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write(rel: str, data: str | bytes) -> None:
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode() if isinstance(data, str) else data
    if len(raw) > MAX_FILE:
        raw = b"[obs: only the last 256 MiB of this file are copied]\n" + raw[-MAX_FILE:]
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def run(cmd: list[str], timeout: float = 30) -> tuple[int, str, str]:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout, check=False)
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]}: no answer within {timeout:.0f} s\n"
    except OSError as exc:
        return 127, "", f"{cmd[0]}: {exc}\n"


def valid_letters(command: str, letters: str) -> str:
    """The format letters this Slurm accepts (an unknown one fails the whole command)."""
    return "".join(c for c in letters if run([command, "-h", "-o", f"%{c}"], timeout=15)[0] == 0)


def table(argv: list[str], letters: str) -> dict:
    """Every field (one format letter each) of every row, with the header Slurm prints for each letter."""
    rc, out, err = run([*argv, "-o", SEP.join(f"%{c}" for c in letters)])
    lines = out.splitlines()
    if rc or not lines:
        return {"rc": rc, "stderr": err, "header": {}, "rows": []}
    header = dict(zip(letters, lines[0].split(SEP), strict=False))
    rows = [dict(zip(letters, line.split(SEP), strict=False)) for line in lines[1:] if line]
    return {"rc": rc, "stderr": err, "header": header, "rows": rows}


class Slurm:
    def __init__(self) -> None:
        self.squeue_letters = ""
        self.sinfo_letters = ""

    def collect(self) -> list[str]:
        if not self.squeue_letters and run(["squeue", "-h", "-o", "%i"], timeout=15)[0] == 0:
            self.squeue_letters = valid_letters("squeue", SQUEUE_LETTERS)
            self.sinfo_letters = valid_letters("sinfo", SINFO_LETTERS)
        if self.squeue_letters:
            # every state the controller still holds (squeue -t all), in squeue's own order; the workstation's squeue
            # applies the default state filter and any other option itself
            write("slurm/squeue-fields.json", json.dumps(table(["squeue", "-a", "-t", "all"], self.squeue_letters)))
            write("slurm/sinfo-fields.json", json.dumps(table(["sinfo", "-a", "-N"], self.sinfo_letters)))
        for name, argv in SLURM_COMMANDS.items():
            rc, out, err = run(argv)
            write(f"slurm/{name}.json", json.dumps({"argv": argv, "rc": rc, "stdout": out, "stderr": err}))
        hosts = []
        try:
            nodes = json.loads((OUT / "slurm" / "sinfo-fields.json").read_text())["rows"]
            hosts = sorted({row.get("n") or row.get("N", "") for row in nodes} - {""})
        except (OSError, ValueError, KeyError):
            pass
        return ["slurmctld", *hosts]


def sync_log(rel: str, data: bytes, mtime: float) -> None:
    """A node's growing log, kept as a growing file: the new bytes appended in place (`tail -f` follows it), the node's
    own modification time kept; a log that shrank or no longer starts the same way (rotated) is rewritten whole."""
    path = OUT / rel
    old = path.stat().st_size if path.exists() else -1
    if len(data) > MAX_FILE or old > len(data) or old < 0:
        write(rel, data)
    elif old < len(data):
        with open(path, "rb") as f:
            same = f.read(4096) == data[: min(old, 4096)]
        if same:
            with open(path, "ab") as f:
                f.write(data[old:])
        else:
            write(rel, data)
    os.utime(path, (mtime, mtime))


def copy_logs(host: str) -> str:
    """The host's /var/log/slurm, whole, over one ssh session (ControlMaster keeps it open between cycles); returns why
    it failed, or ""."""
    try:
        res = subprocess.run([*SSH, f"root@{host}", "tar -C /var/log -cf - slurm"], capture_output=True, timeout=60,
                             check=False)  # fmt: skip
    except subprocess.TimeoutExpired:
        write(f"logs/{host}/UNAVAILABLE", f"{now()} {host}: no answer within 60 s; the files here are older\n")
        return f"logs/{host}: no answer within 60 s"
    if res.returncode != 0:
        why = res.stderr.decode(errors="replace").strip() or f"ssh exited {res.returncode}"
        write(f"logs/{host}/UNAVAILABLE", f"{now()} {host}: {why}; the files here are older\n")
        return f"logs/{host}: {why[:120]}"
    with tarfile.open(fileobj=io.BytesIO(res.stdout)) as tar:
        for member in tar.getmembers():
            name = Path(member.name)
            if not member.isfile() or ".." in name.parts or len(name.parts) < 2:
                continue
            data = tar.extractfile(member)
            if data is not None:
                sync_log(f"logs/{host}/{Path(*name.parts[1:])}", data.read(), member.mtime)
    (OUT / "logs" / host / "UNAVAILABLE").unlink(missing_ok=True)
    return ""


def serve_copy(rel: str, url: str) -> str:
    """A GET endpoint's body as served (`rel`) and its HTTP status (`rel`.status); returns why it failed, or ""."""
    answer = get(url)
    write(rel, answer["body"])
    write(
        f"{rel}.status", f"{answer['status']}\n" if answer["status"] is not None else f"no answer: {answer['body']}\n"
    )
    return "" if answer["status"] is not None else f"{rel}: {answer['body'][:120]}"


def get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return {"status": resp.status, "body": resp.read().decode(errors="replace")}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "body": exc.read().decode(errors="replace")}
    except (OSError, ValueError) as exc:
        return {"status": None, "body": f"{type(exc).__name__}: {exc}"}


README = """\
Read-only views of the live system, refreshed every {interval:.0f} seconds (SNAPSHOT_AT: when the last refresh ended;
CYCLES: one line per refresh). Nothing here can change the system, and nothing written here reaches it.

  slurm/       the scheduler: every field of squeue and sinfo, and the outputs of scontrol show (jobs, nodes,
               partitions, reservations, steps, config), sacct, sdiag, sprio and sshare, as JSON with each exit status;
               squeue, sinfo, scontrol, sacct, ... on this workstation print from these
  logs/HOST/   the daemon logs (/var/log/slurm) of the controller and of every node, whole and growing, with the
               node's own modification times
  nodes/       `ocb nodes` (cgroup memory and CPU counters, filesystems of every node) and `ocb gpus`, as printed (.txt)
  store/       the object store's listing of checkpoint replicas (GET /replicas/), as served, with its HTTP status
  engine/      the serving engine's /health, /slots, /metrics and /props, each as served, with its HTTP status (.status)
"""


def cycle(slurm: Slurm, n: int) -> list[str]:
    """One refresh of every view; returns the views that failed."""
    failed: list[str] = []
    if SUBSTRATE == "serving":
        # /props is static (the server's settings): read until it answers, then kept
        props_done = (OUT / "engine" / "props.status").exists() and (OUT / "engine" / "props.status").read_text()[
            :3
        ] == "200"
        for endpoint in ("health", "slots", "metrics", *(() if props_done else ("props",))):
            failed.append(serve_copy(f"engine/{endpoint}", f"http://engine:8080/{endpoint}"))
        return [f for f in failed if f]
    for host in slurm.collect():
        failed.append(copy_logs(host))
    for view, every in (("nodes", 1), ("gpus", 6)):  # GPUs do not come and go: once a minute
        if n % every == 0:
            rc, out, err = run([sys.executable, "-m", "ocb.cli", view], timeout=120)
            write(f"nodes/ocb-{view}.json", json.dumps({"rc": rc, "stdout": out, "stderr": err}))
            write(f"nodes/ocb-{view}.txt", out + err)
            failed.append(f"nodes/ocb-{view}: exit {rc}" if rc else "")
    failed.append(serve_copy("store/replicas.json", "http://objstore:8000/replicas/"))
    return [f for f in failed if f]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    while not (EVIDENCE / "READY").exists() and not (EVIDENCE / "SETUP_FAILED").exists():
        time.sleep(2)
    write("README", README.format(interval=INTERVAL_S))
    slurm, n = Slurm(), 0
    while True:
        started, began = time.monotonic(), now()
        try:
            failed = cycle(slurm, n)
        except Exception as exc:  # noqa: BLE001 - a failed view must not stop the others' refreshes
            failed = [f"cycle: {type(exc).__name__}: {exc}"]
            print(f"obs: cycle {n}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        took = time.monotonic() - started
        with open(OUT / "CYCLES", "a") as log:  # the trial's record that the views kept refreshing (an artifact)
            log.write(
                f"{began} cycle {n} took {took:.1f}s" + (f" failed: {'; '.join(failed)}" if failed else "") + "\n"
            )
        write("SNAPSHOT_AT", f"{now()} cycle {n} took {took:.1f}s\n")
        n += 1
        time.sleep(max(1.0, INTERVAL_S - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
