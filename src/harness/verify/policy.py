"""Read the agent's /ops strictly as data and check it against the task's rules.

Nothing here executes agent content: no git, no shell, no imports from /ops.
"""

from __future__ import annotations

import fnmatch
import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from harness.config import DEFAULT_FROZEN, DEFAULT_SLURM_ALLOWED, MAX_CHANGED_BYTES, SLURM_DENY, PolicyConfig


@dataclass
class Policy:
    editable: list[str] = field(default_factory=lambda: ["**"])
    frozen: list[str] = field(default_factory=lambda: list(DEFAULT_FROZEN))
    slurm_allowed: set[str] = field(default_factory=lambda: set(DEFAULT_SLURM_ALLOWED))
    contract_file: str = "jobs/train/train.yaml"
    contract_fixed: list[str] = field(default_factory=list)
    contract_bounds: dict[str, dict] = field(default_factory=dict)
    contract_products: list[dict] = field(default_factory=list)

    @classmethod
    def from_config(cls, cfg: PolicyConfig | dict) -> Policy:
        cfg = cfg if isinstance(cfg, PolicyConfig) else PolicyConfig.model_validate(cfg)
        return cls(
            editable=list(cfg.editable),
            frozen=[*DEFAULT_FROZEN, *cfg.frozen],
            slurm_allowed=set(DEFAULT_SLURM_ALLOWED) | set(cfg.slurm_allowed),
            contract_file=cfg.contract.file,
            contract_fixed=list(cfg.contract.fixed),
            contract_bounds={k: b.model_dump(exclude_none=True) for k, b in cfg.contract.bounds.items()},
            contract_products=[p.model_dump() for p in cfg.contract.products],
        )


def _matches(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


# Bounds checked before any untrusted content is read: /ops is a small repository (a few hundred kB) plus at most
# MAX_CHANGED_BYTES of changes, so these leave ample room while keeping a huge tree from exhausting the verifier.
MAX_FILES = 5_000
MAX_TREE_BYTES = 32_000_000


def _read_tree(root: Path) -> tuple[dict[str, bytes], str | None]:
    files: dict[str, bytes] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():  # checked everywhere, including the paths skipped below
            return files, f"symlink not allowed: {rel}"
        if not path.is_dir() and not path.is_file():
            return files, f"special file not allowed: {rel}"
        if rel == ".git" or rel.startswith(".git/") or "__pycache__" in path.parts or rel.endswith(".pyc"):
            continue
        if path.is_dir():
            continue
        total += path.lstat().st_size
        if len(files) >= MAX_FILES or total > MAX_TREE_BYTES:
            return files, f"tree too large: more than {MAX_FILES} files or {MAX_TREE_BYTES // 1_000_000} MB"
        files[rel] = path.read_bytes()
    return files, None


class SlurmConfError(ValueError):
    pass


def slurm_conf_entries(text: str) -> dict[str, str]:
    """Key -> full line. Node/partition lines are keyed by their name, e.g. 'NodeName=c[1-2]'.

    Repeated keys and continuation lines are rejected: slurmctld keeps the first definition of a
    partition, so a repeated line could change the effective value while this parser saw another.
    """
    entries: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.endswith("\\"):
            raise SlurmConfError("continuation lines are not allowed")
        first = line.split()[0]
        record = first.split("=", 1)[0] in ("NodeName", "PartitionName", "NodeSet")
        if not record and len(line.split()) > 1:
            # slurmctld accepts several settings on one line; one per line keeps every key visible to the checks
            raise SlurmConfError(f"one setting per line: {line[:60]}")
        key = first if record else first.split("=", 1)[0]
        if key.lower() in {k.lower() for k in entries}:
            raise SlurmConfError(f"{key} is defined more than once")
        entries[key] = " ".join(line.split())
    return entries


def _check_slurm_conf(agent: str, pristine: str, allowed: set[str]) -> str | None:
    try:
        a = slurm_conf_entries(agent)
    except SlurmConfError as exc:
        return f"slurm.conf: {exc}"
    p = slurm_conf_entries(pristine)
    for key in sorted(a.keys() | p.keys()):
        if a.get(key) == p.get(key):
            continue
        base = key.split("=", 1)[0]
        if SLURM_DENY.match(base):
            return f"slurm.conf: {base} may not be changed"
        if base not in allowed:
            return f"slurm.conf: change to {key} not allowed"
    return None


def _check_contract(agent: dict, pristine: dict, policy: Policy) -> str | None:
    for key in policy.contract_fixed:
        if agent.get(key) != pristine.get(key):
            return f"contract: {key} must stay {pristine.get(key)!r}"
    for key, bound in policy.contract_bounds.items():
        value, base = agent.get(key), pristine.get(key)
        # a finite number of the declared type: YAML's .nan passes no comparison, and a bool is not a number
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return f"contract: {key} must be a finite number"
        if isinstance(base, int) and not isinstance(base, bool) and not isinstance(value, int):
            return f"contract: {key} must be an integer"
        if "min" in bound and value < bound["min"]:
            return f"contract: {key}={value} below {bound['min']}"
        if "max" in bound and value > bound["max"]:
            return f"contract: {key}={value} above {bound['max']}"
    for rule in policy.contract_products:
        values = [agent.get(k) for k in rule["keys"]]
        ints = [v for v in values if isinstance(v, int) and not isinstance(v, bool)]
        if len(ints) != len(values):
            return f"contract: {' x '.join(rule['keys'])} must be integers"
        product = 1
        for v in ints:
            product *= v
        if product != rule["equals"]:
            return f"contract: {' x '.join(rule['keys'])} = {product}, must be {rule['equals']}"
    return None


ANALYSIS = "ANALYSIS.md"  # every instruction asks for it, so it is writable whatever else a task restricts


def check(ops: Path, pristine: Path, policy: Policy) -> str | None:
    """Return a violation message, or None if /ops is acceptable."""
    agent_files, err = _read_tree(ops)
    if err:
        return err
    base_files, _ = _read_tree(pristine)
    changed_bytes = 0
    for rel, data in agent_files.items():
        if base_files.get(rel) == data:
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return f"non-text file not allowed: {rel}"
        if rel != ANALYSIS and (_matches(rel, policy.frozen) or not _matches(rel, policy.editable)):
            return f"file may not be changed: {rel}"
        changed_bytes += len(data)
    if changed_bytes > MAX_CHANGED_BYTES:
        return f"changes too large: {changed_bytes} bytes"
    for rel in base_files.keys() - agent_files.keys():  # a deletion is a change: the same allowlist applies
        if rel != ANALYSIS and (_matches(rel, policy.frozen) or not _matches(rel, policy.editable)):
            return f"file may not be removed: {rel}"
    if "cluster/slurm.conf" in base_files:
        if "cluster/slurm.conf" not in agent_files:
            return "file may not be removed: cluster/slurm.conf"
        err = _check_slurm_conf(
            agent_files["cluster/slurm.conf"].decode(), base_files["cluster/slurm.conf"].decode(), policy.slurm_allowed
        )
        if err:
            return err
    if policy.contract_file not in base_files:
        return None
    if policy.contract_file not in agent_files:
        return f"file may not be removed: {policy.contract_file}"
    try:
        agent_cfg = _parse_config(policy.contract_file, agent_files[policy.contract_file].decode())
    except (yaml.YAMLError, ValueError) as exc:
        return f"contract file does not parse: {exc}"
    return _check_contract(
        agent_cfg, _parse_config(policy.contract_file, base_files[policy.contract_file].decode()), policy
    )


def _parse_config(name: str, text: str) -> dict:
    """train.yaml (YAML) or engine.env (KEY=VALUE lines, integer values)."""
    if not name.endswith(".env"):
        value = yaml.safe_load(text)
        if value is None:
            return {}
        if not isinstance(value, dict):  # a list or a scalar is a policy failure, never a crash of the check
            raise ValueError("the configuration must be a mapping")
        return value
    out = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"not KEY=VALUE: {raw!r}")
        out[key.strip()] = int(value.strip()) if value.strip().isdigit() else value.strip()
    return out
