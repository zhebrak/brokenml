"""Memory limits the margin probe derives from task specs."""

from __future__ import annotations

import pytest

from bench.margins import _mib, node_limits


def test_limits_parse():
    assert _mib("3600m") == 3600 and _mib("9g") == 9216
    with pytest.raises(ValueError):
        _mib("3.6GB")


def test_task_limits_come_from_the_spec_or_the_platform_default():
    assert node_limits("consolidated-copy-oom") == {"c1": 3400, "c2": 3400}
    assert node_limits("degraded-node") == {"c1": 1500, "c2": 1500, "c3": 1500}


def test_probes_below_the_limit_lower_realmemory_but_never_raise_it(tmp_path):
    from bench.margins import _cap_realmemory

    conf = tmp_path / "slurm.conf"
    conf.write_text("NodeName=c[1-2] CPUs=2 RealMemory=1500 State=UNKNOWN\nNodeName=c3 CPUs=2 RealMemory=1000\n")
    _cap_realmemory(conf, 1304)
    assert conf.read_text().count("RealMemory=1304") == 1 and "RealMemory=1000" in conf.read_text()


@pytest.mark.parametrize("factor", ["0", "0.5", "1", "nan", "inf"])
def test_invalid_margin_factors_are_refused_before_launch(factor, monkeypatch):
    from bench import margins

    def unexpected(*args, **kwargs):
        raise AssertionError("invalid factors must never launch an experiment")

    monkeypatch.setattr(margins, "run_under", unexpected)
    with pytest.raises(SystemExit) as exc:
        margins.main(["activation-oom", "--factor", factor])
    assert exc.value.code == 2
