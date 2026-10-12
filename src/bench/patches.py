"""Faults, fixes and wrong fixes as patches against the platform template.

A task's /ops is the template with the task's patches applied:
  families/<F>/<id>/ops.patch                  template   -> broken /ops (the fault)
  families/<F>/<id>/solution.patch             broken     -> reference fix (including ANALYSIS.md)
  families/<F>/<id>/wrong_fixes/<name>.patch   broken     -> a plausible fix that must score 0
  calibration/variants/<name>.patch            reference  -> a legitimate alternative (calibration only)

Patches are applied with `git apply` (no fuzz) in a scratch tree outside any git repository: a hunk that no longer
applies fails the render loudly, and every patch must change the tree, so a template edit can never silently undo a
fault or a fix.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from bench.paths import TEMPLATES
from bench.spec import TaskSpec

GIT = ["git", "-c", "core.quotepath=false", "-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false"]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".git")


class PatchError(RuntimeError):
    pass


def _env() -> dict[str, str]:
    """The environment without GIT_* variables: inside a git hook GIT_DIR and GIT_INDEX_FILE point at the outer
    repository, and a scratch-tree git command must never act on it."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(cwd: Path, *args: str, stdin: str | None = None) -> str:
    res = subprocess.run([*GIT, *args], cwd=cwd, input=stdin, capture_output=True, text=True, check=False, env=_env())
    if res.returncode != 0:
        raise PatchError(f"git {' '.join(args)} failed in {cwd}: {res.stderr.strip()}")
    return res.stdout


def scratch(prefix: str = "bench-tree-") -> Path:
    """A temporary directory that is not inside any git repository (git apply ignores paths outside its cwd there)."""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    res = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=path, capture_output=True, check=False, env=_env()
    )
    if res.returncode == 0:
        raise PatchError(f"{path} is inside a git work tree; set TMPDIR to a directory outside any repository")
    return path


def body(patch_file: Path) -> bytes:
    """The bytes of a patch from its first diff header on. Text before it (the canary line) is a preamble that
    `git apply` ignores, so it is not part of what a recorded result depends on."""
    data = patch_file.read_bytes()
    for marker in (b"diff --git ", b"--- "):
        for line_start in (0, *[i + 1 for i, c in enumerate(data) if c == 10]):
            if data.startswith(marker, line_start):
                return data[line_start:]
    return data


def touched(patch: str) -> list[str]:
    """Paths a patch creates or modifies. Deletions are refused: a fix is delivered as files copied over /ops
    (solution/files, wrong fixes), which cannot express one."""
    if re.search(r"^(deleted file mode|\+\+\+ /dev/null)", patch, flags=re.MULTILINE):
        raise PatchError("patches may add or modify files, not delete them")
    return sorted(set(re.findall(r"^\+\+\+ b/(.+)$", patch, flags=re.MULTILINE)))


def _files(tree: Path) -> set[str]:
    return {p.relative_to(tree).as_posix() for p in tree.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def diff(before: Path, after: Path) -> str:
    """A git-format patch that turns tree `before` into tree `after`, which may add or modify files only."""
    removed = sorted(_files(before) - _files(after))
    if removed:
        raise PatchError(f"patches may add or modify files, not delete them: {removed[:5]}")
    work = scratch("bench-diff-")
    try:
        repo = work / "r"
        shutil.copytree(before, repo, ignore=IGNORE)
        _git(repo, "init", "-q")
        _git(repo, "add", "-A")
        _git(repo, "-c", "user.name=bench", "-c", "user.email=bench@localhost", "commit", "-q", "-m", "base")
        shutil.copytree(after, repo, dirs_exist_ok=True, ignore=IGNORE)
        # Re-hash every file: copies keep size and mtime, so git's stat check would miss same-size edits.
        _git(repo, "rm", "-r", "-q", "--cached", ".")
        _git(repo, "add", "-A")
        return _git(repo, "diff", "--cached", "--no-color", "--no-ext-diff", "--no-renames", "HEAD")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def apply(tree: Path, patch_file: Path) -> list[str]:
    """Apply one patch in place; returns the paths it touched. Fails if it does not apply or changes nothing."""
    patch = patch_file.read_text()
    try:
        paths = touched(patch)
    except PatchError as exc:
        raise PatchError(f"{patch_file}: {exc}") from exc
    if not paths:
        raise PatchError(f"{patch_file}: empty patch")
    before = {p: (tree / p).read_bytes() if (tree / p).exists() else None for p in paths}
    _git(tree, "apply", "--check", "-p1", str(patch_file))
    _git(tree, "apply", "-p1", str(patch_file))
    unchanged = [p for p in paths if (tree / p).exists() and (tree / p).read_bytes() == before[p]]
    if unchanged:
        raise PatchError(f"{patch_file} left {unchanged} unchanged")
    return paths


def materialise(base: Path, *patch_files: Path) -> Path:
    """A scratch copy of `base` with the patches applied in order (the caller removes it; removed here on failure)."""
    tree = scratch()
    try:
        shutil.copytree(base, tree, dirs_exist_ok=True, ignore=IGNORE)
        for patch_file in patch_files:
            apply(tree, patch_file)
    except BaseException:
        shutil.rmtree(tree, ignore_errors=True)
        raise
    return tree


def template_for(spec: TaskSpec) -> Path:
    return TEMPLATES / {"serving": "serving-ops", "gpu": "ops-gpu"}.get(spec.substrate, "ops")


def _dirs(spec: TaskSpec) -> list[Path]:
    """Where a task's patches come from: its own directory, then its CPU twin's (a GPU twin reuses the CPU task's
    fault, fix and wrong fixes unless it has its own)."""
    if spec.twin_of is None:
        return [spec.dir]
    from bench.spec import by_id

    return [spec.dir, by_id(spec.twin_of).dir]


def fault_patch(spec: TaskSpec) -> Path | None:
    return next((d / "ops.patch" for d in _dirs(spec) if (d / "ops.patch").exists()), None)


def solution_patch(spec: TaskSpec) -> Path:
    own = [d / "solution.patch" for d in _dirs(spec) if (d / "solution.patch").exists()]
    return own[0] if own else spec.dir / "solution.patch"


FIX_DIRS = {"wrong": "wrong_fixes", "accepted": "accepted_fixes"}


def fix_patches(spec: TaskSpec, kind: str) -> dict[str, Path]:
    """A task's scripted alternative fixes, applied to the broken /ops: `wrong` ones must score 0 (plausible fixes
    that leave the fault), `accepted` ones must score 1 (valid fixes other than the reference, e.g. those its README
    names), so the grader is checked against false negatives as well as false positives."""
    out: dict[str, Path] = {}
    for d in reversed(_dirs(spec)):  # the task's own fixes override the twin's of the same name
        if (d / FIX_DIRS[kind]).is_dir():
            out.update({p.stem: p for p in sorted((d / FIX_DIRS[kind]).glob("*.patch"))})
    return dict(sorted(out.items()))


def wrong_fix_patches(spec: TaskSpec) -> dict[str, Path]:
    return fix_patches(spec, "wrong")


def accepted_fix_patches(spec: TaskSpec) -> dict[str, Path]:
    return fix_patches(spec, "accepted")


def task_trees(spec: TaskSpec) -> tuple[Path, Path]:
    """Scratch copies of the task's broken /ops and its reference fix (the caller removes both)."""
    fault = fault_patch(spec)
    broken = materialise(template_for(spec), *([fault] if fault else []))
    try:
        reference = materialise(broken, solution_patch(spec))
    except BaseException:
        shutil.rmtree(broken, ignore_errors=True)
        raise
    return broken, reference


def overlay_files(tree: Path, paths: list[str]) -> Path:
    """The given files of `tree`, alone in a scratch directory (what an oracle copies over /ops)."""
    out = scratch("bench-files-")
    for rel in paths:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tree / rel, out / rel)
    return out


def wrong_fix_files(spec: TaskSpec, name: str, kind: str = "wrong") -> Path:
    """A wrong (or accepted) fix as full files to copy over the broken /ops (the caller removes the directory)."""
    patch_file = fix_patches(spec, kind)[name]
    broken, reference = task_trees(spec)
    shutil.rmtree(reference)
    try:
        apply(broken, patch_file)
        return overlay_files(broken, touched(patch_file.read_text()))
    finally:
        shutil.rmtree(broken)
