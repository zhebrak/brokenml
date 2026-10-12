"""Policy invariants over every task: what the instruction and the contract allow passes the
production policy, what they forbid fails, and every reference and accepted fix passes."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from bench import patches
from bench.render import scope
from bench.spec import load_specs, task_dir
from harness.config import DEFAULT_FROZEN, VerifyConfig
from harness.verify import policy
from harness.verify.rules import contract_lines

SPECS = [s for s in load_specs() if s.split in ("test", "dev") and s.substrate == "slurm"]


def _cfg(spec) -> VerifyConfig:
    return VerifyConfig.model_validate(yaml.safe_load((task_dir(spec) / "tests" / "verify.yaml").read_text()))


def _tree(src: Path, tmp_path: Path, name: str) -> Path:
    dst = tmp_path / name
    shutil.copytree(src, dst)
    return dst


@pytest.mark.parametrize("spec", [s for s in load_specs() if s.split in ("test", "dev")], ids=lambda s: s.id)
def test_reference_and_accepted_fixes_pass_the_production_policy(spec, tmp_path):
    tests = task_dir(spec) / "tests"
    rules = policy.Policy.from_config(_cfg(spec).policy)
    ref = patches.materialise(tests / "reference")
    try:
        assert policy.check(ref, tests / "pristine", rules) is None
    finally:
        shutil.rmtree(ref, ignore_errors=True)
    for name in patches.fix_patches(spec, "accepted"):
        tree = _tree(tests / "pristine", tmp_path, f"accepted-{name}")
        files = patches.wrong_fix_files(spec, name, "accepted")
        shutil.copytree(files, tree, dirs_exist_ok=True)
        shutil.rmtree(files)
        assert policy.check(tree, tests / "pristine", rules) is None, f"accepted fix {name}"


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.id)
def test_what_the_instruction_and_contract_allow_passes_and_what_they_forbid_fails(spec, tmp_path):
    cfg = _cfg(spec)
    pristine = task_dir(spec) / "tests" / "pristine"
    rules = policy.Policy.from_config(cfg.policy)
    contract = contract_lines(cfg)

    def edited(rel: str) -> str | None:
        tree = _tree(pristine, tmp_path, rel.replace("/", "_"))
        with (tree / rel).open("a") as f:
            f.write("\n# reviewed\n")
        return policy.check(tree, pristine, rules)

    allowed = cfg.policy.editable if cfg.policy.editable != ["**"] else ["jobs/train/train.yaml", "src/train.py"]
    for rel in allowed:
        if (pristine / rel).exists():
            assert edited(rel) is None, f"{spec.id}: an edit to {rel} (allowed by '{scope(spec)}') is rejected"
    for rel in [*DEFAULT_FROZEN, *cfg.policy.frozen]:
        if (pristine / rel).exists():
            assert edited(rel) is not None, f"{spec.id}: an edit to frozen {rel} passes"
    if cfg.policy.editable != ["**"] and (pristine / "src/train.py").exists():
        assert edited("src/train.py") is not None, f"{spec.id}: a config-only task accepts a code edit"
    if (
        "In `cluster/slurm.conf` only these settings may change" in contract
        and (pristine / "cluster/slurm.conf").exists()
    ):
        tree = _tree(pristine, tmp_path, "slurm")
        conf = tree / "cluster/slurm.conf"
        conf.write_text(conf.read_text().replace("KillWait=10", "KillWait=20"))
        assert policy.check(tree, pristine, rules) is None, f"{spec.id}: the contract allows KillWait, the policy not"
