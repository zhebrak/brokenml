"""The verifier's checkpoint inspection: DCP metadata read without running pickled code (pytest -m torch)."""

from __future__ import annotations

import os
import pickle

import pytest

torch = pytest.importorskip("torch")

import torch.distributed as dist  # noqa: E402
import torch.distributed.checkpoint as dcp  # noqa: E402
from torch.distributed.checkpoint.api import CheckpointException  # noqa: E402
from torch.distributed.checkpoint.metadata import ChunkStorageMetadata  # noqa: E402
from torch.distributed.checkpoint.state_dict import get_state_dict  # noqa: E402

from harness.verify.checkpoint import content_problem, problem, read_metadata  # noqa: E402
from ocb.model import GPT, GPTConfig  # noqa: E402

pytestmark = pytest.mark.torch


@pytest.fixture(scope="module")
def group():
    os.environ.setdefault("MASTER_ADDR", "127.0.0.1")
    os.environ.setdefault("MASTER_PORT", "29533")
    dist.init_process_group("gloo", rank=0, world_size=1)
    yield
    dist.destroy_process_group()


def _save(path, with_optim=True, steps=1):
    model = GPT(GPTConfig())
    opt = torch.optim.AdamW(model.parameters())
    for _ in range(steps):
        model(torch.zeros(2, 8, dtype=torch.long)).sum().backward()
        opt.step()
    msd, osd = get_state_dict(model, opt)
    dcp.save({"model": msd, "optim": osd} if with_optim else {"model": msd}, checkpoint_id=str(path))
    return {n: tuple(p.shape) for n, p in model.named_parameters()}


def _files(path):
    return {f.name: f.stat().st_size for f in path.iterdir()}


def test_a_full_checkpoint_is_well_formed(tmp_path, group):
    params = _save(tmp_path / "ck")
    assert problem(read_metadata((tmp_path / "ck" / ".metadata").read_bytes()), _files(tmp_path / "ck"), params) == ""


def test_a_model_only_checkpoint_is_not(tmp_path, group):
    params = _save(tmp_path / "ck", with_optim=False)
    why = problem(read_metadata((tmp_path / "ck" / ".metadata").read_bytes()), _files(tmp_path / "ck"), params)
    assert "optim.state." in why and "missing" in why


def test_a_missing_or_truncated_shard_is_not(tmp_path, group):
    params = _save(tmp_path / "ck")
    md = read_metadata((tmp_path / "ck" / ".metadata").read_bytes())
    files = _files(tmp_path / "ck")
    assert "is not in the checkpoint" in problem(md, {".metadata": files[".metadata"]}, params)
    shard = next(n for n in files if n.endswith(".distcp"))
    assert "shorter" in problem(md, {**files, shard: 10}, params)


def test_metadata_that_would_run_code_is_refused():
    class Exploit:
        def __reduce__(self):
            return (os.system, ("echo pwned",))

    with pytest.raises(pickle.UnpicklingError, match="not part of checkpoint metadata"):
        read_metadata(pickle.dumps(Exploit()))
    with pytest.raises(pickle.UnpicklingError, match="is a dict"):
        read_metadata(pickle.dumps({"state_dict_metadata": {}}))


def _md(path):
    return read_metadata((path / ".metadata").read_bytes())


def test_a_real_checkpoint_decodes_and_its_optimizer_steps_match(tmp_path, group):
    _save(tmp_path / "ck", steps=2)
    assert content_problem(_md(tmp_path / "ck"), tmp_path / "ck", step=2) == ""


def test_zeroed_same_size_shards_do_not_decode(tmp_path, group):
    _save(tmp_path / "ck")  # zeros of exactly the same length passed the metadata check
    for f in (tmp_path / "ck").glob("*.distcp"):
        f.write_bytes(b"\x00" * f.stat().st_size)
    assert "does not decode" in content_problem(_md(tmp_path / "ck"), tmp_path / "ck", step=1)


def test_a_truncated_shard_does_not_decode(tmp_path, group):
    _save(tmp_path / "ck")
    shard = next((tmp_path / "ck").glob("*.distcp"))
    shard.write_bytes(shard.read_bytes()[: shard.stat().st_size // 2])
    assert "does not decode" in content_problem(_md(tmp_path / "ck"), tmp_path / "ck", step=1)


def test_another_steps_checkpoint_copied_into_place_fails(tmp_path, group):
    _save(tmp_path / "ck", steps=2)  # a valid checkpoint of step 2, presented as step 3
    assert "do not match step 3" in content_problem(_md(tmp_path / "ck"), tmp_path / "ck", step=3)


def test_a_checkpoint_without_optimizer_step_counters_is_not_well_formed(tmp_path, group):
    model = GPT(GPTConfig())
    opt = torch.optim.AdamW(model.parameters())
    model(torch.zeros(2, 8, dtype=torch.long)).sum().backward()
    opt.step()
    msd, osd = get_state_dict(model, opt)
    for state in osd["state"].values():
        state.pop("step")
    dcp.save({"model": msd, "optim": osd}, checkpoint_id=str(tmp_path / "ck"))
    params = {n: tuple(p.shape) for n, p in model.named_parameters()}
    assert ".step is missing" in problem(_md(tmp_path / "ck"), _files(tmp_path / "ck"), params)


def test_an_all_zero_model_is_not_recoverable(tmp_path, group):
    model = GPT(GPTConfig())
    opt = torch.optim.AdamW(model.parameters())
    model(torch.zeros(2, 8, dtype=torch.long)).sum().backward()
    opt.step()
    with torch.no_grad():
        for p in model.parameters():
            p.zero_()
    msd, osd = get_state_dict(model, opt)
    dcp.save({"model": msd, "optim": osd}, checkpoint_id=str(tmp_path / "ck"))
    assert "all zero" in content_problem(_md(tmp_path / "ck"), tmp_path / "ck", step=1)


def test_a_compressed_tensor_record_is_refused():
    import io
    import zipfile

    from harness.verify.checkpoint import _tensor

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("archive/data/0", b"\0" * 4096)
    with pytest.raises(ValueError, match="compressed"):
        _tensor(buf.getvalue(), torch.float32)


def test_a_full_checkpoint_restores_and_same_sized_garbage_does_not(tmp_path, group):
    from harness.verify.checkpoint import geometry_problem, restore

    path = tmp_path / "ck"
    params = _save(path)
    md = read_metadata((path / ".metadata").read_bytes())
    assert geometry_problem(md, params) == ""
    restore(md, path, {})
    shard = next(path.glob("*.distcp"))
    shard.write_bytes(b"\0" * shard.stat().st_size)
    assert problem(md, _files(path), params) == ""  # sizes and metadata alone cannot tell garbage from a checkpoint
    with pytest.raises(CheckpointException):  # DCP wraps the decoder's error (a BaseException, caught by name)
        restore(md, path, {})


def test_chunk_geometry_cannot_be_faked(tmp_path, group):
    from harness.verify.checkpoint import geometry_problem

    path = tmp_path / "ck"
    params = _save(path)
    md = read_metadata((path / ".metadata").read_bytes())
    entry = md.state_dict_metadata[f"model.{next(iter(params))}"]
    entry.chunks.append(entry.chunks[0])
    assert "overlapping" in geometry_problem(md, params)
    chunk = entry.chunks.pop()
    entry.chunks[0] = ChunkStorageMetadata(
        offsets=chunk.offsets, sizes=torch.Size([chunk.sizes[0] - 1, *chunk.sizes[1:]])
    )
    assert "do not cover" in geometry_problem(md, params)


def test_optimizer_bytes_cannot_run_code_during_restore(tmp_path, group):
    import io
    from dataclasses import replace

    from harness.verify.checkpoint import restore

    path = tmp_path / "ck"
    _save(path)
    md = read_metadata((path / ".metadata").read_bytes())
    index = next(k for k in md.storage_data if k.fqn.startswith("optim.param_groups") and k.fqn.endswith("lr"))
    info = md.storage_data[index]

    class Exploit:
        def __reduce__(self):
            return (os.mkdir, (str(tmp_path / "executed"),))

    payload = io.BytesIO()
    torch.save(Exploit(), payload)
    shard = path / info.relative_path
    offset = shard.stat().st_size
    with shard.open("ab") as stream:
        stream.write(payload.getvalue())
    md.storage_data[index] = replace(info, offset=offset, length=len(payload.getvalue()))
    with pytest.raises(CheckpointException):  # the weights-only unpickler refused posix.mkdir
        restore(md, path, {})
    assert not (tmp_path / "executed").exists()


def test_ocb_ckpt_reports_step_files_names_and_matching_counters(tmp_path, group):
    import json

    from ocb import ckpt

    _save(tmp_path / "step_3", steps=3)
    (tmp_path / "step_3" / "meta.json").write_text(json.dumps({"step": 3, "lr": 0.001}))
    (tmp_path / "latest").write_text("step_3")
    out = ckpt.inspect(tmp_path)  # a run directory: followed through latest
    assert out.startswith(f"{tmp_path}/latest -> step_3\ncheckpoint {tmp_path}/step_3")
    assert '"step": 3' in out and ".metadata" in out and "__0_0.distcp" in out
    assert "top-level names: blocks, " in out and "step counters" in out
    assert "AdamW step counters: 3 x" in out and "all equal to step 3: the counters match" in out


def test_ocb_ckpt_names_counters_that_do_not_match_the_step(tmp_path, group):
    import json

    from ocb import ckpt

    _save(tmp_path / "step_800", steps=1)  # another step's state copied into place
    (tmp_path / "step_800" / "meta.json").write_text(json.dumps({"step": 800}))
    out = ckpt.inspect(tmp_path / "step_800")
    assert "do NOT match step 800" in out
    assert "no DCP checkpoint here" in ckpt.inspect(tmp_path / "nowhere")
