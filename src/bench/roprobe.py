"""Is the logs variant's workstation read-only by construction, and what can it see? (QA for the live-logs arm)

    uv run bench readonly-probe [TASK ...] [--split test|dev|all] [--jobs 2] [--keep]
    uv run bench readonly-probe --fidelity [TASK ...]

For each task: renders the logs variant, brings its agent environment up the way Harbor does, waits for READY and the
observer's first views, and checks from the workstation as root (the agent's strongest position):

  network      only a loopback interface and no route; no cluster hostname resolves; no TCP connection to any port any
               cluster container listens on, nor to the Docker host's own addresses (connection refused counts as a
               route); the observer, inside the cluster, reaches the same cluster ports (the control)
  credentials  no ssh private key, munge key or /run/cluster-keys anywhere, shared mounts included
  mounts       every mount shared with the cluster refuses creating, appending, truncating, removing, chmod, links and
               remount, and holds no socket or FIFO (a read-only mount does not stop either)
  ops          a marker written to the workstation's /ops never reaches the cluster's /ops
  writes       every command that would change the cluster refuses (wrappers and the real binaries), and none leaves a
               trace: no new job, no job cancelled or held, no node reason `probe`, the same reservations, no
               reconfiguration; on serving, no restart trigger, no restart request, no tokens served
  reads        the read commands answer (the job and the nodes are listed; the engine's views are fresh)
  liveness     a line a node writes during the probe shows in /shared at once and in /obs within a refresh or two
  leaks        nothing under /obs or /store names the setup machinery; the submit host's name (`provision`), which the
               standard variant shows too (AllocNode in `scontrol show job`), is counted, not failed

It also runs the task's evidence probes (spec `probes`, written before any agent ran) in the workstation, verbatim and
with engine, store and node-counter reads pointed at their /obs copies; a probe whose output is a refusal ("not
available here") is not visible, whatever it printed after. The per-task covariate "the task's evidence probes visible
read-only" is true when every probe of the task is visible either way (docs/variants.md, Live logs).

Rows go to results/readonly-probe.json, each with the stamp of the probe run that made it (taken once at start, with a
hash of the probe and of the variant's programs, and the working tree's state outside results/); exits non-zero if any
task fails a check. `--fidelity` replays every read-only scheduler command form the study's full-arm agents typed
(results/readonly-commands.json) through the real client inside the cluster and through the wrappers, right after a
fresh snapshot, and compares the outputs (results/readonly-fidelity.json); by default on the tasks whose scheduler state
is the evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bench.access import classify
from bench.bootcheck import MAIN_OVERRIDE, merge_row, sh
from bench.paths import RESULTS, ROOT, project_name
from bench.provenance import stamp, task_digest
from bench.render import render
from bench.spec import by_id, load_specs

OUT = RESULTS / "readonly-probe.json"
COMMANDS = RESULTS / "readonly-commands.json"  # every scheduler command form the study's full-arm agents typed
FIDELITY = RESULTS / "readonly-fidelity.json"
FIDELITY_TASKS = ("realmemory-drain", "wait-on-heartbeat", "monitor-step-blocks", "failed-dependency",
                  "gres-from-gpu-template", "degraded-node", "outlives-time-limit")  # fmt: skip
LEAK = re.compile(r"OCB_[A-Z_]+|/opt/task|bootstrap\.yaml|store\.yaml|teacher_seed|\bharness\b|hwsetup|ocb-keys|"
                  r"cluster-keys|/opt/store|imagelock|BEGIN OPENSSH PRIVATE KEY")  # fmt: skip
PARITY = re.compile(r"\bprovision\b")
REFUSAL = re.compile(r"not available here")
WRITES_SLURM = [
    "sbatch --wrap hostname", "/usr/bin/sbatch --wrap hostname", "srun -N1 hostname", "/usr/bin/srun -N1 hostname",
    "salloc -N1 true", "scancel {job}", "/usr/bin/scancel {job}", "scontrol update NodeName={node} State=DRAIN "
    "Reason=probe", "/usr/bin/scontrol update NodeName={node} State=DRAIN Reason=probe", "scontrol reconfigure",
    "scontrol hold {job}", "ocb submit train", "python3 -m ocb.cli submit train", "ocb cluster apply",
    "python3 -m ocb.cli cluster apply", "ocb dump {job}", "ssh {node} true",
    "/usr/bin/ssh -o BatchMode=yes {node} true", "curl -s -m 3 -X PUT --data x http://objstore:8000/replicas/probe",
]  # fmt: skip
WRITES_SERVING = [
    "curl -s -m 3 http://engine:8080/health", "curl -s -m 3 -X POST -d '{\"prompt\":\"x\"}' http://engine:8080/completion",
    "timeout 20 python3 -m ocb.serving http://engine:8080 | grep -q '\"tokens_per_s\": [1-9]'",
    "touch /shared/engine/restart", "ssh engine true",
]  # fmt: skip
# The effective capability set Docker gives a container by default (no cap_add), as /proc/<pid>/status prints it.
DEFAULT_CAPS = {"00000000a80425fb"}
HOST_PORTS = (22, 80, 443, 2375, 2376, 5678, 8000, 8080, 8081, 9090)  # with every port the host listens on


def run_stamp() -> dict:
    """The probe run's own provenance, taken once at start: the commit, whether the tree outside results/ differs from
    it, and a hash of the probe and of the variant's programs as loaded."""
    here = Path(__file__).parent
    code = hashlib.sha256()
    for path in (here / "roprobe.py", here / "render.py", here / "readonly" / "collect.py",
                 here / "readonly" / "tools.py", here / "access.py"):  # fmt: skip
        code.update(path.read_bytes())
    dirty = subprocess.run(["git", "status", "--porcelain", "--", ".", ":(exclude)results"], cwd=ROOT,
                           capture_output=True, text=True, check=False).stdout.strip()  # fmt: skip
    return {**stamp(), "git_dirty": bool(dirty), "probe_code": code.hexdigest()[:16]}


def dx(container: str, script: str, timeout: float = 120) -> tuple[int, str]:
    """A login shell in a container (the agent's PATH), output merged."""
    try:
        res = sh(["docker", "exec", container, "bash", "-lc", script], timeout=timeout)
        return res.returncode, (res.stdout or "") + (res.stderr or "")
    except Exception as exc:  # noqa: BLE001 - a hung exec is a failed check, not a crashed probe
        return 124, f"{type(exc).__name__}: {exc}"


def containers(project: str) -> dict[str, str]:
    """service -> container name, for the project's running containers."""
    out = sh(["docker", "ps", "--filter", f"label=com.docker.compose.project={project}", "--format",
              '{{.Label "com.docker.compose.service"}} {{.Names}}'])  # fmt: skip
    return dict(line.split() for line in out.stdout.splitlines() if line.strip())


def listening(container: str) -> list[int]:
    """TCP ports a container listens on (/proc/net/tcp and tcp6, state 0A)."""
    out = sh(["docker", "exec", container, "sh", "-c", "cat /proc/net/tcp /proc/net/tcp6 2>/dev/null"]).stdout
    ports = {int(f[1].rsplit(":", 1)[1], 16) for f in (line.split() for line in out.splitlines()[1:])
             if len(f) > 3 and f[3] == "0A" and ":" in f[1]}  # fmt: skip
    return sorted(ports)


def host_targets() -> list[str]:
    """The Docker host's own IPv4 addresses (its interfaces and every bridge gateway), on the ports it listens on and
    the usual service ports: what a container reaches through a bridge's gateway."""
    addrs = re.findall(r"inet (\d+\.\d+\.\d+\.\d+)/", sh(["ip", "-4", "-o", "addr", "show"]).stdout)
    ports = {int(m) for m in re.findall(r"\s(?:\d+\.\d+\.\d+\.\d+|\*|0\.0\.0\.0|\[::\]):(\d+)\s",
                                        sh(["ss", "-ltnH"]).stdout)}  # fmt: skip
    return [f"{a}:{p}" for a in addrs if not a.startswith("127.") for p in sorted(ports | set(HOST_PORTS))]


CONNECT = """python3 - <<'EOF'
import errno, json, socket
out = {{}}
for target in {targets!r}:
    ip, port = target.rsplit(":", 1)
    s = socket.socket(); s.settimeout(1.5)
    try:
        s.connect((ip, int(port))); out[target] = "ok"
    except socket.timeout:
        out[target] = "timeout"
    except OSError as e:
        out[target] = errno.errorcode.get(e.errno, str(e.errno))
    finally:
        s.close()
print(json.dumps(out))
EOF"""
REACHED = ("ok", "ECONNREFUSED")  # a refusal came from a host that the packet reached: a route exists


def connect(container: str, targets: list[str]) -> dict[str, str]:
    _, out = dx(container, CONNECT.format(targets=targets), timeout=60 + 2 * len(targets))
    try:
        return json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": out[-300:]}


MOUNT_WRITES = r"""for d in {dirs}; do
  [ -d "$d" ] || continue
  for op in "touch $d/.probe" "mkdir $d/.probe-dir" "chmod 777 $d" "ln -s / $d/.probe-link" "mv $d $d.moved"; do
    sh -c "$op" 2>/dev/null && echo "WROTE: $op"
  done
  f=$(find "$d" -maxdepth 2 -type f 2>/dev/null | head -n 1)
  if [ -n "$f" ]; then
    sh -c "echo x >> '$f'" 2>/dev/null && echo "APPENDED: $f"
    sh -c "truncate -s 0 '$f'" 2>/dev/null && echo "TRUNCATED: $f"
    sh -c "ln '$f' $d/.probe-hard" 2>/dev/null && echo "LINKED: $f"
    sh -c "rm -f '$f'" 2>/dev/null && [ ! -e "$f" ] && echo "REMOVED: $f"
  fi
  mount -o remount,rw "$d" 2>/dev/null && echo "REMOUNTED: $d"
done; echo checked"""
SHARED_MOUNTS = "/shared /shared/logs /shared/evidence /shared/metrics /shared/ckpt /shared/engine /obs /obs/slurm " \
    "/store/datasets"  # fmt: skip

OBS_GET = {
    r"curl[^|;&]*?https?://engine:8080/(health|slots|metrics|props)\S*": "/obs/engine/{0}",
    r"curl[^|;&]*?https?://objstore:8000/replicas/?\S*": "/obs/store/replicas.json",
}
# A node's cgroup counters and filesystems, read over ssh in the standard variant, from its section of `ocb nodes`
# (/obs/nodes/ocb-nodes.txt): "=== HOST" blocks of "--- memory.events", "--- cpu.max", ..., "--- filesystems".
NODE_SECTION = (
    "python3 -c \"import sys; h,f=sys.argv[1:3]; t=open('/obs/nodes/ocb-nodes.txt').read(); "
    "b=t.split('=== '+h+chr(10),1)[1].split(chr(10)+'=== ',1)[0]; print(b.split('--- '+f+chr(10),1)[1]"
    ".split(chr(10)+'--- ',1)[0])\" {host} {section}"
)
OBS_NODE = {
    r"ssh(?: -o \S+)* (\$?\w+) cat /sys/fs/cgroup/([\w.]+)": lambda m: NODE_SECTION.format(host=m[1], section=m[2]),
    r"ssh(?: -o \S+)* (\$?\w+) df -h\w* \S+": lambda m: NODE_SECTION.format(host=m[1], section="filesystems"),
}


def via_obs(command: str) -> str:
    """A probe command with GETs to the engine and the store's listing, and reads of a node's cgroup counters and
    filesystems, replaced by reads of their copies in /obs (what the engine views and `ocb nodes` show)."""
    for pattern, path in OBS_GET.items():
        command = re.sub(pattern, lambda m, p=path: f"cat {p.format(*m.groups())}", command)
    for pattern, replace in OBS_NODE.items():
        command = re.sub(pattern, replace, command)
    return command


def evidence(main: str, probes) -> list[dict]:
    """Each probe in the workstation, verbatim and via /obs: visible if either matches its regex without a refusal."""
    out = []
    for probe in probes:
        row = {"run": probe.run, "expect": probe.expect}
        for key, command in (("verbatim", probe.run), ("via_obs", via_obs(probe.run))):
            _, text = dx(main, command, timeout=180)
            refused = bool(REFUSAL.search(text))
            row[key] = {"ok": bool(re.search(probe.expect, text, re.S)) and not refused, "refused": refused,
                        "excerpt": text[-400:]}  # fmt: skip
        row["visible"] = row["verbatim"]["ok"] or row["via_obs"]["ok"]
        out.append(row)
    return out


def slurm_traces(names: dict[str, str]) -> dict:
    """What a write would leave on the cluster (read from the controller as root)."""
    ctld = names["slurmctld"]
    query = lambda cmd: sh(["docker", "exec", ctld, "sh", "-c", cmd]).stdout
    jobs = [line.split("|") for line in query("squeue -h -t all -o '%i|%T|%r|%j'").splitlines() if line.strip()]
    return {
        "jobs": sorted(j[0] for j in jobs),
        "cancelled_or_held": sorted(j[0] for j in jobs if j[1] == "CANCELLED" or "Held" in j[2]),
        "wrap_jobs": sorted(j[0] for j in jobs if len(j) > 3 and j[3] == "wrap"),
        "probe_reasons": query("sinfo -h -N -o '%N|%E' | grep -i '|probe' || true").split(),
        "reservations": query("scontrol show reservation"),
        "reconfigures": query("grep -ci 'reconfigur' /var/log/slurm/slurmctld.log || true").strip(),
    }


def serving_traces(names: dict[str, str]) -> dict:
    engine = names["engine"]
    query = lambda cmd: sh(["docker", "exec", engine, "sh", "-c", cmd]).stdout.strip()
    metrics = dx(names["obs"], "python3 -c \"import urllib.request; print(urllib.request.urlopen("
                 "'http://engine:8080/metrics', timeout=5).read().decode())\"")[1]  # fmt: skip
    served = re.search(r"^llamacpp:prompt_tokens_total (\S+)", metrics, re.M)
    return {
        "restart_trigger": query("stat -c %Y /shared/engine/restart 2>/dev/null || echo absent"),
        "restart_requests": query("grep -c 'restart requested' /shared/logs/engine.log || true"),
        "prompt_tokens": served.group(1) if served else "engine not answering",
    }


def check(task: str, keep: bool = False, run: dict | None = None) -> dict:
    spec = by_id(task)
    work = Path(tempfile.mkdtemp(prefix="bench-roprobe-"))
    rendered = render(spec, work, "logs")
    env = rendered / "environment"
    override = work / "main.yaml"
    override.write_text(MAIN_OVERRIDE)
    project = project_name("ro", task)
    compose = ["docker", "compose", "-p", project, "-f", str(env / "docker-compose.yaml"), "-f", str(override)]
    serving = spec.substrate == "serving"
    checks: dict[str, dict] = {}
    row: dict = {"task": task, "substrate": spec.substrate, "task_digest": task_digest(rendered)}
    t0 = time.time()

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks[name] = {"ok": bool(ok), "detail": detail[-1500:]}

    try:
        up = sh([*compose, "up", "-d", "--wait", "--build"], cwd=env, timeout=1200)
        if up.returncode != 0:
            record("up", False, (up.stderr or up.stdout)[-1500:])
            return row
        names = containers(project)
        main = names["main"]
        state = "waiting"
        while time.time() - t0 < spec.bootstrap_timeout_s + 300:
            if dx(main, "test -f /shared/evidence/SETUP_FAILED")[0] == 0:
                state = "setup failed: " + dx(main, "cat /shared/evidence/SETUP_FAILED")[1][:300]
                break
            if dx(main, "test -f /obs/SNAPSHOT_AT && test -f /shared/evidence/READY")[0] == 0:
                state = "ready"
                break
            time.sleep(4)
        symptom = dx(main, "cat /shared/evidence/symptom.json 2>/dev/null")[1]
        try:
            row["symptom"] = json.loads(symptom) if symptom.strip() else None
        except ValueError:
            row["symptom"] = None
        record("up", state == "ready" and bool((row["symptom"] or {}).get("observed")), state)
        if state != "ready":
            return row
        cluster = {s: c for s, c in names.items() if s not in ("main", "keys")}

        # network: no interface but loopback, no route, no names; nothing reachable, the host included
        _, links = dx(main, "ls /sys/class/net | tr '\\n' ' '; echo '|'; ip -4 route 2>&1; ip -6 route 2>&1 | "
                      "grep -v ' dev lo ' || true")  # fmt: skip
        interfaces, _, routes = links.partition("|")
        record("no-network", interfaces.split() == ["lo"] and routes.strip() == "", links)
        _, out = dx(main, "for h in " + " ".join([*cluster, "slurmctld", "objstore", "engine", "provision"])
                    + "; do getent hosts $h >/dev/null && echo RESOLVES $h; done; true")  # fmt: skip
        record("no-names", "RESOLVES" not in out, out)
        targets = []
        for container in cluster.values():
            ips = sh(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                      container]).stdout.split()  # fmt: skip
            targets += [f"{ip}:{port}" for ip in ips for port in listening(container) or [22]]
        hosts = host_targets()
        from_main = connect(main, targets + hosts)
        from_obs = connect(names["obs"], targets)
        reached = sorted(t for t, r in from_main.items() if r in REACHED or t == "error")
        control = sorted(t for t, r in from_obs.items() if r in REACHED)
        record("no-route", not reached and bool(control),
               f"{len(targets)} cluster and {len(hosts)} host targets; reached from main: {reached[:20]}; "
               f"outcomes from main: {sorted(set(from_main.values()))}; control from obs: {control[:10]}")  # fmt: skip

        # credentials, shared mounts included
        _, out = dx(main, "ls -A /run/cluster-keys 2>/dev/null; find / \\( -path /proc -o -path /sys -o -path /usr "
                    "-o -path /dev \\) -prune -o -type f \\( -name 'id_*' -o -name '*.key' -o -name 'munge.key' \\) "
                    "-not -path '/etc/ssh/ssh_host_*' -print 2>/dev/null; grep -rIl 'PRIVATE KEY' /root /etc /run "
                    "/tmp /var /opt /shared /obs /store 2>/dev/null | grep -v '^/etc/ssh/ssh_host_'; true",
                    timeout=300)  # fmt: skip
        record("no-credentials", out.strip() == "", out)

        # read-only mounts, and no socket or FIFO in them (a read-only mount does not stop either)
        _, out = dx(main, MOUNT_WRITES.format(dirs=SHARED_MOUNTS), timeout=180)
        record("read-only-mounts", out.strip().endswith("checked") and not re.search(
            r"^(WROTE|APPENDED|TRUNCATED|LINKED|REMOVED|REMOUNTED)", out, re.M), out)  # fmt: skip
        _, out = dx(main, "find /shared /obs /store \\( -type s -o -type p \\) 2>/dev/null | head -n 20; true")
        record("no-sockets-or-pipes", out.strip() == "", out)

        # container configuration: no added capabilities, no runtime socket, every shared mount read-only, no setup
        # settings in the workstation's environment
        _, caps = dx(main, "grep CapEff /proc/1/status | awk '{print $2}'")
        record("default-capabilities", caps.strip().lower() in DEFAULT_CAPS, caps)
        _, socks = dx(main, "ls /var/run/docker.sock /run/docker.sock /run/containerd/containerd.sock 2>/dev/null; "
                      "find / -xdev -type s 2>/dev/null | grep -v '^/tmp/tmux' | head; true")  # fmt: skip
        record("no-runtime-socket", socks.strip() == "", socks)
        _, mounts = dx(main, "awk '$2 ~ \"^/(shared|obs|store)\" {print $2, $4}' /proc/self/mounts")
        writable = [m for m in mounts.splitlines() if m.strip() and not m.split()[1].startswith("ro")]
        record("shared-mounts-read-only", bool(mounts.strip()) and not writable, mounts)
        _, environ = dx(main, "cat /proc/1/environ | tr '\\0' '\\n' | grep -E '^(OCB_|OBS_|BENCH|HARBOR|TASK)' ; true")
        record("no-setup-environment", environ.strip() == "", environ)

        # one modification time across the seeded /ops (a newer file would point at what the fault patch changed)
        _, stamps = dx(main, "find /ops -path /ops/.git -prune -o -type f -printf '%T@\\n' | sort -u | wc -l")
        record("ops-single-mtime", stamps.strip() == "1", stamps)

        # private /ops
        marker = f"probe-{random.randrange(10**9)}"
        dx(main, f"echo {marker}-content > /ops/.{marker}")
        reader = names["engine"] if serving else next(n for s, n in sorted(names.items()) if re.fullmatch(r"c\d+", s))
        _, seen = dx(
            reader, f"test -e /ops/.{marker} && echo PRESENT; grep -rl {marker}-content /ops 2>/dev/null; true"
        )
        _, own = dx(main, f"cat /ops/.{marker}")
        record("private-ops", seen.strip() == "" and own.strip() == f"{marker}-content", f"{seen} / {own}")

        # writes refused, and none leaves a trace
        node = ""
        if serving:
            before = serving_traces(names)
            commands = WRITES_SERVING
        else:
            before = slurm_traces(names)
            node = sorted(s for s in names if re.fullmatch(r"c\d+", s))[0]
            commands = [c.format(job=(before["jobs"] or ["1"])[0], node=node) for c in WRITES_SLURM]
        refusals = []
        for command in commands:
            code, out = dx(main, f"timeout 30 {command}", timeout=60)
            refusals.append({"command": command, "rc": code, "out": out.strip()[-200:],
                             "refused": code != 0 or bool(re.search(r"not available here|Unable to contact|Could not "
                                                                    r"resolve", out))})  # fmt: skip
        record("writes-refused", all(r["refused"] for r in refusals),
               json.dumps([r for r in refusals if not r["refused"]]))  # fmt: skip
        row["refusals"] = refusals
        after = serving_traces(names) if serving else slurm_traces(names)
        if serving:
            traced = [k for k in before if before[k] != after[k]]
        else:
            traced = [k for k in ("cancelled_or_held", "wrap_jobs") if set(after[k]) - set(before[k])]
            traced += ["new jobs"] if set(after["jobs"]) - set(before["jobs"]) else []
            traced += ["node reason probe"] if after["probe_reasons"] else []
            traced += [k for k in ("reservations", "reconfigures") if before[k] != after[k]]
        record("no-write-traces", not traced, f"changed: {traced}; before: {json.dumps(before)[:600]}; after: "
               f"{json.dumps(after)[:600]}")  # fmt: skip

        # reads answer
        if serving:
            _, out = dx(main, "cat /obs/engine/health.status; stat -c %Y /obs/engine/health.status; date +%s")
            parts = out.split()
            fresh = len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit() and int(parts[-1]) - int(
                parts[-2]) < 60  # fmt: skip
            record("reads-answer", fresh, out)
        else:
            _, out = dx(main, "squeue -t all -h -o %i | head -n 1; sinfo -h -N -o %N | head -n 1; "
                        "ocb nodes 2>/dev/null | head -n 1; scontrol show job $(squeue -t all -h -o %i | "
                        "head -n 1) 2>/dev/null | head -n 1")  # fmt: skip
            record("reads-answer", bool(re.search(r"=== \S+", out)) and "JobId=" in out, out)

        # liveness: a node writes a line now; it shows in /shared at once and in /obs within a refresh or two
        line = f"probe-live-{random.randrange(10**9)}"
        if serving:
            sh(["docker", "exec", names["engine"], "sh", "-c", f"echo {line} >> /shared/logs/engine.log"])
            stamp0 = dx(main, "cat /obs/SNAPSHOT_AT")[1]
            time.sleep(25)
            _, out = dx(main, f"grep -c {line} /shared/logs/engine.log; cat /obs/SNAPSHOT_AT")
            record("live", out.split()[0] == "1" and stamp0.strip() not in out, out)
            # does the observer's polling show in the engine's log? (an artefact the standard variant lacks)
            row["engine_log_poll_lines"] = dx(main, "grep -cE 'GET /(slots|metrics|props|health)' "
                                                    "/shared/logs/engine.log || true")[1].strip()  # fmt: skip
        else:
            sh(["docker", "exec", names[node], "sh", "-c", f"echo {line} >> /shared/logs/probe-live.out; "
                f"echo '[probe] {line}' >> /var/log/slurm/slurmd.log"])  # fmt: skip
            time.sleep(25)
            _, out = dx(main, f"grep -c {line} /shared/logs/probe-live.out; grep -c {line} /obs/logs/{node}/slurmd.log")
            record("live", out.split()[:2] == ["1", "1"], out)

        # leaks: setup machinery named in the new exports fails; the submit host's name is counted (both arms show it)
        _, out = dx(main, "grep -rIoE '.{0,40}(" + LEAK.pattern.replace("'", "") + ").{0,40}' /obs /store "
                    "2>/dev/null | sort | uniq -c | sort -rn | head -n 20; true", timeout=180)  # fmt: skip
        record("no-leaks", out.strip() == "", out)
        row["parity_mentions"] = dx(main, "grep -rIoE '" + PARITY.pattern + "' /obs /store 2>/dev/null | wc -l")[
            1
        ].strip()

        # the observer's cost over a minute (cgroup v2 cpu.stat usage_usec)
        def usage() -> int:
            text = sh(["docker", "exec", names["obs"], "cat", "/sys/fs/cgroup/cpu.stat"]).stdout
            m = re.search(r"usage_usec (\d+)", text)
            return int(m.group(1)) if m else 0

        u0, w0 = usage(), time.time()
        time.sleep(60)
        row["observer_cpu_cores"] = round((usage() - u0) / 1e6 / (time.time() - w0), 3)
        row["evidence_probes"] = evidence(main, spec.probes)
        row["evidence_visible"] = all(p["visible"] for p in row["evidence_probes"]) if spec.probes else None
        row["cycles"] = dx(main, "tail -n 3 /obs/CYCLES")[1][-600:]
        return row
    finally:
        row["checks"] = checks
        row["ok"] = bool(checks) and all(c["ok"] for c in checks.values())
        row["seconds"] = round(time.time() - t0)
        row["stamp"] = {**(run or run_stamp()), "row_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if row["ok"] or not keep:
            sh([*compose, "down", "-v"], cwd=env, timeout=300)
        else:
            print(f"kept {project} for inspection (docker compose -p {project} down -v when done)", flush=True)
        shutil.rmtree(work, ignore_errors=True)


# --- wrapper fidelity (QA 3) -----------------------------------------------------------------------------------------

MASKS = [  # what changes between two reads seconds apart: times, loads, free memory, Slurm's date line
    (r"\b\d+-\d\d:\d\d:\d\d\b|\b\d+:\d\d:\d\d\b|\b\d+:\d\d\b", "T"),
    (r"\b\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\b", "TS"),
    (r"^\w{3} \w{3} [ \d]\d \d\d:\d\d:\d\d \d{4}$", "DATE"),
    (r"(CPULoad|FreeMem|LastBusyTime|RunTime|TimeLeft|LastSchedEval|ResumeAfterTime|AccrueTime)=\S+", r"\1=X"),
]
BATCH = """for f in {forms}; do printf '\\n@@@ %s\\n' "$f"; eval "$f" 2>/dev/null; printf '\\n@@@rc %s\\n' "$?"; done"""


def mask(text: str) -> str:
    for pattern, repl in MASKS:
        text = re.sub(pattern, repl, text, flags=re.M)
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def batch_outputs(container: str, commands: list[str]) -> dict[str, tuple[str, str]]:
    """{command: (stdout, rc)} for every command, run one after the other in one login shell."""
    _, out = dx(container, BATCH.format(forms=" ".join(shlex.quote(c) for c in commands)), timeout=600)
    found = {}
    for chunk in out.split("\n@@@ ")[1:]:
        command, _, rest = chunk.partition("\n")
        body, _, rc = rest.rpartition("\n@@@rc ")
        found[command] = (body, rc.strip())
    return found


def read_only_forms() -> tuple[list[str], list[str]]:
    """The recorded command forms that only read (replayed), and the others (listed, never run: they would change the
    cluster under the comparison)."""
    forms = [f for f, _ in json.loads(COMMANDS.read_text())["forms"]]
    return [f for f in forms if classify(f) == {"read"}], [f for f in forms if classify(f) != {"read"}]


def fidelity(task: str, run: dict | None = None) -> dict:
    """Every recorded read-only command form, through the real Slurm client inside the cluster (the observer, root with
    the cluster's keys) and through the workstation's wrappers, right after a fresh snapshot."""
    spec = by_id(task)
    work = Path(tempfile.mkdtemp(prefix="bench-rofid-"))
    env = render(spec, work, "logs") / "environment"
    override = work / "main.yaml"
    override.write_text(MAIN_OVERRIDE)
    project = project_name("rofid", task)
    compose = ["docker", "compose", "-p", project, "-f", str(env / "docker-compose.yaml"), "-f", str(override)]
    try:
        if sh([*compose, "up", "-d", "--wait", "--build"], cwd=env, timeout=1200).returncode != 0:
            return {"task": task, "error": "compose up failed"}
        names = containers(project)
        t0 = time.time()
        while time.time() - t0 < spec.bootstrap_timeout_s + 300:
            if dx(names["main"], "test -f /obs/SNAPSHOT_AT && test -f /shared/evidence/READY")[0] == 0:
                break
            time.sleep(4)
        jobs = sh(["docker", "exec", names["obs"], "squeue", "-h", "-t", "all", "-o", "%i"]).stdout.split()
        node = sorted(s for s in names if re.fullmatch(r"c\d+", s))[0]
        reads, skipped = read_only_forms()
        commands = list(dict.fromkeys(f.replace("{job}", jobs[0] if jobs else "1").replace("{node}", node)
                                      for f in reads))  # fmt: skip
        stamp0 = dx(names["main"], "cat /obs/SNAPSHOT_AT")[1]
        while dx(names["main"], "cat /obs/SNAPSHOT_AT")[1] == stamp0 and time.time() - t0 < 900:
            time.sleep(0.5)  # a fresh snapshot, then both sides at once
        real = batch_outputs(names["obs"], commands)
        wrapped = batch_outputs(names["main"], commands)
        rows = []
        for command in commands:
            (r_out, r_rc), (w_out, w_rc) = real.get(command, ("", "?")), wrapped.get(command, ("", "?"))
            rows.append({"command": command, "rc": [r_rc, w_rc], "exact": r_out == w_out and r_rc == w_rc,
                         "masked": mask(r_out) == mask(w_out) and r_rc == w_rc,
                         "real": r_out[-600:], "wrapper": w_out[-600:]})  # fmt: skip
        return {"task": task, "jobs": jobs, "rows": rows, "not_replayed": skipped, "stamp": run or run_stamp()}
    finally:
        sh([*compose, "down", "-v"], cwd=env, timeout=300)
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench readonly-probe", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("tasks", nargs="*")
    ap.add_argument("--split", default="test", choices=["test", "dev", "all"])
    ap.add_argument("--jobs", type=int, default=2, help="environments up at once")
    ap.add_argument("--keep", action="store_true", help="leave a failing environment up for inspection")
    ap.add_argument("--out", type=Path, default=OUT, help="the record file (default results/readonly-probe.json)")
    ap.add_argument("--fidelity", action="store_true", help="instead: replay every recorded read-only scheduler "
                    "command through the real client and the wrappers (results/readonly-fidelity.json)")  # fmt: skip
    args = ap.parse_args(argv)
    run = run_stamp()
    if args.fidelity:

        def replay(task: str) -> None:
            result = fidelity(task, run)
            merge_row(FIDELITY, task, result)
            rows = result.get("rows", [])
            print(f"{task}: {sum(r['exact'] for r in rows)} exact, {sum(r['masked'] for r in rows)} equal but for "
                  f"times, of {len(rows)} read-only command forms"
                  + (f" ({result['error']})" if "error" in result else ""), flush=True)  # fmt: skip

        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            list(pool.map(replay, args.tasks or FIDELITY_TASKS))
        return
    tasks = args.tasks or [s.id for s in load_specs()
                           if args.split in ("all", s.split) and s.substrate != "gpu"]  # fmt: skip

    def one(task: str) -> dict:
        try:
            r = check(task, args.keep, run)
        except Exception as exc:  # noqa: BLE001 - one task's probe crashing must not stop the others
            import traceback

            r = {"task": task, "ok": False, "stamp": run,
                 "checks": {"probe": {"ok": False, "detail": f"{type(exc).__name__}: {exc}\n"
                                                             f"{traceback.format_exc()[-6000:]}"}}}  # fmt: skip
        bad = [k for k, c in r.get("checks", {}).items() if not c["ok"]]
        print(f"{time.strftime('%H:%M')} {task:32} {'ok' if r['ok'] else 'FAIL ' + ','.join(bad)}  evidence visible "
              f"{r.get('evidence_visible')}  obs {r.get('observer_cpu_cores')} cores", flush=True)  # fmt: skip
        merge_row(args.out, task, r)
        return r

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(one, tasks))
    bad = [r["task"] for r in rows if not r["ok"]]
    print(f"{len(rows) - len(bad)} of {len(rows)} read-only by construction" + (f"; failing: {', '.join(bad)}"
                                                                              if bad else ""))  # fmt: skip
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
