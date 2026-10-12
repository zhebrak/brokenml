"""Identity of the dataset the docs are generated from: the sha256 of results/study/trials.csv and the time of the
study's last graded cell (dataset.json: the local runner's last log line, "00:36 done: every Nemotron cell has a
verdict", 2026-10-09)."""

import hashlib
import json
from pathlib import Path

from common import TRIALS

HERE = Path(__file__).resolve().parent


def meta():
    h = hashlib.sha256(TRIALS.read_bytes()).hexdigest()
    m = json.loads((HERE / "dataset.json").read_text())
    return {"sha256": h, "sha_short": h[:8] + "..." + h[-5:], "final": m["final"]}
