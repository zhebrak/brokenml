"""Faults, fixes and wrong fixes are patches against the template; each applies cleanly and changes the tree."""

from __future__ import annotations

import shutil

import pytest

from bench import patches
from bench.paths import ROOT
from bench.spec import load_specs

SPECS = load_specs()


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_patches_apply_and_change_the_tree(spec):
    broken, reference = patches.task_trees(spec)  # apply() itself fails on a stale hunk or a no-op patch
    reference_touched = [p for p in patches.touched(patches.solution_patch(spec).read_text()) if p != "ANALYSIS.md"]
    try:
        for name, patch_file in patches.wrong_fix_patches(spec).items():
            files = patches.wrong_fix_files(spec, name)
            try:
                changed = [p for p in patches.touched(patch_file.read_text()) if (files / p).exists()]
                assert changed, f"wrong fix {name} changes nothing"
                # Not the reference fix: some file the wrong fix or the reference fix touches differs between the two
                # trees. A compound task's partial fix equals the reference on every file it touches and differs on the
                # files it leaves broken.
                differs = [
                    p
                    for p in dict.fromkeys([*changed, *reference_touched])
                    if (files / p).exists() != (reference / p).exists()
                    or ((files / p).exists() and (files / p).read_bytes() != (reference / p).read_bytes())
                ]
                assert differs, f"wrong fix {name} equals the reference fix"
            finally:
                shutil.rmtree(files)
    finally:
        shutil.rmtree(broken)
        shutil.rmtree(reference)


def test_every_task_has_a_solution_patch_with_an_analysis():
    for spec in SPECS:
        assert "ANALYSIS.md" in patches.touched(patches.solution_patch(spec).read_text()), spec.id


def test_calibration_variants_apply():
    import yaml

    from bench.spec import by_id

    sets = yaml.safe_load((ROOT / "calibration" / "sets.yaml").read_text())
    for cfg in sets.values():
        broken, reference = patches.task_trees(by_id(cfg["task"]))
        try:
            for variant in [*cfg.get("legitimate", []), *cfg.get("shortcuts", [])]:
                shutil.rmtree(patches.materialise(reference, ROOT / "calibration" / "variants" / f"{variant}.patch"))
        finally:
            shutil.rmtree(broken)
            shutil.rmtree(reference)


def test_scratch_trees_are_outside_any_repository():
    tree = patches.scratch()
    try:
        assert ROOT not in tree.parents
    finally:
        tree.rmdir()


def test_scratch_git_ignores_an_outer_repository(monkeypatch, tmp_path):
    """Inside a git hook GIT_DIR/GIT_INDEX_FILE point at the real repo; diffing must not touch it."""
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "not-a-repo"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "index"))
    before, after = tmp_path / "a", tmp_path / "b"
    (before / "x").mkdir(parents=True)
    (before / "x" / "f.txt").write_text("one\n")
    shutil.copytree(before, after)
    (after / "x" / "f.txt").write_text("two\n")
    assert "+two" in patches.diff(before, after)
    assert not (tmp_path / "index").exists()


def test_deleting_patches_are_refused(tmp_path):
    before, after = tmp_path / "a", tmp_path / "b"
    before.mkdir()
    (before / "keep.txt").write_text("x\n")
    (before / "stale.py").write_text("y\n")
    shutil.copytree(before, after)
    (after / "stale.py").unlink()
    (after / "keep.txt").write_text("z\n")
    with pytest.raises(patches.PatchError, match="not delete"):
        patches.diff(before, after)
    patch_file = tmp_path / "p.patch"  # written by hand
    patch_file.write_text("diff --git a/stale.py b/stale.py\ndeleted file mode 100644\n--- a/stale.py\n+++ /dev/null\n"
                          "@@ -1 +0,0 @@\n-y\n")  # fmt: skip
    with pytest.raises(patches.PatchError, match="not delete"):
        patches.materialise(before, patch_file)


def test_failed_apply_leaves_no_scratch_tree(tmp_path, monkeypatch):
    made = []
    real = patches.scratch
    monkeypatch.setattr(patches, "scratch", lambda prefix="bench-tree-": made.append(real(prefix)) or made[-1])
    bad = tmp_path / "bad.patch"
    bad.write_text("diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-nope\n+yes\n")
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "x").write_text("other\n")
    with pytest.raises(patches.PatchError):
        patches.materialise(tmp_path / "base", bad)
    assert made and not made[-1].exists()
