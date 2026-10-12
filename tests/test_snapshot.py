"""The evidence-snapshot variant: render from a fake snapshot tarball, refusal on a stale digest, leak checks."""

from __future__ import annotations

import io
import tarfile
import tomllib

import pytest
import yaml

from bench import snapshot
from bench.provenance import task_digest
from bench.render import NAMESPACES, VARIANTS, render
from bench.spec import by_id, task_dir

FILES = {
    "evidence/report.md": "# Report\nThe job stalled. Dumps: /shared/evidence/dumps/\n",
    "evidence/symptom.json": '{"observed": true}',
    "evidence/dumps/1/stacks.md": "rank 0: allreduce\n",
    "logs/train-1.out": "step 100 loss 3.2\n",
}


def tarball(files: dict[str, str], extra=()) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, text in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(text.encode())
            tar.addfile(info, io.BytesIO(text.encode()))
        for info in extra:
            tar.addfile(info)
    return buf.getvalue()


@pytest.fixture
def spec():
    return by_id("rank0-eval-desync")


@pytest.fixture
def snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "SNAPSHOTS", tmp_path / "snapshots")
    return tmp_path / "snapshots"


def captured(spec, files=FILES):
    return snapshot.store(spec.id, task_digest(task_dir(spec)), tarball(files))


def test_variant_has_its_own_namespace():
    assert "snapshot" in VARIANTS and NAMESPACES["snapshot"] == "brokenml-snapshot"


def test_render_bakes_a_read_only_copy_and_no_cluster(spec, snapshots, tmp_path):
    captured(spec)
    task = render(spec, tmp_path / "out", "snapshot")
    env = task / "environment"
    assert (
        list((env / "snapshot").iterdir())
        and (env / "snapshot/evidence/report.md").read_text() == FILES["evidence/report.md"]
    )
    assert (env / "snapshot/logs/train-1.out").exists() and not (env / "snapshot/evidence/READY").exists()
    doc = yaml.safe_load((env / "docker-compose.yaml").read_text())
    assert list(doc["services"]) == ["main"] and list(doc["volumes"]) == ["ops"]  # nothing live behind /shared
    assert all(not v.startswith("shared") for v in doc["services"]["main"].get("volumes", []))
    assert not (env / "Dockerfile.provision").exists()
    dockerfile = (env / "Dockerfile").read_text()
    assert "COPY snapshot/ /shared/" in dockerfile and "chmod -R a-w /shared/evidence /shared/logs" in dockerfile
    assert "chown -R root:root /shared/evidence /shared/logs" in dockerfile
    meta = tomllib.loads((task / "task.toml").read_text())
    assert meta["task"]["name"] == f"brokenml-snapshot/{spec.id}" and meta["metadata"]["variant"] == "snapshot"
    assert "healthcheck" not in meta["environment"]


def test_instruction_says_the_evidence_is_a_copy(spec, snapshots, tmp_path):
    captured(spec)
    text = (render(spec, tmp_path / "out", "snapshot") / "instruction.md").read_text()
    assert "copy taken then" in text and "/shared/evidence/report.md" in text and "/shared/logs" in text
    assert "No cluster is attached here" in text and "shell access to a workstation attached" not in text
    assert "would not meet its spec" in text


def test_verifier_and_standard_are_untouched_by_the_snapshot(spec, snapshots, tmp_path):
    captured(spec)
    std = render(spec, tmp_path / "s") / "tests"
    snap = render(spec, tmp_path / "n", "snapshot") / "tests"
    for f in std.rglob("*"):
        if f.is_file():
            assert f.read_bytes() == (snap / f.relative_to(std)).read_bytes(), f


def test_refuses_without_a_snapshot_or_on_a_digest_mismatch(spec, snapshots, tmp_path):
    with pytest.raises(snapshot.SnapshotError, match=r"no evidence snapshot for rank0-eval-desync.*snapshot-evidence"):
        render(spec, tmp_path / "a", "snapshot")
    snapshot.store(spec.id, "sha256:" + "0" * 64, tarball(FILES))  # captured for another digest of the task
    with pytest.raises(snapshot.SnapshotError, match=r"another digest.*changed since"):
        render(spec, tmp_path / "b", "snapshot")
    assert not (tmp_path / "b" / spec.id).exists()


def test_a_snapshot_with_harness_terms_or_unsafe_members_is_refused(spec, snapshots):
    with pytest.raises(snapshot.SnapshotError, match="harness terms"):
        captured(spec, {**FILES, "logs/x.out": "reading /opt/task/bootstrap.yaml\n"})
    with pytest.raises(snapshot.SnapshotError, match="outside"):
        captured(spec, {**FILES, "../etc/passwd": "x"})
    link = tarfile.TarInfo("logs/link")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/shadow"
    with pytest.raises(snapshot.SnapshotError, match="not a regular file"):
        snapshot.store(spec.id, "sha256:x", tarball(FILES, [link]))
    assert not snapshots.exists()  # nothing written for a refused capture


def test_a_hand_edited_tarball_is_checked_again_at_render(spec, snapshots, tmp_path):
    captured(spec)
    path = snapshot.snapshot_path(spec.id, task_digest(task_dir(spec)))
    path.write_bytes(snapshot._gzip(tarball({**FILES, "evidence/report.md": "see verify.yaml\n"})))
    with pytest.raises(snapshot.SnapshotError, match="harness terms"):
        render(spec, tmp_path / "out", "snapshot")


def test_manifest_records_digest_images_and_file_hashes(spec, snapshots):
    m = captured(spec)
    assert m["task_digest"] == task_digest(task_dir(spec)) and set(m["files"]) == set(FILES)
    assert "images" in m["stamp"] and "image_ids" in m
    assert snapshot.manifest_path(spec.id, m["task_digest"]).exists()


@pytest.mark.docker
def test_capture_from_a_live_environment():
    m = snapshot.capture("rank0-eval-desync")
    assert "evidence/report.md" in m["files"] and "evidence/READY" not in m["files"]
