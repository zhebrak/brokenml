"""The study dataset as the report's generators read it: results/study/trials.csv (typed) and behaviour.jsonl."""

import csv
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "results" / "study"
TRIALS = STUDY / "trials.csv"
BEHAVIOUR = STUDY / "behaviour.jsonl"

FLOATS = [
    "reward", "tput_ratio", "wall_s", "agent_s", "verifier_s", "agent_steps", "parse_errors", "tokens",
    "tokens_uncached", "probes", "web_calls", "audit_hits", "cutoff_responses", "cost_recorded", "cost_billed",
    "first_edit_s", "n_submit", "files_touched",
]  # fmt: skip
BOOLS = ["counted", "regraded", "patched_runtime", "solved"]
TRIBOOLS = ["edit_before_evidence", "used_ocb_score", "verified_after_last_edit"]


def load(path=TRIALS):
    with open(path) as f:
        lines = [line for line in f if not line.startswith("#")]
    rows = list(csv.DictReader(lines))
    for r in rows:
        for k in FLOATS:
            v = r.get(k, "")
            try:
                r[k] = float(v) if v != "" else None
            except ValueError:
                r[k] = None
        for k in BOOLS:
            r[k] = r.get(k) == "True"
        r["zeroed"] = r.get("zeroed", "") or ""
        for k in TRIBOOLS:
            r[k] = {"True": True, "False": False, "": None}.get(r.get(k, ""))
        r["cell"] = int(r["cell"])
        r["attempt"] = int(r["attempt"])
    return rows


def behaviour(path=BEHAVIOUR):
    """{(job, trial): record}; the first line of the file is the canary."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for line in fh:
            b = json.loads(line)
            if "canary" in b and "trial" not in b:
                continue
            out[(b["job"], b["trial"])] = b
    return out


MODELS = [
    "openai/gpt-6.1-sol", "anthropic/claude-sonnet-5-5", "openrouter/z-ai/glm-5.3-flash", "openai/gpt-6-luna",
    "openrouter/moonshotai/kimi-k2.7-code", "openrouter/minimax/minimax-m3", "openrouter/deepseek/deepseek-v4.1-flash",
    "openrouter/qwen/qwen3.8-27b", "openrouter/nvidia/nemotron-3-super-120b-a12b",
]  # fmt: skip
SHORT = {
    "openai/gpt-6.1-sol": "Sol", "anthropic/claude-sonnet-5-5": "Sonnet", "openrouter/z-ai/glm-5.3-flash": "GLM",
    "openai/gpt-6-luna": "Luna", "openrouter/moonshotai/kimi-k2.7-code": "Kimi",
    "openrouter/minimax/minimax-m3": "MiniMax",
    "openrouter/deepseek/deepseek-v4.1-flash": "DeepSeek", "openrouter/qwen/qwen3.8-27b": "Qwen",
    "openrouter/nvidia/nemotron-3-super-120b-a12b": "Nemotron",
}  # fmt: skip
CONDS = ["live cluster", "live logs + files", "files only"]


def reported(rows):
    return [r for r in rows if not r["not_reported"]]


def counted(rows):
    return [r for r in reported(rows) if r["counted"]]
