"""The counts the README states come from the specs (an auditor checks counts first)."""

from __future__ import annotations

import re
from collections import Counter

from bench.paths import ROOT
from bench.spec import load_specs


def test_readme_counts_match_the_specs():
    test = [s for s in load_specs() if s.split == "test"]
    kinds = Counter(s.metadata.provenance_kind for s in test)
    readme = (ROOT / "README.md").read_text()
    stated = re.findall(r"(\d+) of (?:the )?(\d+) test tasks reproduce a specific public issue", readme)
    assert stated, "the README states how many test tasks reproduce a public issue"
    assert all(int(a) == kinds["issue-repro"] and int(b) == len(test) for a, b in stated)
    assert not re.search(r"\b12 of 46\b", readme)  # the pre-relabel count
