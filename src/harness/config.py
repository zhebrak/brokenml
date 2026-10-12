"""Typed configuration shared by the generator (bench.render), the provisioning sidecar and the verifier.

Every model rejects unknown keys, so a typo in a task spec fails at render time instead of silently turning a rule
off. bench.render writes bootstrap.yaml and verify.yaml from these models (only the values that differ from the
defaults), and provisioning and the verifier parse them back with the same models, so each default lives here only.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ----------------------------------------------------------------------------------------------------------------
# Policy constants: what the agent may change in /ops (enforced by harness.verify.policy, stated in CONTRACT.md).
MAX_CHANGED_BYTES = 1_000_000
# slurm.conf keys that name programs, plugins or identities. Never changeable, whatever a task allows.
SLURM_DENY = re.compile(
    r"^(include|prolog|epilog|prologslurmctld|epilogslurmctld|taskprolog|taskepilog|srunprolog|srunepilog|"
    r"healthcheckprogram|jobcomptype|jobcomploc|plugstackconfig|slurmuser|slurmduser|authtype|authalttypes|"
    r"resumeprogram|suspendprogram|rebootprogram|mailprog|jobsubmitplugins|.*plugin.*|.*program.*)$",
    re.IGNORECASE,
)
DEFAULT_SLURM_ALLOWED = frozenset(
    {
        "NodeName",
        "SchedulerParameters",
        "SlurmdTimeout",
        "SlurmctldTimeout",
        "MessageTimeout",
        "MinJobAge",
        "KillWait",
        "PrologEpilogTimeout",
        "UnkillableStepTimeout",
        "InactiveLimit",
        "ReturnToService",
    }
)
DEFAULT_FROZEN = ("cluster/cgroup.conf",)
# The contract every training task shares (templates/ops/jobs/train/CONTRACT.md states it); tasks add to it.
TRAINING_POLICY = {
    "contract": {
        "file": "jobs/train/train.yaml",
        # lr and warmup_steps are fixed in every training task (no reference or accepted fix changes them), so a
        # contract that freezes them does not single out the tasks where a learning-rate edit would be a wrong fix
        "fixed": [
            "model",
            "steps",
            "seed",
            "train_seqs",
            "val_seqs",
            "data",
            "export",
            "resume_from",
            "ckpt_dir",
            "lr",
            "warmup_steps",
        ],
        # pg_timeout_s is bounded in every training task, so the bound does not single out the one where it matters
        "bounds": {"eval_every": {"min": 1, "max": 100}, "pg_timeout_s": {"min": 1, "max": 300}},
        "products": [{"keys": ["micro_batch", "grad_accum"], "equals": 16}],
    }
}
# GPU tasks (templates/ops-gpu): one node, 2 ranks of 64 sequences, and the device and numeric precision are fixed
# (a precision change speeds a job up more than most faults slow it down).
GPU_TRAINING_POLICY = {
    "contract": {
        **TRAINING_POLICY["contract"],
        "fixed": [*TRAINING_POLICY["contract"]["fixed"], "device", "precision"],
        "products": [{"keys": ["micro_batch", "grad_accum"], "equals": 64}],
    }
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ----------------------------------------------------------------------------------------------------------------
# Data


class Noise(Strict):
    """Upstream data corruption: this share of tokens replaced by an out-of-vocabulary id."""

    rate: float = Field(gt=0, lt=1)
    id: int


DATASETS = "/srv/datasets"  # the object store's dataset volume, for a dataset served only by the store (Data.shards)


class Remap(Strict):
    """Train sequences whose token ids went through a fixed permutation, in `blocks` runs of consecutive rows at
    independent random positions (harness.corpus)."""

    rows: int = Field(gt=0)
    blocks: int = Field(default=1, gt=0)


class Data(Strict):
    noise: Noise | None = None
    # The train split is served only by the object store, as this many objects (harness.corpus).
    shards: int | None = Field(default=None, gt=0)
    remap: Remap | None = None
    # The corpus holds this many train sequences (the data team's full set); the job trains on the first train_seqs.
    train_rows: int | None = Field(default=None, gt=0)
    # The corpus holds this many validation sequences; the job validates on the first val_seqs of them, so a corpus
    # with fewer than val_seqs gives the job fewer sequences than its config asks for.
    val_rows: int | None = Field(default=None, gt=0)
    # The corpus carries a shard manifest (`shards`: one [start, end) row range per rank over the job's train rows):
    # `disjoint` as the data pipeline documents, `identical` when the pipeline wrote rank 0's range for every rank.
    shard_manifest: Literal["disjoint", "identical"] | None = None


class Corpus(Strict):
    """Sizes of the materialised corpus (sequences); set by the generator from the job's train.yaml."""

    train: int = Field(gt=0)
    val: int = Field(gt=0)
    length: int = Field(gt=1)


class Reservation(Strict):
    """A Slurm reservation the site has in place (`scontrol create reservation`), with a start relative to when it is
    created (with TIME_FLOAT it keeps floating that far ahead)."""

    name: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    start_in_min: int = Field(gt=0)
    duration_min: int = Field(gt=0)
    flags: str = Field(default="MAINT,TIME_FLOAT", pattern=r"^[A-Z_,]+$")
    users: str = Field(default="root", pattern=r"^[a-z_][a-z0-9_,-]*$")


class SiteJob(Strict):
    """A job another user of the site has queued, pending until its begin time: visible in squeue (accounting storage
    is off, so not in sacct), unrelated
    to the task (a distractor the hardening plan certifies as non-causal: the reference passes with it present)."""

    name: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    user: Literal["svc-ci", "svc-train"] = "svc-ci"
    begin_in_min: int = Field(default=360, gt=0)
    time_min: int = Field(default=10, gt=0)
    comment: str = Field(default="", pattern=r"^[A-Za-z0-9 _.,:-]*$")


class Site(Strict):
    """Site state outside /ops (not the job's to change) that the agent's cluster and every verifier run start from;
    applied right before each submission, after the run directories are reset."""

    reservations: list[Reservation] = []
    jobs: list[SiteJob] = []


# ----------------------------------------------------------------------------------------------------------------
# Provisioning (bootstrap.yaml)


class Symptom(Strict):
    """What the broken job must show before the agent starts (recorded in /shared/evidence/symptom.json)."""

    kind: Literal["pending", "stall", "failed", "completed", "lingering", "rejected", "running", "serving"]
    reason: str | None = None  # pending: the required Slurm reason
    pending_s: float = 20  # pending without a reason: for this long
    stall_s: float = 45  # stall: RUNNING with no metrics progress for this long
    linger_s: float = 30  # lingering: training finished but the job still runs
    run_s: float = 60  # running: the job has trained for this long
    timeout_s: float = 300  # give up waiting
    log_match: str | None = None  # text the job log (or submission output) must contain


class BootstrapConfig(Strict):
    substrate: Literal["slurm", "serving", "gpu"] = "slurm"
    job: str = "train"
    min_nodes: int = Field(default=2, ge=0)  # idle nodes to wait for (0: only the health checks)
    spec: str = ""  # what the job should do (markdown, shown in report.md)
    store: bool = False  # a checkpoint store is installed at /shared/ckpt-store
    symptom: Symptom
    corpus: Corpus | None = None
    data: Data | None = None
    site: Site | None = None
    # serving
    ready_timeout_s: float = 180
    spec_tokens_per_s: float | None = None
    spec_ttft_p95_s: float | None = None


# ----------------------------------------------------------------------------------------------------------------
# Verification (verify.yaml)


class Product(Strict):
    keys: list[str]
    equals: int


class Bound(Strict):
    min: int | float | None = None
    max: int | float | None = None


class Contract(Strict):
    """Job-config rules: fixed keys, bounds and products in one file of /ops."""

    file: str = "jobs/train/train.yaml"
    fixed: list[str] = []
    bounds: dict[str, Bound] = {}
    products: list[Product] = []


class PolicyConfig(Strict):
    editable: list[str] = ["**"]  # glob patterns of /ops paths the agent may change
    frozen: list[str] = []  # in addition to DEFAULT_FROZEN
    slurm_allowed: list[str] = []  # in addition to DEFAULT_SLURM_ALLOWED
    contract: Contract = Contract()


class Throughput(Strict):
    ratio_min: float = Field(gt=0, le=1)  # reference time / agent time (training) or agent / reference tok/s


class MetricEvery(Strict):
    key: str
    every: int = Field(gt=0)


class Placement(Strict):
    """Where the job's ranks must run: observed by the verifier on the nodes (worker processes of the job's account)."""

    nodes: int = Field(gt=0)
    ranks_per_node: int = Field(gt=0)


class Replay(Strict):
    """The data a recorded verdict was graded on (diagnostics.json), so a re-grade compares verifiers like for like."""

    teacher_seed: int
    heldout_seed: int
    data_seed: int | None = None  # where a remapped block lands (records before 2026-10-03 have none)


class VerifyConfig(Strict):
    substrate: Literal["slurm", "serving", "gpu"] = "slurm"
    job: str = "train"
    min_nodes: int = Field(default=2, ge=0)
    world_size: int = 4  # ranks that must report metrics
    deadline_s: int | float | None = None  # per run, submission to every job terminal (training)
    store: bool = False
    corpus: Corpus | None = None
    data: Data | None = None
    policy: PolicyConfig = PolicyConfig()
    loss_max: int | float | None = None  # held-out loss bound for the export
    calibration: str | None = None  # the calib record the loss bound was set from (default: base-job)
    require_val_every: int | None = None
    require_metric_every: MetricEvery | None = None
    require_checkpoints_every: int | None = None
    require_eval_exports_every: int | None = None  # weights for the eval team at /shared/out/eval/step_<N>.safetensors
    require_step_coverage: bool = False
    placement: Placement | None = None
    throughput: Throughput | None = None
    policy_skip: bool = False  # only bench calibrate sets this (measuring variants outside the contract)
    replay: Replay | None = None  # only bench regrade --replay sets this (a scratch copy of the task, never committed)
    # Seconds for the object store's dataset request budget to refill from empty (rate-limited tasks): waited before
    # each run, so one run's requests never throttle the next.
    store_refill_s: float | None = None
    site: Site | None = None  # created before every run if missing (the controller keeps it)
    # GPU tasks: the GPU class the thresholds were calibrated on (bench.gpu) and the site's memory budget per GPU.
    gpu_class: str | None = None
    gpu_budget_mb: int | None = None
    # serving
    ready_timeout_s: float = 180
    ttft_p95_max_s: float | None = None
