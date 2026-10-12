"""Thin helpers over the Slurm CLI, shared by the `ocb` CLI, provisioning and the verifier.

Queries fail loudly: if `scontrol` or `sinfo` cannot answer, they raise SlurmError rather than returning an empty
answer that a caller could mistake for "no jobs" or "no drained nodes". Pollers catch it and retry.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

JOB_USER = "svc-train"
SLURM_ETC = Path("/shared/etc/slurm")
HEALTH = Path("/shared/slurm/health")  # a node's health check marks it here once it has really run
HARDWARE = Path("/shared/slurm/nodeinit")  # a node marks itself here once its first-start setup took effect
TERMINAL = {
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMEOUT",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "BOOT_FAIL",
    "DEADLINE",
}


class SlurmError(RuntimeError):
    """A Slurm command failed or timed out; its answer is unknown, not empty."""


def _text(value: str | bytes | None) -> str:
    # TimeoutExpired carries bytes even when the command ran with text=True.
    return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")


def run(
    cmd: list[str], timeout: float = 30, user: str | None = None, cwd: str | None = None
) -> subprocess.CompletedProcess:
    """Run a command and return its result; never raises. A timeout returns exit code 124."""
    if user:
        cmd = ["runuser", "-u", user, "--", *cmd]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, _text(exc.stdout), _text(exc.stderr) or "timeout")
    except OSError as exc:  # the program or the working directory does not exist
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def query(cmd: list[str], timeout: float = 30) -> str:
    """Run a Slurm query; its stdout, or SlurmError when it failed."""
    res = run(cmd, timeout=timeout)
    if res.returncode != 0:
        raise SlurmError(f"{' '.join(cmd)}: exit {res.returncode}: {(res.stderr or res.stdout).strip()[:300]}")
    return res.stdout


@dataclass
class Job:
    id: str
    name: str
    user: str
    state: str
    reason: str
    nodes: str
    start: datetime | None
    end: datetime | None
    exit_code: str = ""  # "code:signal" as Slurm reports it

    @property
    def elapsed_s(self) -> float | None:
        return (self.end - self.start).total_seconds() if self.start and self.end else None


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_jobs(text: str) -> list[Job]:
    """Jobs from `scontrol show job --oneliner` output."""
    out = []
    for line in text.splitlines():
        fields = dict(re.findall(r"(\w+)=(\S*)", line))
        if "JobId" not in fields:
            continue
        out.append(
            Job(
                id=fields["JobId"],
                name=fields.get("JobName", ""),
                user=fields.get("UserId", "").split("(")[0],
                state=fields.get("JobState", ""),
                reason=fields.get("Reason", ""),
                nodes=fields.get("NodeList", ""),
                start=_parse_time(fields.get("StartTime", "")),
                end=_parse_time(fields.get("EndTime", "")),
                exit_code=fields.get("ExitCode", ""),
            )
        )
    return out


def jobs(job_ids: list[str] | None = None) -> list[Job]:
    """All jobs the controller still knows about (MinJobAge keeps finished ones), or the given ids."""
    res = run(["scontrol", "show", "job", "--oneliner"])
    if "No jobs in the system" in res.stdout + res.stderr:
        return []
    if res.returncode != 0:
        raise SlurmError(f"scontrol show job: exit {res.returncode}: {(res.stderr or res.stdout).strip()[:300]}")
    return [j for j in parse_jobs(res.stdout) if not job_ids or j.id in job_ids]


def job(job_id: str) -> Job | None:
    found = jobs([job_id])
    return found[0] if found else None


def hostnames(nodelist: str) -> list[str]:
    if not nodelist or nodelist == "(null)":
        return []
    return query(["scontrol", "show", "hostnames", nodelist]).split()


def nodes() -> dict[str, str]:
    """Node name -> state (idle, alloc, drain, down, ...)."""
    out = query(["sinfo", "-h", "-N", "-o", "%N %t"])
    return dict(line.split() for line in out.splitlines() if line.strip())


def drained_nodes() -> dict[str, str]:
    """Nodes that cannot take jobs (drained, draining, down, failed) -> "state: reason"."""
    out = query(["sinfo", "-h", "-N", "-o", "%N|%t|%E"])
    found = {}
    for line in out.splitlines():
        name, _, rest = line.partition("|")
        state, _, reason = rest.partition("|")
        if state.startswith(("drain", "drng", "down", "fail")):
            found[name.strip()] = f"{state.strip()}: {reason.strip()}"
    return found


def health_drained(drained: dict[str, str]) -> dict[str, str]:
    """The drained nodes a node health check drained (the job's configuration's doing), not ones Slurm lost contact
    with (down, failed or "Not responding": the host's)."""
    return {n: r for n, r in drained.items() if r.startswith(("drain", "drng")) and "Not responding" not in r}


def missing_hardware(names: list[str]) -> list[str]:
    """Nodes whose hardware setup (images/runtime/hwsetup.sh) has not marked itself done."""
    return [n for n in names if not (HARDWARE / n).exists()]


# Up and free for jobs: "maint" is an idle node under a maintenance reservation (also one that has not started yet);
# whether a job fits before the window is the job's concern, not the cluster's readiness.
IDLE_STATES = ("idle", "maint")


def wait_for_cluster(min_idle: int, timeout_s: float = 180, since: float | None = None) -> bool:
    """Controller up, every node's hardware set up, and min_idle nodes idle. With `since`, every node must also have
    run its health check after that time, so a node the check will drain is not mistaken for an idle one."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            if "UP" in run(["scontrol", "ping"]).stdout:
                states = nodes()
                checked = since is None or all(
                    (HEALTH / n).exists() and (HEALTH / n).stat().st_mtime >= since for n in states
                )
                idle = sum(1 for s in states.values() if s in IDLE_STATES)
                if states and checked and not missing_hardware(list(states)) and idle >= min_idle:
                    return True
        except SlurmError:
            pass  # the controller is still starting
        time.sleep(1)
    return False


def deploy_cluster_config(ops: Path) -> float:
    """Copy the ops repo's cluster config to where the daemons read it; returns the deploy time."""
    SLURM_ETC.mkdir(parents=True, exist_ok=True)
    for name in ("slurm.conf", "cgroup.conf"):
        shutil.copyfile(ops / "cluster" / name, SLURM_ETC / name)
    return time.time()


def submit(ops: Path, job_name: str, user: str = JOB_USER, timeout: float = 60) -> tuple[list[str], str]:
    """Run the job's submit.sh as `user`. Returns (new job ids, combined output)."""
    before = {j.id for j in jobs()}
    script = ops / "jobs" / job_name / "submit.sh"
    res = run(["bash", str(script)], timeout=timeout, user=user, cwd=str(script.parent))
    new = sorted({j.id for j in jobs() if j.user == user} - before, key=int)
    output = res.stdout + res.stderr
    if res.returncode == 124:
        output += f"\n[submit.sh did not exit within {timeout:.0f}s and was stopped]"
    return new, output
