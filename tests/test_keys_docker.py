"""Credentials, end to end: two compose projects of one task get different credentials, and neither project's
root ssh key nor munge credential works in the other (pytest -m docker; needs the images built)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from bench.spec import task_dir

pytestmark = pytest.mark.docker
OVERRIDE = "services:\n  main:\n    build: {context: .}\n    command: [sleep, infinity]\n"


def sh(*cmd: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, input=stdin, timeout=300, check=False)


@pytest.fixture
def two_projects():
    tests = task_dir("rank0-eval-desync") / "tests"
    override = Path(tempfile.mkdtemp()) / "main.yaml"
    override.write_text(OVERRIDE)
    names = ["keystest-x", "keystest-y"]
    compose = [["docker", "compose", "-p", n, "-f", str(tests / "docker-compose.yaml"), "-f", str(override)]
               for n in names]  # fmt: skip
    try:
        for c in compose:
            assert sh(*c, "up", "-d", "--wait").returncode == 0
        yield names
    finally:
        for c in compose:
            sh(*c, "down", "-v")


def test_a_carried_key_or_credential_does_not_work_in_another_project(two_projects):
    x, y = two_projects
    digest = {p: sh("docker", "exec", f"{p}-c1-1", "sha256sum", "/etc/munge/munge.key").stdout[:64] for p in (x, y)}
    assert digest[x] and digest[x] != digest[y]
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
    assert sh("docker", "exec", f"{y}-main-1", *ssh, "root@c1", "true").returncode == 0  # its own key works
    key = sh("docker", "exec", f"{x}-main-1", "cat", "/root/.ssh/id_ed25519").stdout
    sh("docker", "exec", "-i", f"{y}-main-1", "sh", "-c", "umask 077; cat > /tmp/carried", stdin=key)
    carried = sh("docker", "exec", f"{y}-main-1", *ssh, "-i", "/tmp/carried", "-o", "IdentitiesOnly=yes", "root@c1",
                 "true")  # fmt: skip
    assert carried.returncode != 0 and "Permission denied" in carried.stderr
    cred = sh("docker", "exec", f"{x}-main-1", "munge", "-n").stdout
    assert sh("docker", "exec", "-i", f"{x}-main-1", "unmunge", stdin=cred).returncode == 0
    assert sh("docker", "exec", "-i", f"{y}-main-1", "unmunge", stdin=cred).returncode != 0
