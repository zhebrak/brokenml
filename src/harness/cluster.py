"""The shared volume's layout and the read-only checkpoint store: set up the same way for the agent's cluster
(provisioning sidecar) and the verifier's fresh one."""

from __future__ import annotations

import shutil
from pathlib import Path

from harness.config import Site
from ocb import slurm

SHARED = Path("/shared")
EVIDENCE = SHARED / "evidence"


def prepare_shared() -> None:
    for d in ("etc/slurm", "logs", "out", "data", "slurm", "metrics", "ckpt", "evidence/fr"):
        (SHARED / d).mkdir(parents=True, exist_ok=True)
    shutil.chown(SHARED / "slurm", "slurm", "slurm")
    for d in ("logs", "out", "metrics", "ckpt", "evidence/fr"):
        shutil.chown(SHARED / d, "svc-train", "svc-train")


def install_store(src: Path) -> None:
    """Checkpoint-resume tasks: a read-only store of earlier checkpoints at /shared/ckpt-store."""
    dst = SHARED / "ckpt-store"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("teacher.json"))
    for path in [dst, *dst.rglob("*")]:
        path.chmod(0o555 if path.is_dir() else 0o444)


def apply_site(site: Site | None) -> None:
    """Create the site's reservations and queue its other users' jobs that do not exist yet (the controller keeps
    them across runs)."""
    for r in site.reservations if site else []:
        if slurm.run(["scontrol", "show", "reservation", r.name]).returncode == 0:
            continue
        res = slurm.run(["scontrol", "create", "reservation", f"ReservationName={r.name}",
                         f"StartTime=now+{r.start_in_min}minutes", f"Duration={r.duration_min}", "Nodes=ALL",
                         f"Users={r.users}", f"Flags={r.flags}"])  # fmt: skip
        if res.returncode != 0:
            raise RuntimeError(f"reservation {r.name} not created: {(res.stderr or res.stdout).strip()}")
    for j in site.jobs if site else []:
        if slurm.run(["squeue", "-h", "-u", j.user, "-n", j.name, "-o", "%i"]).stdout.strip():
            continue  # already queued (the controller keeps it across runs)
        cmd = ["sbatch", f"--job-name={j.name}", f"--begin=now+{j.begin_in_min}minutes", f"--time={j.time_min}",
               "--output=/dev/null", "--wrap=sleep 60"] + ([f"--comment={j.comment}"] if j.comment else [])  # fmt: skip
        res = slurm.run(cmd, user=j.user)
        if res.returncode != 0:
            raise RuntimeError(f"site job {j.name} not queued: {(res.stderr or res.stdout).strip()}")
