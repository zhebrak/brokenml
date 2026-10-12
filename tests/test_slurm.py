"""The Slurm client fails loudly: an unanswerable query raises instead of looking like an empty answer."""

from __future__ import annotations

import subprocess

import pytest

from ocb import slurm


def test_timeout_returns_text_not_bytes():
    res = slurm.run(["sh", "-c", "echo partial; sleep 5"], timeout=1)
    assert res.returncode == 124
    assert isinstance(res.stdout, str) and isinstance(res.stderr, str)
    assert "partial" in res.stdout + res.stderr or res.stdout == ""
    assert res.stdout + res.stderr  # concatenation works (it raised TypeError when stdout was bytes)


def _fake(monkeypatch, code, out="", err=""):
    monkeypatch.setattr(slurm, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, code, out, err))


def test_failed_queries_raise(monkeypatch):
    _fake(monkeypatch, 1, err="slurm_load_jobs error: Unable to contact slurm controller")
    with pytest.raises(slurm.SlurmError):
        slurm.jobs()
    with pytest.raises(slurm.SlurmError):
        slurm.nodes()
    with pytest.raises(slurm.SlurmError):
        slurm.drained_nodes()  # never "no drained nodes" when sinfo could not answer


def test_empty_queue_is_not_an_error(monkeypatch):
    _fake(monkeypatch, 0, out="No jobs in the system\n")
    assert slurm.jobs() == []


def test_parse_jobs():
    text = (
        "JobId=7 JobName=train UserId=svc-train(2000) JobState=PENDING Reason=PartitionTimeLimit NodeList=(null) "
        "StartTime=Unknown EndTime=Unknown\n"
        "JobId=8 JobName=train UserId=svc-ci(2001) JobState=COMPLETED Reason=None NodeList=c[1-2] "
        "StartTime=2026-10-01T10:00:00 EndTime=2026-10-01T10:01:00\n"
    )
    a, b = slurm.parse_jobs(text)
    assert (a.id, a.user, a.state, a.reason, a.start) == ("7", "svc-train", "PENDING", "PartitionTimeLimit", None)
    assert b.user == "svc-ci" and b.elapsed_s == 60.0


def test_a_missing_program_or_directory_is_a_result_not_a_crash(tmp_path):
    res = slurm.run(["bash", "x.sh"], cwd=str(tmp_path / "missing"))
    assert res.returncode == 127 and "No such file" in res.stderr
    assert slurm.run(["/no/such/program"]).returncode == 127


def test_nodes_under_a_maintenance_reservation_count_as_ready(monkeypatch, tmp_path):
    """A MAINT reservation (even one floating ahead) shows idle nodes as "maint": the cluster is up."""
    _fake(monkeypatch, 0, out="Slurmctld(primary) at slurmctld is UP")
    monkeypatch.setattr(slurm, "nodes", lambda: {"c1": "maint", "c2": "maint"})
    monkeypatch.setattr(slurm, "missing_hardware", lambda names: [])
    assert slurm.wait_for_cluster(2, timeout_s=2)
    monkeypatch.setattr(slurm, "nodes", lambda: {"c1": "maint", "c2": "drain"})
    assert not slurm.wait_for_cluster(2, timeout_s=1.5)


def test_only_health_check_drains_are_the_jobs(monkeypatch):
    out = ("c1|idle|none\nc2|drain|healthcheck: configured memory 4000MB exceeds the 3000MB this node has\n"
           "c3|down*|Not responding\nc4|drain|Not responding\n")  # fmt: skip
    _fake(monkeypatch, 0, out=out)
    drained = slurm.drained_nodes()
    assert set(drained) == {"c2", "c3", "c4"} and drained["c3"] == "down*: Not responding"
    assert set(slurm.health_drained(drained)) == {"c2"}
