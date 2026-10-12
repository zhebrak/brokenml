"""Can this host run the benchmark, and how many trials at once?

  uv run bench doctor

Checks Docker, Compose and Harbor, counts physical cores and memory, and lists the bench images with their IDs.
Leaderboard runs use one trial at a time (throughput rules compare two timed runs on one host, so a busy host moves
verdicts: docs/leaderboard.md); the upper bound printed for larger hosts, one trial per 8 physical cores and 8 GB
(each trial's cluster, then its verifier's, takes about 8 CPUs), is a rule of thumb until measured.
The study's images are on GHCR (images/study-images.json): `make image-pull` fetches them by
digest, `make image` rebuilds them (other ids), and doctor says which the host has. Exits non-zero when something
required is missing.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

from bench.provenance import image_ids, image_tags, study_image_status, study_images

CPUS_PER_TRIAL = 8
MEMORY_PER_TRIAL_GB = 8
HARBOR_VERSION = "0.23.0"


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def image_store() -> str:
    """The daemon's image store: "containerd" (Docker 29's default), "classic" (overlay2 and the other graph drivers)
    or "" when Docker does not say. Protocol validation compares image IDs that only the containerd store reports as
    the study's (the OCI index digest), so the classic store makes `bench protocol` refuse."""
    status = _run(["docker", "info", "--format", "{{range .DriverStatus}}{{index . 0}}={{index . 1}} {{end}}"])
    if "io.containerd.snapshotter" in status:
        return "containerd"
    driver = _run(["docker", "info", "--format", "{{.Driver}}"])
    return "classic" if driver else ""


def study_image_lines(local_ids: dict[str, str]) -> list[str]:
    """One line per study image (images/study-images.json) for what this host holds under its local tag (role ->
    local image id). Informational: a rebuilt or classic-store image runs trials, but is not the study's."""
    lines = []
    for role, e in study_images()["images"].items():
        local = local_ids.get(role, "")
        status = study_image_status(role, local)
        short = f"({local[7:15]}\u2026)"
        if status == "study":
            what = f"study build ({e['id'][7:15]}\u2026)"
        elif status == "classic-store":
            what = ("classic image store (config digest matches): bench protocol validation needs the containerd "
                    "image store; see docs/hosts.md")  # fmt: skip
        elif status == "rebuilt":
            what = f"rebuilt locally {short}: published rows ran on the study images; make image-pull"
        else:
            what = "not present: make image-pull or make image"
        lines.append(f"study image {role}: {what}")
    return lines


def physical_cores() -> int:
    """Distinct (physical id, core id) pairs in /proc/cpuinfo; logical CPUs when the file does not say."""
    try:
        text = Path("/proc/cpuinfo").read_text()
    except OSError:
        return os.cpu_count() or 1
    pairs = set(re.findall(r"physical id\s*:\s*(\d+)[\s\S]*?core id\s*:\s*(\d+)", text))
    return len(pairs) or (os.cpu_count() or 1)


def memory_gb() -> float:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 1024**2
    except OSError:
        pass
    return 0.0


def safe_concurrency(cores: int, mem_gb: float) -> int:
    return max(0, min(cores // CPUS_PER_TRIAL, int(mem_gb // MEMORY_PER_TRIAL_GB)))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench doctor", description=(__doc__ or "").split("\n")[0])
    ap.parse_args(argv)
    problems = []
    docker = _run(["docker", "version", "--format", "{{.Server.Version}}"])
    compose = _run(["docker", "compose", "version", "--short"])
    harbor = _run(["harbor", "--version"]) if shutil.which("harbor") else ""
    print(f"docker server   {docker or 'MISSING'}")
    print(f"docker compose  {compose or 'MISSING'}")
    print(f"harbor          {harbor or 'MISSING'} (the benchmark is pinned to {HARBOR_VERSION})")
    if not docker:
        problems.append("Docker is not reachable")
    if not compose:
        problems.append("Docker Compose v2 is missing")
    if not harbor:
        problems.append(f"Harbor is missing (uv tool install harbor=={HARBOR_VERSION})")
    elif HARBOR_VERSION not in harbor:
        problems.append(f"Harbor {harbor} is not {HARBOR_VERSION}")
    cores, mem = physical_cores(), memory_gb()
    n = safe_concurrency(cores, mem)
    print(f"physical cores  {cores} (logical {os.cpu_count()}), memory {mem:.0f} GB")
    from bench.concurrency import measured  # here: concurrency imports this module's helpers

    safe = measured()
    if safe is not None:
        print(f"concurrency     -n {safe} measured for this host class and these images, where throughput verdicts "
              "stay unchanged (bench concurrency; results/concurrency.json)")  # fmt: skip
    else:
        print(f"concurrency     -n 1 until `bench concurrency` measures this host (rule of thumb: one trial per "
              f"{CPUS_PER_TRIAL} physical cores and {MEMORY_PER_TRIAL_GB} GB gives {n})")  # fmt: skip
    if n < 1:
        problems.append(f"fewer than {CPUS_PER_TRIAL} physical cores or {MEMORY_PER_TRIAL_GB} GB: trials will be slow "
                        "and throughput verdicts unreliable")  # fmt: skip
    ids = image_ids() if docker else {}
    for role, ref in image_tags().items():
        found = ids.get(ref) or ""
        print(f"image {role:13} {ref}  {found or 'NOT BUILT'}")
        if not found and role != "runtime-cuda":  # the CUDA image is only for the GPU track
            problems.append(f"{ref} is missing (make image-pull; or make image to rebuild)")
    if docker:
        store = image_store()
        if store:
            note = "" if store == "containerd" else " (bench protocol needs the containerd store: docs/hosts.md)"
            print(f"image store     {store}{note}")
        entries = study_images()["images"]
        lines = study_image_lines(
            {role: _run(["docker", "image", "inspect", "-f", "{{.Id}}", e["tag"]]) for role, e in entries.items()}
        )
        for line in lines:
            print(line)
    print("images          the study's are on GHCR (images/study-images.json): make image-pull fetches them by digest")
    for p in problems:
        print(f"PROBLEM: {p}")
    if problems:
        raise SystemExit(1)
    print("ok")


if __name__ == "__main__":
    main()
