"""Verifier entry point: python3 -m harness.verify /tests/verify.yaml (a harness.config.VerifyConfig).

Reads the agent's /ops as data, builds a fresh cluster, runs the job from /ops and checks it against the task's
rules (harness.verify.rules). Writes /logs/verifier/reward.json ({"reward": 0|1}; absent after an infrastructure
failure), diagnostics.json, ctrf.json and job-logs/. How runs are isolated from each other and from the agent's code
is described in harness.verify.run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from harness import imagelock
from harness.cluster import install_store, prepare_shared
from harness.config import VerifyConfig
from harness.verify import gpus, rules
from harness.verify import policy as pol
from harness.verify.report import LOGS, Report
from harness.verify.rules import INFRA, VERIFIER_BUG
from harness.verify.run import (
    JOB_USER,
    OPS,
    REF_USER,
    SHARED,
    TESTS,
    CheckpointWatch,
    EvalExportWatch,
    Observer,
    Snapshot,
    checkpoint_bytes_max,
    gpu_state,
    kill_local,
    lock_tests,
    node_build,
    ops_swapped,
    replicated,
    run_job,
    site_services,
    snapshot,
)
from ocb import slurm

if TYPE_CHECKING:
    from harness.teacher import Teacher

EVAL_TIMEOUT_S = 300
SAME_AS_FINAL = "same weights as the final export"  # harness.verify.evaluate --final
CKPT_TIMEOUT_S = 120


def main(config_path: str) -> None:
    lock_tests()
    LOGS.mkdir(parents=True, exist_ok=True)
    os.chown(LOGS, 0, 0)
    # Harbor creates it 777. While agent code can run, it is root-only: it holds the reference run's job logs and the
    # verifier's output. Opened for reading (0755) only once every agent process is gone.
    LOGS.chmod(0o700)
    report = Report()
    for name, path in (("runtime_version", "/opt/ocb/VERSION"), ("harness_version", "/opt/harness/VERSION"),
                       ("runtime_build", "/opt/ocb/BUILD"), ("harness_build", "/opt/harness/BUILD")):  # fmt: skip
        report.diag[name] = Path(path).read_text().strip() if Path(path).exists() else "unknown"
    # The task's render pinned the sources its images are built from (tests/images.lock, copied into this image by
    # tests/Dockerfile). A verifier rebuilt since would grade with code the task was never certified with: an
    # infrastructure failure, never a verdict (harness.imagelock).
    lock = Path("/tests/images.lock")
    drift = imagelock.mismatches(imagelock.parse(lock.read_text()), imagelock.running()) if lock.exists() else []
    if drift:
        report.diag["image_mismatch"] = "; ".join(drift)
    report.write()  # a crash anywhere below leaves reward 0
    try:
        if drift:
            report.check("verifier image matches the task's render", False, "; ".join(drift), blame=INFRA)
        else:
            cfg = VerifyConfig.model_validate(yaml.safe_load(Path(config_path).read_text()))
            report.diag["substrate"] = cfg.substrate
            if cfg.substrate == "serving":
                report.required = {"engine ready"}
            verify(cfg, report)
    except Exception:  # noqa: BLE001 -- any crash of the verifier itself is recorded as such, never as a pass
        report.check("verifier error", False, traceback.format_exc()[-2000:], blame=VERIFIER_BUG)
    finally:
        kill_local(JOB_USER)
        report.complete = True
        report.write()
        LOGS.chmod(0o755)


def verify(cfg: VerifyConfig, report: Report) -> None:
    pristine = TESTS / "pristine"  # /ops as the agent received it
    # policy_skip exists only for `bench calibrate`, which measures variants outside the contract.
    violation = None if cfg.policy_skip else pol.check(OPS, pristine, pol.Policy.from_config(cfg.policy))
    report.diag["policy_ok"] = float(violation is None)
    if not report.check("policy", violation is None, violation or ""):
        return
    if cfg.substrate == "serving":
        from harness.verify.serving import verify_serving

        verify_serving(cfg, report, ops_swapped)
        return
    train_cfg = yaml.safe_load((pristine / "jobs" / cfg.job / "train.yaml").read_text())

    from harness import corpus  # torch: imported only where data is generated, so host tests run without it
    from harness.teacher import Teacher

    prepare_shared()
    if cfg.store:  # resume tasks: the verifier's own store, trained on a teacher the agent never saw
        install_store(TESTS / "store")
        teacher = Teacher.load(TESTS / "store" / "teacher.json")
    else:
        noise = cfg.data.noise.model_dump() if cfg.data and cfg.data.noise else None
        seed = cfg.replay.teacher_seed if cfg.replay else int.from_bytes(os.urandom(4), "little")
        teacher = Teacher(seed=seed, noise=noise)
    # never derived from anything the job can read; a replay re-uses the recorded one (bench regrade --replay)
    heldout_seed = cfg.replay.heldout_seed if cfg.replay else int.from_bytes(os.urandom(4), "little")
    # Where the data fault lands (a remapped block): drawn here, not inside corpus, so a replay reproduces it.
    replayed_data = cfg.replay.data_seed if cfg.replay else None
    data_seed = replayed_data if replayed_data is not None else int.from_bytes(os.urandom(4), "little")
    # In the record from now on (written only at the end, root-only while agent code runs), so every verdict that
    # gets this far can be replayed, whichever check ends it; a replay is marked as one and never scored.
    report.diag.update({"teacher_seed": float(teacher.seed), "heldout_seed": float(heldout_seed),
                        "data_seed": float(data_seed)})  # fmt: skip
    if cfg.replay:
        report.diag["replay"] = 1.0
    assert cfg.corpus is not None, "training tasks carry the corpus sizes"
    # The job gets data only; the dataset definition and the held-out sequences stay with the verifier.
    corpus.write(teacher, SHARED / "data" / "corpus.safetensors", cfg.corpus.train, cfg.corpus.val, cfg.corpus.length,
                 data=cfg.data, data_seed=data_seed)  # fmt: skip
    if cfg.data and cfg.data.shards:
        corpus.DATASETS.chmod(0o700)  # the store reads it; nothing the job runs on this workstation can

    # Infrastructure gate: the cluster must come up under the reference fix's cluster configuration, which the agent
    # never touched. If it does not, nothing below says anything about the agent.
    deployed = slurm.deploy_cluster_config(TESTS / "reference")
    slurm.run(["scontrol", "reconfigure"])  # running daemons (a reused cluster) must read it too
    if not slurm.wait_for_cluster(cfg.min_nodes, timeout_s=240, since=deployed):
        try:
            missing = slurm.missing_hardware(list(slurm.nodes()))
        except slurm.SlurmError as exc:
            missing = [str(exc)]
        report.check("cluster up", False, f"not ready under the reference configuration; not initialised: {missing}",
                     blame=INFRA)  # fmt: skip
        return
    report.check("cluster up", True)
    gpu_baseline = None
    if cfg.substrate == "gpu":  # the node's GPUs, read before any agent code runs on it
        why = "the GPU node did not answer nvidia-smi"
        for _ in range(30):  # the site's ballast takes its share of each GPU shortly after the node starts
            gpu_baseline = gpu_state()
            if gpu_baseline is not None:
                why = gpus.class_problem(gpu_baseline, cfg.gpu_class) or (
                    gpus.budget_problem(gpu_baseline, cfg.gpu_budget_mb) if cfg.gpu_budget_mb else ""
                )
                if not why:
                    break
            time.sleep(2)
        if not report.check("GPUs ready", not why, why, blame=INFRA):
            return

    ref = None
    ref_gpu_idle = {g.uuid: g.used_mb for g in gpu_baseline} if gpu_baseline else None
    ckpt_dir = train_cfg["ckpt_dir"]
    if cfg.throughput:
        with ops_swapped(TESTS / "reference"):
            # Observed exactly like the agent's run (same watches, results unused), so what observing costs falls on
            # both sides of the ratio.
            ref_watch = checkpoint_watch(cfg, ckpt_dir, train_cfg)
            ref_evals = EvalExportWatch(steps=train_cfg["steps"]) if cfg.require_eval_exports_every else None
            ref_observer = Observer(REF_USER, ref_watch, placement=cfg.placement is not None, gpu_idle=ref_gpu_idle,
                                    evals=ref_evals)  # fmt: skip
            try:
                ref = run_job(cfg, "reference", REF_USER, LOGS, ref_observer)
            finally:
                if ref_watch:
                    ref_watch.close()
        clean = not ref.survivors and not ref.unreachable
        detail = "; ".join([ref.detail, *ref.survivors, *ref.unreachable]).strip("; ")
        if not report.check("reference run completed", ref.completed and clean, detail, blame=INFRA):
            return

    watch = checkpoint_watch(cfg, ckpt_dir, train_cfg)
    services = site_services()
    gpu_idle = {g.uuid: g.used_mb for g in gpu_baseline} if gpu_baseline else None
    evals = EvalExportWatch(steps=train_cfg["steps"]) if cfg.require_eval_exports_every else None
    observer = Observer(JOB_USER, watch, placement=cfg.placement is not None, gpu_idle=gpu_idle, evals=evals)
    try:
        run = run_job(cfg, "job", JOB_USER, LOGS, observer)
        checkpoints = inspect_checkpoints(watch, train_cfg["model"]) if watch else None
    finally:
        if watch:
            watch.close()
    usable = "" if run.cluster_ok else f"drained or down: {run.detail}"
    if not report.check("cluster usable under /ops/cluster config", run.cluster_ok, usable):
        return
    report.diag["node_build"] = node_build()  # the nodes' image, which the verifier's own need not share
    if not report.check("cluster runs the platform's protected settings", not run.settings, "; ".join(run.settings)):
        return
    # A node the health check drained is the job's configuration's doing; decided before the infrastructure checks
    # below, which would otherwise turn it into a re-run (seen: a job pending behind a drained node, then a node that
    # did not answer cleanup). A node Slurm lost contact with (down, failed, not responding) stays the host's.
    health = slurm.health_drained(run.drained)
    if health and not report.check("no node drained", False, _nodes(health)):
        return
    # A site service (the controller, a node daemon, the object store) that stopped or restarted during the run is the
    # platform's fault, never the job's (the job's account cannot touch them), and it can be why the job did not
    # complete: in the sweep's reused cluster a sick sidecar once read as five agent failures (docs/backlog.md). So it
    # is decided before the job's verdict and blamed on the infrastructure.
    changed = [n for n, pids in site_services().items() if pids != services.get(n)]
    stopped = f"restarted or stopped during the run on {', '.join(changed)}" if changed else ""
    if not report.check("site services kept running", not changed, stopped, blame=INFRA):
        return
    # Completion is Slurm's word, known whatever cleanup finds: an incomplete job is the agent's result before any
    # cleanup trouble can turn it into an infrastructure re-grade.
    report.diag["completed"] = float(run.completed)
    report.diag["elapsed_s"] = round(run.elapsed_s, 1)
    if not report.check("job completed before deadline", run.completed, run.incomplete_reason()):
        return
    # Everything below reads what the job left behind: only once nothing of the job's account is left running.
    if run.survivors:
        report.check("job's processes stopped", False, "; ".join(run.survivors))
        return
    if run.unreachable:
        report.check("job's processes stopped", False, "; ".join(run.unreachable), blame=INFRA)
        return
    if gpu_baseline:  # settings that outlive containers (compute mode, clocks, power, MIG) are the host's
        after = gpu_state()
        moved = gpus.changed(gpu_baseline, after) if after is not None else ["the GPU node did not answer nvidia-smi"]
        if not report.check("GPU settings unchanged", not moved, "; ".join(moved), blame=INFRA):
            return
    if not report.check("no node drained", not run.drained, _nodes(run.drained)):
        return
    snap = snapshot(
        run.job_ids,
        train_cfg["model"],
        world=cfg.world_size,
        steps=train_cfg["steps"],
        eval_every=cfg.require_eval_exports_every or train_cfg["steps"],
    )
    if not report.check("bounded run artifacts", not snap.errors, "; ".join(snap.errors[:10])):
        return
    if not report.check("final model exported", snap.export is not None):
        return
    first = run_start(cfg)
    check_records(cfg, train_cfg, snap, first, report)
    if cfg.placement:  # CPU ranks are also counted as busy processes; GPU ranks wait on the device (rules.gpus_used)
        busy = observer.busy if gpu_baseline is None else None
        report.add(rules.placement(observer.ranks, cfg.placement.nodes, cfg.placement.ranks_per_node, busy))
    if gpu_baseline:
        report.add(rules.gpus_used(observer.gpus_used, [g.uuid for g in gpu_baseline]))
    if cfg.require_eval_exports_every:
        loaded = check_eval_exports(snap, train_cfg["model"], train_cfg["steps"])
        if evals is not None:
            loaded = mid_run_only(loaded, snap, evals, train_cfg["steps"])
        report.add(rules.eval_exports(loaded, cfg.require_eval_exports_every, first, train_cfg["steps"]))
    if cfg.require_checkpoints_every and checkpoints is not None and watch is not None:
        replicas = replicated(Path(ckpt_dir).name, run.started, run.started + run.elapsed_s + 10)
        report.add(rules.checkpoints_written(checkpoints, replicas, watch.hashes, cfg.require_checkpoints_every,
                                             first, train_cfg["steps"], ckpt_dir))  # fmt: skip
    if cfg.loss_max is not None:
        result = evaluate(snap, teacher, train_cfg["model"], heldout_seed)
        if "loss" in result:
            report.diag["loss"] = round(result["loss"], 4)
        report.add(rules.heldout(result, cfg.loss_max))
    if ref is not None and cfg.throughput:
        for key, value in (("host_busy_ref", ref.host_busy), ("host_busy_job", run.host_busy)):
            if value is not None:
                report.diag[key] = value  # contention while each was timed
        check, ratio = rules.throughput(ref.elapsed_s, run.elapsed_s, cfg.throughput.ratio_min)
        report.diag["tput_ratio"] = round(ratio, 3)
        report.add(rules.timed(check, ratio, cfg.throughput.ratio_min, ref.host_busy, run.host_busy))


def run_start(cfg: VerifyConfig) -> int:
    """The first step the job's run must cover: 1, or for a resume task one past the checkpoint the reference fix
    resumes from (a step directory, or the newest complete checkpoint, DCP metadata and meta.json present, of the run
    directory it names in the verifier's own store). Never read from the job's records, which job code writes."""
    if not cfg.store:
        return 1
    source = yaml.safe_load((TESTS / "reference" / "jobs" / cfg.job / "train.yaml").read_text()).get("resume_from")
    if not source:
        return 1
    path = Path(source)
    if path.name.startswith("step_") and path.name[5:].isdigit():
        return int(path.name[5:]) + 1
    complete = [int(d.name[5:]) for d in path.glob("step_*")
                if d.name[5:].isdigit() and (d / ".metadata").is_file() and (d / "meta.json").is_file()]  # fmt: skip
    return max(complete, default=0) + 1


def check_records(cfg: VerifyConfig, train_cfg: dict, snap: Snapshot, first: int, report: Report) -> None:
    """The rules over what the job logged (read as data from the snapshot)."""
    ranks: dict[int, list[dict]] = {}
    for per_rank in snap.metrics.values():
        for rank, records in per_rank.items():
            ranks.setdefault(rank, []).extend(records)
    rank0 = ranks.get(0, [])
    steps = train_cfg["steps"]
    report.add(rules.all_ranks_trained(ranks, cfg.world_size, first, steps))
    if cfg.require_val_every:
        report.add(rules.logged_every(rank0, "val_loss", cfg.require_val_every, first, steps, "validation logged",
                                      "val_loss"))  # fmt: skip
    if cfg.require_step_coverage:
        by_job = [(job_id, snap.metrics[job_id].get(0, [])) for job_id in sorted(snap.metrics, key=int)]
        report.add(rules.step_coverage(by_job, steps))
    if cfg.require_metric_every:
        m = cfg.require_metric_every
        report.add(rules.logged_every(rank0, m.key, m.every, first, steps, f"{m.key} logged", m.key))


def _nodes(drained: dict[str, str]) -> str:
    return "; ".join(f"{n} ({why})" for n, why in sorted(drained.items()))


def checkpoint_watch(cfg: VerifyConfig, ckpt_dir: str, train_cfg: dict) -> CheckpointWatch | None:
    if not cfg.require_checkpoints_every:
        return None
    return CheckpointWatch(SHARED / Path(ckpt_dir).relative_to("/shared"), cfg.require_checkpoints_every,
                           train_cfg["steps"], checkpoint_bytes_max(train_cfg["model"]))  # fmt: skip


def _as_nobody(module: str, args: list[str], work: Path, timeout: int) -> subprocess.CompletedProcess:
    """Run a harness module as `nobody` in `work` (a scratch directory only it and root can read). Every process of
    `nobody` is killed afterwards, so nothing a stage decoded can outlive it into the next stage's files; if one
    survives, the verifier stops (fail closed)."""
    for path in (work, *work.rglob("*")):
        shutil.chown(path, "nobody", "nobody")
    try:
        return slurm.run(["env", "PYTHONPATH=/opt/ocb:/opt/harness", "python3", "-m", module, *args],
                         timeout=timeout, user="nobody", cwd=str(work))  # fmt: skip
    finally:
        if not kill_local("nobody"):
            raise RuntimeError(f"processes of nobody survived the {module} stage")


def inspect_checkpoints(watch: CheckpointWatch, model_cfg: dict) -> dict[int, str]:
    """For each checkpoint the watch kept (the newest per cadence window and the last; nothing else can count): ""
    if it holds the model and optimizer state and decodes, else why not."""
    if not watch.seen:
        return {}
    work = Path(tempfile.mkdtemp(prefix="ckpt-"))
    try:
        listing = {}
        for step, files in watch.seen.items():
            shutil.copytree(watch.store / str(step), work / str(step))
            listing[str(step)] = {"metadata": str(work / str(step) / ".metadata"), "files": files,
                                  "dir": str(work / str(step))}  # fmt: skip
        (work / "listing.json").write_text(json.dumps(listing))
        res = _as_nobody("harness.verify.checkpoint", [json.dumps(model_cfg), str(work / "listing.json")], work,
                         CKPT_TIMEOUT_S)  # fmt: skip
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if res.returncode == 124:  # bounded input (CheckpointWatch), so a decode that does not finish is the job's
        return dict.fromkeys(watch.seen, f"inspection did not finish within {CKPT_TIMEOUT_S}s")
    try:
        return {int(k): v for k, v in json.loads(res.stdout.strip().splitlines()[-1]).items()}
    except (IndexError, ValueError, AttributeError) as exc:
        raise RuntimeError(f"checkpoint inspection failed: {(res.stderr or res.stdout)[-500:]}") from exc


def mid_run_only(loaded: dict[int, str], snap: Snapshot, evals: EvalExportWatch, steps: int) -> dict[int, str]:
    """An eval export before the last step counts only if it appeared while training ran (before the final export
    existed) and was not changed afterwards; check_eval_exports separately rejects the final model's weights."""
    out = dict(loaded)
    for step in snap.eval_exports:
        if step >= steps or out.get(step):
            continue
        if evals.after_final.get(step) is not False:
            out[step] = "written after training ended" if step in evals.after_final else "not seen during the run"
        elif evals.rewritten(step):
            out[step] = "changed after training ended"
    return out


def check_eval_exports(snap: Snapshot, model_cfg: dict, steps: int) -> dict[int, str]:
    """Each eval export the job wrote: "" if it loads strictly into the platform model (as `nobody`) and, before the
    last step, does not hold the final model's weights; else why not."""
    if not snap.eval_exports:
        return {}
    work = Path(tempfile.mkdtemp(prefix="evals-"))
    try:
        names = {}
        for step, path in snap.eval_exports.items():
            names[str(work / path.name)] = step
            shutil.copyfile(path, work / path.name)
        final = []
        if snap.export is not None:  # an eval export holding the final model's weights is not that step's
            shutil.copyfile(snap.export, work / "final.safetensors")
            final = ["--final", str(work / "final.safetensors")]
        res = _as_nobody("harness.verify.evaluate", ["--load-only", json.dumps(model_cfg), *final, *names], work,
                         EVAL_TIMEOUT_S)  # fmt: skip
    finally:
        shutil.rmtree(work, ignore_errors=True)
    try:
        out = {names[f]: why for f, why in json.loads(res.stdout.strip().splitlines()[-1]).items()}
    except (IndexError, ValueError, KeyError) as exc:
        raise RuntimeError(f"eval export check failed: {(res.stderr or res.stdout)[-500:]}") from exc
    # the last step's export is the final model's weights
    return {s: "" if s >= steps and why == SAME_AS_FINAL else why for s, why in out.items()}


def evaluate(snap: Snapshot, teacher: Teacher, model_cfg: dict, heldout_seed: int) -> dict:
    """Score the export as `nobody`, in a scratch directory holding only the export and the dataset definition."""
    assert snap.export is not None
    work = Path(tempfile.mkdtemp(prefix="eval-"))
    try:
        shutil.copyfile(snap.export, work / "model.safetensors")
        teacher.save(work / "teacher.json")
        res = _as_nobody("harness.verify.evaluate", [str(work / "model.safetensors"), str(work / "teacher.json"),
                         json.dumps(model_cfg), str(heldout_seed)], work, EVAL_TIMEOUT_S)  # fmt: skip
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if res.returncode == 124:
        return {"error": f"evaluation did not finish within {EVAL_TIMEOUT_S}s", "timeout": True}
    try:
        return json.loads(res.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"error": (res.stderr or res.stdout)[-500:]}


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tests/verify.yaml")
