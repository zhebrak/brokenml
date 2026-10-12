"""The logs variant's read-only commands (bench.readonly.tools), answered from a fake /obs."""

from __future__ import annotations

import ast
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bench.readonly import collect, tools

SQUEUE_HEADER = {"i": "JOBID", "A": "JOBID", "P": "PARTITION", "j": "NAME", "u": "USER", "U": "UID", "t": "ST",
                 "T": "STATE", "M": "TIME", "D": "NODES", "R": "NODELIST(REASON)", "N": "NODELIST", "l": "TIME_LIMIT",
                 "S": "START_TIME", "Y": "SCHEDNODES", "r": "REASON"}  # fmt: skip
JOBS = [
    {"i": "12", "A": "12", "P": "debug", "j": "train", "u": "svc-train", "U": "1001", "t": "R", "T": "RUNNING",
     "M": "1:02", "D": "2", "R": "c[1-2]", "N": "c[1-2]", "l": "30:00", "S": "2026-10-07T09:00:00", "Y": "(null)",
     "r": "None"},
    {"i": "11", "A": "11", "P": "debug", "j": "prep", "u": "svc-train", "U": "1001", "t": "CD", "T": "COMPLETED",
     "M": "0:05", "D": "1", "R": "c1", "N": "c1", "l": "5:00", "S": "2026-10-07T08:59:00", "Y": "(null)",
     "r": "None"},
    {"i": "13", "A": "13", "P": "debug", "j": "a-very-long-job-name", "u": "svc-train", "U": "1001", "t": "PD",
     "T": "PENDING", "M": "0:00", "D": "2", "R": "(Dependency)", "N": "", "l": "30:00", "S": "N/A", "Y": "(null)",
     "r": "Dependency"},
]  # fmt: skip
SINFO_HEADER = {"N": "NODELIST", "n": "HOSTNAMES", "P": "PARTITION", "R": "PARTITION", "T": "STATE", "t": "STATE",
                "E": "REASON", "D": "NODES", "c": "CPUS", "C": "CPUS(A/I/O/T)", "m": "MEMORY", "e": "FREE_MEM",
                "a": "AVAIL", "l": "TIMELIMIT"}  # fmt: skip
NODES = [
    {"N": "c1", "n": "c1", "P": "debug*", "R": "debug", "T": "allocated", "t": "alloc", "E": "none", "D": "1",
     "c": "2", "C": "2/0/0/2", "m": "1400", "e": "900", "a": "up", "l": "infinite"},
    {"N": "c2", "n": "c2", "P": "debug*", "R": "debug", "T": "allocated", "t": "alloc", "E": "none", "D": "1",
     "c": "2", "C": "2/0/0/2", "m": "1400", "e": "950", "a": "up", "l": "infinite"},
    {"N": "c3", "n": "c3", "P": "debug*", "R": "debug", "T": "drained", "t": "drain", "E": "Low RealMemory",
     "D": "1", "c": "2", "C": "0/0/2/2", "m": "1400", "e": "1300", "a": "up", "l": "infinite"},
]  # fmt: skip
JOB_TEXT = (
    "JobId=11 JobName=prep\n   UserId=svc-train(1001) JobState=COMPLETED Reason=None\n   NodeList=c1\n\n"
    "JobId=12 JobName=train\n   UserId=svc-train(1001) JobState=RUNNING Reason=None\n   NodeList=c[1-2]\n\n"
)
NODE_TEXT = (
    "NodeName=c1 Arch=x86_64 CoresPerSocket=2\n   State=ALLOCATED\n\nNodeName=c2 Arch=x86_64\n   State=ALLOCATED\n"
)


def _put(obs: Path, name: str, data: dict) -> None:
    (obs / name).parent.mkdir(parents=True, exist_ok=True)
    (obs / name).write_text(json.dumps(data))


def _stored(stdout: str, rc: int = 0, stderr: str = "") -> dict:
    return {"argv": [], "rc": rc, "stdout": stdout, "stderr": stderr}


@pytest.fixture
def obs(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "OBS", tmp_path)
    (tmp_path / "SNAPSHOT_AT").write_text(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") + " cycle 3 took 1.0s\n")
    _put(tmp_path, "slurm/squeue-fields.json", {"rc": 0, "stderr": "", "header": SQUEUE_HEADER, "rows": JOBS})
    _put(tmp_path, "slurm/sinfo-fields.json", {"rc": 0, "stderr": "", "header": SINFO_HEADER, "rows": NODES})
    _put(tmp_path, "slurm/squeue-l.json", _stored("Wed Oct  7 09:01:02 2026\n  JOBID ...\n"))
    _put(tmp_path, "slurm/sinfo-R.json", _stored("REASON USER TIMESTAMP NODELIST\nLow RealMemory root now c3\n"))
    _put(tmp_path, "slurm/sinfo-R-noheader.json", _stored("Low RealMemory root now c3\n"))
    _put(tmp_path, "slurm/scontrol-job.json", _stored(JOB_TEXT))
    _put(tmp_path, "slurm/scontrol-job-d.json", _stored(JOB_TEXT.replace("NodeList=c1", "NodeList=c1\n   Nodes=c1")))
    _put(tmp_path, "slurm/scontrol-node.json", _stored(NODE_TEXT))
    _put(tmp_path, "slurm/scontrol-reservation.json", _stored("No reservations in the system\n"))
    _put(
        tmp_path,
        "slurm/scontrol-step.json",
        _stored("StepId=12.batch JobId=12\n   State=RUNNING\n\nStepId=12.0 JobId=12\n   State=RUNNING\n"),
    )
    _put(tmp_path, "slurm/scontrol-version.json", _stored("slurm 26.05.2\n"))
    _put(tmp_path, "slurm/sacct.json", _stored("", 1, "Slurm accounting storage is disabled\n"))
    _put(tmp_path, "nodes/ocb-nodes.json", _stored("=== c1\n--- memory.events\noom_kill 0\n"))
    return tmp_path


def run(capsys, *argv) -> tuple[int, str, str]:
    code = tools.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_squeue_default_hides_finished_jobs_and_pads_like_slurm(obs, capsys):
    code, out, err = run(capsys, "squeue")
    lines = out.splitlines()
    assert code == 0 and "read-only view" in err
    assert lines[0] == f"{'JOBID':>18} {'PARTITION':>9} {'NAME':>8} {'USER':>8} {'ST':>2} {'TIME':>10} {'NODES':>6} " \
        "NODELIST(REASON)"  # fmt: skip
    assert [line.split()[0] for line in lines[1:]] == ["12", "13"]  # 11 is COMPLETED
    assert " a-very-l " in lines[2] and "svc-trai" in lines[1]  # truncated to the field's size


def test_squeue_filters_and_custom_formats(obs, capsys):
    assert run(capsys, "squeue", "-h", "-u", "svc-train", "-o", "%i")[1] == "12\n13\n"
    # explicit job ids keep squeue's default state filter (a finished job needs -t all); an unknown id is an error
    assert run(capsys, "squeue", "-j", "11", "-o", "%i %t %M")[1] == "JOBID ST TIME\n"
    assert run(capsys, "squeue", "-j11", "-t", "all", "-h", "-o", "%T")[1] == "COMPLETED\n"
    code, out, err = run(capsys, "squeue", "-j", "99")
    assert code == 1 and out == "" and "Invalid job id" in err
    assert run(capsys, "squeue", "-h", "-o", "%i", "-j")[1] == "12\n13\n"  # a bare -j lists every job
    assert run(capsys, "squeue", "-t", "PD", "-h", "-o", "%i %r")[1] == "13 Dependency\n"
    assert run(capsys, "squeue", "-u", "root")[1].count("\n") == 1  # header only: root has no jobs here
    assert run(capsys, "squeue", "-w", "c2", "-h", "-o", "%i")[1] == "12\n"
    assert run(capsys, "squeue", "-h", "-O", "JobID:5,State:.9")[1] == "12      RUNNING\n13      PENDING\n"
    assert run(capsys, "squeue", "--start", "-h", "-o", "%i")[1] == "13\n"
    assert run(capsys, "squeue", "-h", "-S", "-i", "-t", "all", "-o", "%i")[1] == "13\n12\n11\n"


def test_squeue_long_keeps_slurms_date_line(obs, capsys):
    out = run(capsys, "squeue", "-l")[1].splitlines()
    assert out[0] == "Wed Oct  7 09:01:02 2026" and out[1].split()[4] == "STATE"


def test_squeue_refuses_what_it_cannot_answer(obs, capsys):
    code, _, err = run(capsys, "squeue", "-i", "5")
    assert code == 1 and "watch" in err
    code, _, err = run(capsys, "squeue", "--bogus")
    assert code == 1 and "--help" in err


def test_sinfo_replays_the_usual_forms_and_renders_others(obs, capsys):
    assert run(capsys, "sinfo", "-R")[1].startswith("REASON")
    assert run(capsys, "sinfo", "-R", "-h")[1] == "Low RealMemory root now c3\n"
    assert run(capsys, "sinfo", "-N", "-h", "-o", "%N %T %E")[1] == "c1 allocated none\nc2 allocated none\n" \
        "c3 drained Low RealMemory\n"  # fmt: skip
    grouped = run(capsys, "sinfo", "-h", "-o", "%P %D %t %N %C")[1]
    assert grouped == "debug* 2 alloc c[1-2] 4/0/0/4\ndebug* 1 drain c3 0/0/2/2\n"
    assert run(capsys, "sinfo", "-h", "-n", "c3", "-o", "%N %E")[1] == "c3 Low RealMemory\n"
    assert (
        run(capsys, "sinfo", "-h", "-o", "%n %c %C")[1] == "c1 2 2/0/0/2\nc2 2 2/0/0/2\nc3 2 0/0/2/2\n"
    )  # one per host


def test_scontrol_show_answers_from_the_records(obs, capsys):
    code, out, _ = run(capsys, "scontrol", "show", "job", "12")
    assert code == 0 and out.startswith("JobId=12 JobName=train") and "JobId=11" not in out
    assert run(capsys, "scontrol", "-o", "show", "job", "12")[1] == (
        "JobId=12 JobName=train UserId=svc-train(1001) JobState=RUNNING Reason=None NodeList=c[1-2]\n"
    )
    assert "Nodes=c1" in run(capsys, "scontrol", "show", "job", "11", "-d")[1]
    code, out, err = run(capsys, "scontrol", "show", "job", "99")
    assert code == 1 and "Invalid job id" in err
    assert run(capsys, "scontrol", "show", "nodes")[1].count("NodeName=") == 2
    assert run(capsys, "scontrol", "show", "node", "c2")[1].startswith("NodeName=c2")
    assert run(capsys, "scontrol", "show", "node", "c9")[:2] == (1, "Node c9 not found\n")
    assert run(capsys, "scontrol", "show", "reservation")[1] == "No reservations in the system\n"
    assert run(capsys, "scontrol", "show", "hostnames", "c[1-3],gpu01")[1] == "c1\nc2\nc3\ngpu01\n"
    assert run(capsys, "scontrol", "show", "step", "12")[1].count("StepId=12.") == 2  # every step of the job
    assert run(capsys, "scontrol", "show", "step", "12.0")[1].count("StepId=") == 1
    assert run(capsys, "scontrol", "show", "step", "99")[:2] == (1, "Job step 99. not found\n")
    assert run(capsys, "scontrol", "show", "node", "c1", "c1")[0] == 1
    code, _, err = run(capsys, "scontrol", "update", "NodeName=c3", "State=RESUME")
    assert code == 1 and "not available" in err


def test_writes_shells_and_ocb_side_effects_are_refused(obs, capsys):
    for argv in (["sbatch", "x.sbatch"], ["srun", "hostname"], ["scancel", "12"], ["ocb", "submit", "train"],
                 ["ocb", "dump", "12"], ["ocb", "cluster", "apply"]):  # fmt: skip
        code, out, err = run(capsys, *argv)
        assert code == 1 and out == "" and "not available here" in err, argv
    code, _, err = run(capsys, "ssh", "c1")
    assert code == 255 and "ssh to the cluster's machines" in err
    code, out, _ = run(capsys, "ocb", "nodes")
    assert code == 0 and out.startswith("=== c1")


def test_sacct_replays_the_controllers_answer_for_any_options(obs, capsys):
    code, out, err = run(capsys, "sacct", "-j", "12", "--format=JobID,State")
    assert code == 1 and out == "" and "accounting storage is disabled" in err and "not applied" not in err


def test_stale_or_missing_views_say_so(obs, capsys):
    (obs / "SNAPSHOT_AT").unlink()
    code, _, err = run(capsys, "squeue")
    assert code == 1 and "not ready yet" in err


def test_hostlists_round_trip():
    hosts = ["c1", "c2", "c3", "c5", "gpu01", "gpu02", "login"]
    assert tools.expand(tools.compress(hosts)) == hosts
    assert tools.compress(["c1", "c2", "c3", "c5"]) == "c[1-3,5]"
    assert tools.expand("node[08-10]") == ["node08", "node09", "node10"]


def test_formats_parse_like_slurm():
    assert tools.parse_format("%.18i %5j%%") == [("", "i", True, 18), (" ", "j", False, 5), ("%", "", False, None)]
    assert tools.cell("abcdef", True, 4) == "abcd" and tools.cell("ab", True, 4) == "  ab"
    assert tools.cell("ab", False, 4) == "ab  " and tools.cell("abc", False, None) == "abc"


@pytest.mark.parametrize("module", [tools, collect])
def test_readonly_programs_use_the_standard_library_only(module):
    """They run in the runtime image's Python (main and obs), which has neither bench nor harness."""
    tree = ast.parse(Path(module.__file__).read_text())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert names - {"__future__"} <= set(sys.stdlib_module_names)


def test_collector_tables_split_every_field(tmp_path, monkeypatch):
    fake = tmp_path / "squeue"
    fake.write_text("#!/bin/sh\nprintf 'JOBID\\037NAME\\n12\\037train\\n13\\037prep\\n'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    got = collect.table(["squeue"], "ij")
    assert got["header"] == {"i": "JOBID", "j": "NAME"}
    assert got["rows"] == [{"i": "12", "j": "train"}, {"i": "13", "j": "prep"}]


def test_collector_writes_atomically_and_keeps_the_newest_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "OUT", tmp_path)
    monkeypatch.setattr(collect, "MAX_FILE", 10)
    collect.write("logs/c1/slurmd.log", "0123456789ABCDEF")
    text = (tmp_path / "logs" / "c1" / "slurmd.log").read_text()
    assert text.endswith("6789ABCDEF") and "only the last" in text
    assert not list((tmp_path / "logs" / "c1").glob(".*.tmp"))
