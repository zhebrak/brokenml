"""The committed tasks/ is exactly what the generator renders from families/ and templates/: no hand edits, no drift."""

from __future__ import annotations

import filecmp
import os
from pathlib import Path

from bench import render
from bench.paths import ROOT
from bench.spec import load_specs


def _tree(root: Path, skip: tuple[str, ...] = ()) -> dict[str, Path]:
    return {
        p.relative_to(root).as_posix(): p
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.name not in skip
    }


def test_render_matches_committed_tasks(tmp_path):
    for spec in load_specs():
        render.render(spec, tmp_path / spec.split)
    rendered, committed = (
        _tree(tmp_path),
        _tree(ROOT / "tasks", skip=("versions.json", "dataset.toml", "lite.txt", "metric.py")),
    )
    assert sorted(rendered) == sorted(committed), {
        "missing from tasks/": sorted(set(rendered) - set(committed))[:10],
        "stale in tasks/": sorted(set(committed) - set(rendered))[:10],
    }
    differ = [rel for rel in rendered if not filecmp.cmp(rendered[rel], committed[rel], shallow=False)]
    assert not differ, f"rendered files differ from tasks/: {differ[:10]}"
    modes = [
        rel for rel in rendered if os.stat(rendered[rel]).st_mode & 0o111 != os.stat(committed[rel]).st_mode & 0o111
    ]
    assert not modes, f"executable bits differ: {modes[:10]}"


def test_each_split_ships_the_hub_metric_its_manifest_pins():
    import hashlib

    metric = (ROOT / "templates" / "dataset" / "metric.py").read_bytes()
    for split in ("test", "dev", "gpu"):
        assert (ROOT / "tasks" / split / "metric.py").read_bytes() == metric
        assert (
            f'digest = "sha256:{hashlib.sha256(metric).hexdigest()}"'
            in (ROOT / "tasks" / split / "dataset.toml").read_text()
        )
