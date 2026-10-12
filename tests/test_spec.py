"""Task specs are validated at load time: typos and inconsistent specs fail loudly, before anything renders."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from bench import spec as specmod
from bench.paths import FAMILIES
from bench.spec import load, load_specs
from harness.config import VerifyConfig
from harness.verify.rules import contract_lines


def test_every_spec_loads():
    specs = load_specs()
    assert len(specs) >= 40
    assert {s.split for s in specs} == {"test", "dev", "gpu"}


def _copy_spec(tmp_path: Path, task: str, edit) -> Path:
    src = next(FAMILIES.glob(f"*/{task}"))
    dst = tmp_path / src.parent.name / task
    shutil.copytree(src, dst)
    raw = yaml.safe_load((dst / "spec.yaml").read_text())
    edit(raw)
    (dst / "spec.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    return dst


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda r: r["verify"].update(require_checkpoint_every=100), "require_checkpoint_every"),  # typo of ..._every
        (lambda r: r["bootstrap"]["symptom"].update(kind="hung"), "kind"),
        (lambda r: r["metadata"].update(category="networking"), "category"),
        (lambda r: r["metadata"].update(provenance=["github.com/pytorch/pytorch/issues/1"]), "https"),
        (lambda r: r.update(split="train"), "split"),
        (lambda r: r["verify"].pop("deadline_s"), "deadline_s"),
        (lambda r: r.update(id="Rank0_Eval"), "id"),
    ],
)
def test_bad_specs_fail_with_a_readable_error(tmp_path, edit, message):
    with pytest.raises(ValueError, match=message):
        load(_copy_spec(tmp_path, "rank0-eval-desync", edit))


def test_directory_must_match_id_and_family(tmp_path):
    dst = _copy_spec(tmp_path, "rank0-eval-desync", lambda r: None)
    moved = dst.parent.parent / "B" / dst.name
    moved.parent.mkdir()
    dst.rename(moved)
    with pytest.raises(ValueError, match="family"):
        load(moved)


def test_store_teachers_must_differ(tmp_path):
    def same(r):
        r["store"]["verifier_teacher_seed"] = r["store"]["agent_teacher_seed"]

    with pytest.raises(ValueError, match="different teachers"):
        load(_copy_spec(tmp_path, "latest-half-written", same))


RULE_EXAMPLES = {
    "require_val_every": (100, "validation loss at least every 100 steps"),
    "require_checkpoints_every": (50, "At least every 50 steps the run trains, a checkpoint of the model"),
    "require_eval_exports_every": (10, "`/shared/out/eval/step_<N>.safetensors`"),
    "placement": ({"nodes": 2, "ranks_per_node": 2}, "2 ranks on each of 2 nodes, observed while it runs:"),
    "require_metric_every": ({"key": "replica_check", "every": 100}, "`replica_check`"),
    "require_step_coverage": (True, "every step from 1 to the end"),
    "throughput": ({"ratio_min": 0.5}, "at most 2x as long"),
    "loss_max": (1.5, "at most 1.5"),
    "policy": ({"frozen": ["jobs/train/launch.sbatch"]}, "jobs/train/launch.sbatch"),
}
# VerifyConfig fields that are not rules the agent must meet (plumbing, or stated by the instruction itself).
NOT_RULES = {"substrate", "job", "min_nodes", "world_size", "deadline_s", "store", "corpus", "data", "calibration",
             "policy_skip", "replay", "ready_timeout_s", "ttft_p95_max_s", "store_refill_s", "site", "gpu_class",
             "gpu_budget_mb"}  # fmt: skip


def test_every_verifier_rule_field_has_a_contract_sentence():
    """A new VerifyConfig field is either listed in NOT_RULES or has an example here, so CONTRACT.md states it."""
    assert set(VerifyConfig.model_fields) == NOT_RULES | set(RULE_EXAMPLES)


@pytest.mark.parametrize("key", sorted(RULE_EXAMPLES))
def test_every_verifier_rule_is_stated_in_the_contract(key):
    value, phrase = RULE_EXAMPLES[key]
    assert phrase in contract_lines(VerifyConfig.model_validate({"deadline_s": 300, key: value}))


def test_calibration_names_a_known_set():
    sets = specmod.calibration_sets()
    assert all(s.verify.calibration in sets for s in load_specs() if s.verify.calibration)


def test_no_evidence_channel_holds_more_than_a_fifth_of_the_test_split():
    from collections import Counter

    test = [s for s in load_specs() if s.split == "test"]
    counts = Counter(s.metadata.channel for s in test)
    assert max(counts.values()) <= len(test) / 5, counts


def test_every_category_states_its_principle():
    from bench.spec import CATEGORIES, CATEGORY_PRINCIPLES

    assert set(CATEGORY_PRINCIPLES) == set(CATEGORIES)
