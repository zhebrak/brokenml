"""The platform's model definition (a small pre-LN GPT) and how an exported model is scored.

Exports are always loaded into this class, strictly, by `ocb score` and by the evaluation service, so a job's own
code cannot change the architecture that gets scored.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
import torch.nn.functional as F
from torch import nn


@dataclass(frozen=True)
class GPTConfig:
    vocab: int = 32
    ctx: int = 64
    d_model: int = 128
    n_layer: int = 2
    n_head: int = 4

    def to_dict(self) -> dict:
        return asdict(self)


class Block(nn.Module):
    def __init__(self, cfg: GPTConfig):
        super().__init__()
        self.n_head = cfg.n_head
        self.ln1 = nn.LayerNorm(cfg.d_model)
        self.qkv = nn.Linear(cfg.d_model, 3 * cfg.d_model)
        self.proj = nn.Linear(cfg.d_model, cfg.d_model)
        self.ln2 = nn.LayerNorm(cfg.d_model)
        self.fc = nn.Linear(cfg.d_model, 4 * cfg.d_model)
        self.out = nn.Linear(4 * cfg.d_model, cfg.d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, t, d = x.shape
        q, k, v = self.qkv(self.ln1(x)).view(b, t, 3, self.n_head, d // self.n_head).unbind(2)
        att = F.scaled_dot_product_attention(q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2), is_causal=True)
        x = x + self.proj(att.transpose(1, 2).reshape(b, t, d))
        return x + self.out(F.gelu(self.fc(self.ln2(x))))


class GPT(nn.Module):
    def __init__(self, cfg: GPTConfig):
        super().__init__()
        self.cfg = cfg
        self.tok_emb = nn.Embedding(cfg.vocab, cfg.d_model)
        self.pos_emb = nn.Embedding(cfg.ctx, cfg.d_model)
        self.blocks = nn.ModuleList(Block(cfg) for _ in range(cfg.n_layer))
        self.ln_f = nn.LayerNorm(cfg.d_model)
        self.head = nn.Linear(cfg.d_model, cfg.vocab, bias=False)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        """Logits [batch, time, vocab]; position t predicts token t + 1."""
        pos = torch.arange(tokens.shape[1], device=tokens.device)
        x = self.tok_emb(tokens) + self.pos_emb(pos)
        for block in self.blocks:
            x = block(x)
        return self.head(self.ln_f(x))


CHUNK_TOKENS = 8192  # tokens per forward pass: a pass's activations are tokens x 4 d_model floats, whatever the context


def heldout_loss(model: GPT, tokens: torch.Tensor, start: int = 2, chunk_tokens: int = CHUNK_TOKENS) -> float:
    """Next-token cross-entropy on targets at positions >= start (full order-2 context), summed over passes of at most
    `chunk_tokens` tokens. Passes are sized by tokens, not sequences: 256 sequences of a 512-token context at once took
    2 GB and were OOM-killed in the verifier's 2 GB container on a host without swap (2026-10-03)."""
    lo, total, count = start - 1, 0.0, 0
    chunk = max(1, chunk_tokens // tokens.shape[1])
    with torch.no_grad():
        for i in range(0, len(tokens), chunk):
            part = tokens[i : i + chunk]
            logits = model(part[:, :-1])[:, lo:]
            targets = part[:, 1:][:, lo:]
            total += F.cross_entropy(logits.reshape(-1, logits.shape[-1]), targets.reshape(-1), reduction="sum").item()
            count += targets.numel()
    return total / count


HELDOUT_TOKENS = 131_072  # 2048 sequences of the base job's 64 tokens
EVAL_FLOPS = 2e12  # cap for larger models (about a minute single-threaded)


class ExportError(ValueError):
    """An export that does not load into the platform model."""


def load_export(weights: str, cfg: GPTConfig) -> GPT:
    """The exported safetensors weights (no pickle), loaded strictly into the platform model."""
    from safetensors.torch import load_file

    model = GPT(cfg)
    try:
        model.load_state_dict(load_file(weights), strict=True)
    except Exception as exc:  # whatever fails to load is the export's fault, reported as such
        raise ExportError(f"{type(exc).__name__}: {str(exc)[:500]}") from exc
    return model.eval()


def heldout_count(cfg: GPTConfig, model: GPT) -> int:
    """How many held-out sequences to score: about HELDOUT_TOKENS, fewer for large models (EVAL_FLOPS), at least 128."""
    n_params = sum(p.numel() for p in model.parameters())
    return max(128, min(HELDOUT_TOKENS, int(EVAL_FLOPS / (2 * n_params))) // cfg.ctx)


def well_formed(tokens: torch.Tensor, vocab: int) -> torch.Tensor:
    """Sequences whose every token is in the vocabulary (held-out loss is defined over those)."""
    return tokens[((tokens >= 0) & (tokens < vocab)).all(dim=1)]
