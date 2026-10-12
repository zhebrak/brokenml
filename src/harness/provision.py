"""Agent-environment provisioning: deploy /ops, write the data, submit the broken job, wait until the spec violation
shows, collect evidence, and mark the environment ready.

Runs in the provisioning sidecar (python3 -m harness.provision), configured by /opt/task/bootstrap.yaml
(harness.config.BootstrapConfig). READY means the environment is set up (cluster up, every node initialised, the job
submitted) and the fault's symptom showed (symptom.json). When setup fails, or the symptom did not show, SETUP_FAILED
is written instead, with the reason, and the task's healthcheck fails at once: an environment whose fault did not fire
is not an instance of the task (an agent would face a working job and pass by doing nothing), so Harbor retries it,
and a fault that never fires shows as errored trials, not as passes.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path

import yaml

from harness import corpus, imagelock
from harness.cluster import EVIDENCE, SHARED, apply_site, install_store, prepare_shared
from harness.config import BootstrapConfig, Symptom
from harness.teacher import Teacher
from ocb import cli, slurm

OPS = Path("/ops")
CONFIG = Path("/opt/task/bootstrap.yaml")


def write_corpus(cfg: BootstrapConfig, teacher: Teacher) -> None:
    """The job's data: /shared/data/corpus.safetensors (train, val, and a held-out split for `ocb score`)."""
    assert cfg.corpus is not None, "training tasks carry the corpus sizes"
    c = cfg.corpus
    corpus.write(teacher, SHARED / "data" / "corpus.safetensors", c.train, c.val, c.length, heldout=2048, data=cfg.data,
                 world=getattr(cfg, "world_size", 4))  # fmt: skip


def _metrics_age(job_id: str) -> float | None:
    files = list((SHARED / "metrics" / job_id).glob("rank*.jsonl"))
    return time.time() - max(f.stat().st_mtime for f in files) if files else None


def _training_done(job_id: str) -> bool:
    return any('"event": "done"' in f.read_text() for f in (SHARED / "metrics" / job_id).glob("rank*.jsonl"))


def wait_for_symptom(job_ids: list[str], symptom: Symptom) -> dict:
    kind = symptom.kind
    deadline = time.time() + symptom.timeout_s
    lingering_since = pending_since = None
    jobs: list[slurm.Job] = []
    while time.time() < deadline:
        try:
            jobs = slurm.jobs(job_ids)
        except slurm.SlurmError:
            jobs = []
        if not jobs:
            time.sleep(2)
            continue
        main = jobs[-1]
        terminal = all(j.state in slurm.TERMINAL for j in jobs)
        running_for = (datetime.now() - main.start).total_seconds() if main.start else None
        if kind == "pending" and main.state == "PENDING":
            if symptom.reason:
                if symptom.reason in main.reason:  # scontrol may add detail (e.g. ",_Reserved_for_maintenance")
                    return {"observed": True, "state": main.state, "reason": main.reason}
            else:
                pending_since = pending_since or time.time()
                if time.time() - pending_since > symptom.pending_s:
                    return {"observed": True, "state": main.state, "reason": main.reason}
        if kind == "failed" and terminal and any(j.state != "COMPLETED" for j in jobs):
            return {"observed": True, "state": main.state}
        if kind == "completed" and terminal:
            return {"observed": all(j.state == "COMPLETED" for j in jobs), "state": main.state}
        if kind == "stall":
            if terminal:
                return {"observed": main.state != "COMPLETED", "state": main.state}
            age = _metrics_age(main.id)
            age = running_for if age is None else age
            if main.state == "RUNNING" and age is not None and age > symptom.stall_s:
                return {"observed": True, "state": main.state, "stalled_s": round(age)}
        if kind == "running":
            if terminal:
                return {"observed": False, "state": main.state}
            trained = _metrics_age(main.id) is not None
            if main.state == "RUNNING" and trained and running_for is not None and running_for > symptom.run_s:
                return {"observed": True, "state": main.state}
        if kind == "lingering" and main.state == "RUNNING" and _training_done(main.id):
            lingering_since = lingering_since or time.time()
            if time.time() - lingering_since > symptom.linger_s:
                return {"observed": True, "state": main.state}
        time.sleep(2)
    return {"observed": False, "state": jobs[-1].state if jobs else "UNKNOWN", "timeout": True}


def log_contains(job_ids: list[str], text: str) -> bool:
    return any(
        text in f.read_text(errors="replace") for job_id in job_ids for f in (SHARED / "logs").glob(f"*-{job_id}.out")
    )


def job_lines(job_ids: list[str]) -> list[str]:
    """One line per submitted job: its state, exit code and pending reason as the scheduler reports them (finished
    jobs leave the queue, so the report says what became of them), and where its output is."""
    if not job_ids:
        return ["- none accepted (see the submission output above)"]
    try:
        known = {j.id: j for j in slurm.jobs(job_ids)}
    except slurm.SlurmError:
        known = {}
    lines = []
    for job_id in job_ids:
        j = known.get(job_id)
        if j is None:
            lines.append(f"- {job_id}: no longer known to the controller; output: `ocb logs {job_id}`")
            continue
        extra = f", exit {j.exit_code}" if j.exit_code and j.exit_code != "0:0" else ""
        extra += f", reason {j.reason}" if j.reason and j.reason != "None" else ""
        lines.append(f"- {j.id} ({j.name}): {j.state}{extra}; output: `ocb logs {j.id}`")
    return lines


def write_report(cfg: BootstrapConfig, job_ids: list[str], symptom: dict, dumped: bool, submit_output: str) -> None:
    main_id = job_ids[-1] if job_ids else None
    sections = [
        "# Job report",
        "",
        cfg.spec.strip(),
        "",
        "## Jobs submitted at bootstrap",
        *job_lines(job_ids),
        "",
        "## Submission output (`ocb submit train` as svc-train)",
        "```",
        submit_output.strip() or "(no output)",
        "```",
        "",
        "## Scheduler",
        "```",
        cli.status(),
        "```",
        "",
        # Neither the job's own output nor its per-rank progress is quoted here (hardening: the error text often all
        # but names the cause, and the per-rank table alone solved same-shard and rank0-eval-desync in the gate).
        # Both stay where the platform keeps them: /shared/logs/ and `ocb metrics <job>`.
        f"Per-rank training progress: `ocb metrics {main_id}`." if main_id else "No job ran.",
        "More: `ocb --help`, /ops/RUNBOOK.md."
        + (" Stack and Flight Recorder dumps taken at bootstrap: /shared/evidence/dumps/" if dumped else ""),
    ]
    (EVIDENCE / "report.md").write_text("\n".join(sections) + "\n")
    (EVIDENCE / "symptom.json").write_text(json.dumps({"job_ids": job_ids, **symptom}))


def serving_main(cfg: BootstrapConfig) -> dict:
    """Serving tasks: the engine reads /ops/serving/engine.env; measure it under the standard load."""
    from ocb import serving

    url = "http://engine:8080"
    ready = serving.wait_ready(url, cfg.ready_timeout_s)
    result = serving.run_load(url) if ready else {}
    if result:
        result.pop("outputs")
    restarts = SHARED / "engine" / "restarts"
    symptom = {
        "observed": not ready
        or result.get("n_errors", 0) > 0
        or result.get("tokens_per_s", 0) < (cfg.spec_tokens_per_s or 0)
        or result.get("ttft_p95_s", 1e9) > (cfg.spec_ttft_p95_s or 1e9),
        "ready": ready,
        "restarts": int(restarts.read_text()) if restarts.exists() else 0,
        **result,
    }
    sections = [
        "# Serving report",
        "",
        cfg.spec.strip(),
        "",
        "## Standard load (64 requests, 16 concurrent clients, greedy)",
        "```",
        json.dumps({k: v for k, v in symptom.items() if k != "observed"}, indent=1),
        "```",
        "",
        "Engine log: /shared/logs/engine.log.",
        "Engine endpoints: http://engine:8080/health, /metrics, /slots. Re-run the load: `python3 -m ocb.serving http://engine:8080`.",
        "More: /ops/RUNBOOK.md.",
    ]
    (EVIDENCE / "report.md").write_text("\n".join(sections) + "\n")
    (EVIDENCE / "symptom.json").write_text(json.dumps(symptom))
    return symptom


def setup_failed(reason: str) -> None:
    (EVIDENCE / "SETUP_FAILED").write_text(reason.strip() + "\n")
    print(f"setup failed: {reason}", flush=True)


def main() -> None:
    """Runs in the task's provisioning sidecar (harness image), which exits when this returns. Any crash is a setup
    failure: SETUP_FAILED makes the task's healthcheck fail at once instead of after its timeout."""
    try:
        _provision()
    except Exception:  # whatever went wrong, the environment is not usable and must say so (re-raised)
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        setup_failed(f"provisioning crashed:\n{traceback.format_exc()[-2000:]}")
        raise


def _provision() -> None:
    drift = imagelock.mismatches(imagelock.expected_from_env(), imagelock.running())
    if drift:  # a sidecar rebuilt since the task was rendered must not provision it (harness.imagelock)
        setup_failed("the provisioning image does not match the task's render: " + "; ".join(drift))
        return
    cfg = BootstrapConfig.model_validate(yaml.safe_load(CONFIG.read_text()))
    if not any(OPS.iterdir()):
        subprocess.run(["cp", "-a", "/opt/ops-seed/.", str(OPS)], check=True)
    if cfg.substrate == "serving":
        for d in ("logs", "engine", "evidence"):
            (SHARED / d).mkdir(parents=True, exist_ok=True)
        symptom = serving_main(cfg)
        if not symptom["observed"]:
            setup_failed(f"the fault's symptom did not show: {json.dumps(symptom)[:500]}")
            return
        (EVIDENCE / "READY").touch()
        return
    prepare_shared()
    deployed = slurm.deploy_cluster_config(OPS)
    if cfg.store:  # resume tasks: the data the stored checkpoints were trained on
        install_store(Path("/opt/store"))
        write_corpus(cfg, Teacher.load("/opt/store/teacher.json"))
    else:
        noise = cfg.data.noise.model_dump() if cfg.data and cfg.data.noise else None
        write_corpus(cfg, Teacher(seed=int.from_bytes(os.urandom(4), "little"), noise=noise))
    # Wait for every node's first-start setup and health check under this config (it may drain nodes), then for idle
    # nodes; a task whose fault drains nodes needs only the health checks (min_nodes: 0).
    if not slurm.wait_for_cluster(cfg.min_nodes, timeout_s=240, since=deployed):
        try:
            missing = slurm.missing_hardware(list(slurm.nodes()))
        except slurm.SlurmError as exc:
            missing = [str(exc)]
        setup_failed(f"cluster did not come up (nodes not initialised: {missing})")
        return
    try:
        apply_site(cfg.site)
        job_ids, output = slurm.submit(OPS, cfg.job)
    except (slurm.SlurmError, RuntimeError) as exc:
        setup_failed(f"could not submit the job: {exc}")
        return
    (EVIDENCE / "submit.txt").write_text(output)
    if cfg.symptom.kind == "rejected":
        # sbatch refuses an unsatisfiable request outright, except right after the cluster comes up, when Slurm
        # sometimes accepts it and fails it before it starts (Reason=BadConstraints, both hosts, Slurm 26.05.2); that
        # is the same symptom observed a little later (docs/backlog.md, mem-request-unsatisfiable).
        symptom = {"observed": not job_ids, "state": "REJECTED" if not job_ids else "SUBMITTED"}
        if job_ids:
            deadline = time.time() + 120
            while time.time() < deadline:
                jobs = slurm.jobs(job_ids)
                states = {j.state.split()[0] for j in jobs} if jobs else set()
                if jobs and states <= {"FAILED", "CANCELLED", "COMPLETED", "TIMEOUT"}:
                    before_start = all(j.state.startswith("FAILED") and "BadConstraints" in j.reason for j in jobs)
                    symptom = {
                        "observed": before_start,
                        "state": "FAILED_BEFORE_START" if before_start else ",".join(sorted(states)),
                        "reason": "; ".join(sorted({j.reason for j in jobs})),
                    }
                    break
                time.sleep(3)
    elif job_ids:
        symptom = wait_for_symptom(job_ids, cfg.symptom)
    else:
        setup_failed(f"the job was not accepted by the scheduler:\n{output}")
        return
    found = None
    if cfg.symptom.log_match:
        found = log_contains(job_ids, cfg.symptom.log_match) if job_ids else cfg.symptom.log_match in output
        if symptom.get("state") == "FAILED_BEFORE_START":
            found = True  # the job never ran, so it wrote no log: the scheduler's BadConstraints reason is the match
        symptom["log_match"] = found
    dumped = False
    if job_ids and cfg.symptom.kind in ("stall", "lingering", "running"):
        try:
            cli.dump(job_ids[-1])
        except slurm.SlurmError as exc:  # evidence is best effort; the environment is still usable
            print(f"stack dumps skipped: {exc}", flush=True)
        dumped = any((EVIDENCE / "dumps").glob("*/stacks.md"))
    # The report is what the agent is handed: written as things stood when the symptom showed, so waiting for the
    # log line below never adds it to the evidence.
    write_report(cfg, job_ids, symptom, dumped, output)
    match = cfg.symptom.log_match
    if (
        match
        and found is False
        and job_ids
        and symptom["observed"]
        and cfg.symptom.kind in ("stall", "running", "lingering")
    ):
        # A running job writes the line when it happens (srun reports a blocked step only after its first
        # step-create wait, about a minute in): keep reading until it shows or the symptom's time runs out.
        deadline = time.time() + cfg.symptom.timeout_s
        while not found and time.time() < deadline:
            time.sleep(2)
            found = log_contains(job_ids, match)
        symptom["log_match"] = found
    if found is False:
        symptom["observed"] = False
    (EVIDENCE / "symptom.json").write_text(json.dumps({"job_ids": job_ids, **symptom}))  # the final verdict
    if not symptom["observed"]:
        setup_failed(f"the fault's symptom did not show: {json.dumps(symptom)[:500]}")
        return
    (EVIDENCE / "READY").touch()


if __name__ == "__main__":
    main()
