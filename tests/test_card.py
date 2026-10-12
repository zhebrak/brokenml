"""The dataset card's counts come from the specs."""

from __future__ import annotations

from bench.card import card
from bench.spec import load_specs


def test_the_card_counts_the_test_split_and_carries_the_canary():
    text = card()
    test = [s for s in load_specs() if s.split == "test"]
    assert f"{len(test)} test tasks" in text and "canary" in text and "license: apache-2.0" in text
