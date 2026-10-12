"""bench doctor: the concurrency rule (one trial per 8 physical cores and 8 GB) and the study-image lines."""

from __future__ import annotations

import pytest

from bench import doctor
from bench.doctor import safe_concurrency
from bench.provenance import study_images


def test_concurrency_is_bounded_by_cores_and_memory():
    assert safe_concurrency(8, 27) == 1  # this 8-core, 16-thread box: one trial at a time
    assert safe_concurrency(32, 128) == 4
    assert safe_concurrency(64, 16) == 2  # memory binds
    assert safe_concurrency(4, 64) == 0


STUDY = study_images()["images"]


def _fake_docker(monkeypatch, ids: dict[str, str], info: dict[str, str] | None = None):
    """Docker answers `image inspect -f {{.Id}} TAG` from `ids` (tag -> id; absent tags give no output, as a failing
    inspect does) and `docker info` from `info` (format string -> output)."""

    def run(cmd: list[str]) -> str:
        if cmd[:2] == ["docker", "version"]:
            return "29.2.0"
        if cmd[:3] == ["docker", "image", "inspect"]:
            return ids.get(cmd[-1], "")
        if cmd[:2] == ["docker", "info"]:
            return (info or {}).get(cmd[-1], "")
        return ""

    monkeypatch.setattr(doctor, "_run", run)


def test_study_image_lines_name_each_state():
    ids = {
        "runtime": STUDY["runtime"]["id"],
        "harness": STUDY["harness"]["config"],
        "serve": "sha256:" + "6" * 64,
        "runtime-getenvfix": "",
    }
    lines = doctor.study_image_lines(ids)
    assert lines[0] == "study image runtime: study build (2dbb48ff…)"
    assert lines[1].startswith("study image harness: classic image store (config digest matches)")
    assert "docs/hosts.md" in lines[1]
    assert lines[2] == (
        "study image serve: rebuilt locally (66666666…): published rows ran on the study images; make image-pull"
    )
    assert lines[3] == "study image runtime-getenvfix: not present: make image-pull or make image"


def test_image_store_reads_the_daemons_store(monkeypatch):
    fmt = "{{range .DriverStatus}}{{index . 0}}={{index . 1}} {{end}}"
    _fake_docker(monkeypatch, {}, {fmt: "driver-type=io.containerd.snapshotter.v1 "})
    assert doctor.image_store() == "containerd"
    _fake_docker(monkeypatch, {}, {fmt: "Backing Filesystem=extfs ", "{{.Driver}}": "overlay2"})
    assert doctor.image_store() == "classic"
    _fake_docker(monkeypatch, {})
    assert doctor.image_store() == ""


def test_doctor_prints_the_study_lines_and_the_store(monkeypatch, capsys):
    fmt = "{{range .DriverStatus}}{{index . 0}}={{index . 1}} {{end}}"
    tags = {e["tag"]: e["id"] for e in STUDY.values()}
    _fake_docker(monkeypatch, tags, {fmt: "Backing Filesystem=extfs ", "{{.Driver}}": "overlay2"})
    monkeypatch.setattr(doctor, "image_ids", lambda: {r: tags.get(r, "") for r in doctor.image_tags().values()})
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit):  # no Harbor or Compose in the fake: problems, but the lines still print
        doctor.main([])
    out = capsys.readouterr().out
    assert "image store     classic" in out
    assert "study image runtime: study build (2dbb48ff…)" in out
    assert "study image runtime-getenvfix: study build (1ceed41f…)" in out
