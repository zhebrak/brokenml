"""Re-grade recorded trials with Harbor's `trial regrade`:

  bench regrade TRIAL_DIR [TRIAL_DIR ...] [--replay | --runtime IMAGE] [--out DIR]

A plain re-grade (an infrastructure failure, a quiet-host timing review) grades the trial against the task exactly as
its agent faced it: the snapshot its lock.json names, refused when that is missing or its digest no longer matches.
Results go to runs/jobs/<name>/, where `bench analyze` resolves them to their original trial by id.

--replay is diagnostic only: it grades the trial with the current verifier on the teacher and held-out seeds its
verdict recorded (diagnostics.json), from a scratch copy of the current render whose verify.yaml carries them, so a
verifier revision can be compared like for like (how many verdicts flip, and which way). Replayed gradings record
`replay: 1`, go to runs/regrades/, and are never scored: a verifier revision re-grades the whole run on fresh seeds
(docs/leaderboard.md).

--runtime IMAGE re-grades on a patched runtime image (docs/leaderboard.md, Re-grades: trials a platform defect
left without a verdict). The trial's snapshot, checked as for a plain re-grade, is copied with only the runtime image
and the source version its nodes expect swapped (both compose files and environment/images.lock); the image must carry
/opt/ocb/VERSION.base equal to the version the snapshot was rendered against. Each pair of task digests is recorded by
trial id in protocol/patched-gradings.json, which is what lets `bench analyze` score the grading. Run it on the
original trial directories only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

from bench.analyze import PATCHED_GRADINGS
from bench.paths import ROOT, RUNS
from bench.provenance import task_digest
from bench.spec import by_id, task_dir

HARBOR = os.environ.get("HARBOR", "harbor").split()


def recorded_seeds(trial: Path) -> dict[str, int] | None:
    diag = trial / "verifier" / "diagnostics.json"
    d = json.loads(diag.read_text()) if diag.exists() else {}
    if "teacher_seed" not in d or "heldout_seed" not in d:
        return None
    out = {"teacher_seed": int(d["teacher_seed"]), "heldout_seed": int(d["heldout_seed"])}
    if d.get("data_seed") is not None:
        out["data_seed"] = int(d["data_seed"])
    return out


def replay_task(task: str, seeds: dict[str, int], scratch: Path) -> Path:
    """A copy of the task whose verifier grades on the recorded seeds; returns the directory holding it."""
    dst = scratch / task
    shutil.copytree(task_dir(by_id(task)), dst)
    verify = dst / "tests" / "verify.yaml"
    cfg = yaml.safe_load(verify.read_text())
    cfg["replay"] = seeds
    verify.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return scratch


def snapshot(trial: Path) -> Path:
    """The task directory the trial's agent faced (lock.json), checked against the digest recorded there."""
    task = json.loads((trial / "lock.json").read_text()).get("task") or {}
    path = Path(task.get("path") or "")
    if not (path / "task.toml").exists():
        raise ValueError(f"the task the trial ran ({path}) is gone")
    if task_digest(path) != task.get("digest"):
        raise ValueError(f"{path} changed since the trial ran (digest {task.get('digest')})")
    return path


def image_versions(image: str) -> tuple[str, str, str]:
    """A patched runtime image's source version (/opt/ocb/VERSION), the version of the study image it patches
    (/opt/ocb/VERSION.base, which only a patched image carries) and its build ID (/opt/ocb/BUILD: what the verifier
    records as node_build for nodes that run it)."""
    files = ["/opt/ocb/VERSION", "/opt/ocb/VERSION.base", "/opt/ocb/BUILD"]
    cmd = ["docker", "run", "--rm", "--entrypoint", "cat", image, *files]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    words = res.stdout.split()
    if res.returncode != 0 or len(words) != 3:
        raise ValueError(
            f"{image} is not a patched runtime image (no /opt/ocb/VERSION.base): {res.stderr.strip()[:200]}"
        )
    return words[0], words[1], words[2]


COMPOSE_FILES = ("tests/docker-compose.yaml", "environment/docker-compose.yaml")
TOP_LEVEL = re.compile(r"^\S")
SERVICE = re.compile(r"^  ([^\s#][^:]*):\s*$")


def _swap_runtime(compose: str, old: str, image: str, base: str, version: str) -> str:
    """Within each service that runs `old` (the nodes and their daemons), the image becomes `image` and the runtime
    version the node expects `version`. Every other line is kept byte for byte: services on other images (the harness
    sidecars carry the study runtime's sources and keep expecting `base`), comments, anchors."""
    services = (yaml.safe_load(compose) or {}).get("services") or {}
    runtime = {name for name, svc in services.items() if (svc or {}).get("image") == old}
    out, service, in_services = [], None, False
    for line in compose.splitlines(keepends=True):
        if TOP_LEVEL.match(line):
            in_services, service = line.startswith("services:"), None
        elif in_services and (m := SERVICE.match(line)):
            service = m.group(1)
        if service in runtime:
            line = line.replace(f"image: {old}\n", f"image: {image}\n")
            line = line.replace(f"OCB_EXPECT_RUNTIME: {base}\n", f"OCB_EXPECT_RUNTIME: {version}\n")
        out.append(line)
    swapped = "".join(out)
    after = (yaml.safe_load(swapped) or {}).get("services") or {}
    for name, svc in services.items():  # the swap did exactly that, and nothing else
        want = dict(svc or {})
        if name in runtime:
            want["image"] = image
            env = want.get("environment")
            if isinstance(env, dict) and env.get("OCB_EXPECT_RUNTIME") == base:
                want["environment"] = {**env, "OCB_EXPECT_RUNTIME": version}
        if after.get(name) != want:
            raise ValueError(f"service {name}: the runtime image was not swapped cleanly")
    return swapped


def patched_snapshot(path: Path, image: str, version: str, base: str, dst: Path) -> Path:
    """A copy of the task snapshot whose nodes run `image` (built from source `version`) in place of the study's
    runtime image; refused unless the snapshot was rendered against `base`. Only the services that run the runtime
    image change (their image and the version they expect), and environment/images.lock records the swap;
    tests/images.lock stays as rendered, since the verifier checks it against its own (harness) image."""
    lock = (path / "environment" / "images.lock").read_text()
    runtime = next((line.split() for line in lock.splitlines() if line.split()[:1] == ["runtime"]), [])
    if len(runtime) < 3 or runtime[2] != base:
        raise ValueError(
            f"{path} was rendered against runtime {runtime[2] if len(runtime) > 2 else 'unknown'}, not {base}"
        )
    old = runtime[1]
    shutil.copytree(path, dst)
    for rel in COMPOSE_FILES:
        f = dst / rel
        if f.exists():
            f.write_text(_swap_runtime(f.read_text(), old, image, base, version))
    if f"image: {image}\n" not in (dst / COMPOSE_FILES[0]).read_text():
        raise ValueError(f"{dst / COMPOSE_FILES[0]}: no service runs the runtime image {old}")
    (dst / "environment" / "images.lock").write_text(
        lock.replace(f"runtime {old} {base}", f"runtime {image} {version}")
    )
    return dst


def register(trial: Path, result: dict, entry: dict, path: Path | None = None) -> None:
    """Record a patched re-grading's digest pair under the trial's id (written atomically)."""
    path = path or PATCHED_GRADINGS
    reg = json.loads(path.read_text()) if path.exists() else {"deviation": "ag", "trials": {}}
    reg.setdefault("trials", {})[str(result["id"])] = {
        "job": trial.parent.name, "trial": trial.name, "task": (result.get("task_name") or "").split("/")[-1], **entry,
    }  # fmt: skip
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, indent=1, sort_keys=True) + "\n")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench regrade", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("trials", nargs="+", type=Path)
    ap.add_argument("--replay", action="store_true", help="grade on the seeds each verdict recorded")
    ap.add_argument("--out", type=Path, help="where the new trial directories go")
    ap.add_argument("--runtime", help="grade on this patched runtime image (deviation ag)")
    args = ap.parse_args(argv)
    if args.replay and args.runtime:
        ap.error("--replay and --runtime do not combine")
    versions = image_versions(args.runtime) if args.runtime else None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = args.out or (RUNS / ("regrades" if args.replay else "jobs") / f"regrade-{stamp}")
    out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for trial in args.trials:
        result = json.loads((trial / "result.json").read_text())
        task = (result.get("task_name") or "").split("/")[-1]
        if args.replay:
            seeds = recorded_seeds(trial)
            if seeds is None:
                print(f"{trial}: no recorded seeds, skipped", flush=True)
                failed += 1
                continue
            path = replay_task(task, seeds, ROOT / "build" / f"replay-{stamp}-{trial.name}") / task
        else:
            try:
                path = snapshot(trial)
                if versions:
                    if (result.get("config") or {}).get("source_trial"):
                        raise ValueError("a re-grading; give the original trial")
                    version, base, build = versions
                    original = task_digest(path)
                    path = patched_snapshot(path, args.runtime, version, base,
                                            ROOT / "build" / f"patched-{stamp}-{trial.name}" / path.name)  # fmt: skip
                    entry = {"original_digest": original, "patched_digest": task_digest(path), "image": args.runtime,
                             "runtime_version": version, "base_version": base, "node_build": build}  # fmt: skip
                    register(trial, result, entry)
            except ValueError as exc:
                print(f"{trial}: {exc}; not re-graded", flush=True)
                failed += 1
                continue
        cmd = [*HARBOR, "trial", "regrade", str(trial), "-p", str(path), "-o", str(out)]
        print(" ".join(cmd), flush=True)
        failed += subprocess.run(cmd, check=False).returncode != 0
    print(f"re-graded {len(args.trials) - failed} of {len(args.trials)} into {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
