"""Edit a task's fault, fix or wrong fix as a tree, and save it back as a patch.

  bench patch TASK ops|solution|wrong NAME --edit DIR   write the tree to edit into DIR (patch applied, if it exists)
  bench patch TASK ops|solution|wrong NAME --save DIR   write the patch that turns the base into DIR, then re-render

The base each patch applies to:
  ops       templates/ops (templates/serving-ops for serving tasks)   -> the broken /ops the agent starts from
  solution  the broken /ops                                            -> the reference fix (must add ANALYSIS.md)
  wrong     the broken /ops                                            -> a plausible fix that must score 0
  accepted  the broken /ops                                            -> another valid fix that must score 1
Patches may add or modify files, not delete them. DIR must be outside this repository (e.g. under /tmp).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from bench import patches
from bench.paths import ROOT
from bench.render import render
from bench.spec import by_id, load_specs, task_dir


def _target(task: str, kind: str, name: str | None) -> tuple[Path, Path, Path | None]:
    """(base tree to diff against, patch file, scratch tree to remove afterwards)."""
    spec = by_id(task)
    if kind == "ops":
        return patches.template_for(spec), spec.dir / "ops.patch", None
    fault = patches.fault_patch(spec)
    broken = patches.materialise(patches.template_for(spec), *([fault] if fault else []))
    if kind == "solution":  # always saved in the task's own directory (a GPU twin's override, not the CPU twin's file)
        return broken, spec.dir / "solution.patch", broken
    if not name:
        raise SystemExit(f"bench patch TASK {kind} NAME: give the fix a name")
    return broken, spec.dir / patches.FIX_DIRS[kind] / f"{name}.patch", broken


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench patch", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("task")
    ap.add_argument("kind", choices=["ops", "solution", "wrong", "accepted"])
    ap.add_argument("name", nargs="?", help="the wrong fix's name (kind wrong)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--edit", type=Path, metavar="DIR")
    mode.add_argument("--save", type=Path, metavar="DIR")
    args = ap.parse_args(argv)
    tree = (args.edit or args.save).resolve()
    if ROOT in tree.parents or tree == ROOT:
        ap.error("DIR must be outside the repository (git apply ignores paths inside a repo's subdirectories)")

    base, patch_file, scratch_tree = _target(args.task, args.kind, args.name)
    try:
        if args.edit:
            if tree.exists() and any(tree.iterdir()):
                ap.error(f"{tree} is not empty")
            edited = patches.materialise(base, *([patch_file] if patch_file.exists() else []))
            shutil.copytree(edited, tree, dirs_exist_ok=True)
            shutil.rmtree(edited)
            print(
                f"edit {tree}, then: bench patch {args.task} {args.kind} {args.name or ''} --save {tree}".replace(
                    "  ", " "
                )
            )
            return
        text = patches.diff(base, tree)
        if not text.strip():
            ap.error("no changes: the tree equals its base")
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(text)
        print(f"wrote {patch_file.relative_to(ROOT)} ({len(patches.touched(text))} files)")
    finally:
        if scratch_tree is not None:
            shutil.rmtree(scratch_tree, ignore_errors=True)
    load_specs.cache_clear()
    spec = by_id(args.task)
    print(f"rendered {render(spec, task_dir(spec).parent).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
