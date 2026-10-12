"""Environment layout generated from task specs: the checkpoint store, dual-homed nodes, store-only datasets."""

from __future__ import annotations

from bench.compose import compose
from bench.spec import by_id
from harness.config import DATASETS

IMAGES = {"runtime": "r", "harness": "h", "serve": "s"}


def _both(task_id: str) -> tuple[dict, dict]:
    spec = by_id(task_id)
    return compose(spec, IMAGES, verifier=False), compose(spec, IMAGES, verifier=True)


def test_every_training_task_has_a_size_limited_checkpoint_store():
    for env in _both("degraded-node"):
        assert env["volumes"]["ckpt"]["driver_opts"]["o"] == "size=512m"
        for name in ("main", "c1", "c2"):
            assert "ckpt:/shared/ckpt" in env["services"][name]["volumes"]
    agent, _ = _both("ckpt-space-held-open")
    assert agent["volumes"]["ckpt"]["driver_opts"] == {"type": "tmpfs", "device": "tmpfs", "o": "size=40m"}
    assert "ckpt:/shared/ckpt" in agent["services"]["provision"]["volumes"]


def test_serving_tasks_have_no_checkpoint_store():
    for env in _both("engine-single-slot"):
        assert "ckpt" not in env["volumes"]


def test_dual_homed_node_puts_the_management_network_first_in_both_clusters():
    for env in _both("wrong-nic-one-node"):
        assert env["services"]["c1"]["networks"] == {"mgmt": {"interface_name": "eth0"},
                                                     "cluster": {"interface_name": "eth1"}}  # fmt: skip
        assert env["services"]["c2"]["networks"] == ["cluster"]
        assert env["networks"]["mgmt"] == {"internal": True}
        # an address below every Docker pool, so c2 (higher) always dials c1's management address in Gloo
        assert env["services"]["c1"]["environment"]["OCB_MGMT_ADDR"] == "10.20.0.11/24"
        assert "NET_ADMIN" in env["services"]["c1"]["cap_add"]
    agent, _ = _both("degraded-node")
    assert "mgmt" not in agent["networks"]


def test_store_only_dataset_is_mounted_by_the_writer_and_the_store_only():
    agent, verifier = _both("objstore-slowdown-backoff")
    mount = f"datasets:{DATASETS}"
    assert mount in agent["services"]["provision"]["volumes"] and mount in verifier["services"]["main"]["volumes"]
    for env in (agent, verifier):
        store = env["services"]["objstore"]
        assert f"{mount}:ro" in store["volumes"]
        assert store["environment"]["OBJSTORE_DATASETS"] == DATASETS
        assert store["environment"]["OBJSTORE_GET_BURST"] == "16"
        for name in ("c1", "c2"):
            assert not any(v.startswith("datasets:") for v in env["services"][name]["volumes"])
    assert not any(v.startswith("datasets:") for v in agent["services"]["main"]["volumes"])


def test_every_named_volume_a_service_mounts_is_declared_in_every_variant(tmp_path, monkeypatch):
    """A compose file that mounts an undeclared volume fails at `docker compose build` (found when the ops-only
    variant inherited the checkpoint volume's mount without the volume)."""
    import yaml

    from bench import snapshot
    from bench.render import VARIANTS, render
    from bench.spec import load_specs

    monkeypatch.setattr(snapshot, "materialise", lambda task, dest: (dest / "evidence").mkdir(parents=True))
    for spec in [s for s in load_specs() if s.split in ("test", "dev")]:
        for variant in VARIANTS:
            out = render(spec, tmp_path / variant, variant)
            for rel in ("environment/docker-compose.yaml", "tests/docker-compose.yaml"):
                f = out / rel
                if not f.exists():
                    continue
                doc = yaml.safe_load(f.read_text())
                declared = set(doc.get("volumes") or {})
                for name, svc in doc["services"].items():  # every dependency is a service of this file
                    missing = set(svc.get("depends_on") or {}) - set(doc["services"])
                    assert not missing, (spec.id, variant, rel, name, missing)
                for name, svc in doc["services"].items():
                    for v in svc.get("volumes") or []:
                        src = v.split(":", 1)[0] if isinstance(v, str) else v.get("source", "")
                        if src and not src.startswith(("/", ".")):
                            assert src in declared, f"{spec.id} {variant} {rel}: {name} mounts undeclared {src}"


def test_the_engine_never_gates_start_up_on_the_image_healthcheck(tmp_path):
    """Harbor runs `docker compose up --wait`: an inherited HEALTHCHECK on an engine that the fault (or an agent's
    unfinished fix) keeps unhealthy turns the trial into an error instead of a score."""
    import yaml

    from bench.render import render
    from bench.spec import load_specs

    for spec in [s for s in load_specs() if s.substrate == "serving"]:
        out = render(spec, tmp_path, "standard")
        for rel in ("environment/docker-compose.yaml", "tests/docker-compose.yaml"):
            engine = yaml.safe_load((out / rel).read_text())["services"]["engine"]
            assert engine.get("healthcheck") == {"disable": True}, (spec.id, rel)


def test_every_cluster_service_gets_this_projects_keys_and_waits_for_them():
    """Credentials are made per compose project; the agent's and the verifier's differ."""
    from bench.compose import KEYS_MOUNT

    for env in _both("rank0-eval-desync"):
        services = env["services"]
        assert services["keys"]["entrypoint"] == ["/usr/local/libexec/ocb-keys"] and "keys" in env["volumes"]
        for name, svc in services.items():
            if name in ("keys", "objstore"):  # the object store uses neither ssh nor munge
                assert KEYS_MOUNT not in svc.get("volumes", []), name
                continue
            assert KEYS_MOUNT in svc["volumes"], name
            assert svc["depends_on"]["keys"] == {"condition": "service_completed_successfully"}, name
    for env in _both("engine-single-slot"):  # serving runs no munged
        assert "keys" not in env["services"] and "keys" not in env["volumes"]


def test_no_image_layer_carries_a_credential():
    from pathlib import Path

    for dockerfile in Path("images").glob("*/Dockerfile"):
        text = dockerfile.read_text()
        assert "ssh-keygen" not in text and "authorized_keys" not in text.replace("authorized_keys:", ""), dockerfile
        assert "COPY" not in "".join(line for line in text.splitlines() if "munge.key" in line), dockerfile


def test_a_site_job_env_variable_is_set_on_every_node():
    """The TaskProlog also runs for the batch step on the first node, whose environment srun passes to every task: a
    variable set in one node's site job.env alone leaks to the others (found when subgroup-skip-deadlock fired no
    fault), so each must be stated on every node of the task."""
    from bench.spec import load_specs

    for spec in load_specs():
        names = {node: {line.split("=", 1)[0] for line in (setup.site_job_env or [])}
                 for node, setup in spec.hardware.node_setup.items()}  # fmt: skip
        variables = set().union(*names.values()) if names else set()
        for node in spec.nodes:
            missing = variables - names.get(node, set())
            assert not missing, f"{spec.id}: {sorted(missing)} not set in {node}'s site job.env"
