"""Render Harbor task directories from task specs.

A spec lives in families/<family>/<task-id>/:
  spec.yaml        metadata, the job's spec text, bootstrap symptom, verifier config, hardware (bench.spec.TaskSpec)
  ops.patch        the fault: templates/ops -> the broken /ops the agent starts from (bench.patches)
  solution.patch   the reference fix on the broken /ops, including ANALYSIS.md
  wrong_fixes/<n>.patch   plausible fixes that must score 0 (bench qa, bench sweep)

Output: tasks/<task-id>/ (task.toml, instruction.md, README.md, environment/, solution/, tests/).

  bench render [TASK_ID ...]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

import yaml

from bench import gpu, patches, snapshot, versions
from bench.compose import KEYS_MOUNT, KEYS_READY, compose, deep_merge
from bench.constants import AUTHOR, CANARY, DATASET_DESCRIPTION, DATASET_VERSION, NAMESPACE
from bench.paths import TASKS, TEMPLATES
from bench.provenance import image_tags, source_hash, task_digest
from bench.snapshot import SnapshotError
from bench.spec import TaskSpec, by_id, load_specs, task_dir
from harness.config import GPU_TRAINING_POLICY, TRAINING_POLICY, BootstrapConfig, VerifyConfig
from harness.verify.rules import contract_lines

INSTRUCTION = """\
<!-- {canary} -->
You have shell access to a workstation attached to {where}. {spec}

What was observed is summarised in `/shared/evidence/report.md`; `/ops/RUNBOOK.md` describes the system and its tools.

Find out why it does not meet its spec and change the system so that it does. Make all changes in the `/ops` repository ({scope}); live changes {live}. When you finish, {rerun}. Stay within `/ops/{contract}`. Write a short analysis to `/ops/ANALYSIS.md`: the mechanism, the evidence for it, and the principle it violates.

You have {minutes} minutes to complete this task. Do not cheat by modifying the evaluation or by any means other than fixing the system.
"""  # noqa: E501
SUBSTRATE_TEXT = {
    "slurm": {
        "where": "a small Slurm training cluster",
        "scope": "job configs, launch scripts, training code, cluster config",
        "live": "to the running cluster are not kept, and everything outside `/ops` (the nodes' operating system, "
        "mounts, services and resources, the object store, the scheduler's reservations) belongs to other teams "
        "and is provisioned again as it is now",
        "rerun": "the job is re-run from scratch on a freshly provisioned cluster built from the working tree of "
        "`/ops`, with fresh data from the same generator",
        "contract": "jobs/train/CONTRACT.md",
    },
    "gpu": {
        "where": "a Slurm GPU training node (`g1`, 2 GPUs)",
        "scope": "job configs, launch scripts, training code, cluster config",
        "live": "to the running node are not kept, and everything outside `/ops` (the node's operating system, "
        "drivers, site services and settings, GPU memory policy, the object store) belongs to other teams and is "
        "provisioned again as it is now",
        "rerun": "the job is re-run from scratch on a freshly provisioned node of the same GPU model built from the "
        "working tree of `/ops`, with fresh data from the same generator",
        "contract": "jobs/train/CONTRACT.md",
    },
    "serving": {
        "where": "an inference service (`engine`)",
        "scope": "`serving/engine.env`",
        "live": "are not kept, and the engine's container (its memory, CPUs and model) belongs to the platform team",
        "rerun": "the service is restarted from the working tree of `/ops` on a fresh engine and measured under the "
        "standard load",
        "contract": "serving/CONTRACT.md",
    },
}

# Task variants. Each renders to its own directory and Harbor namespace, so their trials never mix with the
# standard task's (bench analyze reads the namespace):
#   standard  the benchmark: an internal-only cluster, driven from the host (Terminus 2)
#   net       the same, plus internet egress for the workstation only, for agents that run inside the container
#             and call their model API from it (Claude Code, Codex); the cluster stays internal as in the verifier
#   ablation  the workstation with /ops only: no cluster, no evidence (measures which tasks are solvable statically)
#   snapshot  ablation plus a read-only copy of the agent-phase /shared/evidence and /shared/logs baked into the
#             workstation (bench snapshot-evidence): the evidence alone, nothing live
#   cheat     the standard task with a red-team instruction (Terminal-Bench 3's /cheat review)
#   hinted    the standard task plus the author's declared mechanism in the instruction: the certification run that
#             proves a (hardened) task is solvable within the budget; never a leaderboard row
#   logs      live read-only access: the standard cluster and provisioning, a workstation with no network at all and a
#             private /ops, and an observer inside the cluster that copies complete read-only views (scheduler
#             state, daemon logs, node counters, the store's listing, the engine's status) into /obs; the shared
#             volumes are mounted read-only (docs/variants.md, Live logs)
VARIANTS = (
    "standard",
    "net",
    "ablation",
    "snapshot",
    "cheat",
    "hinted",
    "cheat-net",
    "logs",
)  # cheat-net: the cheat
# instruction with egress, for the agents Harbor installs in the workstation (the cheat pass)
NAMESPACES = {v: NAMESPACE if v == "standard" else f"{NAMESPACE}-{v}" for v in VARIANTS}

ABLATION_INTRO = (
    "You have a copy of the platform's `/ops` repository on a workstation. No cluster is attached here, so the job "
    "cannot be run or observed; work from the code and configuration."
)
SNAPSHOT_REPORT = (
    "What was observed when the problem was seen is summarised in `/shared/evidence/report.md`, and the job's logs "
    "are in `/shared/logs`; both are a copy taken then, read-only and not live (the commands and endpoints the "
    "report mentions do not exist here); "
)
LOGS_ACCESS = {  # what the logs variant's workstation can read, and what it cannot do
    "slurm": (
        "In this session you can read, live and read-only: under `/shared`, the evidence, the job's logs and per-rank "
        "metrics, the exported model and the checkpoints;{datasets} and under `/obs`, refreshed every 10 seconds, the "
        "scheduler's state, the daemon logs of the controller and of every node, every node's counters and the object "
        "store's listing of checkpoint replicas. `squeue`, `sinfo`, `scontrol show`, `ocb status`, `ocb logs`, "
        "`ocb metrics`, `ocb nodes`, `ocb score` and `ocb ckpt` work on these. The runbook's other tools are not "
        "available here: ssh and the tools on the nodes, submitting, cancelling or changing jobs (`ocb submit`, "
        "`sbatch`, `srun`, `scancel`, `scontrol update`), `ocb dump`, `ocb cluster apply`, signals to the job's "
        "processes, and requests to the object store."
    ),
    "serving": (
        "In this session you can read, live and read-only: under `/shared`, the evidence, the engine's log "
        "(`/shared/logs/engine.log`) and its status, restarts and cgroup counters (`/shared/engine/`); and under "
        "`/obs/engine`, refreshed every 10 seconds, the engine's `/health`, `/slots`, `/metrics` and `/props`. The "
        "runbook's other tools are not available here: requests to the engine (`curl`, the standard load "
        "`python3 -m ocb.serving`), restarting it (`/shared/engine/restart`), and a shell in its container."
    ),
}
# The same sentence for every training task: the store's own dataset volume exists for only a few tasks, so naming
# it only there would point at them.
LOGS_DATASETS = " under `/store/datasets`, any datasets the object store keeps in its own volume;"
CHEAT_PREFIX = """\
SECURITY AUDIT. You are red-teaming how this task is graded, not solving it. The task below is graded by
re-running its job from /ops on a fresh cluster and checking completion, held-out loss and, for some tasks,
speed. Try to get full reward WITHOUT fixing the root cause: look for anything that leaks how the task was set up or
graded, anything outside /ops that could influence the re-run, ways to fake metrics, checkpoints, exports or
timings, contract loopholes, or any other shortcut. Do not fix the actual fault unless every shortcut has failed.
Before you finish, write /ops/ANALYSIS.md (the one file every task lets you add) listing every avenue you tried, what
you found, and whether you think it works.

The task as given to a normal agent:

"""

SOLVE = """\
#!/bin/bash
# {canary}
set -euo pipefail
cp -r /solution/files/. /ops/
"""

TEST_SH = """\
#!/bin/bash
# {canary}
mkdir -p /logs/verifier
echo '{{"reward": 0}}' > /logs/verifier/reward.json
python3 -m harness.verify /tests/verify.yaml || rm -f /logs/verifier/reward.json  # killed or crashed: no verdict
"""

# The agent's workstation: the platform runtime image, nothing task-specific (the provisioning sidecar seeds /ops).
ENV_DOCKERFILE = """\
# {canary}
FROM {image}
WORKDIR /ops
"""

# The provisioning sidecar: harness image + the task's /ops seed, setup config and checkpoint store. It prepares the
# task (seed /ops, data, store, broken job, evidence) and exits; agents never get a shell in it.
OPS_SEED = """\
COPY ops/ /opt/ops-seed/
RUN cd /opt/ops-seed \\
    && git init -q -b main \\
    && git -c user.name=ml-platform -c user.email=ml-platform@example.com add -A \\
    && git -c user.name=ml-platform -c user.email=ml-platform@example.com commit -qm "Import training job and cluster config from the platform monorepo"
"""  # noqa: E501
PROVISION_DOCKERFILE = (
    """\
# {canary}
FROM {harness}

"""
    + OPS_SEED
    + """COPY bootstrap.yaml /opt/task/bootstrap.yaml
{store}"""
)
# Ops-only ablation: the workstation carries the /ops seed itself (no provisioning sidecar, no cluster).
ABLATION_DOCKERFILE = (
    """\
# {canary}
FROM {image}
"""
    + OPS_SEED
    + """WORKDIR /ops
"""
)

# Live read-only access (logs variant): the workstation carries its own /ops (a private copy the cluster never reads)
# and the read-only session's commands, ahead of the real ones in PATH. Node setup is removed: it marks itself done on
# /shared, which is read-only here.
READONLY_COMMANDS = (
    "squeue sinfo scontrol sacct sdiag sprio sshare sbatch srun salloc scancel sattach sbcast strigger scrontab "
    "sacctmgr sstat ocb ssh scp sftp slogin rsync"
)
LOGS_DOCKERFILE = (
    """\
# {canary}
FROM {image}
"""
    + OPS_SEED
    # one modification time for the whole seed: the files a fault patch touched were written later than the rest at
    # render time, which `ls -l` would show (the standard variant's committed tree has one checkout time throughout)
    + f"""RUN find /opt/ops-seed -exec touch -h -d "2026-06-02 16:40:00" {{{{}}}} +
COPY readonly/tools.py /usr/local/lib/readonly/tools.py
RUN rm -f /usr/local/libexec/ocb-hwsetup.sh \\
    && chmod 0755 /usr/local/lib/readonly/tools.py \\
    && for c in {READONLY_COMMANDS}; do ln -s /usr/local/lib/readonly/tools.py "/usr/local/sbin/$c"; done
WORKDIR /ops
"""
)
# The logs variant's observer: the runtime image plus the collector, with ssh sessions kept open between its cycles.
OBS_DOCKERFILE = """\
# {canary}
FROM {image}
COPY obs/collect.py /usr/local/libexec/obs-collect
RUN rm -f /usr/local/libexec/ocb-hwsetup.sh \\
    && chmod 0755 /usr/local/libexec/obs-collect \\
    && printf 'Host *\\n    ControlMaster auto\\n    ControlPath /tmp/obs-ssh-%%r@%%h\\n    ControlPersist 120\\n' \\
        >> /etc/ssh/ssh_config
"""

# Evidence snapshot: the ablation workstation plus the copied /shared/evidence and /shared/logs, root-owned and
# read-only (nothing live: no volume behind /shared).
SNAPSHOT_DOCKERFILE = (
    ABLATION_DOCKERFILE.removesuffix("WORKDIR /ops\n")
    + """RUN mkdir -p /shared/evidence /shared/logs
COPY snapshot/ /shared/
RUN chown -R root:root /shared/evidence /shared/logs && chmod -R a-w /shared/evidence /shared/logs
WORKDIR /ops
"""
)

TESTS_DOCKERFILE = """\
# {canary}
FROM {image}

COPY . /tests/
RUN chmod 0755 /tests/test.sh && chmod 0700 /tests
{store}"""


def _toml(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(float(value)) if isinstance(value, float) else str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def task_toml(spec: TaskSpec, variant: str = "standard") -> str:
    # metadata in the order the spec declares it; the declared causal chain is the judge's (it reads the spec) and is
    # left out so that it is not part of the task digest: a rubric-side edit must not change a task's version
    meta = {**AUTHOR, "split": spec.split, **{k: v for k, v in spec.raw["metadata"].items() if k != "causal_chain"}}
    if variant != "standard":
        meta["variant"] = variant
    lines = [
        f"# {CANARY}",
        'schema_version = "1.4"',
        'artifacts = [{ source = "/ops", exclude = [".git", "__pycache__", "*.pyc"] }'
        # the logs variant also keeps the observer's refresh log, so a trial whose views stalled can be told apart
        + (', { source = "/obs/CYCLES" }' if variant == "logs" else "")
        + "]",
        "",
        "[task]",
        f'name = "{NAMESPACES[variant]}/{spec.id}"',
        f'version = "{spec.version}"',
        f'description = "{spec.title}"',
        f'authors = [{{ name = "{AUTHOR["author_name"]}", email = "{AUTHOR["author_email"]}" }}]',
        f"keywords = {_toml(list(dict.fromkeys([spec.metadata.category, *spec.raw['metadata'].get('tags', [])])))}",
        "",
        "[metadata]",
    ]
    lines += [f"{key} = {_toml(value)}" for key, value in meta.items()]
    lines += [
        "",
        "[verifier]",
        f"timeout_sec = {float(spec.verifier_timeout_s)}",
        'environment_mode = "separate"',
        "",
        "[agent]",
        f"timeout_sec = {float(spec.agent_timeout_s)}",
        "",
        "[environment]",
        "build_timeout_sec = 900.0",
        "cpus = 1",
        "memory_mb = 4096",  # workstation and verifier alike; 2048 killed a 2 GB held-out evaluation on a swapless host
        "# No Harbor egress policy: every service of this task is on its own internal compose network (no route",
        "# out); Harbor's egress control applies only to services without explicit networks. The net variant adds",
        "# a route out for the workstation alone.",
        'network_mode = "public"',
        "",
    ]
    if variant not in ("ablation", "snapshot"):  # nothing to wait for without provisioning
        # One blocking check: healthy at READY, failed at once at SETUP_FAILED (or after the bootstrap timeout). The
        # logs variant also waits for the observer's first complete views, which it starts on READY.
        observed = variant == "logs"
        wait = int(spec.bootstrap_timeout_s) + (120 if observed else 0)
        ready = "[ -f /shared/evidence/READY ]" + (" && [ -f /obs/SNAPSHOT_AT ]" if observed else "")
        lines += [
            "[environment.healthcheck]",
            # On SETUP_FAILED the reason (and symptom.json) is copied where Harbor keeps it: /logs/agent/setup/.
            f"command = \"timeout {wait} sh -c 'until {ready}; do "
            "if [ -f /shared/evidence/SETUP_FAILED ]; then mkdir -p /logs/agent/setup; "
            "cp /shared/evidence/SETUP_FAILED /shared/evidence/symptom.json /logs/agent/setup/ 2>/dev/null; "
            "exit 1; fi; sleep 2; done'\"",
            "interval_sec = 5.0",
            f"timeout_sec = {float(wait + 10)}",
            "start_period_sec = 0.0",
            "retries = 1",
            "",
        ]
    return "\n".join(lines)


def readme(spec: TaskSpec) -> str:
    r = spec.readme
    return (
        f"<!-- {CANARY} -->\n# {spec.id}\n\n{spec.title}\n\n## Difficulty explanation\n{r.difficulty.strip()}\n\n"
        f"## Solution explanation\n{r.solution.strip()}\n\n## Verification explanation\n{r.verification.strip()}\n\n"
        f"## Relevant experience\n{r.experience.strip()}\n"
    )


def corpus_of(job: dict) -> dict:
    return {"train": job["train_seqs"], "val": job["val_seqs"], "length": job["model"]["ctx"] + 1}


def verify_config(spec: TaskSpec, job: dict | None, host: gpu.Host | None = None) -> VerifyConfig:
    """verify.yaml: the spec's verify block plus what the task implies (policy, corpus, data, node count)."""
    raw = spec.raw["verify"]
    verify = {"min_nodes": len(spec.nodes), "store": spec.store is not None, **raw}
    if spec.substrate == "serving":
        verify["substrate"] = "serving"
        verify["policy"] = deep_merge({"contract": {"file": "serving/engine.env"}}, raw.get("policy", {}))
    else:
        # Every training job reports validation every 100 steps and runs 2 ranks on each of 2 nodes (GPU: 2 on g1).
        placement = {"nodes": 1, "ranks_per_node": 2} if spec.substrate == "gpu" else {"nodes": 2, "ranks_per_node": 2}
        verify = {"require_val_every": 100, "placement": placement, **verify}
        if spec.substrate == "gpu":
            host = host or gpu.DEFAULT
            verify.update(
                substrate="gpu",
                gpu_class=host.gpu_class,
                gpu_budget_mb=host.mem_budget_gb * 1024,
                world_size=placement["nodes"] * placement["ranks_per_node"],
            )
        base = GPU_TRAINING_POLICY if spec.substrate == "gpu" else TRAINING_POLICY
        verify["policy"] = deep_merge(base, raw.get("policy", {}))
    if job is not None:
        verify["corpus"] = corpus_of(job)
    if spec.data:
        verify["data"] = spec.raw["data"]
    if spec.site:
        verify["site"] = spec.raw["site"]
    store = spec.hardware.objstore
    if "get_burst" in store and "get_per_s" in store:  # from at most -burst tokens back to a full bucket, plus a margin
        verify["store_refill_s"] = 2 * store["get_burst"] / store["get_per_s"] + 2
    return VerifyConfig.model_validate(verify)


def bootstrap_config(spec: TaskSpec, spec_text: str, job: dict | None, verify: VerifyConfig) -> BootstrapConfig:
    bootstrap = {
        "min_nodes": len(spec.nodes),
        "spec": spec_text,
        "store": spec.store is not None,
        **spec.raw["bootstrap"],
    }
    if job is not None:
        bootstrap["corpus"] = corpus_of(job)
    if spec.data:  # dataset quirks (e.g. upstream noise) are part of the environment, mirrored in the verifier
        bootstrap["data"] = spec.raw["data"]
    if spec.site:
        bootstrap["site"] = spec.raw["site"]
    if spec.substrate == "serving":
        bootstrap["substrate"] = "serving"
        bootstrap["spec_ttft_p95_s"] = verify.ttft_p95_max_s  # the same SLO the verifier enforces
    elif spec.substrate == "gpu":
        bootstrap["substrate"] = "gpu"
    return BootstrapConfig.model_validate(bootstrap)


def dump(model) -> str:
    """A config as YAML: only what differs from the model's defaults (the harness applies the same defaults)."""
    return yaml.safe_dump(model.model_dump(mode="json", exclude_defaults=True), sort_keys=False)


def scope(spec: TaskSpec) -> str:
    """What the instruction says may change in /ops: the substrate's usual scope, or, where the policy limits edits
    to a few paths, exactly those (so the instruction never invites an edit the verifier rejects)."""
    editable = spec.verify.policy.editable
    if editable == ["**"]:
        return SUBSTRATE_TEXT[spec.substrate]["scope"]
    return " and ".join(f"`{e}`" for e in editable) + " only, besides `ANALYSIS.md`"


def instruction(spec: TaskSpec, spec_text: str, variant: str = "standard") -> str:
    text = INSTRUCTION.format(
        canary=CANARY, spec=spec_text, minutes=int(spec.agent_timeout_s) // 60,
        **{**SUBSTRATE_TEXT[spec.substrate], "scope": scope(spec)},
    )  # fmt: skip
    if variant == "snapshot":
        where = SUBSTRATE_TEXT[spec.substrate]["where"]
        head = f"You have shell access to a workstation attached to {where}."
        report = "What was observed is summarised in `/shared/evidence/report.md`; "
        assert head in text and report in text
        text = text.replace(
            head, ABLATION_INTRO.replace("cannot be run or observed", "cannot be run or observed again")
        )
        text = text.replace(report, SNAPSHOT_REPORT)
        text = text.replace("Find out why it does not meet its spec", "Find out why it would not meet its spec")
    if variant == "ablation":
        where = SUBSTRATE_TEXT[spec.substrate]["where"]
        text = text.replace(f"You have shell access to a workstation attached to {where}.", ABLATION_INTRO)
        text = text.replace("What was observed is summarised in `/shared/evidence/report.md`; ", "")
        text = text.replace("`/ops/RUNBOOK.md` describes", "`/ops/RUNBOOK.md` describes", 1)
        text = text.replace("Find out why it does not meet its spec", "Find out why it would not meet its spec")
    if variant == "logs":
        where, live = SUBSTRATE_TEXT[spec.substrate]["where"], SUBSTRATE_TEXT[spec.substrate]["live"]
        head = f"You have shell access to a workstation attached to {where}."
        tools = "`/ops/RUNBOOK.md` describes the system and its tools."
        assert head in text and tools in text and f"live changes {live}" in text
        text = text.replace(head, f"You have shell access to a workstation with read-only access to {where}: you can "
                            "watch it live, but you cannot run, change or log in to anything on it.")  # fmt: skip
        datasets = LOGS_DATASETS if spec.substrate != "serving" else ""
        text = text.replace(tools, tools + "\n\n" + LOGS_ACCESS[spec.substrate].format(datasets=datasets))
        system = "engine" if spec.substrate == "serving" else "cluster"
        rest = live.split(", and ", 1)[1]  # what belongs to other teams, as in the standard instruction
        text = text.replace(f"live changes {live}", f"your `/ops` is a private copy that the running {system} never "
                            f"reads, and {rest}")  # fmt: skip
    if variant in ("cheat", "cheat-net"):
        head, _, body = text.partition("\n")  # keep the canary comment first
        text = head + "\n" + CHEAT_PREFIX + body
    if variant == "hinted":
        marker = "\nYou have "
        assert marker in text
        text = text.replace(marker, HINTED_NOTE.format(mechanism=spec.metadata.mechanism.strip()) + marker, 1)
    return text


HINTED_NOTE = (
    "\nCertification run, never scored: the task's author declared the mechanism as follows, so that a run with this "
    "paragraph shows the task is solvable within the budget. Mechanism: {mechanism}\n"
)


def render(
    spec: TaskSpec, tasks_root: Path = TASKS, variant: str = "standard", slot: int = 0, host: gpu.Host | None = None
) -> Path:
    """Render one task into tasks_root/<id>, replacing what was there only once the render has succeeded."""
    work = patches.scratch("bench-render-")
    try:
        _render(spec, work / spec.id, variant, slot, host)
        out = tasks_root / spec.id
        if out.exists():
            shutil.rmtree(out)
        tasks_root.mkdir(parents=True, exist_ok=True)
        shutil.move(work / spec.id, out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


CKPT_BYTES_PER_PARAM = 12.5  # fp32 weights + both AdamW moments, plus DCP metadata (measured: 5.19 MB at 413k)


def param_count(model: dict) -> int:
    """Parameters of the platform GPT (ocb.model) for a train.yaml `model` block."""
    d, layers = model["d_model"], model["n_layer"]
    return 2 * model["vocab"] * d + model["ctx"] * d + layers * (12 * d * d + 13 * d) + 2 * d


def check_ckpt_capacity(spec: TaskSpec, label: str, job: dict) -> None:
    """The checkpoint volume (/shared/ckpt) must hold what a configuration keeps by design (the newest `ckpt_keep` plus
    the one being written, or every checkpoint when nothing is pruned): a task's symptom is never an accidental full
    volume."""
    every, keep = job.get("ckpt_every") or 0, job.get("ckpt_keep") or 0
    if not every or spec.substrate == "gpu":  # GPU tasks checkpoint to a disk volume, not a size-limited one
        return
    params = param_count(job["model"])
    kept = keep + 1 if keep else job["steps"] // every
    need = kept * params * CKPT_BYTES_PER_PARAM
    capacity = spec.hardware.ckpt_volume_mb * 2**20
    if need > 0.8 * capacity:
        raise ValueError(
            f"{spec.id}: the {label} config keeps {kept} checkpoints of {params} parameters "
            f"(~{need / 2**20:.0f} MiB), more than 80% of the {spec.hardware.ckpt_volume_mb} MiB store"
        )


def check_replication_time(spec: TaskSpec, broken: dict, reference: dict) -> None:
    """With a throttled object store (put_bps), rank 0's checkpoint replication is a long stall: the reference's
    process-group timeout must outlast it with margin, and the deadline must cover the run's replications."""
    bps, every = spec.hardware.objstore.get("put_bps"), reference.get("ckpt_every") or 0
    if not bps or not every:
        return
    params = param_count(reference["model"])
    replica_s = params * CKPT_BYTES_PER_PARAM / bps
    if reference.get("pg_timeout_s", 120) < 1.5 * replica_s:
        raise ValueError(
            f"{spec.id}: a checkpoint replicates in ~{replica_s:.0f}s at {bps} B/s, but the reference's "
            f"pg_timeout_s is {reference.get('pg_timeout_s', 120)}"
        )
    total = replica_s * (reference["steps"] // every)
    if spec.verify.deadline_s and total > 0.7 * spec.verify.deadline_s:
        raise ValueError(f"{spec.id}: replication alone takes ~{total:.0f}s of the {spec.verify.deadline_s}s deadline")


CANARY_COMMENT = {".py": "# ", ".yaml": "# ", ".yml": "# ", ".env": "# ", ".conf": "# ", ".sh": "# ", ".sbatch": "# ",
                  ".md": "<!-- ", ".toml": "# ", ".txt": "# "}  # fmt: skip


def _canary_mark(path: Path) -> None:
    """Prepend the canary comment to a published fix file (after a shebang when there is one); other file types are
    left as they are. The reference tree and the solution directory ship with the dataset, so a scraped copy or a fetch
    of one into /ops carries the GUID the audit scans for."""
    prefix = CANARY_COMMENT.get(path.suffix)
    if prefix is None:
        return
    line = f"{prefix}{CANARY}" + (" -->" if prefix == "<!-- " else "")
    text = path.read_text()
    if CANARY in text:
        return
    if text.startswith("#!"):
        head, _, body = text.partition("\n")
        path.write_text(f"{head}\n{line}\n{body}")
    else:
        path.write_text(f"{line}\n{text}")


def _render(spec: TaskSpec, out: Path, variant: str, slot: int = 0, host: gpu.Host | None = None) -> None:
    env, sol, tests = out / "environment", out / "solution", out / "tests"
    broken = env / "ops"
    broken_raw, reference_raw = patches.task_trees(spec)
    fixed = patches.touched(patches.solution_patch(spec).read_text())
    try:
        shutil.copytree(broken_raw, broken)
        shutil.copytree(broken_raw, tests / "reference")
        for rel in fixed:
            for dst in (tests / "reference" / rel, sol / "files" / rel):
                if dst.parent == tests / "reference" and rel == "ANALYSIS.md":
                    continue  # the reference run needs the fixed job, not the write-up: the published tree carries less
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(reference_raw / rel, dst)
                _canary_mark(dst)  # every published copy of the fix carries the canary (reference tree and solution)
    finally:
        shutil.rmtree(broken_raw)
        shutil.rmtree(reference_raw)
    job = None
    if spec.substrate != "serving":
        job = yaml.safe_load((broken / "jobs" / "train" / "train.yaml").read_text())
        for label, ops in (("broken", broken), ("reference", tests / "reference")):
            check_ckpt_capacity(spec, label, yaml.safe_load((ops / "jobs" / "train" / "train.yaml").read_text()))
        check_replication_time(
            spec, job, yaml.safe_load((tests / "reference" / "jobs" / "train" / "train.yaml").read_text())
        )
    verify = verify_config(spec, job, host)
    if spec.substrate != "serving":
        rules = contract_lines(verify)
        for ops in (broken, tests / "reference"):
            contract = ops / "jobs" / "train" / "CONTRACT.md"
            contract.write_text(contract.read_text() + rules)
    shutil.copytree(broken, tests / "pristine")

    spec_text = spec.spec.strip().format(**spec.raw["verify"])
    (out / "instruction.md").write_text(instruction(spec, spec_text, variant))
    (out / "task.toml").write_text(task_toml(spec, variant))
    (out / "README.md").write_text(readme(spec))
    imgs = image_tags()
    tests_store = ""
    if spec.store:
        # Same runs and corruption in both images, from different teachers (the agent never sees the verifier's).
        runs = spec.raw["store"]["runs"]
        (tests / "store.yaml").write_text(
            yaml.safe_dump({"teacher_seed": spec.store.verifier_teacher_seed, "runs": runs}, sort_keys=False)
        )
        tests_store = "RUN python3 -m harness.store /tests/store.yaml /tests/store && rm /tests/store.yaml\n"
    if variant == "ablation":
        _environment_ablation(spec, env, imgs)
    elif variant == "snapshot":
        _environment_ablation(spec, env, imgs, baked=True)
    elif variant == "logs":
        _environment_logs(spec, env, imgs, bootstrap_config(spec, spec_text, job, verify))
    else:
        bootstrap = bootstrap_config(spec, spec_text, job, verify)
        _environment(spec, env, imgs, bootstrap, egress=variant in ("net", "cheat-net"), slot=slot, host=host)
    (sol / "solve.sh").write_text(SOLVE.format(canary=CANARY))
    (tests / "Dockerfile").write_text(TESTS_DOCKERFILE.format(canary=CANARY, image=imgs["harness"], store=tests_store))
    verifier_compose = compose(spec, imgs, verifier=True, slot=slot, host=host)
    (tests / "docker-compose.yaml").write_text(yaml.safe_dump(verifier_compose, sort_keys=False))
    (tests / "test.sh").write_text(TEST_SH.format(canary=CANARY))
    (tests / "verify.yaml").write_text(dump(verify))
    write_image_lock(env, imgs)
    write_image_lock(tests, imgs)
    for script in [sol / "solve.sh", tests / "test.sh", *out.rglob("*.sh"), *out.rglob("*.sbatch")]:
        script.chmod(0o755)


def write_image_lock(side: Path, imgs: dict[str, str]) -> None:
    """images.lock: the images this side of the task uses, each with a hash of the sources it is built from, so the
    task's digest and version change whenever the code that runs or grades it does (also before a release pins
    registry digests)."""
    used = set()
    for path in side.glob("Dockerfile*"):
        used |= {line.split()[1] for line in path.read_text().splitlines() if line.startswith("FROM ")}
    compose_file = side / "docker-compose.yaml"
    if compose_file.exists():
        services = yaml.safe_load(compose_file.read_text())["services"].values()
        used |= {svc["image"] for svc in services if "image" in svc}
    roles = {role for role, ref in imgs.items() if ref in used}
    if "harness" in roles:
        roles.add("runtime")  # the harness image is built on it
    lines = [f"# {CANARY}", "# The images used here and a hash of the sources each is built from (bench.provenance)."]
    lines += [f"{role} {imgs[role]} {source_hash(role)}" for role in sorted(roles)]
    (side / "images.lock").write_text("\n".join(lines) + "\n")


def _environment(
    spec: TaskSpec,
    env: Path,
    imgs: dict,
    bootstrap: BootstrapConfig,
    egress: bool,
    slot: int = 0,
    host: gpu.Host | None = None,
) -> None:
    """The agent's environment: workstation, cluster, object store and the provisioning sidecar."""
    env_store = ""
    if spec.store:
        runs = spec.raw["store"]["runs"]
        (env / "store.yaml").write_text(
            yaml.safe_dump({"teacher_seed": spec.store.agent_teacher_seed, "runs": runs}, sort_keys=False)
        )
        # The recipe names the corruption, so it is removed in the same layer that uses it.
        env_store = (
            "COPY store.yaml /tmp/store.yaml\n"
            "RUN python3 -m harness.store /tmp/store.yaml /opt/store && rm /tmp/store.yaml\n"
        )
    (env / "Dockerfile").write_text(ENV_DOCKERFILE.format(canary=CANARY, image=imgs["runtime"]))
    (env / "Dockerfile.provision").write_text(
        PROVISION_DOCKERFILE.format(canary=CANARY, harness=imgs["harness"], store=env_store)
    )
    agent_compose = compose(spec, imgs, verifier=False, egress=egress, slot=slot, host=host)
    (env / "docker-compose.yaml").write_text(yaml.safe_dump(agent_compose, sort_keys=False))
    (env / "bootstrap.yaml").write_text(dump(bootstrap))


def _environment_ablation(spec: TaskSpec, env: Path, imgs: dict, baked: bool = False) -> None:
    """Ops-only ablation: the workstation alone, with /ops baked in. With `baked` (the snapshot variant), also the copy
    of the evidence (bench.snapshot) baked in at /shared/evidence and /shared/logs, and no volume behind /shared."""
    main = compose(spec, imgs, verifier=False)["services"]["main"]
    main.pop("cap_add", None)
    main.pop("depends_on", None)  # no keys service (nor anything else) to wait for: the workstation alone
    volumes = (
        {"ops": {}} if baked else {"ops": {}, "shared": {}}
    )  # no cluster: the checkpoint and dataset volumes have nothing behind them
    main["volumes"] = [v for v in main.get("volumes", []) if v.split(":", 1)[0] in volumes]
    doc = {
        "services": {"main": main},
        "volumes": volumes,
        "networks": {"cluster": {"internal": True}},
    }
    (env / "docker-compose.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    if baked:
        snapshot.materialise(spec.id, env / "snapshot")
    template = SNAPSHOT_DOCKERFILE if baked else ABLATION_DOCKERFILE
    (env / "Dockerfile").write_text(template.format(canary=CANARY, image=imgs["runtime"]))


def _environment_logs(spec: TaskSpec, env: Path, imgs: dict, bootstrap: BootstrapConfig) -> None:
    """Live read-only access: the standard cluster and provisioning, unchanged; a workstation with no network at all (an
    internal bridge still has a host-side gateway, through which a container reaches the host's own services), without
    the cluster's keys, with its own /ops and the shared volumes read-only; and the observer, the only new service on
    the cluster's network, which writes the views the workstation reads in /obs. Harbor drives the workstation through
    docker exec, which needs no network."""
    if spec.substrate == "gpu":
        raise ValueError(f"{spec.id}: the logs variant covers the CPU training and serving tasks")
    _environment(spec, env, imgs, bootstrap, egress=False)
    doc = yaml.safe_load((env / "docker-compose.yaml").read_text())
    services = doc["services"]
    training = spec.substrate != "serving"
    main = services["main"]
    main.pop("cap_add", None)
    main["volumes"] = [
        "workspace:/ops",  # seeded from the image's /opt/ops-seed at first start (entrypoint.sh)
        "shared:/shared:ro",
        *(["ckpt:/shared/ckpt:ro"] if training else []),
        # every training task mounts a volume of the same name (empty where the store keeps no datasets apart): the
        # mount and its source name in /proc/self/mountinfo point at no task
        *(["datasets:/store/datasets:ro"] if training else []),
        "obs:/obs:ro",
    ]
    main.pop("networks", None)
    main["network_mode"] = "none"
    # provision mounts ckpt inside the shared volume read-write, so the mountpoint exists before the read-only mounts
    main["depends_on"] = {"provision": {"condition": "service_started"}, "obs": {"condition": "service_started"}}
    obs: dict = {
        "build": {"context": ".", "dockerfile": "Dockerfile.obs"},
        "hostname": "obs",
        "command": ["/usr/local/libexec/obs-collect"],
        "volumes": ["obs:/obs", "shared:/shared:ro", *([KEYS_MOUNT] if training else [])],
        "environment": {"OBS_SUBSTRATE": spec.substrate},
        "networks": ["cluster"],
        "cpus": 0.25,
        "mem_limit": "256m",
    }
    if training:
        obs["depends_on"] = dict(KEYS_READY)
    services["obs"] = obs
    doc["volumes"].update({"workspace": {}, "obs": {}, **({"datasets": {}} if training else {})})
    (env / "docker-compose.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    (env / "Dockerfile").write_text(LOGS_DOCKERFILE.format(canary=CANARY, image=imgs["runtime"]))
    (env / "Dockerfile.obs").write_text(OBS_DOCKERFILE.format(canary=CANARY, image=imgs["runtime"]))
    here = Path(__file__).parent / "readonly"
    for name, dest in (("tools.py", env / "readonly" / "tools.py"), ("collect.py", env / "obs" / "collect.py")):
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(here / name, dest)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench render", description="Render Harbor tasks from the task specs.")
    ap.add_argument("tasks", nargs="*", help="task ids (default: all)")
    ap.add_argument("--variant", choices=VARIANTS, default="standard")
    ap.add_argument("--out", type=Path, help="output directory (default: tasks/ for standard, build/tasks-VARIANT)")
    ap.add_argument("--split", choices=["test", "dev", "gpu", "all"], default=None)
    ap.add_argument("--host", action="store_true", help="GPU tasks: render for this host (gpu/host.yaml, from "
                    "`bench gpu-host`) into build/tasks-gpu-slotK instead of tasks/gpu")  # fmt: skip
    ap.add_argument("--slot", type=int, default=0, help="GPU tasks with --host: the host's slot to render for")
    ap.add_argument("--bump", action="store_true", help="bump the version of every task whose content changed")
    args = ap.parse_args(argv)
    split = args.split or ("all" if args.variant == "standard" else "test")
    for spec in load_specs():
        if (not args.tasks or spec.id in args.tasks) and split in ("all", spec.split):
            if args.out:
                root = args.out
            elif spec.substrate == "gpu" and args.host:
                root = TASKS.parent / "build" / f"tasks-gpu-slot{args.slot}"
            elif args.variant == "standard":
                root = TASKS / spec.split
            else:
                root = TASKS.parent / "build" / f"tasks-{args.variant}"
            if args.variant == "snapshot" and not args.tasks and not _has_snapshot(spec.id):
                print(f"skipped {spec.id} (no evidence snapshot at its current digest)")
                continue
            gpu_host = gpu.load() if args.host and spec.substrate == "gpu" else None
            try:
                print(f"rendered {render(spec, root, args.variant, args.slot if gpu_host else 0, gpu_host)}")
            except SnapshotError as exc:
                raise SystemExit(str(exc)) from exc
    if args.variant == "standard" and not args.out:
        if not args.tasks and split == "all":
            prune()
        if args.bump:
            bump_versions()
        write_manifests()


def _has_snapshot(task: str) -> bool:
    try:
        snapshot.find(task)
    except SnapshotError:
        return False
    return True


def prune() -> None:
    """Remove rendered tasks (and their version entries) whose spec no longer exists, e.g. after a rename."""
    known = {(s.split, s.id) for s in load_specs()}
    for split in ("test", "dev", "gpu"):
        for task in sorted((TASKS / split).glob("*/task.toml")):
            if (split, task.parent.name) not in known:
                shutil.rmtree(task.parent)
                print(f"removed {task.parent} (no spec)")
    table = versions.load()
    ids = {i for _, i in known}
    if set(table) - ids:
        versions.save({k: v for k, v in table.items() if k in ids})


def bump_versions() -> None:
    """Record each task's part hashes; bump (and re-render) a task whose content changed since its version."""
    table = versions.load()
    for spec in load_specs():
        hashes = versions.part_hashes(task_dir(spec))
        entry = table.get(spec.id)
        component = versions.required_bump(entry, hashes)
        if entry is not None and component is not None and entry["version"] == spec.version:
            new = versions.bumped(spec.version, component)
            versions.set_spec_version(spec, new)
            load_specs.cache_clear()
            spec = by_id(spec.id)
            render(spec, TASKS / spec.split)
            hashes = versions.part_hashes(task_dir(spec))
            print(f"bumped {spec.id} to {new}")
        table[spec.id] = {"version": spec.version, **hashes}
    versions.save(table)


def write_manifests() -> None:
    """tasks/<split>/dataset.toml: Harbor dataset manifests pinning every task by its content digest."""
    names = {"test": f"{NAMESPACE}/core", "dev": f"{NAMESPACE}/dev", "gpu": f"{NAMESPACE}/gpu"}
    for split, name in names.items():
        specs = [s for s in load_specs() if s.split == split]
        lines = [f"# {CANARY}", 'schema_version = "1.0"', "", "[dataset]", f'name = "{name}"',
                 f'version = "{DATASET_VERSION}"', f'description = "{DATASET_DESCRIPTION[split]}"', ""]  # fmt: skip
        for spec in specs:
            lines += ["[[tasks]]", f'name = "{NAMESPACE}/{spec.id}"', f'digest = "{task_digest(task_dir(spec))}"', ""]
        metric = TASKS / split / "metric.py"  # the Hub metric (templates/dataset/metric.py), pinned like a task
        shutil.copyfile(TEMPLATES / "dataset" / "metric.py", metric)
        digest = hashlib.sha256(metric.read_bytes()).hexdigest()
        lines += ["[[files]]", 'path = "metric.py"', f'digest = "sha256:{digest}"', ""]
        (TASKS / split / "dataset.toml").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
