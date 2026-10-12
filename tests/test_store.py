"""The checkpoint stores are trained with the job's own settings, so the job's resume path loads what they hold."""

from __future__ import annotations

import importlib.util

import pytest

from bench.paths import TEMPLATES
from harness import store


def _trainer(module: str):
    spec = importlib.util.spec_from_file_location(f"trainer_{module}", TEMPLATES / "ops/src/trainer" / f"{module}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_store_settings_equal_the_trainer_defaults():
    d = _trainer("config").DEFAULTS
    assert d["model"] == store.JOB_MODEL
    assert (
        d["lr"], d["warmup_steps"], d["min_lr_ratio"], d["weight_decay"]
    ) == (store.LR, store.WARMUP, store.MIN_LR_RATIO, store.WEIGHT_DECAY)  # fmt: skip
    assert list(store.BETAS) == d["betas"]
    assert (d["micro_batch"], d["train_seqs"]) == (store.MICRO_BATCH, store.TRAIN_SEQS)


@pytest.mark.torch
def test_store_schedule_equals_the_trainer_schedule():
    cfg = {**_trainer("config").DEFAULTS, "steps": 800, "decay_steps": None}
    lr_at = _trainer("optim").lr_at
    assert all(abs(store.lr_at(s, 800) - lr_at(s, cfg)) < 1e-12 for s in range(800))
