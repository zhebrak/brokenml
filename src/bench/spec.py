"""Task specs (families/<F>/<id>/spec.yaml): the typed model and the one loader every tool uses."""

from __future__ import annotations

import re
import warnings
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from bench.paths import FAMILIES, TASKS
from harness.config import BootstrapConfig, Data, Site, VerifyConfig

Category = Literal["collectives", "performance", "memory", "state", "liveness", "scheduling", "serving", "correctness"]
CATEGORIES: tuple[str, ...] = Category.__args__  # display order
# The systems principle each category's faults violate (bench catalog prints it; membership is judged against it).
CATEGORY_PRINCIPLES = {
    "collectives": "Ranks must form one process group (rendezvous, addresses, ports) and then issue the same "
    "collectives, in the same order, with the same shapes.",
    "performance": "A synchronous step runs at the speed of its slowest participant; many small messages are "
    "latency-bound; redundant communication wastes bandwidth.",
    "memory": "Weights, gradients and optimizer state per parameter, and activations per micro-batch, set the "
    "footprint; sharding divides state, accumulation divides activations.",
    "state": "A checkpoint must be atomic, complete, and loadable under the current topology.",
    "liveness": "Inner timeouts must be shorter than outer ones, and longer than the longest legitimate stall.",
    "scheduling": "A job starts only if its request can be satisfied, and ends only when every process it owns exits.",
    "serving": "Batching and concurrency raise throughput until a resource or the latency limit binds.",
    "correctness": "Training must optimise the intended objective on the intended data; data-parallel training must "
    "equal large-batch SGD.",
}
# The evidence that decides a task: live process stacks and Flight Recorder traces; exception messages; scheduler
# state; a node's own state or configuration (often against another node's); storage; a service's responses; data
# statistics; metric trajectories. No channel may hold more than a fifth of the test split (tests/test_spec.py).
Channel = Literal["stacks", "errors", "scheduler", "node-state", "storage", "service", "data", "metrics"]
CHANNELS: tuple[str, ...] = Channel.__args__


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Metadata(Strict):
    """Declared before any agent runs (task.toml [metadata]); measured labels live in results/labels.json."""

    family: Literal["H", "M", "S", "B", "O", "C", "T", "P", "F", "V", "D"]
    category: Category
    channel: Channel  # the evidence that decides the task
    subcategory: str
    principle: str
    mechanism: str
    # The declared chain the diagnosis rubric grades ANALYSIS.md against (docs/diagnosis-rubric.md): the fault in the
    # system, the intermediate effect, the symptom the agent sees. Host-side only: the judge reads it from the spec;
    # it is not rendered into task.toml (so not in the task digest), the instruction, /ops, CONTRACT.md or the report.
    causal_chain: list[str] = Field(min_length=3, max_length=3)
    fault_kind: Literal[
        "hang", "mismatch", "slowdown", "crash", "pending", "rejected", "never-ends", "never-ready", "stall",
        "errors", "quality",
    ]  # fmt: skip
    difficulty: Literal["easy", "medium", "hard"]  # the author's label; empirical difficulty comes from runs
    evidence_author: Literal["static", "runtime"]  # the author's judgement; the ops-only ablation measures it
    gpu_symptom: Literal[
        "same", "louder-on-gpu", "louder-on-cpu", "absent-on-gpu", "misleading-on-gpu", "different-evidence",
        "link-dependent", "not-measured",
    ]  # fmt: skip
    provenance_kind: Literal["issue-repro", "taxonomy-derived"]
    provenance: list[str] = Field(min_length=1)
    tags: list[str]
    expert_time_estimate_min: float = Field(gt=0)
    junior_time_estimate_min: float = Field(gt=0)

    @field_validator("causal_chain")
    @classmethod
    def _chain(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if not s.strip() or len(s) > 300]
        if bad:
            raise ValueError(f"causal_chain entries must be non-empty and short (at most 300 characters): {bad}")
        return v

    @field_validator("provenance")
    @classmethod
    def _urls(cls, v: list[str]) -> list[str]:
        bad = [u for u in v if not u.startswith("https://")]
        if bad:
            raise ValueError(f"provenance entries must be https URLs: {bad}")
        return v


class Readme(Strict):
    """The four human-written sections Terminal-Bench requires in a task README."""

    difficulty: str
    solution: str
    verification: str
    experience: str


class Link(Strict):
    """Emulated inter-node link (netem on the nodes)."""

    delay_ms: int | float | None = None
    rate_mbit: int | float | None = None


class NodeSetup(Strict):
    """Site state a node starts with (images/runtime/hwsetup.sh applies it at first start, then forgets how)."""

    stale_host: str | None = None  # an /etc/hosts entry for this host name that points at an unused address
    loopback_self: bool = False  # the node's own name resolves to 127.0.1.1 (a Debian-style /etc/hosts line)
    metrics_port: int | None = Field(default=None, gt=0, lt=65536)  # the site exporter's port (default 9100)
    site_job_env: list[str] = []  # extra KEY=VALUE lines of the site's job environment (/etc/platform/job.env)
    nccl_conf: list[str] = []  # extra lines of the site's /etc/nccl.conf (GPU nodes)

    @field_validator("site_job_env", "nccl_conf")
    @classmethod
    def _assignments(cls, v: list[str]) -> list[str]:
        bad = [line for line in v if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=[^\n]*", line)]
        if bad:
            raise ValueError(f"lines must be KEY=VALUE: {bad}")
        return v


class Hardware(Strict):
    network: Link | None = None
    # Object store: bandwidth in bytes/s (put_bps, get_bps, or per client host, e.g. get_bps_c2), and the request
    # rate on datasets per client (get_burst requests at once, refilled at get_per_s per second).
    objstore: dict[str, int] = {}
    # Per-service docker compose overrides (memory limits, emulation environment); mirrored in both composes.
    services: dict[str, dict[str, Any]] = {}
    # Capacity of the checkpoint volume (/shared/ckpt: its own filesystem in every CPU training task), in MiB. Not the
    # checkpoint store (`store`, /shared/ckpt-store): that holds an earlier run's checkpoints for resume tasks.
    ckpt_volume_mb: int = Field(default=512, gt=0)
    node_setup: dict[str, NodeSetup] = {}  # per node: site state at first start (validated; see NodeSetup)
    model_fetch_s: int | None = Field(default=None, gt=0)  # serving: the emulated model store's fetch time
    # Nodes that are also on the site's management network: it is their eth0 and the cluster network their eth1.
    mgmt_nodes: list[str] = []

    @field_validator("services")
    @classmethod
    def _no_raw_knobs(cls, v: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        raw = sorted(k for svc in v.values() for k in (svc.get("environment") or {}) if str(k).startswith("OCB_"))
        if raw:
            raise ValueError(f"set {raw} through hardware.node_setup / model_fetch_s, not as raw environment")
        return v

    @field_validator("objstore")
    @classmethod
    def _rates(cls, v: dict[str, int]) -> dict[str, int]:
        known = ("put_bps", "get_bps", "get_burst", "get_per_s")
        bad = [k for k in v if not (k in known or k.startswith(("put_bps_", "get_bps_")))]
        if bad:
            raise ValueError(f"unknown objstore keys: {bad}")
        return v


class StoreRun(Strict):
    name: str
    steps: int = Field(gt=0)
    ckpt_every: int = Field(gt=0)
    schedule_steps: int | None = None
    model: dict[str, int] = {}
    corrupt: list[str] = []


class Store(Strict):
    """Checkpoint-resume tasks: stores trained at image build time, from different teachers for agent and verifier."""

    agent_teacher_seed: int
    verifier_teacher_seed: int
    runs: list[StoreRun] = Field(min_length=1)

    @model_validator(mode="after")
    def _distinct_teachers(self) -> Store:
        if self.agent_teacher_seed == self.verifier_teacher_seed:
            raise ValueError("the agent's and the verifier's stores must come from different teachers")
        return self


class Probe(Strict):
    """A decisive observation from the task's principle-7 write-up: `run` in the agent's workstation of a bootchecked
    environment, and `expect` (a regex) must match the output. Host-side only (bench bootcheck); never rendered."""

    run: str
    expect: str
    note: str = ""


class TaskSpec(Strict):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str
    split: Literal["test", "dev", "gpu"] = "test"  # gpu: the GPU track (its own dataset and leaderboard column)
    substrate: Literal["slurm", "serving", "gpu"] = "slurm"  # gpu: one GPU node (templates/ops-gpu)
    spec: str  # the job's spec as the agent reads it; {placeholders} are filled from `verify`
    metadata: Metadata
    readme: Readme
    bootstrap: BootstrapConfig
    verify: VerifyConfig
    hardware: Hardware = Hardware()
    store: Store | None = None
    data: Data | None = None
    site: Site | None = None  # site state outside /ops, applied before every run in both clusters
    # Issue-repro tasks: what the source reports and what the task adapts (task cards). Host-side only: never
    # rendered into a task directory.
    adaptation: str | None = None
    probes: list[Probe] = []  # evidence probes asserted by bench bootcheck
    twin_of: str | None = None  # GPU twin: the CPU task whose fault, fix and wrong fixes it reuses (bench.patches)
    nodes: list[str] = ["c1", "c2"]
    version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")  # semver; bench.versions bumps it
    agent_timeout_s: float = 1500
    bootstrap_timeout_s: float = 600
    verifier_timeout_s: float = 1200

    _dir: Path = PrivateAttr()
    _raw: dict = PrivateAttr()

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def raw(self) -> dict:
        """The spec as written (key order preserved), for outputs that mirror it."""
        return self._raw

    @model_validator(mode="after")
    def _consistent(self) -> TaskSpec:
        if self.substrate in ("slurm", "gpu"):
            if self.verify.deadline_s is None:
                raise ValueError("training tasks need verify.deadline_s")
            if self.verify.throughput is None and self.verify.loss_max is None and self.split == "test":
                warnings.warn(f"{self.id}: no loss or throughput check", stacklevel=2)
        else:
            if self.verify.throughput is None or self.verify.ttft_p95_max_s is None:
                raise ValueError("serving tasks need verify.throughput and verify.ttft_p95_max_s")
        if self.twin_of is not None and self.substrate != "gpu":
            raise ValueError("only GPU tasks are twins of a CPU task")
        if (self.substrate == "gpu") != (self.split == "gpu"):
            raise ValueError("GPU tasks (substrate gpu) form the gpu split, and only they do")
        if self.substrate == "gpu" and self.nodes != ["g1"]:
            raise ValueError("GPU tasks run on one GPU node: nodes: [g1]")
        unknown = (set(self.hardware.mgmt_nodes) | set(self.hardware.node_setup)) - set(self.nodes)
        if unknown:
            raise ValueError(f"hardware.mgmt_nodes / node_setup name nodes not in nodes: {sorted(unknown)}")
        if self.metadata.subcategory == "checkpoint-resume" and self.store is None:
            raise ValueError("checkpoint-resume tasks need a store")
        return self


def load(spec_dir: Path) -> TaskSpec:
    raw = yaml.safe_load((spec_dir / "spec.yaml").read_text())
    try:
        spec = TaskSpec.model_validate(raw)
    except ValueError as exc:
        raise ValueError(f"{spec_dir / 'spec.yaml'}: {exc}") from exc
    if spec.id != spec_dir.name:
        raise ValueError(f"{spec_dir}: id {spec.id!r} does not match the directory name")
    if spec.metadata.family != spec_dir.parent.name:
        raise ValueError(f"{spec_dir}: family {spec.metadata.family!r} does not match the directory")
    spec._dir, spec._raw = spec_dir, raw
    return spec


@cache
def load_specs(families: Path = FAMILIES) -> tuple[TaskSpec, ...]:
    """Every task spec, sorted by id. The only way tools read specs."""
    specs = tuple(sorted((load(p.parent) for p in families.glob("*/*/spec.yaml")), key=lambda s: s.id))
    ids = [s.id for s in specs]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate task ids: {sorted(dupes)}")
    sets = calibration_sets()
    for s in specs:
        if s.verify.calibration and s.verify.calibration not in sets:
            raise ValueError(f"{s.id}: verify.calibration {s.verify.calibration!r} is not in calibration/sets.yaml")
    return specs


def calibration_sets() -> dict:
    return yaml.safe_load((FAMILIES.parent / "calibration" / "sets.yaml").read_text())


def by_id(task_id: str) -> TaskSpec:
    for spec in load_specs():
        if spec.id == task_id:
            return spec
    raise KeyError(f"no task spec with id {task_id!r}")


def task_dir(task: str | TaskSpec) -> Path:
    """Where a task is rendered: tasks/<split>/<id> (so `harbor run -p tasks/test` runs exactly the test split)."""
    spec = task if isinstance(task, TaskSpec) else by_id(task)
    return TASKS / spec.split / spec.id
