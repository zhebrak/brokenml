"""Every verifier check has a contract clause (bench validation prints it next to the check each wrong fix declares),
so a check without its contract line cannot land."""

from __future__ import annotations

import re
from pathlib import Path

from bench import sweep
from bench.patches import wrong_fix_patches
from bench.spec import load_specs
from harness.verify import rules

VERIFY = Path(rules.__file__).parent


def test_every_literal_check_name_has_a_clause():
    names: set[str] = set()
    for src in VERIFY.glob("*.py"):
        names |= set(re.findall(r'(?:\.check|\bCheck)\(\s*"([^"]+)"', src.read_text()))
    assert names, "no check names found in the verifier sources"
    missing = sorted(n for n in names if rules.clause(n) is None)
    assert not missing, missing


def test_every_declared_expectation_has_a_clause():
    missing = []
    for spec in load_specs():
        for name in wrong_fix_patches(spec):
            for want in sweep.expectation(spec.id, f"wrong:{name}") or []:
                if rules.clause(want.partition(": ")[0]) is None:
                    missing.append(f"{spec.id}/{name}: {want}")
    assert not missing, missing


def test_metric_logged_checks_have_a_clause():
    assert rules.clause("tokens_per_s logged")
    assert rules.clause("something else entirely") is None
