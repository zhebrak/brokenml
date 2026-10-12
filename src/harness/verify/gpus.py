"""GPU state on the GPU node, read by the verifier as root over ssh (GPU tasks only).

nvidia-smi cannot name the processes using a GPU from inside a container (NVML reports host PIDs), so everything
here works per GPU: its identity, the settings that outlive a container (compute mode, clocks, power limit, MIG,
persistence), and its memory. The site's ballast (images/runtime/gpu-ballast.py) leaves `budget` bytes free on each
GPU, so "free memory is back to the budget" means nothing else holds it.
"""

from __future__ import annotations

from dataclasses import dataclass

QUERY = (
    "uuid,name,memory.total,memory.used,memory.free,compute_mode,persistence_mode,power.limit,"
    "clocks.applications.graphics,mig.mode.current"
)
COMMAND = f"nvidia-smi --query-gpu={QUERY} --format=csv,noheader,nounits"
# Settings a container can leave behind on a physical GPU; any change across a run is the host's fault, not the job's.
PERSISTENT = ("compute_mode", "persistence_mode", "power_limit", "app_clock", "mig")


@dataclass(frozen=True)
class GPU:
    uuid: str
    name: str
    total_mb: int
    used_mb: int
    free_mb: int
    compute_mode: str
    persistence_mode: str
    power_limit: str
    app_clock: str
    mig: str


def parse(csv: str) -> list[GPU]:
    gpus = []
    for line in csv.strip().splitlines():
        c = [x.strip() for x in line.split(",")]
        if len(c) != 10:
            raise ValueError(f"unexpected nvidia-smi line: {line!r}")
        gpus.append(GPU(c[0], c[1], int(c[2]), int(c[3]), int(c[4]), *c[5:]))
    return gpus


def class_problem(gpus: list[GPU], expected: str | None, slot_size: int = 2) -> str:
    """Why this node cannot grade the task (infra), or "": the slot's GPU count and the calibrated GPU model."""
    if len(gpus) != slot_size:
        return f"{len(gpus)} GPUs visible on the node, the task's slot has {slot_size}"
    if expected and expected != "unknown" and not expected.startswith(gpus[0].name + "/"):
        return f"GPU model {gpus[0].name}, the task was calibrated on {expected}"
    return ""


def budget_problem(gpus: list[GPU], budget_mb: int, slack: float = 0.05) -> str:
    """Why a GPU does not offer exactly the site budget, or "": less free means something else holds memory, more
    means the site's ballast is not (yet) holding the rest."""
    off = [f"{g.uuid}: {g.free_mb} MiB free" for g in gpus if abs(g.free_mb - budget_mb) > budget_mb * slack]
    return f"not the {budget_mb} MiB budget free: {', '.join(off)}" if off else ""


def changed(before: list[GPU], after: list[GPU]) -> list[str]:
    """Persistent settings that differ between two readings of the same GPUs."""
    out = []
    old = {g.uuid: g for g in before}
    for g in after:
        b = old.get(g.uuid)
        if b is None:
            out.append(f"{g.uuid} appeared")
            continue
        out += [
            f"{g.uuid} {f}: {getattr(b, f)} -> {getattr(g, f)}" for f in PERSISTENT if getattr(b, f) != getattr(g, f)
        ]
    return out + [f"{u} disappeared" for u in old.keys() - {g.uuid for g in after}]


def busy(gpus: list[GPU], idle_used_mb: dict[str, int], margin_mb: int = 256) -> set[str]:
    """GPUs holding clearly more memory than at idle (the ballast's share): in use by the job."""
    return {g.uuid for g in gpus if g.used_mb > idle_used_mb.get(g.uuid, 0) + margin_mb}
