"""Corpus options: a remapped block of train rows, and a dataset served only by the object store (pytest -m torch)."""

from __future__ import annotations

import json

import pytest

torch = pytest.importorskip("torch")

from safetensors.torch import load_file  # noqa: E402

from harness import corpus  # noqa: E402
from harness.config import Data  # noqa: E402
from harness.teacher import Teacher  # noqa: E402

pytestmark = pytest.mark.torch


def test_remap_changes_one_contiguous_block_with_in_range_ids():
    train = Teacher(seed=1).sample(200, 9, seed=2)
    out = corpus.remapped(train, rows=30, vocab=32)
    changed = (out != train).any(dim=1).nonzero().flatten().tolist()
    assert len(changed) == 30 and changed == list(range(changed[0], changed[0] + 30))
    assert int(out.min()) >= 0 and int(out.max()) < 32  # a range check cannot see it


def test_remap_permutation_is_fixed_across_draws():
    train = torch.arange(32).repeat(40, 1)
    a, b = corpus.remapped(train, rows=40, vocab=32), corpus.remapped(train, rows=40, vocab=32)
    assert torch.equal(a, b) and not torch.equal(a, train)


def test_sharded_corpus_lives_in_the_store_volume(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "DATASETS", tmp_path / "datasets")
    where = corpus.write(Teacher(seed=3), tmp_path / "data" / "corpus.safetensors", 100, 20, 9, heldout=16,
                         data=Data(shards=4))  # fmt: skip
    index = json.loads((where / "index.json").read_text())
    assert len(index["train"]) == 4 and index["sequences"] == 100
    assert sum(len(load_file(str(where / name))["train"]) for name in index["train"]) == 100
    assert len(load_file(str(where / "val.safetensors"))["val"]) == 20
    assert not (tmp_path / "data" / "corpus.safetensors").exists()  # the job cannot read it from shared storage
    assert len(load_file(str(tmp_path / "data" / "heldout.safetensors"))["heldout"]) == 16


def test_shard_manifest_identical_repeats_rank_zero_range(tmp_path):
    teacher = Teacher(seed=5)
    data = Data(shard_manifest="identical")
    path = corpus.write(teacher, tmp_path / "corpus.safetensors", 64, 8, 9, data=data, world=4)
    shards = load_file(str(path))["shards"]
    assert shards.tolist() == [[0, 16]] * 4
    disjoint = corpus.shard_manifest(64, 4, "disjoint").tolist()
    assert disjoint == [[0, 16], [16, 32], [32, 48], [48, 64]]
