"""Provenance: what code, images and host produced a record, and which exact task content it measured.

Every record the tools write (calibration, sweep, QA, analysis, leak audit) embeds `stamp()`, so a published number
can be traced to a commit, a set of image IDs and a machine. Task content is identified by `task_digest()`, the same
digest Harbor records for every trial in lock.json, so records from different task versions are never pooled.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import yaml

from bench.paths import IMAGES, ROOT

# Harbor's content digest of a task directory (harbor.publisher.packager.Packager.compute_content_hash, Harbor 0.23):
# task.toml, instruction.md, README.md and every file under environment/, tests/, solution/ and steps/, minus default
# ignores, hashed as sha256 over "relpath\0sha256(file)\n" in path order.
_SINGLE = ("task.toml", "instruction.md", "README.md")
_DIRS = ("environment", "tests", "solution", "steps")
_IGNORED_SUFFIXES = (".pyc", ".swp", ".swo", "~")


def _run(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=ROOT, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return res.stdout.strip() if res.returncode == 0 else ""


# What each image is built from (for its source hash, recorded in the image as /opt/<pkg>/VERSION).
# The harness image is built on the runtime image, so its hash covers the platform code it runs as well.
IMAGE_SOURCES = {"runtime": ("src/ocb", "images/runtime"),
                 "runtime-cuda": ("src/ocb", "images/runtime"),
                 "harness": ("src/ocb", "images/runtime", "src/harness", "images/harness"),
                 "serve": ("images/serve",)}  # fmt: skip


def image_lock() -> dict[str, dict[str, str]]:
    return tomllib.loads((IMAGES / "images.toml").read_text())


def image_tags() -> dict[str, str]:
    """Role -> image reference: tag@digest once a release has recorded a digest, the local tag before."""
    return {role: f"{e['tag']}@{e['digest']}" if e.get("digest") else e["tag"] for role, e in image_lock().items()}


def source_hash(role: str) -> str:
    """A hash of the files an image is built from (tracked or not), so a dirty build is told apart from a clean one."""
    h = hashlib.sha256()
    for root in IMAGE_SOURCES[role]:
        for path in sorted((ROOT / root).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                h.update(
                    path.relative_to(ROOT).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest()
                )
    return h.hexdigest()[:16]


def image_ids() -> dict[str, str]:
    """Full immutable local image ID per configured image; empty when it is not built or Docker is absent. Read
    fresh on every call: an image rebuilt during a long chain must show in the rows stamped after it."""
    return {ref: _run(["docker", "image", "inspect", "-f", "{{.Id}}", ref]) for ref in image_tags().values()}


def study_images() -> dict:
    """images/study-images.json: the study's published images (registry ref, index digest, config digest, hashes)."""
    return json.loads((IMAGES / "study-images.json").read_text())


def study_image_status(role: str, local_id: str) -> str:
    """How a local image relates to the study's: "study" (the id is the study's), "classic-store" (the id is the
    study image's config digest, which is what the classic image store reports for it), "rebuilt" (another image)
    or "missing" (nothing under the tag)."""
    entry = study_images()["images"][role]
    if not local_id:
        return "missing"
    if local_id == entry["id"]:
        return "study"
    if local_id == entry["config"]:
        return "classic-store"
    return "rebuilt"


def pull_plan() -> list[str]:
    """The docker commands that fetch the study's images by digest and give them the local names the code expects."""
    cmds = []
    for entry in study_images()["images"].values():
        repo = entry["ref"].rsplit(":", 1)[0]
        cmds.append(f"docker pull {repo}@{entry['id']}")
        cmds.append(f"docker tag {repo}@{entry['id']} {entry['tag']}")
    return cmds


OPTIONAL_STUDY_ROLES = ("runtime-getenvfix",)  # only the re-grade needs it: absent is not a problem


def study_check() -> dict[str, str]:
    """Role -> study_image_status of what this host has under the role's local tag."""
    return {role: study_image_status(role, _run(["docker", "image", "inspect", "-f", "{{.Id}}", e["tag"]]))
            for role, e in study_images()["images"].items()}  # fmt: skip


def task_image_refs(task: Path) -> dict[str, str]:
    """Only the image roles used by this rendered task, including the harness's runtime base."""
    refs = {}
    for side in ("environment", "tests"):
        lock = task / side / "images.lock"
        if lock.exists():
            for line in lock.read_text().splitlines():
                if line.strip() and not line.lstrip().startswith("#"):
                    role, ref, _source = line.split()
                    if role in refs and refs[role] != ref:
                        raise ValueError(f"inconsistent image role {role} in {task}")
                    refs[role] = ref
    if not refs:
        raise ValueError(f"no image dependency lock in {task}")
    return refs


def task_image_ids(task: Path, available: dict[str, str] | None = None) -> dict[str, str]:
    available = image_ids() if available is None else available
    return {ref: available.get(ref, "") for ref in task_image_refs(task).values()}


def images_match(measured: dict, current: dict) -> bool:
    """Missing builds never qualify; unrelated image roles do not invalidate an experiment."""
    return bool(current) and all(value and measured.get(ref) == value for ref, value in current.items())


def _cpu() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def host_id() -> str:
    """A short opaque id of this machine (8 hex of the hashed node name): enough to tell two hosts' records apart, and
    the name itself stays out of records that get published."""
    return hashlib.sha256(platform.node().encode()).hexdigest()[:8]


def _portable_argv(argv: list[str]) -> list[str]:
    """The command line without the machine's paths: the program by name, an absolute path under the repository
    relative to it, any other argument as given."""
    out = []
    for arg in argv[1:]:
        path = Path(arg)
        if path.is_absolute() and path.is_relative_to(ROOT):
            arg = path.relative_to(ROOT).as_posix()
        out.append(arg)
    return [Path(argv[0]).name if argv else "", *out]


def stamp() -> dict:
    return {
        "git_sha": _run(["git", "rev-parse", "HEAD"])[:12],
        "git_dirty": bool(_run(["git", "status", "--porcelain"])),
        "images": image_ids(),
        "harbor": _run(["harbor", "--version"]) or None,
        "host": host_id(),
        "cpu": _cpu(),
        "argv": _portable_argv(sys.argv),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def describe(s: dict) -> str:
    """One line for report headers."""
    images = ", ".join(f"{tag.split('/')[-1]} {iid[7:19] or '?'}" for tag, iid in s.get("images", {}).items())
    dirty = "+dirty" if s.get("git_dirty") else ""
    return f"{s.get('utc')} · commit {s.get('git_sha')}{dirty} · {images} · {s.get('cpu')} ({s.get('host')})"


def _ignored(rel: str) -> bool:
    parts = rel.split("/")
    return "__pycache__" in parts[:-1] or parts[-1] == ".DS_Store" or rel.endswith(_IGNORED_SUFFIXES)


# Keys of non-markdown files that only carry text for the agent: bootstrap.yaml's `spec` is what provisioning writes
# into the agent's report.md (its `symptom` is used and stays hashed).
_TEXT_KEYS = {"environment/bootstrap.yaml": ("spec",)}


def grader_digest(task_dir: Path, without_thresholds: bool = False) -> str:
    """What a task's grading depends on: the files of task_digest without text the agent reads and the grader never
    does (every `*.md`: instruction, README, RUNBOOK, CONTRACT; the verifier's rules come from tests/verify.yaml) and
    task.toml without its [metadata] (labels, provenance) or the task's version, description and Harbor name (a
    version bump for a wording change, or a namespace rename, must not invalidate results). Separation, QA and margin
    results therefore stay valid across wording, labelling, naming and version changes, while any change to the
    environment, tests, solution or the verifier's timeout invalidates them. The agent's time budget ([agent]
    timeout_sec) is not a grading input either: the verifier never reads it, and the oracle, nop and wrong-fix runs
    finish in seconds. It is a row attribute: a change bumps the task version, which keeps rows run under different
    budgets apart in the analysis."""
    outer = hashlib.sha256()
    toml_path = task_dir / "task.toml"
    if toml_path.exists():
        cfg = tomllib.loads(toml_path.read_text())
        cfg.pop("metadata", None)
        for key in ("version", "description", "name"):  # name: the Harbor namespace is not a grading input
            cfg.get("task", {}).pop(key, None)
        agent = cfg.get("agent", {})
        agent.pop("timeout_sec", None)
        if not agent:
            cfg.pop("agent", None)
        outer.update(b"task.toml\0" + json.dumps(cfg, sort_keys=True).encode() + b"\n")
    files = [p for d in _DIRS if (task_dir / d).exists() for p in (task_dir / d).rglob("*") if p.is_file()]
    for rel, path in sorted((p.relative_to(task_dir).as_posix(), p) for p in files):
        if _ignored(rel) or rel.endswith(".md"):
            continue
        data = path.read_bytes()
        if rel in _TEXT_KEYS:
            doc = yaml.safe_load(data) or {}
            data = json.dumps({k: v for k, v in doc.items() if k not in _TEXT_KEYS[rel]}, sort_keys=True).encode()
        if without_thresholds and rel == "tests/verify.yaml":
            data = json.dumps(_without_thresholds(yaml.safe_load(data) or {}), sort_keys=True).encode()
        outer.update(f"{rel}\0{hashlib.sha256(data).hexdigest()}\n".encode())
    return "sha256:" + outer.hexdigest()


THRESHOLDS = ("loss_max", "ttft_p95_max_s", ("throughput", "ratio_min"))  # verify.yaml keys calibration sets


def _without_thresholds(doc: dict) -> dict:
    out = json.loads(json.dumps(doc))
    for key in THRESHOLDS:
        if isinstance(key, tuple):
            parent = out.get(key[0])
            if isinstance(parent, dict):
                parent.pop(key[1], None)
        else:
            out.pop(key, None)
    return out


def calibration_digest(task_dir: Path) -> str:
    """What a calibration record depends on: the grader digest without the thresholds the calibration exists to set
    (loss_max, throughput.ratio_min, ttft_p95_max_s). Retuning a threshold from a set's measurements keeps the
    record current; changing the job, the data, the images or the verifier's mechanics does not."""
    return grader_digest(task_dir, without_thresholds=True)


def task_digest(task_dir: Path) -> str:
    files = [task_dir / f for f in _SINGLE if (task_dir / f).exists()]
    for d in _DIRS:
        if (task_dir / d).exists():
            files += [p for p in (task_dir / d).rglob("*") if p.is_file()]
    outer = hashlib.sha256()
    for rel, path in sorted((p.relative_to(task_dir).as_posix(), p) for p in files):
        if not _ignored(rel):
            outer.update(f"{rel}\0{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode())
    return "sha256:" + outer.hexdigest()


if __name__ == "__main__":
    # python -m bench.provenance [stamp | tag ROLE | source ROLE | pull-plan | study-check]  (the Makefile reads tags,
    # source hashes and the study's pull commands here; study-check exits 1 when a study image is rebuilt or missing)
    if sys.argv[1:2] == ["tag"]:
        print(image_lock()[sys.argv[2]]["tag"])
    elif sys.argv[1:2] == ["source"]:
        print(source_hash(sys.argv[2]))
    elif sys.argv[1:2] == ["pull-plan"]:
        print("\n".join(pull_plan()))
    elif sys.argv[1:2] == ["study-check"]:
        found = study_check()
        for role, status in found.items():
            print(f"{role:18} {study_images()['images'][role]['tag']:26} {status}")
        raise SystemExit(any(st in ("rebuilt", "missing") and r not in OPTIONAL_STUDY_ROLES for r, st in found.items()))
    else:
        print(json.dumps(stamp(), indent=1))
