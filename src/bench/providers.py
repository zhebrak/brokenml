"""Choose the OpenRouter endpoint an open-weight model is pinned to (bench run PROVIDERS).

  uv run bench providers MODEL [--probe] [--env-file .env] [--prompt-tokens 25000] [--rounds 2]

Lists the model's endpoints from OpenRouter's public API (provider, quantization, context, uptime, price) and, with
--probe, measures each eligible one the way Terminus 2 loads it: one streamed completion on a prompt of about
--prompt-tokens tokens (the median step of a trial sends about 20k, the largest about 80k), recording time to first
token and output tokens per second. Eligible: a context window of at least MIN_CONTEXT tokens (a smaller one fails a
long trial) and uptime over the last day of at least MIN_UPTIME. The recommendation is the fastest eligible endpoint,
full precision first unless a quantized one is at least SPEEDUP_FOR_QUANT times faster; quantization is part of the
configuration's identity either way (`@provider/quant` in every row), so a pin is never silently mixed with another.
The key is read from the env file and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

from bench.paths import ROOT

API = "https://openrouter.ai/api/v1"
MIN_CONTEXT = 131_072  # Terminus 2 prompts reached 78k tokens in trials
MIN_UPTIME = 99.0  # per cent over the last day
SPEEDUP_FOR_QUANT = 2.0  # a lower precision displaces a higher one only when this much faster per call
FULL_PRECISION = {"bf16", "fp16", "fp32"}
# Precision classes, best first: full, 8-bit, 4-bit, undeclared. A vendor serving its own model is full precision
# whatever it declares (none quantize their own frontier models); any other undeclared endpoint ranks last.
PRECISION = {"bf16": 0, "fp16": 0, "fp32": 0, "fp8": 1, "int8": 1, "fp4": 2, "int4": 2, "nvfp4": 2, "mxfp4": 2}
FILLER = (
    "[rank2] step 137 loss 2.3141 lr 0.00298 step_s 0.118 tokens/s 4337 mem_mb 612 host c2 pid 4411 "
    "all_reduce bucket 25MB wait 0.004s\n"
)


def endpoints(model: str) -> list[dict]:
    """The model's endpoints as OpenRouter lists them (no key needed)."""
    with urllib.request.urlopen(f"{API}/models/{model}/endpoints", timeout=30) as resp:
        data = json.loads(resp.read()).get("data") or {}
    return [
        {
            "provider": e.get("provider_name"),
            "slug": str(e.get("provider_name") or "").lower().replace(" ", "-"),
            "quantization": e.get("quantization") or "unknown",
            "context": e.get("context_length") or 0,
            "max_out": e.get("max_completion_tokens"),
            "uptime_1d": e.get("uptime_last_1d"),
            "uptime_30m": e.get("uptime_last_30m"),
            "out_per_m": float((e.get("pricing") or {}).get("completion") or 0) * 1e6,
        }
        for e in data.get("endpoints", [])
    ]


def eligible(e: dict) -> bool:
    return e["context"] >= MIN_CONTEXT and (e["uptime_1d"] or 0) >= MIN_UPTIME


def key_from(env_file: Path) -> str:
    for line in env_file.read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY=") and line.split("=", 1)[1].strip():
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"OPENROUTER_API_KEY is not set in {env_file}")


def probe(model: str, e: dict, key: str, prompt_tokens: int, max_tokens: int = 300) -> dict:
    """One streamed completion pinned to the endpoint: time to first token, output tokens per second, total time."""
    prompt = (
        "You are debugging a distributed training job. Here is the log:\n"
        + FILLER * (prompt_tokens // 72)
        + ("\nSummarise the three most likely causes of a slow rank in two paragraphs.")
    )
    routing: dict = {"order": [e["slug"]], "allow_fallbacks": False}
    if e["quantization"] != "unknown":
        routing["quantizations"] = [e["quantization"]]
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens,
            "stream": True, "provider": routing}  # fmt: skip
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    req = urllib.request.Request(f"{API}/chat/completions", data=json.dumps(body).encode(), headers=headers)
    t0, first, usage, text = time.monotonic(), None, None, ""
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw in resp:
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                d = json.loads(line[6:])
                usage = d.get("usage") or usage
                delta = (d.get("choices") or [{}])[0].get("delta") or {}
                piece = delta.get("content") or delta.get("reasoning") or delta.get("reasoning_content")
                if piece:
                    first = first if first is not None else time.monotonic() - t0
                    text += piece
    except Exception as exc:  # noqa: BLE001 -- an endpoint that fails the probe is reported, not fatal
        return {"error": f"{type(exc).__name__}: {str(exc)[:100]}"}
    total = time.monotonic() - t0
    out = (usage or {}).get("completion_tokens") or int(len(text.split()) * 1.3)
    gen = total - (first or total)
    return {"ttft_s": round(first, 2) if first is not None else None, "total_s": round(total, 2),
            "tok_per_s": round(out / gen, 1) if gen > 0 else None,
            "prompt_tokens": (usage or {}).get("prompt_tokens")}  # fmt: skip


def precision_class(row: dict, vendor: str | None = None) -> int:
    if vendor and row["slug"] == vendor:
        return 0
    return PRECISION.get(row["quantization"], 3)


def recommend(rows: list[dict], vendor: str | None = None) -> dict | None:
    """The endpoint to pin. The model's own vendor (`vendor`, the slug before the slash) wins when its endpoint is
    eligible and answered the probe: the model as its maker serves it. Otherwise, among eligible probed endpoints, the
    fastest of the best precision class present; a lower class displaces it only when SPEEDUP_FOR_QUANT times faster
    per call (fp8 is not traded for fp4 to save a second; a 4x faster int4 endpoint is taken, and labelled). Without
    probes: the best class, then uptime."""
    ok = [r for r in rows if eligible(r) and not r.get("error")]
    if not ok:
        return None
    probed = [r for r in ok if r.get("total_s")]
    if not probed:
        return sorted(ok, key=lambda r: (precision_class(r, vendor), -(r["uptime_1d"] or 0)))[0]
    own = [r for r in probed if vendor and r["slug"] == vendor]
    if own:  # the model as its maker serves it: no third-party quantization in the row's identity
        return min(own, key=lambda r: r["total_s"])
    classes = sorted({precision_class(r, vendor) for r in probed})
    pick = min((r for r in probed if precision_class(r, vendor) == classes[0]), key=lambda r: r["total_s"])
    for lower in classes[1:]:
        candidate = min((r for r in probed if precision_class(r, vendor) == lower), key=lambda r: r["total_s"])
        if candidate["total_s"] * SPEEDUP_FOR_QUANT <= pick["total_s"]:
            pick = candidate
    return pick


def table(rows: list[dict]) -> str:
    lines = ["| Provider | Quant | Context | Uptime 1d | $/M out | Eligible | TTFT s | tok/s | Per call s |",
             "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for r in sorted(rows, key=lambda r: (not eligible(r), r.get("total_s") or 1e9, -(r["uptime_1d"] or 0))):
        lines.append(_row(r))
    return "\n".join(lines)


def _row(r: dict) -> str:
    def cell(k: str) -> str:
        return "-" if r.get(k) is None else str(r[k])

    error = f" {r['error']}" if r.get("error") else ""
    return (
        f"| {r['provider']} | {r['quantization']} | {r['context']} | {cell('uptime_1d')} | {r['out_per_m']:.2f} | "
        f"{'yes' if eligible(r) else 'no'} | {cell('ttft_s')} | {cell('tok_per_s')} | {cell('total_s')}{error} |"
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bench providers", description=(__doc__ or "").split("\n")[0])
    ap.add_argument("model", help="e.g. qwen/qwen3.8-27b (without the openrouter/ prefix)")
    ap.add_argument("--probe", action="store_true", help="measure each eligible endpoint (costs a few cents)")
    ap.add_argument("--env-file", type=Path, default=ROOT / ".env")
    ap.add_argument("--prompt-tokens", type=int, default=25_000)
    ap.add_argument("--rounds", type=int, default=2, help="probes per endpoint; the median per-call time counts")
    args = ap.parse_args(argv)
    rows = endpoints(args.model.removeprefix("openrouter/"))
    if args.probe:
        key = key_from(args.env_file) if "OPENROUTER_API_KEY" not in os.environ else os.environ["OPENROUTER_API_KEY"]
        for r in rows:
            if not eligible(r):
                continue
            results = [probe(args.model.removeprefix("openrouter/"), r, key, args.prompt_tokens)
                       for _ in range(max(1, args.rounds))]  # fmt: skip
            good = sorted((x for x in results if x.get("total_s")), key=lambda x: x["total_s"])
            r.update(good[len(good) // 2] if good else results[-1])
    print(table(rows))
    model = args.model.removeprefix("openrouter/")
    best = recommend(rows, vendor=model.split("/")[0])
    if best:
        pin = best["slug"] + (f"/{best['quantization']}" if best["quantization"] != "unknown" else "")
        print(f"\nrecommended pin: {pin}  (bench run --provider {pin}, or PROVIDERS in bench/run.py; the row is "
              f"labelled @{pin})")  # fmt: skip
    else:
        print("\nno eligible endpoint (context >= 131k and uptime >= 99% over the last day)")


if __name__ == "__main__":
    main()
