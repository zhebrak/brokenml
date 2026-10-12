"""The lite subset is reproducible, covers every category in proportion, and spreads difficulty."""

from __future__ import annotations

from collections import Counter

from bench.lite import quotas, select
from bench.spec import load_specs

SPECS = [s for s in load_specs() if s.split == "test"]


def test_quotas_are_proportional_with_one_seat_minimum():
    assert quotas({"a": 10, "b": 5, "c": 1}, 8) == {"a": 5, "b": 2, "c": 1}
    assert sum(quotas({"a": 3, "b": 3, "c": 3, "d": 3}, 6).values()) == 6


def test_selection_is_reproducible_and_covers_every_category():
    a, b = select(SPECS, 20, seed=0), select(SPECS, 20, seed=0)
    assert a == b and len(a) == 20
    cats = Counter(s.metadata.category for s in SPECS if s.id in a)
    assert set(cats) == {s.metadata.category for s in SPECS}
    assert select(SPECS, 20, seed=1) != a or len(SPECS) <= 20


def test_measured_pass_rates_spread_difficulty():
    rates = {s.id: (0.1 if i % 3 == 0 else 0.5 if i % 3 == 1 else 0.9) for i, s in enumerate(SPECS)}
    chosen = select(SPECS, 24, seed=0, pass_rates=rates)
    levels = Counter("hard" if rates[t] < 1 / 3 else "medium" if rates[t] < 2 / 3 else "easy" for t in chosen)
    assert min(levels.values()) >= 4  # no level is left out


def test_measured_evidence_labels_override_the_authors():
    from bench.lite import evidence

    spec = SPECS[0]
    flipped = "static" if spec.metadata.evidence_author == "runtime" else "runtime"
    assert evidence(spec, {}) == spec.metadata.evidence_author
    assert evidence(spec, {spec.id: {"evidence": {"value": flipped}}}) == flipped
