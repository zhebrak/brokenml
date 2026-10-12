"""The report-and-logs snapshot (one capture per task): what the standard agent could read at READY.

    uv run bench snapshot-evidence [TASK ...] [--split test|dev|all] [--keep]

Brings up the task's standard agent environment the way `bench bootcheck` does (compose up --wait, the workstation
idle), waits until provisioning marks it READY, copies /shared/evidence (report.md, symptom.json, dumps/, submit.txt;
not the READY marker) and /shared/logs out of the workstation, and tears the environment down. Writes
results/snapshots/<task>/<task_digest>.tar.gz and <task_digest>.json (the task digest, the image IDs, a stamp and the
sha256 of every file). No agent runs. The `snapshot` task variant (bench.render) bakes such a tarball, read-only, into
an ops-only workstation: no cluster, nothing live. The tarball is keyed by the digest of the standard task as it renders
now, so a task that changed needs a new capture (rendering refuses a stale one).

The snapshot is exactly what the standard agent could read at READY, nothing from the harness. Capture and render
both check the tarball: only regular files and directories under `evidence/` and `logs/`, no absolute or `..` paths,
and none of the harness terms of the leak audit (bench.leak_audit.TERMS, plus the setup paths of bench.analyze.PROBE
that name harness internals) in any file. A hit fails the capture, naming the file and line.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import subprocess
import tarfile
import time
from pathlib import Path

from bench.bootcheck import _compose, sh
from bench.leak_audit import TERMS
from bench.paths import RESULTS, project_name
from bench.provenance import stamp, task_digest
from bench.spec import by_id, load_specs, task_dir

SNAPSHOTS = RESULTS / "snapshots"
ROOTS = ("evidence", "logs")  # the only top-level directories of a snapshot (as under /shared)
EXCLUDED = ("evidence/READY", "evidence/SETUP_FAILED")  # provisioning's own markers, not evidence
HARNESS_PATHS = r"/opt/task\b|/opt/store\b|/opt/ops-seed|teacher\.json|bootstrap\.yaml|verify\.yaml|/tests/|/solution/"
LEAK = re.compile(f"(?:{TERMS})|(?:{HARNESS_PATHS})", re.IGNORECASE)


class SnapshotError(RuntimeError):
    """No usable snapshot for this task as it renders now (or a snapshot that must not be baked)."""


def snapshot_path(task: str, digest: str) -> Path:
    return SNAPSHOTS / task / f"{digest.removeprefix('sha256:')}.tar.gz"


def manifest_path(task: str, digest: str) -> Path:
    return snapshot_path(task, digest).with_suffix("").with_suffix(".json")


def check_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """The members of a snapshot, or SnapshotError: regular files and directories only, relative, under ROOTS."""
    members = tar.getmembers()
    for m in members:
        parts = Path(m.name).parts
        if m.name.startswith("/") or ".." in parts or not parts or parts[0] not in ROOTS:
            raise SnapshotError(f"snapshot member {m.name!r} is outside {', '.join(ROOTS)}")
        if not (m.isfile() or m.isdir()):
            raise SnapshotError(f"snapshot member {m.name!r} is not a regular file or directory")
    return members


def leaks(tar: tarfile.TarFile) -> list[str]:
    """`file:line: text` for every line of every file that mentions a harness term (see LEAK)."""
    hits = []
    for m in tar.getmembers():
        if m.isfile():
            data = tar.extractfile(m).read().decode("utf-8", errors="replace")  # type: ignore[union-attr]
            for n, line in enumerate(data.splitlines(), 1):
                if LEAK.search(line):
                    hits.append(f"{m.name}:{n}: {line.strip()[:160]}")
    return hits


def verify_tarball(path: Path) -> list[tarfile.TarInfo]:
    """Structure and leak check of a snapshot tarball on disk; raises SnapshotError."""
    with tarfile.open(path) as tar:
        members = check_members(tar)
        found = leaks(tar)
    if found:
        raise SnapshotError(f"{path.name} mentions harness terms:\n  " + "\n  ".join(found[:10]))
    return members


def find(task: str) -> Path:
    """The snapshot tarball for the task as it renders now (tasks/), or SnapshotError saying what to do."""
    digest = task_digest(task_dir(task))
    path = snapshot_path(task, digest)
    if path.exists():
        return path
    have = (
        sorted(p.stem.removesuffix(".tar") for p in (SNAPSHOTS / task).glob("*.tar.gz"))
        if (SNAPSHOTS / task).exists()
        else []
    )
    raise SnapshotError(
        f"no evidence snapshot for {task} at its current digest {digest[:19]}"
        + (f" (captured for another digest: {', '.join(have)}; the task changed since)" if have else "")
        + f"; capture one with `uv run bench snapshot-evidence {task}`"
    )  # fmt: skip


def materialise(task: str, dest: Path) -> None:
    """Extract the task's current snapshot into dest/evidence and dest/logs (both created), verified first."""
    path = find(task)
    verify_tarball(path)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path) as tar:
        tar.extractall(dest, filter="data")
    for root in ROOTS:
        (dest / root).mkdir(exist_ok=True)


def _gzip(raw: bytes) -> bytes:
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(raw)
    return out.getvalue()


def capture(task: str, keep: bool = False) -> dict:
    """Bring up the standard agent environment, copy the evidence out at READY, tear down; returns the manifest."""
    spec, env_dir = by_id(task), task_dir(task) / "environment"
    digest = task_digest(task_dir(task))
    project = project_name("snap", task)
    compose, main, t0 = _compose(env_dir, project), f"{project}-main-1", time.time()
    ok = False
    try:
        up = sh([*compose, "up", "-d", "--wait", "--build"], cwd=env_dir, timeout=900)
        if up.returncode != 0:
            raise SnapshotError(f"compose up --wait: {(up.stderr or up.stdout)[-300:]}")
        while True:
            if sh(["docker", "exec", main, "test", "-f", "/shared/evidence/SETUP_FAILED"]).returncode == 0:
                why = sh(["docker", "exec", main, "cat", "/shared/evidence/SETUP_FAILED"]).stdout
                raise SnapshotError(f"setup failed: {why.strip()[:300]}")
            if sh(["docker", "exec", main, "test", "-f", "/shared/evidence/READY"]).returncode == 0:
                break
            if time.time() - t0 > spec.bootstrap_timeout_s + 120:
                raise SnapshotError("neither READY nor SETUP_FAILED before the bootstrap timeout")
            time.sleep(3)
        symptom = json.loads(sh(["docker", "exec", main, "cat", "/shared/evidence/symptom.json"]).stdout or "null")
        if not (symptom or {}).get("observed"):
            raise SnapshotError(f"ready without the symptom: {json.dumps(symptom)[:300]}")
        # The agent's own view: root in main, /shared as the workstation mounts it. A log still being written may
        # change under tar (exit 1): the snapshot is what was readable at this moment.
        excludes = [f"--exclude={e}" for e in EXCLUDED]
        cp = subprocess.run(["docker", "exec", main, "tar", "-C", "/shared", *excludes, "-cf", "-", *ROOTS],
                            capture_output=True, check=False, timeout=300)  # fmt: skip
        if cp.returncode > 1 or not cp.stdout:
            raise SnapshotError(f"tar in main failed ({cp.returncode}): {cp.stderr.decode(errors='replace')[-300:]}")
        ok = True
    finally:
        if ok or not keep:
            sh([*compose, "down", "-v"], cwd=env_dir, timeout=300)
        else:
            print(f"kept {project} for inspection (docker compose -p {project} down -v when done)", flush=True)
    return store(task, digest, cp.stdout, {"seconds": round(time.time() - t0), "symptom": symptom,
                                           "tar_warnings": cp.stderr.decode(errors="replace")[-300:]})  # fmt: skip


def store(task: str, digest: str, raw_tar: bytes, extra: dict | None = None) -> dict:
    """Check a captured tar stream, write results/snapshots/<task>/<digest>.tar.gz and its manifest."""
    with tarfile.open(fileobj=io.BytesIO(raw_tar)) as tar:
        members = check_members(tar)
        found = leaks(tar)
        files = {m.name: hashlib.sha256(tar.extractfile(m).read()).hexdigest()  # type: ignore[union-attr]
                 for m in members if m.isfile()}  # fmt: skip
    if found:
        raise SnapshotError("the snapshot mentions harness terms, not written:\n  " + "\n  ".join(found[:10]))
    path = snapshot_path(task, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gzip(raw_tar))
    s = stamp()
    manifest = {"task": task, "task_digest": digest, "image_ids": s["images"], "files": dict(sorted(files.items())),
                "stamp": s, **(extra or {})}  # fmt: skip
    manifest_path(task, digest).write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench snapshot-evidence", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("tasks", nargs="*")
    ap.add_argument("--split", default="test", choices=["test", "dev", "all"])
    ap.add_argument("--keep", action="store_true", help="leave a failing environment up for inspection")
    args = ap.parse_args(argv)
    tasks = args.tasks or [s.id for s in load_specs() if args.split in ("all", s.split)]
    bad = []
    for task in tasks:
        try:
            m = capture(task, args.keep)
            where = snapshot_path(task, m["task_digest"])
            print(f"{time.strftime('%H:%M')} {task:32} ok  {len(m['files'])} files  {where}", flush=True)
        except (SnapshotError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            bad.append(task)
            print(f"{time.strftime('%H:%M')} {task:32} FAIL  {exc}", flush=True)
    print(
        f"{len(tasks) - len(bad)} of {len(tasks)} snapshots captured" + (f"; failing: {', '.join(bad)}" if bad else "")
    )
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
