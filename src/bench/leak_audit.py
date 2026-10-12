"""Agent's-eye leak audit: what can an agent read or reach in a task's environment?

  uv run python -m bench.leak_audit TASK [TASK ...]

Brings up the task's agent environment as Harbor would (main + sidecars), waits for provisioning to finish
(/shared/evidence/READY), then, as root in the workstation and in every node (what an agent with ssh has), lists:
files outside OS paths that mention task or harness terms, environment variables of every process, process command
lines, listening sockets, mounts, logs, and docker sockets. Anything here that a practitioner on the real system would
not see is a leak. Writes results/leak-audit/<task>.md, stamped.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

from bench.paths import ROOT, project_name
from bench.provenance import describe, stamp, task_digest
from bench.spec import task_dir

OUT = ROOT / "results" / "leak-audit"

# The task id must not reach the agent either: Harbor names a trial's compose project after the task directory, so
# `bench run` builds under opaque names (bench.run.opaque_name). The audit brings its environment up under an opaque
# project too and then greps the id wherever the gate's agents found it (hostnames, scheduler records, mounts, logs).
ID_PROBE = r"""
echo "### task id: places the agent reads, grepped for {taskid}"
( hostname -f; hostname; cat /etc/hosts; getent hosts c1 c2 c3 main engine objstore slurmctld 2>/dev/null;
  scontrol show job 2>/dev/null; scontrol show node 2>/dev/null | grep -iE 'NodeName|Reason';
  cat /proc/mounts; findmnt -rn 2>/dev/null; for e in /proc/[0-9]*/environ; do tr '\0' '\n' < "$e" 2>/dev/null; done;
  grep -rIl '{taskid}' /shared /etc /opt /tmp /var/log 2>/dev/null ) 2>/dev/null | grep -F '{taskid}' | sort -u | head -20
echo "### task id hits: $( ( hostname -f; cat /etc/hosts; scontrol show job 2>/dev/null; cat /proc/mounts; for e in /proc/[0-9]*/environ; do tr '\0' '\n' < "$e" 2>/dev/null; done ) 2>/dev/null | grep -cF '{taskid}' )"
"""

# The agent's own view: docker exec inherits a container's configured environment, which no ssh session
# gets, so the per-container probes above over-report variables. From the workstation, each other service is tried over
# ssh as the agent would, and every OCB_ variable any of its processes carries is listed with its value.
AGENT_VIEW = r"""
for p in /proc/[0-9]*; do
  vars=$(tr '\0' '\n' < $p/environ 2>/dev/null | grep -E '^OCB_' | grep -vE '^OCB_EXPECT_' | tr '\n' ' ')
  [ -n "$vars" ] && echo "pid ${p#/proc/} [$(tr '\0' ' ' < $p/cmdline 2>/dev/null | cut -c1-70)]: $vars"
done
echo "reachable as $(id -un)"
"""

# Terms that should not appear anywhere the agent can read (beyond /ops and the evidence it is meant to have).
TERMS = (
    r"\b(solution|wrong_fix|wrong_fixes|pristine|calibrat[a-z]*|emulat[a-z]*|bootstrap\.yaml|verify\.yaml|"
    r"OCB_[A-Z_]+|teacher|canary|oracle|harbor|benchmark|injected|ablation|gpu_symptom|provenance|reward)\b"
)

PROBE = r"""
set +e
echo "## whoami: $(id -un) on $(hostname)"
echo "### files mentioning task/harness terms (outside /ops, /proc, /sys, /usr/lib*, /usr/share, python site-packages)"
for d in /opt /usr/local /etc/platform /etc/slurm /etc/hosts /etc/profile.d /etc/environment /etc/bashrc \
         /etc/bash.bashrc /etc/sysconfig /etc/default /shared /var/log /root /home /tmp /srv /run; do
    [ -e "$d" ] && grep -rIlE '{terms}' "$d" --exclude-dir=spack --exclude-dir=modulefiles --exclude-dir=__pycache__ --exclude-dir=lib --exclude-dir=lib64 --exclude-dir=share \
        --exclude-dir=logs --exclude-dir=metrics 2>/dev/null
done | grep -vE '^/var/log/dnf|^/root/examples' | head -120
echo "### environment variables of all processes (names only, non-standard; this probe's own session left out)"
self_sid=$(ps -o sid= -p $$ | tr -d ' ')
for e in /proc/[0-9]*/environ; do p=${e#/proc/}; p=${p%/environ}
  [ "$(ps -o sid= -p "$p" 2>/dev/null | tr -d ' ')" = "$self_sid" ] && continue
  tr '\0' '\n' < "$e" 2>/dev/null; done | cut -d= -f1 | sort -u | grep -vE '^(PATH|HOME|HOSTNAME|TERM|LANG|LC_.*|SHLVL|PWD|OLDPWD|_|container|SHELL|USER|LOGNAME|MAIL|SLURM_CONF|PYTHONPATH|PYTHONDONTWRITEBYTECODE|OMP_NUM_THREADS|SSH_.*|MOTD_SHOWN|XDG_.*|DBUS_.*|LS_COLORS|HISTSIZE|HISTCONTROL|SLURMD_NODENAME|SLURM_.*|TORCH_.*|GLOO_.*|PYTHONUNBUFFERED|LOCAL_RANK|RANK|WORLD_SIZE|LOCAL_WORLD_SIZE|GROUP_.*|ROLE_.*|MASTER_.*|TORCHELASTIC_.*|CUDA_.*|NCCL_.*)$'
echo "### processes"
ps -eo user,args --no-headers | cut -c1-200 | grep -vE '^\S+ +(ps|cut|grep|bash -c|sh -c|sleep|/bin/sh|-bash)' | sort -u | head -150
echo "### listening sockets"
(ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null || awk 'NR>1 && $4=="0A" {{print "listen", $2}}' /proc/net/tcp /proc/net/tcp6) | head -20
echo "### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)"
grep -vE ' (proc|sysfs|devpts|mqueue|cgroup2?|overlay|securityfs|debugfs|tracefs) ' /proc/mounts \
    | grep -vE '^tmpfs /(dev|proc/[a-z_]+|sys/[a-z_/]+|dev/shm) ' | head -20
echo "### names: reverse lookups of every interface address, and the hosts file"
for a in $(ip -o -4 addr show 2>/dev/null | awk '{{print $4}}' | cut -d/ -f1); do echo "$a -> $(getent hosts "$a" | awk '{{print $2}}')"; done
cat /etc/hosts 2>/dev/null | grep -v '^#'
echo "### scheduler: reservations and partitions"
scontrol show reservation 2>/dev/null | head -10; scontrol show partition 2>/dev/null | grep -E 'PartitionName|MaxTime|State' | head -6
echo "### object store response headers"
curl -sI -m 5 http://objstore:8000/datasets/ 2>/dev/null | head -8
echo "### environment of non-job processes not started by a login (names only)"
own=$(ps -o sid= -p $$ | tr -d ' ')
for d in /proc/[0-9]*; do u=$(stat -c %U "$d" 2>/dev/null); [ "$u" = svc-train ] && continue
  [ "$(ps -o sid= -p "${d#/proc/}" 2>/dev/null | tr -d ' ')" = "$own" ] && continue  # this probe (docker exec env)
  names=$(tr '\0' '\n' < "$d/environ" 2>/dev/null | cut -d= -f1 | grep -E '^OCB_' | tr '\n' ' ')
  [ -n "$names" ] && printf '%s %s: %s\n' "${d#/proc/}" "$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null | cut -c1-60)" "$names"
done | sort -u | head -10
echo "### GPUs: device files here (only the GPU node may have them), site GPU and NCCL config, GPU variables"
ls /dev/nvidia* 2>/dev/null | tr '\n' ' '; echo
for f in /etc/nccl.conf /etc/nvidia* /etc/profile.d/*; do [ -f "$f" ] && echo "-- $f ($(stat -c %y "$f" | cut -c1-19))" && head -5 "$f"; done 2>/dev/null
for d in /proc/[0-9]*; do u=$(stat -c %U "$d" 2>/dev/null); [ "$u" = svc-train ] && continue; tr '\0' '\n' < "$d/environ" 2>/dev/null | grep -E '^(NCCL|CUDA|NVIDIA|TORCH_NCCL)_' | sed "s|^|$(basename "$d"): |"; done | sort -u | head -20
echo "### docker sockets / credentials"
ls -la /var/run/docker.sock /run/docker.sock 2>/dev/null; ls -la /root/.docker 2>/dev/null
echo "### logs"
ls -la /var/log 2>/dev/null | grep -vE 'dnf|hawkey|lastlog|wtmp|btmp|tallylog|^total' | head
for d in /opt /opt/* /usr/local/bin /usr/local/libexec /etc/platform /root; do
    [ -d "$d" ] && echo "### ls $d" && ls -la "$d" 2>/dev/null | head -40
done
echo "### site configuration files"
for f in /etc/platform/*; do [ -f "$f" ] && echo "-- $f ($(stat -c '%s bytes, %y' "$f" | cut -c1-40))" && head -20 "$f"; done
"""


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def audit(task: str) -> Path:
    env_dir = task_dir(task) / "environment"
    project = project_name("leak", hashlib.sha256(task.encode()).hexdigest()[:10])  # as opaque as a trial's
    override = Path(tempfile.mkdtemp()) / "main.yaml"
    override.write_text("services:\n  main:\n    build: {context: .}\n    command: [sleep, infinity]\n")
    compose = ["docker", "compose", "-p", project, "-f", str(env_dir / "docker-compose.yaml"), "-f", str(override)]
    report = [
        f"# Leak audit: {task}",
        "",
        f"Run on the agent environment after provisioning. {describe(stamp())}; task {task_digest(task_dir(task))}.",
        "",
    ]
    try:
        sh([*compose, "up", "-d", "--build"], cwd=env_dir, timeout=900)
        main = f"{project}-main-1"
        for _ in range(200):
            if sh(["docker", "exec", main, "test", "-f", "/shared/evidence/READY"]).returncode == 0:
                break
            time.sleep(3)
        services = yaml.safe_load((env_dir / "docker-compose.yaml").read_text())["services"]
        for svc in services:
            ctr = f"{project}-{svc}-1"
            probe = PROBE.format(terms=TERMS) + ID_PROBE.format(taskid=task)
            res = sh(["docker", "exec", ctr, "bash", "-c", probe], timeout=300)
            report += [f"## container `{svc}`", "", "```", res.stdout.strip()[:200000], "```", ""]
            if res.stderr.strip():
                report += ["stderr:", "", "```", res.stderr.strip()[:4000], "```", ""]
        report += ["## the agent's view (ssh from the workstation)", ""]
        for svc in services:
            target = ["bash", "-c", AGENT_VIEW] if svc == "main" else [
                "bash", "-c", f"timeout 30 ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 {svc} "
                f"'bash -s' <<'EOF'\n{AGENT_VIEW}\nEOF"]  # fmt: skip
            res = sh(["docker", "exec", main, *target], timeout=120)
            out = res.stdout.strip()
            if "reachable as" not in out:
                tail = (res.stderr or res.stdout).strip().splitlines()
                out = "not reachable: " + (tail[-1][:120] if tail else "no output")
            report += [f"- `{svc}`: " + out.replace("\n", "; ")]
        report.append("")
    finally:
        sh([*compose, "down", "-v"], cwd=env_dir, timeout=300)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{task}.md"
    out.write_text("\n".join(report) + "\n")
    return out


def main(argv: list[str] | None = None) -> None:
    for name in sys.argv[1:] if argv is None else argv:
        print("wrote", audit(name).relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
