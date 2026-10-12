"""Task versions follow what changed; the dataset manifests pin every task by Harbor's content digest."""

from __future__ import annotations

import tomllib

import pytest

from bench import versions
from bench.paths import TASKS
from bench.provenance import task_digest
from bench.spec import load_specs, task_dir


@pytest.mark.parametrize("spec", load_specs(), ids=lambda s: s.id)
def test_version_matches_content(spec):
    assert versions.check(spec, task_dir(spec), versions.load()) is None


@pytest.mark.parametrize("split", ["test", "dev"])
def test_manifest_pins_every_task_of_the_split(split):
    manifest = tomllib.loads((TASKS / split / "dataset.toml").read_text())
    pinned = {t["name"].split("/", 1)[1]: t["digest"] for t in manifest["tasks"]}
    specs = [s for s in load_specs() if s.split == split]
    assert set(pinned) == {s.id for s in specs}
    assert all(pinned[s.id] == task_digest(task_dir(s)) for s in specs)


def test_bump_rules():
    old = {"version": "1.2.3", "env": "a", "tests": "b", "meta": "c"}
    assert versions.required_bump(old, {"env": "a", "tests": "b", "meta": "c"}) is None
    assert versions.required_bump(old, {"env": "a", "tests": "b", "meta": "X"}) == 2  # patch
    assert versions.required_bump(old, {"env": "a", "tests": "X", "meta": "X"}) == 1  # minor
    assert versions.required_bump(old, {"env": "X", "tests": "b", "meta": "c"}) == 0  # major
    assert versions.bumped("1.2.3", 1) == "1.3.0" and versions.bumped("1.2.3", 0) == "2.0.0"
    assert versions.bumped("0.1.1", 0) == "0.2.0" and versions.bumped("0.1.1", 1) == "0.1.2"  # before the freeze


def test_a_manual_bump_must_be_at_least_what_the_change_needs(monkeypatch, tmp_path):
    from types import SimpleNamespace

    entry = {"version": "1.2.3", "env": "a", "tests": "b", "meta": "c"}
    monkeypatch.setattr(versions, "part_hashes", lambda d: {"env": "X", "tests": "b", "meta": "c"})  # env changed
    spec = lambda v: SimpleNamespace(id="t", version=v)
    assert versions.check(spec("1.2.4"), tmp_path, {"t": entry})  # a patch bump is not enough
    assert versions.check(spec("2.0.0"), tmp_path, {"t": entry}) is None


def test_set_spec_version_writes_a_plain_quoted_semver(tmp_path, monkeypatch):
    import yaml

    from bench.spec import by_id

    spec = by_id("rank0-eval-desync")
    copy = tmp_path / "spec.yaml"
    copy.write_text((spec.dir / "spec.yaml").read_text())
    monkeypatch.setattr(type(spec), "dir", property(lambda self: tmp_path))
    versions.set_spec_version(spec, "2.3.4")
    assert yaml.safe_load(copy.read_text())["version"] == "2.3.4"
    text = copy.read_text().replace('version: "2.3.4"\n', "")
    copy.write_text(text)
    versions.set_spec_version(spec, "0.1.0")
    assert yaml.safe_load(copy.read_text())["version"] == "0.1.0"
