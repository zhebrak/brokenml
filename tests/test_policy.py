"""The verifier's /ops policy: exploit fixtures and contract rules."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from bench.paths import ROOT
from harness.verify import policy as pol

TEMPLATE = ROOT / "templates" / "ops"
POLICY = pol.Policy.from_config(
    {
        "contract": {
            "file": "jobs/train/train.yaml",
            "fixed": ["model", "steps", "seed"],
            "bounds": {"eval_every": {"min": 1, "max": 100}},
            "products": [{"keys": ["micro_batch", "grad_accum"], "equals": 16}],
        }
    }
)


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path]:
    pristine, agent = tmp_path / "pristine", tmp_path / "ops"
    shutil.copytree(TEMPLATE, pristine)
    shutil.copytree(TEMPLATE, agent)
    return pristine, agent


def check(trees, policy=POLICY):
    pristine, agent = trees
    return pol.check(agent, pristine, policy)


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new))


def test_unchanged_tree_passes(trees):
    assert check(trees) is None


def test_ordinary_code_and_config_edits_pass(trees):
    _, agent = trees
    edit(agent / "src/trainer/loop.py", 'torch.manual_seed(cfg["seed"])', 'torch.manual_seed(cfg["seed"])  # seed')
    edit(agent / "jobs/train/train.yaml", "micro_batch: 16\ngrad_accum: 1", "micro_batch: 8\ngrad_accum: 2")
    (agent / "ANALYSIS.md").write_text("mechanism ...")
    assert check(trees) is None


def test_git_directory_is_ignored(trees):
    _, agent = trees
    hooks = agent / ".git" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "post-checkout").write_text("#!/bin/sh\ntouch /logs/verifier/pwned\n")
    (agent / ".git" / "config").write_text("[core]\n\tfsmonitor = touch /logs/verifier/pwned\n")
    assert check(trees) is None


def test_symlink_rejected(trees):
    _, agent = trees
    os.symlink("/logs/verifier/reward.json", agent / "jobs/train/out")
    assert "symlink" in check(trees)


def test_binary_file_rejected(trees):
    _, agent = trees
    (agent / "weights.bin").write_bytes(bytes(range(256)) * 10)
    assert "non-text" in check(trees)


def test_too_large_change_rejected(trees):
    _, agent = trees
    (agent / "src" / "weights.py").write_text("W = '" + "a" * (pol.MAX_CHANGED_BYTES + 10) + "'\n")
    assert "too large" in check(trees)


def test_frozen_file_rejected(trees):
    _, agent = trees
    (agent / "cluster/cgroup.conf").write_text("CgroupPlugin=autodetect\n")
    assert "may not be changed" in check(trees)


@pytest.mark.parametrize(
    "line",
    [
        "Prolog=/ops/evil.sh",
        "Epilog=/ops/evil.sh",
        "HealthCheckProgram=/ops/evil.sh",
        "JobCompType=jobcomp/script",
        "Include /ops/more.conf",
        "PlugStackConfig=/ops/plugstack.conf",
        "TaskProlog=/ops/evil.sh",
    ],
)
def test_slurm_program_and_plugin_keys_rejected(trees, line):
    _, agent = trees
    conf = agent / "cluster/slurm.conf"
    conf.write_text(conf.read_text() + line + "\n")
    assert "slurm.conf" in check(trees)


def test_slurm_allowed_key_change_passes(trees):
    _, agent = trees
    edit(agent / "cluster/slurm.conf", "SlurmdTimeout=30", "SlurmdTimeout=60")
    assert check(trees) is None


def test_partition_change_rejected_unless_allowed(trees):
    _, agent = trees
    edit(agent / "cluster/slurm.conf", "MaxTime=00:15:00", "MaxTime=INFINITE")
    assert "PartitionName" in check(trees)
    allowed = pol.Policy.from_config(
        {"slurm_allowed": ["PartitionName"], "contract": {"file": "jobs/train/train.yaml"}}
    )
    assert check(trees, allowed) is None


def test_contract_fixed_field_rejected(trees):
    _, agent = trees
    edit(agent / "jobs/train/train.yaml", "steps: 500", "steps: 250")
    assert "steps" in check(trees)


def test_contract_bound_rejected(trees):
    _, agent = trees
    edit(agent / "jobs/train/train.yaml", "eval_every: 100", "eval_every: 0")
    assert "eval_every" in check(trees)


def test_contract_product_rejected(trees):
    _, agent = trees
    edit(agent / "jobs/train/train.yaml", "micro_batch: 16", "micro_batch: 8")
    assert "micro_batch x grad_accum" in check(trees)


def test_removing_contract_file_rejected(trees):
    _, agent = trees
    (agent / "jobs/train/train.yaml").unlink()
    assert "removed" in check(trees)


def test_duplicate_partition_line_rejected(trees):
    # slurmctld keeps the first PartitionName definition; a line inserted above would win.
    _, agent = trees
    conf = agent / "cluster/slurm.conf"
    conf.write_text("PartitionName=main Nodes=c[1-2] Default=YES MaxTime=01:00:00 State=UP\n" + conf.read_text())
    assert "more than once" in check(trees)


def test_continuation_line_rejected(trees):
    _, agent = trees
    conf = agent / "cluster/slurm.conf"
    conf.write_text(conf.read_text() + "SchedulerParameters=sched_interval=5,\\\nbf_interval=5\n")
    assert "continuation" in check(trees)


def test_bytecode_is_ignored(trees):
    _, agent = trees
    cache = agent / "src" / "__pycache__"
    cache.mkdir()
    (cache / "train.cpython-312.pyc").write_bytes(b"\xcb\r\r\n" + bytes(64))
    assert check(trees) is None


@pytest.mark.parametrize("change", ["remove", "weaken"])
def test_private_data_cannot_be_removed_or_weakened(trees, change):
    """PrivateData keeps the verifier's reference jobs invisible to the agent's job account."""
    _, agent = trees
    conf = agent / "cluster/slurm.conf"
    new = "" if change == "remove" else "PrivateData=usage\n"
    edit(conf, "PrivateData=jobs,usage\n", new)
    assert "PrivateData" in check(trees)


def test_a_second_setting_on_one_line_is_rejected(trees):
    """slurmctld reads every key=value on a line; an allowed key must not carry a denied one with it."""
    _, agent = trees
    edit(agent / "cluster/slurm.conf", "MinJobAge=900", "MinJobAge=900 PrivateData=usage")
    assert "one setting per line" in check(trees)


def test_symlinks_are_rejected_even_where_files_are_ignored(trees):
    _, agent = trees
    (agent / ".git").mkdir(exist_ok=True)
    (agent / ".git" / "evil").symlink_to("/etc/shadow")
    assert "symlink" in check(trees)


def test_analysis_is_writable_in_config_only_tasks(trees):
    """Every instruction asks for /ops/ANALYSIS.md, so a task that restricts edits to its config must still allow it."""
    config_only = pol.Policy.from_config(
        {"editable": ["jobs/train/train.yaml"], "contract": {"file": "jobs/train/train.yaml", "fixed": ["model"]}}
    )
    _, agent = trees
    (agent / "ANALYSIS.md").write_text("mechanism ...")
    assert check(trees, config_only) is None
    edit(agent / "src/trainer/loop.py", 'torch.manual_seed(cfg["seed"])', 'torch.manual_seed(cfg["seed"])  # seed')
    assert "may not be changed: src/trainer/loop.py" in check(trees, config_only)


@pytest.mark.parametrize("value", [".nan", ".inf", "true", "50.5", "'50'"])
def test_a_bound_takes_a_finite_number_of_the_declared_type(trees, value):
    _, agent = trees  # YAML .nan passes every comparison; a bool is not a number
    edit(agent / "jobs/train/train.yaml", "eval_every: 100", f"eval_every: {value}")
    assert "eval_every" in check(trees)


def test_deleting_a_file_outside_the_editable_paths_is_rejected(trees):
    _, agent = trees  # deletions were checked only against the frozen list
    (agent / "src/train.py").unlink()
    config_only = pol.Policy.from_config({"editable": ["jobs/train/train.yaml"]})
    assert "may not be removed: src/train.py" in check(trees, config_only)
    assert check(trees) is None  # where every path is editable, deleting one is a change like any other


def test_a_huge_tree_is_rejected_before_it_is_read(trees, monkeypatch):
    _, agent = trees
    monkeypatch.setattr(pol, "MAX_TREE_BYTES", 1000)
    (agent / "blob.txt").write_text("x" * 2000)
    assert "tree too large" in check(trees)


def test_a_non_mapping_contract_file_is_a_policy_failure_not_a_crash(trees):
    _, agent = trees
    (agent / POLICY.contract_file).write_text("- just\n- a list\n")
    assert "does not parse" in (check(trees) or "")  # a list parsed, then `.get` crashed the verifier: a free re-grade
    (agent / POLICY.contract_file).write_text("42\n")
    assert "does not parse" in (check(trees) or "")
