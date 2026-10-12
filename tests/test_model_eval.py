"""The held-out evaluation shared by `ocb score` and the verifier (needs torch: pytest -m torch)."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
safetensors = pytest.importorskip("safetensors.torch")

from harness.teacher import Teacher  # noqa: E402
from ocb.model import GPT, ExportError, GPTConfig, heldout_count, heldout_loss, load_export, well_formed  # noqa: E402

pytestmark = pytest.mark.torch


def test_export_with_renamed_keys_is_rejected(tmp_path):
    cfg = GPTConfig()
    state = {k.replace("blocks.", "layers."): v for k, v in GPT(cfg).state_dict().items()}
    safetensors.save_file(state, str(tmp_path / "m.safetensors"))
    with pytest.raises(ExportError, match="Missing key"):
        load_export(str(tmp_path / "m.safetensors"), cfg)


def test_export_round_trip_and_loss(tmp_path):
    cfg = GPTConfig()
    torch.manual_seed(0)
    model = GPT(cfg)
    safetensors.save_file(model.state_dict(), str(tmp_path / "m.safetensors"))
    loaded = load_export(str(tmp_path / "m.safetensors"), cfg)
    tokens = Teacher(seed=3).sample(32, cfg.ctx + 1, seed=4)
    assert heldout_loss(loaded, tokens) == pytest.approx(heldout_loss(model.eval(), tokens))


def test_heldout_loss_is_the_same_in_any_chunking_and_chunks_by_tokens():
    cfg = GPTConfig(ctx=16)
    torch.manual_seed(0)
    model = GPT(cfg).eval()
    tokens = Teacher(seed=3).sample(40, cfg.ctx + 1, seed=4)  # 40 rows of 17 tokens
    whole = heldout_loss(model, tokens, chunk_tokens=10**9)
    assert heldout_loss(model, tokens, chunk_tokens=17) == pytest.approx(whole)  # one row per pass
    assert heldout_loss(model, tokens, chunk_tokens=5) == pytest.approx(whole)  # never fewer than one row
    passes, forward = [], model.forward
    model.forward = lambda t: passes.append(len(t)) or forward(t)
    heldout_loss(model, tokens, chunk_tokens=100)
    assert passes == [5] * 8  # 100 tokens per pass over 17-token rows: 5 rows at a time, however long the rows


def test_heldout_count_caps_large_models():
    small = GPTConfig()
    assert heldout_count(small, GPT(small)) == 2048  # 131072 tokens / 64
    big = GPTConfig(d_model=512, n_layer=8, n_head=8)
    assert 128 <= heldout_count(big, GPT(big)) < 2048


def test_well_formed_drops_out_of_vocabulary_sequences():
    t = torch.tensor([[1, 2, 3], [1, 40, 3], [-1, 0, 0]])
    assert well_formed(t, 32).tolist() == [[1, 2, 3]]


def test_teacher_sampling_is_deterministic():
    t = Teacher(seed=7)
    assert torch.equal(t.sample(4, 65, seed=1), t.sample(4, 65, seed=1))
    assert not torch.equal(t.sample(4, 65, seed=1), t.sample(4, 65, seed=2))


def test_load_only_reports_the_final_models_weights(tmp_path, capsys):
    import json

    from harness.verify.evaluate import check_loads

    cfg = GPTConfig()
    torch.manual_seed(0)
    final = GPT(cfg).state_dict()
    safetensors.save_file(final, str(tmp_path / "final.safetensors"))
    # the same weights saved again with other metadata: a different file, the same model
    safetensors.save_file(final, str(tmp_path / "copy.safetensors"), metadata={"step": "10"})
    safetensors.save_file(GPT(cfg).state_dict(), str(tmp_path / "step.safetensors"))
    files = [str(tmp_path / n) for n in ("copy.safetensors", "step.safetensors")]
    check_loads(json.dumps({}), files, str(tmp_path / "final.safetensors"))
    out = json.loads(capsys.readouterr().out)
    assert out[files[0]] == "same weights as the final export" and out[files[1]] == ""


def test_load_only_reports_a_malformed_final_export_as_submission_data(tmp_path, capsys):
    import json

    from harness.verify.evaluate import check_loads

    final = tmp_path / "final.safetensors"
    final.write_bytes(b"not safetensors")
    check_loads("{}", ["eval.safetensors"], str(final))
    assert "invalid final export" in json.loads(capsys.readouterr().out)["eval.safetensors"]
