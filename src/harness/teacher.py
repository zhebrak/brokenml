"""Synthetic data source: an order-2 Markov chain where every context has exactly k successors.

Each context (a, b) has k distinct successor tokens, chosen at random from the seed, and they are
equally likely. The entropy rate is therefore exactly log(k) for every draw, so a fresh teacher
is exactly as hard to learn as the one the agent saw, while weights trained on another draw are
useless on it.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import torch


@dataclass(frozen=True)
class Teacher:
    seed: int
    vocab: int = 32
    k: int = 4
    noise: dict | None = None  # {"rate": r, "id": i}: an upstream bug writes token id i at rate r (task data spec)

    @property
    def entropy_rate(self) -> float:
        """Loss floor (nats per token) for positions with a full order-2 context."""
        return math.log(self.k)

    def table(self) -> torch.Tensor:
        """Successor ids, shape [vocab, vocab, k]."""
        g = torch.Generator().manual_seed(self.seed)
        scores = torch.rand(self.vocab * self.vocab, self.vocab, generator=g, device="cpu")
        return scores.topk(self.k, dim=1).indices.view(self.vocab, self.vocab, self.k)

    def sample(self, n: int, length: int, seed: int) -> torch.Tensor:
        """n sequences of `length` tokens, deterministic in (teacher seed, seed)."""
        table = self.table()
        g = torch.Generator().manual_seed(seed)
        out = torch.empty(n, length, dtype=torch.long, device="cpu")  # data stays on the host (GPU runs move batches)
        out[:, :2] = torch.randint(self.vocab, (n, 2), generator=g, device="cpu")
        choice = torch.randint(self.k, (n, length), generator=g, device="cpu")
        for t in range(2, length):
            out[:, t] = table[out[:, t - 2], out[:, t - 1], choice[:, t]]
        if self.noise:
            g2 = torch.Generator().manual_seed((self.seed * 1000003 + seed) % 2**62)
            hit = torch.rand(n, length, generator=g2, device="cpu") < self.noise["rate"]
            out[hit] = int(self.noise["id"])
        return out

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self)))

    @classmethod
    def load(cls, path: str | Path) -> Teacher:
        return cls(**json.loads(Path(path).read_text()))
