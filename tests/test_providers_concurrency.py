"""Endpoint choice and concurrency measurement: the rules on synthetic data."""

from __future__ import annotations

import json

import pytest

from bench import concurrency, providers


def endpoint(name, quant, ctx=262_144, uptime=99.9, total=None, **extra):
    row = {"provider": name, "slug": name.lower(), "quantization": quant, "context": ctx, "max_out": 1000,
           "uptime_1d": uptime, "uptime_30m": uptime, "out_per_m": 2.0}  # fmt: skip
    if total is not None:
        row.update(total_s=total, ttft_s=1.0, tok_per_s=100.0)
    return {**row, **extra}


def test_small_context_or_flaky_endpoints_are_never_eligible():
    assert not providers.eligible(endpoint("Cerebras", "fp16", ctx=65_536))
    assert not providers.eligible(endpoint("Reka", "unknown", uptime=80.2))
    assert providers.eligible(endpoint("Parasail", "fp8"))


def test_full_precision_wins_unless_a_quantized_endpoint_is_twice_as_fast():
    close = [endpoint("DeepInfra", "bf16", total=5.0), endpoint("Parasail", "fp8", total=3.0)]
    assert providers.recommend(close)["provider"] == "DeepInfra"
    far = [endpoint("DeepInfra", "bf16", total=14.0), endpoint("Parasail", "fp8", total=3.5)]
    assert providers.recommend(far)["provider"] == "Parasail"
    unprobed = [endpoint("Parasail", "fp8"), endpoint("DeepInfra", "bf16", uptime=99.5)]
    assert providers.recommend(unprobed)["provider"] == "DeepInfra"  # no probe: full precision first
    assert providers.recommend([endpoint("X", "fp8", error="timeout")]) is None
    assert "recommended" not in providers.table(far) and "| Parasail | fp8 |" in providers.table(far)


def test_precision_classes_fp8_over_fp4_unless_twice_as_fast_and_vendors_count_as_full():
    deepseek = [endpoint("Relace", "fp4", total=3.6), endpoint("DeepInfra", "fp8", total=5.2),
                endpoint("Azure", "unknown", total=4.4)]  # fmt: skip
    assert providers.recommend(deepseek, vendor="deepseek")["provider"] == "DeepInfra"  # fp4 is not 2x faster
    kimi = [endpoint("CoreWeave", "int4", total=2.0), endpoint("SiliconFlow", "fp8", total=8.4)]
    assert providers.recommend(kimi, vendor="moonshotai")["provider"] == "CoreWeave"  # 4x faster: taken, labelled
    gpt = [endpoint("Azure", "unknown", total=7.1), endpoint("OpenAI", "unknown", total=8.3)]
    assert providers.recommend(gpt, vendor="openai")["provider"] == "OpenAI"  # the vendor's own endpoint wins
    assert providers.recommend(gpt, vendor="anthropic")["provider"] == "Azure"  # no vendor present: fastest undeclared
    minimax = [endpoint("CoreWeave", "fp4", total=2.4), endpoint("Minimax", "fp8", total=5.7)]
    assert providers.recommend(minimax, vendor="minimax")["provider"] == "Minimax"  # even against a 2x faster fp4


def trial(task, n, reward=1.0, ratio=1.0, ref=0.2, job=0.2):
    return {"task": task, "reward": reward, "outcome": "pass" if reward == 1.0 else "agent", "tput_ok": reward == 1.0,
            "tput_ratio": ratio, "tput_min": 0.67, "host_busy_ref": ref, "host_busy_job": job, "level": n}  # fmt: skip


def test_safe_concurrency_is_the_largest_gapless_level_with_no_flag_flip_or_drift():
    levels = {
        1: [trial("a", 1, ratio=1.0), trial("b", 1, ratio=0.98)],
        2: [trial("a", 2, ratio=0.97), trial("b", 2, ratio=0.95)],
        3: [trial("a", 3, ratio=0.99), trial("b", 3, ratio=0.70)],  # b drifted past RATIO_DRIFT
        4: [trial("a", 4), trial("b", 4)],  # fine again, but 3 failed: not a result
    }
    out = concurrency.derive(levels)
    assert out["safe_n"] == 2 and out["levels"]["3"]["safe"] is False and out["levels"]["4"]["safe"] is True
    flagged = {1: levels[1], 2: [trial("a", 2, ref=0.1, job=0.6)]}  # a load shift the verifier would review
    assert concurrency.derive(flagged)["safe_n"] == 1
    failed = {1: levels[1], 2: [trial("a", 2, reward=0.0)]}
    assert concurrency.derive(failed)["safe_n"] == 1


def test_a_record_counts_only_for_the_host_it_was_measured_on(tmp_path, monkeypatch):
    path = tmp_path / "concurrency.json"
    current = {"images": {"runtime": "old"}, "tasks": {"a": "old"}}
    monkeypatch.setattr(concurrency, "inputs", lambda tasks: current)
    record = {"safe_n": 3, "host": concurrency.host_signature(), "tasks": list(concurrency.DEFAULT_TASKS),
              "inputs": current, "levels": {str(n): {"safe": True} for n in (1, 2, 3)}}  # fmt: skip
    path.write_text(json.dumps(record))
    assert concurrency.measured(path) == 3
    current["images"]["runtime"] = "rebuilt"
    assert concurrency.measured(path) is None
    current["images"]["runtime"] = "old"
    current["tasks"]["a"] = "edited"
    assert concurrency.measured(path) is None
    current["tasks"]["a"] = "old"
    path.write_text(json.dumps({**record, "tasks": [concurrency.DEFAULT_TASKS[0]]}))
    assert concurrency.measured(path) is None
    path.write_text(json.dumps({**record, "safe_n": "invalid"}))
    assert concurrency.measured(path) is None
    path.write_text(json.dumps({**record, "host": {"cpu": "other", "physical_cores": 64, "memory_gb": 256}}))
    assert concurrency.measured(path) is None
    assert concurrency.measured(tmp_path / "missing.json") is None


def test_missing_tasks_or_repetitions_do_not_certify_concurrency():
    levels = {1: [trial("a", 1), trial("b", 1)], 2: [trial("a", 2)]}
    assert concurrency.derive(levels)["safe_n"] == 1
    assert concurrency.derive(levels, tasks=["a", "b"], k=2)["safe_n"] == 0
    assert concurrency.derive({1: [trial("a", 1)]}, tasks=["a", "b"])["safe_n"] == 0


@pytest.mark.parametrize("key", ["tput_ratio", "host_busy_ref", "host_busy_job"])
@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True, -1, "0.2"])
def test_missing_or_invalid_measurements_do_not_certify_concurrency(key, value):
    measurement = {**trial("a", 1), key: value}
    out = concurrency.derive({1: [measurement]})
    assert out["safe_n"] == 0
    assert out["levels"]["1"]["missing_measurements"] == 1


def test_ratio_drift_is_checked_before_rounding():
    assert concurrency.derive({1: [trial("a", 1)], 2: [trial("a", 2, ratio=1.1004)]})["safe_n"] == 1
