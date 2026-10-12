"""bench run pins OpenRouter models to one provider and precision, so a configuration is one serving setup."""

from __future__ import annotations

import contextlib
import json

import pytest

from bench.run import parser, provider_kwargs


def _routing(kwargs: list[str]) -> dict:
    flag, value = kwargs
    assert flag == "--ak" and value.startswith("llm_call_kwargs=")
    return json.loads(value.split("=", 1)[1])["extra_body"]["provider"]


def test_openrouter_models_are_pinned_with_fallbacks_off():
    routing = _routing(provider_kwargs("openrouter/qwen/qwen3.8-27b"))
    assert routing == {"order": ["parasail"], "allow_fallbacks": False, "quantizations": ["fp8"]}


def test_other_routes_are_left_alone_and_unknown_openrouter_models_refused():
    assert provider_kwargs("anthropic/claude-haiku-4-5") == []
    vendor = _routing(provider_kwargs("openrouter/openai/gpt-6.1-sol"))
    assert vendor == {"order": ["openai"], "allow_fallbacks": False}  # the vendor's own endpoint: no quantization
    with pytest.raises(SystemExit, match="no provider pinned"):
        provider_kwargs("openrouter/some/new-model")
    assert _routing(provider_kwargs("openrouter/some/new-model", "parasail"))["order"] == ["parasail"]


def test_agents_that_cannot_take_the_pin_are_refused():
    with pytest.raises(SystemExit, match="cannot take a provider pin"):
        provider_kwargs("openrouter/qwen/qwen3.8-27b", agent="mini-swe-agent")
    assert provider_kwargs("anthropic/claude-haiku-4-5", agent="mini-swe-agent") == []


def test_task_ids_may_follow_the_options():
    args = parser().parse_intermixed_args(["openrouter/qwen/qwen3.8-27b", "--split", "dev", "--dry-run", "dev-pending"])
    assert args.tasks == ["dev-pending"] and args.split == "dev" and args.dry_run


def test_installed_agents_need_the_net_variant_and_a_version_and_held_out_models_a_confirmation(
    tmp_path, monkeypatch, capsys
):
    from bench import run

    env = tmp_path / "x.env"
    env.write_text("OPENROUTER_API_KEY=k\n")
    with pytest.raises(SystemExit):
        run.main(["anthropic/claude-sonnet-5-5", "--agent", "claude-code", "--dry-run", "--env-file", str(env)])
    with pytest.raises(SystemExit):
        run.main(
            [
                "anthropic/claude-sonnet-5-5",
                "--agent",
                "claude-code",
                "--variant",
                "net",
                "--dry-run",
                "--env-file",
                str(env),
            ]
        )  # no --agent-version
    model = "openrouter/deepseek/deepseek-v4.1-flash"
    assert run.HELD_OUT == ()  # no model is held out in a fresh tree
    capsys.readouterr()
    with contextlib.suppress(SystemExit):
        run.main([model, "--dry-run", "--env-file", str(env)])
    assert "held-out" not in capsys.readouterr().err
    monkeypatch.setattr(run, "HELD_OUT", (model,))
    with pytest.raises(SystemExit):
        run.main([model, "--dry-run", "--env-file", str(env)])  # held out
    assert "held-out" in capsys.readouterr().err
    monkeypatch.setattr(run, "HELD_OUT", ())
    env.write_text("ANTHROPIC_API_KEY=k\nANTHROPIC_BASE_URL=https://openrouter.ai/api\n")
    assert run.routed_through(str(env)) == ["ANTHROPIC_BASE_URL"]
    with pytest.raises(SystemExit):
        run.main(["anthropic/claude-sonnet-5-5", "--dry-run", "--env-file", str(env)])
    assert run.lite_tasks() and all("-" in t for t in run.lite_tasks())


def test_concurrency_above_the_measured_value_is_refused(tmp_path, monkeypatch):
    from bench import concurrency, run

    env = tmp_path / "x.env"
    env.write_text("OPENROUTER_API_KEY=k\n")
    monkeypatch.setattr(concurrency, "measured", lambda: None)
    with pytest.raises(SystemExit):
        run.main(["openrouter/qwen/qwen3.8-27b", "-n", "2", "--dry-run", "--env-file", str(env), "--split", "dev"])
    monkeypatch.setattr(concurrency, "measured", lambda: 2)
    run.main(["openrouter/qwen/qwen3.8-27b", "-n", "2", "--dry-run", "--env-file", str(env), "--split", "dev",
              "dev-pending"])  # fmt: skip
    with pytest.raises(SystemExit):
        run.main(["openrouter/qwen/qwen3.8-27b", "-n", "3", "--dry-run", "--env-file", str(env), "--split", "dev"])
    monkeypatch.setattr(concurrency, "measured", lambda: 0)
    with pytest.raises(SystemExit):
        run.main(["openrouter/qwen/qwen3.8-27b", "-n", "1", "--dry-run", "--env-file", str(env), "--split", "dev"])


def test_route_detection_uses_dotenv_syntax_inheritance_aliases_and_precedence(tmp_path, monkeypatch):
    from bench.run import effective_environment, routed_through

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://inherited.example")  # Harbor's agent inherits our environment
    (tmp_path / ".env.local").write_text('export OPENAI_API_BASE = "https://local.example"\n')  # Harbor reads it too
    env = tmp_path / "keys.env"
    env.write_text('ANTHROPIC_BASE_URL = ""\nexport GEMINI_BASE_URL = "${OPENAI_API_BASE}/gemini"\n')
    assert routed_through("keys.env") == ["GEMINI_BASE_URL", "OPENAI_API_BASE"]  # the file's empty value wins
    assert effective_environment(str(env))["GEMINI_BASE_URL"] == "https://local.example/gemini"
    import os

    assert os.environ["ANTHROPIC_BASE_URL"] == "https://inherited.example"  # caller state is restored
    with pytest.raises(ValueError, match="does not exist"):
        routed_through("absent.env")


def test_default_reasoning_sends_no_effort_parameter_and_an_explicit_level_is_passed(tmp_path, capsys, monkeypatch):
    from bench import run

    monkeypatch.chdir(tmp_path)
    env = tmp_path / "keys.env"
    env.write_text("OPENROUTER_API_KEY=k\n")
    run.main(["openrouter/qwen/qwen3.8-27b", "--split", "dev", "--dry-run", "--reasoning-effort", "default",
              "--name", "t-default", "--env-file", str(env), "dev-pending"])  # fmt: skip
    assert "reasoning_effort=" not in capsys.readouterr().out
    run.main(["openrouter/qwen/qwen3.8-27b", "--split", "dev", "--dry-run", "--reasoning-effort", "medium",
              "--name", "t-medium", "--env-file", str(env), "dev-pending"])  # fmt: skip
    assert "reasoning_effort=medium" in capsys.readouterr().out


def test_build_directories_carry_nothing_of_the_task_id():
    from bench.leak_audit import ID_PROBE
    from bench.run import opaque_name

    a, b = opaque_name("job-1", "scratch-is-tmpfs"), opaque_name("job-1", "stale-hosts-entry")
    assert a != b and a == opaque_name("job-1", "scratch-is-tmpfs") and a != opaque_name("job-2", "scratch-is-tmpfs")
    assert a.startswith("t-") and len(a) == 12 and "scratch" not in a and "tmpfs" not in a
    assert "scratch-is-tmpfs" in ID_PROBE.format(taskid="scratch-is-tmpfs")  # the audit greps the id


def test_oracle_needs_no_env_file(tmp_path, monkeypatch):
    """The oracle and nop agents call no model, so a missing .env is not an error and no --env-file is passed on."""
    from bench import run as run_mod

    monkeypatch.chdir(tmp_path)
    assert "oracle" in run_mod.KEYLESS_AGENTS and "nop" in run_mod.KEYLESS_AGENTS
    assert not (tmp_path / ".env").exists()
