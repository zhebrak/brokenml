"""Task cards are generated for every test task and carry what a reader needs to judge it."""

from __future__ import annotations

from bench import cards
from bench.patches import wrong_fix_patches
from bench.spec import by_id, load_specs


def test_a_card_names_the_chain_every_shortcut_and_its_expected_check():
    spec = by_id("rank0-eval-desync")
    text = cards.card(spec, {"bootcheck": "ok", "green": False}, None, {})
    for step in spec.metadata.causal_chain:
        assert step in text
    for name in wrong_fix_patches(spec):
        assert f"`{name}`" in text
    assert "`validation logged`" in text and "No sweep record yet." in text
    assert "| ok |" in text  # the qualification row is the one passed in


def test_contract_controls_are_marked_and_their_note_is_not_repeated(tmp_path):
    patch = tmp_path / "x.patch"
    patch.write_text("")
    patch.with_suffix(".expect").write_text("# contract control\n# rank 0 saves alone\ncheckpoints written\n")
    checks, note, control = cards.expectation_text(patch)
    assert control and note == "rank 0 saves alone" and checks == "`checkpoints written`"


def test_every_test_task_gets_a_card_and_missing_adaptation_notes_are_listed(tmp_path):
    missing = cards.write(tmp_path, rows={})
    test = [s for s in load_specs() if s.split == "test"]
    assert sorted(p.stem for p in tmp_path.glob("*.md") if p.stem != "README") == sorted(s.id for s in test)
    assert set(missing) == {s.id for s in test if s.metadata.provenance_kind == "issue-repro" and not s.adaptation}
