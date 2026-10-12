"""Trust zones (docs/architecture.md): the platform (ocb) is what agents can reach, so it must never import the harness
or the authoring tools; the harness must not import the authoring tools."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from bench.paths import ROOT

FORBIDDEN = {"ocb": {"harness", "bench"}, "harness": {"bench"}}


def _imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module.split(".")[0])
    return out


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_import_direction(package):
    bad = {
        str(p.relative_to(ROOT)): sorted(_imports(p) & FORBIDDEN[package])
        for p in (ROOT / "src" / package).rglob("*.py")
    }
    assert not {k: v for k, v in bad.items() if v}


def test_runtime_image_copies_only_the_platform():
    dockerfile = (ROOT / "images" / "runtime" / "Dockerfile").read_text()
    copies = [line.split()[1] for line in dockerfile.splitlines() if line.startswith("COPY ") and "--from" not in line]
    assert all(src.startswith(("src/ocb/", "images/runtime/")) for src in copies), copies


def test_dockerignore_admits_no_authoring_code():
    allowed = {line[1:] for line in (ROOT / ".dockerignore").read_text().splitlines() if line.startswith("!")}
    assert allowed == {"images/", "src/ocb/", "src/harness/"}
