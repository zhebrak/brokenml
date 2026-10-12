"""Evidence labels pool ops-only trials over models; pass rates pool standard trials; infra errors are left out."""

from __future__ import annotations

from bench.labels import evidence_labels, pass_rates


def _t(task, reward, variant="ablation", config="t2:sonnet", infra=False, errored=False, **extra):
    return {
        "task": task,
        "reward": reward,
        "variant": variant,
        "config": config,
        "infra": infra,
        "errored": errored,
        "digest": "d",
        "agent_steps": 10,
        **extra,
    }


def test_static_needs_pooled_ops_only_success_of_a_third():
    trials = [_t("a", 1.0), _t("a", 0.0), _t("a", 0.0, config="t2:opus"),  # 1/3: static
              _t("b", 1.0, config="t2:opus"), _t("b", 0.0), _t("b", 0.0), _t("b", 0.0),  # 1/4: runtime
              _t("c", 0.0), _t("c", 1.0, infra=True)]  # fmt: skip
    labels = evidence_labels(trials, 1 / 3)
    a = labels["a"]["evidence"]
    assert a["value"] == "static" and a["configs"] == ["t2:opus", "t2:sonnet"] and not a["provisional"]
    assert labels["b"]["evidence"]["value"] == "runtime"
    c = labels["c"]["evidence"]
    assert c["trials"] == 1 and c["value"] == "runtime" and c["provisional"] and c["ci95"][1] > 0.7


def test_pass_rates_come_from_standard_trials_only():
    trials = [_t("a", 1.0, "standard"), _t("a", 0.0, "standard", "t2:opus"), _t("a", 1.0),
              _t("b", 1.0, "standard", infra=True)]  # fmt: skip
    assert pass_rates(trials) == {"a": 0.5}


def test_only_trials_the_agent_never_had_count_as_nothing():
    trials = [_t("a", 1.0), _t("a", 0.0, errored=True, limit=True), _t("a", 0.0, errored=True, agent_steps=0),
              _t("a", 0.0, errored=True, exception="EnvironmentStartTimeoutError"),
              _t("b", 1.0), _t("b", 0.0, errored=True, exception="ContextLengthExceededError")]  # fmt: skip
    labels = evidence_labels(trials, 1 / 3)
    assert labels["a"]["evidence"]["ops_only_success"] == 1.0 and labels["a"]["evidence"]["trials"] == 1
    assert labels["b"]["evidence"]["trials"] == 2  # an agent crash is the attempt's result


def test_pass_rates_average_configurations_first():
    trials = [_t("a", 1.0, "standard"), _t("a", 1.0, "standard"), _t("a", 1.0, "standard"),
              _t("a", 0.0, "standard", "t2:opus"), _t("b", 1.0, "standard"),
              _t("b", 1.0, "standard", "t2:opus")]  # fmt: skip
    assert pass_rates(trials, {"a", "b"}) == {"a": 0.5, "b": 1.0}
