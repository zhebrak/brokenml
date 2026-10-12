"""bench try-it picks one task per category first, fastest first."""

from __future__ import annotations

from bench.tryit import pick


def test_one_per_category_first_then_the_fastest():
    rows = [(30.0, "memory", "a"), (40.0, "memory", "b"), (50.0, "state", "c"), (60.0, "serving", "d")]
    assert pick(rows, 2) == ["a", "c"]
    assert pick(rows, 4) == ["a", "c", "d", "b"]
    assert pick([], 5) == []


def test_a_record_that_differs_only_in_image_ids_still_counts_as_a_candidate(monkeypatch):
    """Local image IDs differ on every host that rebuilds the images; the guard at trial time still checks them."""
    from bench import sweep, tryit, validation
    from bench.paths import RESULTS
    from bench.spec import load_specs

    spec = next(s for s in load_specs() if s.split == "test")
    current = {"task_digest": "t", "grader_digest": "g", "wrong_fixes": "w", "images": {"img:1": "sha256:local"}}
    recorded = {**current, "images": {"img:1": "sha256:elsewhere"}}
    row = {"verdict": "PASS", "inputs": recorded, "runs": {"reference": {"wall_s": 42.0}}}
    boot = {"task_digest": "t", "ok": True, "stamp": {"images": {"img:1": "sha256:elsewhere"}}, "probes_hash": "p"}
    only = [s for s in load_specs() if s.id == spec.id]
    monkeypatch.setattr(tryit, "load_specs", lambda: only)
    monkeypatch.setattr(sweep, "load_table", lambda: {"tasks": {spec.id: row}})
    monkeypatch.setattr(sweep, "inputs", lambda task: current)
    monkeypatch.setattr(validation, "_load", lambda path: {spec.id: boot} if path == RESULTS / "bootcheck.json" else {})
    monkeypatch.setattr(validation, "task_digest", lambda d: "t")
    monkeypatch.setattr(validation, "probes_hash", lambda task: "p")
    monkeypatch.setattr(validation, "image_ids", lambda: {"img:1": "sha256:local"})
    monkeypatch.setattr(validation, "task_image_ids", lambda d, available=None: {"img:1": "sha256:local"})
    assert tryit.candidates() == [(42.0, spec.metadata.category, spec.id)]
    # anything else that differs still makes the record stale
    monkeypatch.setattr(sweep, "inputs", lambda task: {**current, "grader_digest": "other", "task_digest": "u"})
    assert tryit.candidates() == []
    # and the strict comparison, used everywhere else, still sees the image difference
    assert not sweep.fresh(recorded, current)
    assert sweep.fresh(recorded, current, ignore_images=True)
