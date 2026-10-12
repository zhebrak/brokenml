"""A record's stamp says what code and images produced it without naming the machine or its paths."""

from __future__ import annotations

import hashlib
import sys

from bench import provenance
from bench.paths import ROOT


def test_the_stamp_hashes_the_host_and_keeps_no_absolute_repository_paths(monkeypatch):
    monkeypatch.setattr(provenance.platform, "node", lambda: "build-box-7")
    monkeypatch.setattr(sys, "argv", [str(ROOT / "src" / "bench" / "sweep.py"), str(ROOT / "tasks" / "x"), "--n=3",
                                      "/elsewhere/file", "relative"])  # fmt: skip
    monkeypatch.setattr(provenance, "image_ids", lambda: {"img:1": "sha256:" + "a" * 64})
    s = provenance.stamp()
    assert s["host"] == hashlib.sha256(b"build-box-7").hexdigest()[:8] and "build-box" not in str(s)
    assert s["argv"] == ["sweep.py", "tasks/x", "--n=3", "/elsewhere/file", "relative"]
    assert s["images"] == {"img:1": "sha256:" + "a" * 64}
    assert {"git_sha", "git_dirty", "harbor", "cpu", "utc"} <= set(s)
    line = provenance.describe(s)
    assert s["host"] in line and s["git_sha"] in line


def test_the_stamp_host_is_not_the_concurrency_host_signature():
    from bench import concurrency

    assert set(concurrency.host_signature()) == {"cpu", "physical_cores", "memory_gb"}
    assert isinstance(provenance.stamp()["host"], str) and len(provenance.stamp()["host"]) == 8


def test_study_images_lists_the_four_published_images_and_classifies_local_ids():
    study = provenance.study_images()
    assert list(study["images"]) == ["runtime", "harness", "serve", "runtime-getenvfix"]
    for entry in study["images"].values():
        assert entry["ref"].startswith("ghcr.io/zhebrak/brokenml-")
        assert entry["id"].startswith("sha256:") and entry["config"].startswith("sha256:")
        assert entry["id"] != entry["config"]
    runtime = study["images"]["runtime"]
    assert provenance.study_image_status("runtime", runtime["id"]) == "study"
    assert provenance.study_image_status("runtime", runtime["config"]) == "classic-store"
    assert provenance.study_image_status("runtime", "sha256:" + "0" * 64) == "rebuilt"
    assert provenance.study_image_status("runtime", "") == "missing"


def test_the_pull_plan_pulls_by_digest_and_tags_the_local_names():
    plan = provenance.pull_plan()
    first = provenance.study_images()["images"]["runtime"]
    assert plan[0] == f"docker pull ghcr.io/zhebrak/brokenml-runtime@{first['id']}"
    assert plan[1] == f"docker tag ghcr.io/zhebrak/brokenml-runtime@{first['id']} bench/runtime:dev"
    assert len(plan) == 8 and plan[-1].endswith("bench/runtime:getenvfix1")
    assert "bench/serve:dev" in plan[5]
