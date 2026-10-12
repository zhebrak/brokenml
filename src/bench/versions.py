"""Per-task versions that follow Harbor's comparability rules, checked against what actually changed.

Each rendered task has three parts, hashed separately (tasks/versions.json records them per version):
  env    environment/ and instruction.md: what the agent works with      -> a change bumps the major version
  tests  tests/: what the verifier runs and checks                       -> minor
  meta   task.toml (without its version line), README.md, solution/      -> patch
Harbor treats trials of a task as reusable across patch versions, re-grades them across minor versions and re-runs
them across major versions. `bench render --bump` applies the bump each changed part requires and records it;
tests/test_versions.py fails when a part changed without one.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from bench.paths import TASKS
from bench.spec import TaskSpec

VERSIONS = TASKS / "versions.json"
PARTS = {"env": 0, "tests": 1, "meta": 2}  # which semver component a change to each part bumps


def _hash_files(root: Path, files: list[Path], strip_version: bool = False) -> str:
    h = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        data = path.read_bytes()
        if strip_version and path.name == "task.toml":
            data = re.sub(rb'(?m)^version = ".*"\n', b"", data)
        h.update(path.relative_to(root).as_posix().encode() + b"\0" + hashlib.sha256(data).digest())
    return h.hexdigest()[:16]


def _tree(d: Path) -> list[Path]:
    return [p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts] if d.exists() else []


def part_hashes(task_dir: Path) -> dict[str, str]:
    return {
        "env": _hash_files(task_dir, [task_dir / "instruction.md", *_tree(task_dir / "environment")]),
        "tests": _hash_files(task_dir, _tree(task_dir / "tests")),
        "meta": _hash_files(
            task_dir,
            [task_dir / "task.toml", task_dir / "README.md", *_tree(task_dir / "solution")],
            strip_version=True,
        ),
    }


def load() -> dict:
    return json.loads(VERSIONS.read_text()) if VERSIONS.exists() else {}


def save(table: dict) -> None:
    VERSIONS.write_text(json.dumps(dict(sorted(table.items())), indent=1) + "\n")


def required_bump(old: dict | None, new: dict[str, str]) -> int | None:
    """The semver component (0 major, 1 minor, 2 patch) a change from `old` to `new` requires, or None."""
    if old is None:
        return None
    changed = [PARTS[p] for p in PARTS if old.get(p) != new[p]]
    return min(changed) if changed else None


def _parse(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(x) for x in version.split("."))
    return major, minor, patch


def bumped(version: str, component: int) -> str:
    """The version after a change of the given kind. Below 1.0.0 (the 0.x series; the first frozen version is
    0.1.0) every kind moves one place down, the usual semver convention for 0.x: an environment change bumps the minor
    version, anything else the patch version."""
    parts = list(_parse(version))
    if parts[0] == 0:
        component = min(component + 1, 2)
    parts[component] += 1
    return ".".join(str(x) if i <= component else "0" for i, x in enumerate(parts))


def check(spec: TaskSpec, task_dir: Path, table: dict) -> str | None:
    """A problem with this task's version, or None."""
    entry = table.get(spec.id)
    if entry is None:
        return f"{spec.id}: not in tasks/versions.json (run bench render --bump)"
    component = required_bump(entry, part_hashes(task_dir))
    if component is None:
        if entry["version"] != spec.version:
            return f"{spec.id}: spec version {spec.version} but tasks/versions.json records {entry['version']}"
        return None
    needed = bumped(entry["version"], component)
    if _parse(spec.version) < _parse(needed):
        part = next(p for p, c in PARTS.items() if c == component)
        return (f"{spec.id}: its {part} changed since {entry['version']}, which needs at least {needed}; "
                "run bench render --bump")  # fmt: skip
    return None


def set_spec_version(spec: TaskSpec, version: str) -> None:
    """Write `version:` into the spec file (after `split:`), keeping the rest of the file as it is."""
    path = spec.dir / "spec.yaml"
    text = path.read_text()
    line = f'version: "{version}"'
    if re.search(r"(?m)^version: ", text):
        text = re.sub(r"(?m)^version: .*$", lambda _: line, text, count=1)
    else:
        text = re.sub(r"(?m)^(split: .*)$", lambda m: f"{m.group(1)}\n{line}", text, count=1)
    path.write_text(text)
