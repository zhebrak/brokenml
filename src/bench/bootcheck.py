"""Does each task's agent environment come up with its fault showing, and its verifier environment start?

    uv run bench bootcheck [TASK ...] [--split test|dev|all] [--repeat N] [--keep]

Brings up the task's agent environment the way Harbor does (`compose up --wait`, the workstation idle), waits until
provisioning marks it READY or SETUP_FAILED, records symptom.json and the failure reason, and tears it down; then
starts the task's verifier environment (`tests/docker-compose.yaml`, the same way) and tears it down. No agent and no
verifier run. Provisioning refuses to mark an environment ready when the fault's symptom did not show
(harness.provision), so a task that fails here would turn every agent trial into an errored one. `--repeat N` brings
each environment up N times (a symptom that fires only sometimes shows as k of N); `--keep` leaves a failing
environment up for inspection. A failing row keeps the provisioning output and the tail of the bootstrap job's log.
Writes results/bootcheck.json (one row per task, with the task digest and a stamp), keeping other tasks' rows; exits
non-zero if any checked task fails.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from bench.paths import RESULTS, project_name
from bench.provenance import stamp, task_digest
from bench.spec import by_id, load_specs, task_dir

OUT = RESULTS / "bootcheck.json"
MAIN_OVERRIDE = "services:\n  main:\n    build: {context: .}\n    command: [sleep, infinity]\n"


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def verdict(ready: bool, failed: str | None, symptom: dict | None) -> tuple[bool, str]:
    """(ok, why): ready with the symptom observed, or why not."""
    if failed is not None:
        return False, f"setup failed: {failed.strip()[:300]}"
    if not ready:
        return False, "neither READY nor SETUP_FAILED before the bootstrap timeout"
    if not (symptom or {}).get("observed"):
        return False, f"ready without the symptom: {json.dumps(symptom)[:300]}"
    return True, ""


def probes_hash(task: str) -> str:
    """What the spec's probes say, hashed: a record is stale once the probes change (they are host-side, so the task
    digest cannot see them)."""
    import hashlib

    probes = [p.model_dump() for p in by_id(task).probes]
    return hashlib.sha256(json.dumps(probes, sort_keys=True).encode()).hexdigest()[:16]


def run_probes(main: str, probes, runner=sh) -> list[dict]:
    """The spec's evidence probes in the ready agent workstation: each command's output must match its regex (the
    decisive observation of the task's principle-7 write-up), so the evidence the task is built on is really there."""
    out = []
    for probe in probes:
        try:
            res = runner(["docker", "exec", main, "bash", "-lc", probe.run], timeout=180)
            text = (res.stdout or "") + (res.stderr or "")
        except subprocess.TimeoutExpired:
            text = "(probe timed out)"
        out.append({"run": probe.run, "expect": probe.expect, "ok": bool(re.search(probe.expect, text, re.S)),
                    "excerpt": text[-400:]})  # fmt: skip
    return out


def merge_row(path: Path, key: str, row: dict) -> None:
    """Write one row into the records file under a lock, re-reading the file first: a chain and a one-off check may run
    at the same time, and neither may erase the other's rows (a stale in-memory copy once did)."""
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        rows = json.loads(path.read_text()) if path.exists() and path.read_text().strip() else {}
        rows[key] = row
        path.write_text(json.dumps(dict(sorted(rows.items())), indent=1) + "\n")
        fcntl.flock(fh, fcntl.LOCK_UN)


def _compose(directory: Path, project: str) -> list[str]:
    override = Path(tempfile.mkdtemp()) / "main.yaml"
    override.write_text(MAIN_OVERRIDE)
    return ["docker", "compose", "-p", project, "-f", str(directory / "docker-compose.yaml"), "-f", str(override)]


def agent_environment(task: str, keep: bool) -> dict:
    spec, env_dir = by_id(task), task_dir(task) / "environment"
    project = project_name("boot", task)
    compose, main, t0 = _compose(env_dir, project), f"{project}-main-1", time.time()
    ready, failed, symptom, detail, probes = False, None, None, "", []
    try:
        up = sh([*compose, "up", "-d", "--wait", "--build"], cwd=env_dir, timeout=900)
        if up.returncode != 0:
            failed = f"compose up --wait: {(up.stderr or up.stdout)[-300:]}"
        while failed is None and time.time() - t0 < spec.bootstrap_timeout_s + 120:
            if sh(["docker", "exec", main, "test", "-f", "/shared/evidence/SETUP_FAILED"]).returncode == 0:
                failed = sh(["docker", "exec", main, "cat", "/shared/evidence/SETUP_FAILED"]).stdout or "(no reason)"
                break
            if sh(["docker", "exec", main, "test", "-f", "/shared/evidence/READY"]).returncode == 0:
                ready = True
                break
            time.sleep(3)
        raw = sh(["docker", "exec", main, "cat", "/shared/evidence/symptom.json"]).stdout
        symptom = json.loads(raw) if raw.strip() else None
        if ready and failed is None:
            probes = run_probes(main, spec.probes)
        if failed is not None or not ready or not (symptom or {}).get("observed"):
            provision = sh(["docker", "logs", "--tail", "30", f"{project}-provision-1"])
            joblog = sh(["docker", "exec", main, "sh", "-c", "tail -n 20 /shared/logs/*.out 2>/dev/null"])
            detail = f"provision:\n{(provision.stdout + provision.stderr)[-2000:]}\njob log:\n{joblog.stdout[-2000:]}"
    except (json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        failed = failed or f"check error: {exc}"
    finally:
        ok_so_far = failed is None and ready and (symptom or {}).get("observed") and all(p["ok"] for p in probes)
        if ok_so_far or not keep:
            sh([*compose, "down", "-v"], cwd=env_dir, timeout=300)
        elif keep:
            print(f"kept {project} for inspection (docker compose -p {project} down -v when done)", flush=True)
    ok, why = verdict(ready, failed, symptom)
    if ok and (bad := [p for p in probes if not p["ok"]]):
        ok, why = False, f"evidence probe failed: {bad[0]['run'][:80]} (expected /{bad[0]['expect']}/)"
    return {"ok": ok, "why": why, "symptom": symptom, "seconds": round(time.time() - t0), "detail": detail,
            "probes": probes}  # fmt: skip


def verifier_environment(task: str) -> tuple[bool, str]:
    """The verifier's environment starts the way Harbor starts it (a failed inherited health check shows here)."""
    tests = task_dir(task) / "tests"
    project = project_name("bootv", task)
    compose = _compose(tests, project)
    try:
        up = sh([*compose, "up", "-d", "--wait", "--build"], cwd=tests, timeout=900)
        return up.returncode == 0, "" if up.returncode == 0 else f"verifier compose up --wait: {up.stderr[-300:]}"
    except subprocess.TimeoutExpired:
        return False, "verifier compose up --wait timed out"
    finally:
        sh([*compose, "down", "-v"], cwd=tests, timeout=300)


def check(task: str, repeat: int = 1, keep: bool = False) -> dict:
    runs = [agent_environment(task, keep) for _ in range(repeat)]
    v_ok, v_why = verifier_environment(task)
    good = sum(r["ok"] for r in runs)
    reasons = {r["why"] for r in runs if r["why"]} | ({v_why} if v_why else set())
    why = "; ".join(sorted(reasons))
    first_bad = next((r for r in runs if not r["ok"]), None)
    probes = runs[-1].get("probes", [])
    return {"ok": good == repeat and v_ok, "agent_env_ok": f"{good}/{repeat}", "verifier_env_ok": v_ok, "why": why,
            "probes": probes, "probes_ok": f"{sum(p['ok'] for p in probes)}/{len(probes)}",
            "symptom": runs[-1]["symptom"], "detail": first_bad["detail"] if first_bad else "",
            "seconds": sum(r["seconds"] for r in runs), "task_digest": task_digest(task_dir(task)),
            "probes_hash": probes_hash(task),
            "stamp": stamp()}  # fmt: skip


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench bootcheck", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("tasks", nargs="*")
    ap.add_argument("--split", default="test", choices=["test", "dev", "all"])
    ap.add_argument("--repeat", type=int, default=1, help="bring each agent environment up N times")
    ap.add_argument("--keep", action="store_true", help="leave a failing agent environment up for inspection")
    args = ap.parse_args(argv)
    tasks = args.tasks or [s.id for s in load_specs() if args.split in ("all", s.split)]
    rows = {}
    for task in tasks:
        rows[task] = check(task, args.repeat, args.keep)
        r = rows[task]
        state = "ok" if r["ok"] else "FAIL"
        print(f"{time.strftime('%H:%M')} {task:32} {state}  agent {r['agent_env_ok']}  {r['why']}", flush=True)
        merge_row(OUT, task, r)
    bad = [t for t in tasks if not rows[t]["ok"]]
    print(f"{len(tasks) - len(bad)} of {len(tasks)} come up with their symptom and a startable verifier"
          + (f"; failing: {', '.join(bad)}" if bad else ""))  # fmt: skip
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
