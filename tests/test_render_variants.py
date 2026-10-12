"""Variants render to their own namespace, and differ from the standard task only where they should."""

from __future__ import annotations

import tomllib

import pytest
import yaml

from bench.render import CHEAT_PREFIX, HINTED_NOTE, render
from bench.spec import by_id


@pytest.fixture(params=["rank0-eval-desync", "engine-single-slot"])
def spec(request):
    return by_id(request.param)


def _toml(task):
    return tomllib.loads((task / "task.toml").read_text())


def _compose(task, side="environment"):
    return yaml.safe_load((task / side / "docker-compose.yaml").read_text())


def test_namespaces_and_metadata(spec, tmp_path):
    for variant, name in (("standard", "brokenml"), ("net", "brokenml-net"), ("ablation", "brokenml-ablation"),
                          ("cheat", "brokenml-cheat"), ("hinted", "brokenml-hinted"),
                          ("cheat-net", "brokenml-cheat-net"), ("logs", "brokenml-logs")):  # fmt: skip
        task = render(spec, tmp_path / variant, variant)
        meta = _toml(task)
        assert meta["task"]["name"] == f"{name}/{spec.id}"
        assert meta["metadata"].get("variant", "standard") == variant


def test_net_variant_gives_egress_to_the_workstation_only(spec, tmp_path):
    doc = _compose(render(spec, tmp_path, "net"))
    import ipaddress

    from bench.compose import EGRESS_RANGE, egress_subnet

    egress = {"ipam": {"config": [{"subnet": egress_subnet(spec.id)}]}}
    assert doc["networks"] == {"cluster": {"internal": True}, "egress": egress}
    subnet = ipaddress.ip_network(egress_subnet(spec.id))
    assert subnet.prefixlen == 28 and subnet.subnet_of(ipaddress.ip_network(EGRESS_RANGE))
    assert egress_subnet(spec.id) == egress_subnet(spec.id) and egress_subnet("a") != egress_subnet("b")
    with_egress = [n for n, svc in doc["services"].items() if "egress" in svc.get("networks", [])]
    assert with_egress == ["main"]
    assert "egress" not in _compose(render(spec, tmp_path / "s", "net"), "tests").get("networks", {})


def test_ablation_is_the_workstation_alone(spec, tmp_path):
    task = render(spec, tmp_path, "ablation")
    assert list(_compose(task)["services"]) == ["main"]
    assert not (task / "environment" / "Dockerfile.provision").exists()
    assert "COPY ops/ /opt/ops-seed/" in (task / "environment" / "Dockerfile").read_text()
    assert "healthcheck" not in _toml(task)["environment"]
    assert "report.md" not in (task / "instruction.md").read_text()


def test_cheat_variant_only_prefixes_the_instruction(spec, tmp_path):
    std = (render(spec, tmp_path / "s") / "instruction.md").read_text()
    cheat = (render(spec, tmp_path / "c", "cheat") / "instruction.md").read_text()
    head, _, body = std.partition("\n")
    assert cheat == head + "\n" + CHEAT_PREFIX + body


def test_hinted_variant_adds_the_declared_mechanism_before_the_time_budget(spec, tmp_path):
    std = (render(spec, tmp_path / "s") / "instruction.md").read_text()
    hinted = (render(spec, tmp_path / "h", "hinted") / "instruction.md").read_text()
    mechanism = spec.metadata.mechanism.strip()
    assert mechanism in hinted and mechanism not in std
    note = HINTED_NOTE.format(mechanism=mechanism)
    assert hinted == std.replace("\nYou have ", note + "\nYou have ", 1)  # the only difference is the note


def test_verifier_is_identical_across_variants(spec, tmp_path):
    std = render(spec, tmp_path / "s") / "tests"
    for variant in ("net", "ablation", "cheat", "cheat-net", "logs"):
        other = render(spec, tmp_path / variant, variant) / "tests"
        for f in std.rglob("*"):
            if f.is_file():
                assert f.read_bytes() == (other / f.relative_to(std)).read_bytes(), (variant, f)


def test_cheat_net_is_the_cheat_instruction_in_the_net_environment(spec, tmp_path):
    cheat = render(spec, tmp_path / "c", "cheat")
    net = render(spec, tmp_path / "n", "net")
    both = render(spec, tmp_path / "cn", "cheat-net")
    assert (both / "instruction.md").read_text() == (cheat / "instruction.md").read_text()
    assert _compose(both) == _compose(net)
    assert _compose(both) != _compose(cheat)


def test_logs_workstation_has_no_path_to_the_cluster_and_reads_only(spec, tmp_path):
    """Live read-only access by construction: the workstation has no network at all and holds none of the cluster's
    keys; every volume it shares with the cluster is read-only; its /ops is its own."""
    std = _compose(render(spec, tmp_path / "s"))
    doc = _compose(render(spec, tmp_path / "l", "logs"))
    main = doc["services"]["main"]
    assert main["network_mode"] == "none" and "networks" not in main  # no bridge, so no gateway to the host either
    assert set(doc["networks"]) == set(std["networks"])
    assert "cap_add" not in main and not any(v.startswith("keys:") for v in main["volumes"])
    shared_with_cluster = {v.split(":")[0] for n, svc in doc["services"].items() if n != "main"
                           for v in svc.get("volumes", [])}  # fmt: skip
    for volume in main["volumes"]:
        name, _, *mode = volume.split(":")
        assert name not in shared_with_cluster or mode == ["ro"], volume
    assert "workspace:/ops" in main["volumes"] and "ops" not in {v.split(":")[0] for v in main["volumes"]}
    # the cluster itself is the standard one, plus the observer
    assert {n: svc for n, svc in doc["services"].items() if n not in ("main", "obs")} == {
        n: svc for n, svc in std["services"].items() if n != "main"
    }
    obs = doc["services"]["obs"]
    assert obs["networks"] == ["cluster"] and "ports" not in obs and "obs:/obs" in obs["volumes"]
    assert "shared:/shared:ro" in obs["volumes"]


def test_logs_instruction_states_the_access_and_keeps_the_task(spec, tmp_path):
    std = (render(spec, tmp_path / "s") / "instruction.md").read_text()
    logs = (render(spec, tmp_path / "l", "logs") / "instruction.md").read_text()
    assert "read-only access to" in logs and "never reads" in logs and "not available here" in logs
    assert "/obs" in logs and "live changes" not in logs
    spec_sentence = std.splitlines()[1].split(". ", 1)[1]
    assert spec_sentence in logs  # the job's spec is unchanged
    assert logs.split("Stay within")[1] == std.split("Stay within")[1]


def test_logs_environment_carries_its_own_programs(spec, tmp_path):
    task = render(spec, tmp_path, "logs")
    env = task / "environment"
    dockerfile = (env / "Dockerfile").read_text()
    assert "COPY ops/ /opt/ops-seed/" in dockerfile and "/usr/local/sbin/$c" in dockerfile
    assert "rm -f /usr/local/libexec/ocb-hwsetup.sh" in dockerfile
    assert (env / "readonly" / "tools.py").is_file() and (env / "obs" / "collect.py").is_file()
    assert "obs-collect" in (env / "Dockerfile.obs").read_text()
    health = _toml(task)["environment"]["healthcheck"]["command"]
    assert "/shared/evidence/READY" in health and "/obs/SNAPSHOT_AT" in health
