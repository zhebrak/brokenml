"""The GPU track's host: which GPUs form each 2-GPU slot (gpu/host.yaml).

A GPU task's compose files reserve its slot's GPUs by UUID and pin the node to the slot's CPUs; the class names the
GPU model, link and driver the task's thresholds were calibrated on. The verifier detects the class itself on the
node before any agent code runs, so nothing about the hardware is read from /ops. Write gpu/host.yaml on a new host
with `bench gpu-host` (from nvidia-smi); without it, tasks render for slot 0 = GPUs 0 and 1 of an unknown class.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from bench.paths import ROOT

HOST_FILE = ROOT / "gpu" / "host.yaml"


class Slot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uuids: list[str] = Field(min_length=2, max_length=2)
    cpuset: str | None = None  # CPUs on the GPUs' NUMA node, e.g. "0-15"


class Host(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gpu_class: str  # e.g. "NVIDIA A100-SXM4-80GB/NV12/r580"
    mem_budget_gb: int = Field(default=16, gt=0)  # usable GPU memory per GPU (a site ballast holds the rest)
    slots: list[Slot] = Field(min_length=1)


DEFAULT = Host(gpu_class="unknown", slots=[Slot(uuids=["0", "1"])])


def load(path: Path = HOST_FILE) -> Host:
    return Host.model_validate(yaml.safe_load(path.read_text())) if path.exists() else DEFAULT


def _cpu_list(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out += list(range(int(lo), int(hi or lo) + 1))
    return out


def parse_host(gpus_csv: str, topo: str, driver: str, cpus_per_slot: int = 8) -> Host:
    """A host from `nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader` and `nvidia-smi topo -m`: GPUs are
    paired in index order, and a pair becomes a slot only if its link is NVLink (NV#) or one PCIe switch (PIX). Each
    slot gets its own CPUs: `cpus_per_slot` of the CPUs on its GPUs' NUMA node ("CPU Affinity"), none shared."""
    gpus = [[c.strip() for c in line.split(",")] for line in gpus_csv.strip().splitlines()]
    names = {g[2] for g in gpus}
    if len(names) != 1:
        raise ValueError(f"mixed GPU models: {sorted(names)}")
    lines = [line for line in topo.splitlines() if line.strip()]
    header = [h.strip() for h in lines[0].split("\t") if h.strip()]
    affinity_col = header.index("CPU Affinity") if "CPU Affinity" in header else None
    rows = {}
    for line in lines[1:]:
        cells = [c.strip() for c in line.split("\t")]
        if cells and re.fullmatch(r"GPU\d+", cells[0]):
            rows[int(cells[0][3:])] = cells[1:]
    taken: set[int] = set()
    slots, links = [], set()
    for a, b in zip(gpus[0::2], gpus[1::2], strict=False):
        i, j = int(a[0]), int(b[0])
        row = rows.get(i, [])
        link = row[j] if j < len(row) else "?"
        if not (link.startswith("NV") or link == "PIX"):
            continue
        cpuset = None
        cell = row[affinity_col] if affinity_col is not None and affinity_col < len(row) else ""
        if re.fullmatch(r"\d+(-\d+)?(,\d+(-\d+)?)*", cell):
            free = [c for c in _cpu_list(cell) if c not in taken][:cpus_per_slot]
            if len(free) < cpus_per_slot:
                raise ValueError(f"not enough CPUs left on GPU{i}'s NUMA node for slot {len(slots)}")
            taken |= set(free)
            cpuset = ",".join(map(str, free))
        slots.append(Slot(uuids=[a[1], b[1]], cpuset=cpuset))
        links.add(link)
    if not slots:
        raise ValueError("no GPU pair is joined by NVLink or one PCIe switch")
    return Host(gpu_class=f"{names.pop()}/{'+'.join(sorted(links))}/r{driver.split('.')[0]}", slots=slots)


def save(host: Host, path: Path = HOST_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(host.model_dump(), sort_keys=False))


def _smi(*args: str) -> str:
    return subprocess.run(["nvidia-smi", *args], capture_output=True, text=True, check=True, timeout=60).stdout


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench gpu-host", description="Describe this GPU host's slots in gpu/host.yaml.")
    ap.add_argument("--budget-gb", type=int, default=16, help="usable memory per GPU")
    args = ap.parse_args(argv)
    host = parse_host(
        _smi("--query-gpu=index,uuid,name", "--format=csv,noheader"),
        _smi("topo", "-m"),
        _smi("--query-gpu=driver_version", "--format=csv,noheader").splitlines()[0],
    )
    host = host.model_copy(update={"mem_budget_gb": args.budget_gb})
    save(host)
    print(f"{HOST_FILE}: {host.gpu_class}, {len(host.slots)} slots, {host.mem_budget_gb} GB per GPU")


if __name__ == "__main__":
    main()
