"""bench bootcheck: an environment counts only when provisioning marked it ready with the fault's symptom showing."""

from __future__ import annotations

from bench.bootcheck import verdict


def test_ready_needs_the_symptom_and_setup_failures_are_reported():
    assert verdict(True, None, {"observed": True}) == (True, "")
    assert not verdict(True, None, {"observed": False})[0]
    ok, why = verdict(False, "the fault's symptom did not show", None)
    assert not ok and why.startswith("setup failed")
    assert verdict(False, None, None) == (False, "neither READY nor SETUP_FAILED before the bootstrap timeout")


def test_probes_match_their_regex_over_the_command_output():
    from types import SimpleNamespace

    from bench.bootcheck import run_probes

    def runner(cmd, timeout=0):
        assert cmd[:4] == ["docker", "exec", "main", "bash"]
        return SimpleNamespace(stdout="latest -> ../train-wide/step_800\n", stderr="", returncode=0)

    probes = [SimpleNamespace(run="cat latest", expect=r"train-wide/step_800"),
              SimpleNamespace(run="true", expect=r"nothing here")]  # fmt: skip
    out = run_probes("main", probes, runner)
    assert [p["ok"] for p in out] == [True, False]
    assert out[0]["excerpt"].startswith("latest")
