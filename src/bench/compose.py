"""Docker Compose files for a task's two clusters: the agent's (with the provisioning sidecar) and the verifier's.

Both are built from the same spec, so hardware faults (CPU and memory limits, the emulated link, object-store
bandwidth) are mirrored by construction.
"""

from __future__ import annotations

import copy
import hashlib
import ipaddress
from typing import Any

from bench import gpu
from bench.provenance import source_hash
from bench.spec import TaskSpec
from harness.config import DATASETS

PROVISION_SERVICE = {
    "build": {"context": ".", "dockerfile": "Dockerfile.provision"},
    "hostname": "provision",
    "command": ["provision"],
    "volumes": ["ops:/ops", "shared:/shared"],
}


def provision_service() -> dict:
    """The sidecar, told which image sources the task is rendered against: a sidecar from an image rebuilt since
    refuses to provision (harness.imagelock), so a `make image` during a run cannot change what a trial runs on."""
    service = copy.deepcopy(PROVISION_SERVICE)
    service["environment"] = {"OCB_EXPECT_HARNESS": source_hash("harness"),
                              "OCB_EXPECT_RUNTIME": source_hash("runtime")}  # fmt: skip
    return service


# Per-project cluster credentials: the one-shot keys service writes a fresh root ssh keypair and
# munge key into this project's `keys` volume; every service that runs munged or ssh mounts it read-only and starts
# only once it has finished (images/runtime/keys.sh, entrypoint.sh). The agent's and the verifier's clusters are
# separate compose projects, so they never share a key.
KEYS_MOUNT = "keys:/run/cluster-keys:ro"
KEYS_READY = {"keys": {"condition": "service_completed_successfully"}}


def keys_service(image: str) -> dict:
    return {"image": image, "pull_policy": "never", "entrypoint": ["/usr/local/libexec/ocb-keys"],
            "volumes": ["keys:/run/cluster-keys"], "network_mode": "none", "restart": "no"}  # fmt: skip


# The net variants' route out lives in RFC 2544's benchmarking range: no cloud VPC default (AWS uses 172.31.0.0/16,
# which collided on the first run host) and no Docker address pool (172.17-31, 192.168) uses it. tools/egress_guard.sh
# fences the whole range on the host. Each task gets its own /28 inside it (egress_subnet), because Docker allows one
# network per subnet at a time and the run hosts keep several trials up at once.
EGRESS_RANGE = "198.18.0.0/15"


def egress_subnet(task_id: str) -> str:
    """The task's egress network: a /28 (16 addresses, two are used) at a slot chosen by the task id, so the rendered
    compose file and its digest are the same in every job, and concurrent tasks almost never share a slot (8192 slots;
    a collision is a loud compose error, not a wrong verdict)."""
    net = ipaddress.ip_network(EGRESS_RANGE)
    slot = int(hashlib.sha256(task_id.encode()).hexdigest(), 16) % (net.num_addresses // 16)
    return str(ipaddress.ip_network((int(net.network_address) + slot * 16, 28)))


def node_setup_env(setup) -> dict[str, str]:
    """A node's site state as the environment hwsetup reads at first start (cleared before any daemon starts)."""
    env: dict[str, str] = {}
    if setup.stale_host:
        env["OCB_STALE_HOST"] = setup.stale_host
    if setup.loopback_self:
        env["OCB_LOOPBACK_SELF"] = "1"
    if setup.metrics_port:
        env["OCB_METRICS_PORT"] = str(setup.metrics_port)
    if setup.site_job_env:  # printf %b expands the \n separators
        env["OCB_SITE_JOB_ENV"] = "".join(f"{line}\\n" for line in setup.site_job_env)
    if setup.nccl_conf:
        env["OCB_NCCL_CONF"] = "".join(f"{line}\\n" for line in setup.nccl_conf)
    return env


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _node(name: str, image: str, network: str | None, ptrace: bool) -> dict:
    svc: dict[str, Any] = {
        "image": image,
        "pull_policy": "never",
        "hostname": name,
        "command": ["slurmd"],
        "volumes": ["ops:/ops:ro", "shared:/shared"],
        "cpus": 2,
        "mem_limit": "1500m",
        "memswap_limit": "1500m",
        # Two torch ranks with their Gloo and OpenMP threads, slurmd and a step's shells use under 60 pids (measured
        # 16-18 per node during a job); the limit stops job code from exhausting the shared host's process table.
        "pids_limit": 512,
    }
    if ptrace:
        svc["cap_add"] = ["SYS_PTRACE"]
    if network:
        svc["networks"] = [network]
    return svc


def _document(spec: TaskSpec, services: dict, net: str, egress: bool) -> dict:
    doc: dict[str, Any] = {
        "services": deep_merge(services, spec.hardware.services),
        "volumes": {
            "ops": {},
            "shared": {},
            **({"datasets": {}} if spec.data and spec.data.shards else {}),
            **({"keys": {}} if "keys" in services else {}),
        },
        "networks": {net: {"internal": True}, **({"mgmt": {"internal": True}} if spec.hardware.mgmt_nodes else {})},
    }
    if spec.substrate != "serving":  # a memory-backed filesystem, so its capacity is a hard limit (ENOSPC)
        opts = {"type": "tmpfs", "device": "tmpfs", "o": f"size={spec.hardware.ckpt_volume_mb}m"}
        doc["volumes"]["ckpt"] = {"driver": "local", "driver_opts": opts}
    if egress:  # the workstation alone gets a route out (net variant); the cluster stays internal
        doc["services"]["main"]["networks"] = [*doc["services"]["main"]["networks"], "egress"]
        # a pinned subnet, so the host's DOCKER-USER rules (tools/egress_guard.sh) can keep it off the host, the LAN and
        # a cloud metadata service; everything else (the model API, install hosts) stays reachable
        doc["networks"]["egress"] = {"ipam": {"config": [{"subnet": egress_subnet(spec.id)}]}}
    return doc


def serving(spec: TaskSpec, images: dict[str, str], verifier: bool, egress: bool) -> dict:
    net = "cluster"
    engine: dict[str, Any] = {
        "image": images["serve"],
        "pull_policy": "never",
        "hostname": "engine",
        "volumes": ["ops:/ops:ro", "shared:/shared"],
        "cpus": 2,
        "mem_limit": "1500m",
        "memswap_limit": "1500m",
        # The llama.cpp base image's HEALTHCHECK (curl /health) must not gate start-up: Harbor brings environments up
        # with --wait, so an engine that a broken or slow config keeps unhealthy turned the trial into an error
        # instead of a score. Readiness is the supervisor's and the verifier's to judge (STARTUP_TIMEOUT_S, ready_s).
        "healthcheck": {"disable": True},
    }
    if spec.hardware.model_fetch_s:  # the emulated slow model store (images/serve/supervisor.sh)
        engine["environment"] = {"OCB_MODEL_FETCH_S": str(spec.hardware.model_fetch_s)}
    services: dict[str, Any] = {"main": {"volumes": ["ops:/ops", "shared:/shared"]}, "engine": engine}
    if not verifier:
        services["provision"] = provision_service()
    if net:
        if "provision" in services:
            services["provision"]["networks"] = [net]
        services["main"]["networks"] = [net]
        engine["networks"] = [net]
    return _document(spec, services, net, egress)


def training(spec: TaskSpec, images: dict[str, str], verifier: bool, egress: bool) -> dict:
    net = "cluster"
    services: dict[str, Any] = {
        "main": {"volumes": ["ops:/ops", "shared:/shared"]},
        "slurmctld": {
            "image": images["runtime"],
            "pull_policy": "never",
            "hostname": "slurmctld",
            "command": ["slurmctld"],
            "volumes": ["shared:/shared"],
            "cpus": 0.5,
            "mem_limit": "512m",
        },
    }
    if not verifier:
        services["main"]["cap_add"] = ["SYS_PTRACE"]
        services["provision"] = provision_service()
    for name in spec.nodes:
        services[name] = _node(name, images["runtime"], net, ptrace=True)  # root reads ranks' /proc (verifier)
    if net:
        services["main"]["networks"] = [net]
        services["slurmctld"]["networks"] = [net]
        if "provision" in services:
            services["provision"]["networks"] = [net]
    store: dict[str, Any] = {
        "image": images["harness"],
        "pull_policy": "never",
        "hostname": "objstore",
        "command": ["objstore"],
        "volumes": ["shared:/shared:ro"],
        "cpus": 0.5,
        "mem_limit": "256m",
    }
    if spec.hardware.objstore:  # bandwidth (bytes/s) and dataset request rate, for every client or one host
        store["environment"] = {f"OBJSTORE_{k.upper()}": str(v) for k, v in spec.hardware.objstore.items()}
    if spec.data and spec.data.shards:  # the dataset lives only in the store's volume (harness.corpus.DATASETS)
        store["volumes"] = [*store["volumes"], f"datasets:{DATASETS}:ro"]
        store.setdefault("environment", {})["OBJSTORE_DATASETS"] = str(DATASETS)
        writer = "main" if verifier else "provision"
        services[writer]["volumes"] = [*services[writer]["volumes"], f"datasets:{DATASETS}"]
    if net:
        store["networks"] = [net]
    services["objstore"] = store
    for name, svc in services.items():  # munged (and the nodes' sshd) need this project's keys; the store uses neither
        if name == "objstore":
            continue
        svc["volumes"] = [*svc["volumes"], KEYS_MOUNT]
        svc["depends_on"] = {**svc.get("depends_on", {}), **KEYS_READY}
    services["keys"] = keys_service(images["runtime"])
    for i, name in enumerate(spec.hardware.mgmt_nodes):  # dual-homed: management network first (eth0), cluster second
        services[name]["networks"] = {"mgmt": {"interface_name": "eth0"}, net: {"interface_name": "eth1"}}
        services[name].setdefault("environment", {}).update({
            "OCB_HOSTNAME_IFACE": "eth0",  # its name -> management address
            # The site numbers its management network below the cluster's range (Docker's pools are 172.17+ and
            # 192.168+). Gloo lets the higher address of a pair dial (Device::isInitiator), unbound; a Docker-chosen
            # management subnet above the cluster's let c1 dial out over eth1, and the fault vanished by luck.
            "OCB_MGMT_ADDR": f"10.20.0.{11 + i}/24",
        })  # fmt: skip
        services[name]["cap_add"] = sorted(set(services[name].get("cap_add", [])) | {"NET_ADMIN"})  # setup only
    for name, setup in spec.hardware.node_setup.items():  # site state at first start (images/runtime/hwsetup.sh)
        services[name].setdefault("environment", {}).update(node_setup_env(setup))
    for name in spec.nodes:  # a node from an image rebuilt since the render refuses to join (hwsetup.sh)
        services[name].setdefault("environment", {})["OCB_EXPECT_RUNTIME"] = source_hash("runtime")
    for name in ("main", "provision", *spec.nodes):  # the checkpoint volume: its own size-limited filesystem
        if name in services:
            services[name]["volumes"] = [*services[name]["volumes"], "ckpt:/shared/ckpt"]
    link = spec.hardware.network  # emulated inter-node link: netem on every node, applied by the node's hwsetup
    if link:
        env = {k: str(v) for k, v in (("OCB_NET_DELAY_MS", link.delay_ms), ("OCB_NET_RATE_MBIT", link.rate_mbit)) if v}
        for name in spec.nodes:
            services[name].setdefault("environment", {}).update(env)
            services[name]["cap_add"] = sorted(set(services[name].get("cap_add", [])) | {"NET_ADMIN"})
    return _document(spec, services, net, egress)


GPU_NODE = {  # the GPU node's limits: CUDA contexts and DCP staging need host memory, NCCL and loaders need shm
    "cpus": 8,
    "mem_limit": "32g",
    "memswap_limit": "32g",
    "shm_size": "8g",
    "ulimits": {"core": 0},  # the NCCL watchdog aborts with SIGABRT: no core files on /shared
}


def gpu_training(
    spec: TaskSpec, images: dict[str, str], verifier: bool, egress: bool, slot: int = 0, host: gpu.Host | None = None
) -> dict:
    """The training cluster with one GPU node, g1, which alone reserves GPUs (its slot's, by UUID) and runs the
    CUDA image. Every other service runs with runc, so no GPU is visible outside g1 even on a host whose default
    runtime is nvidia (the images also set NVIDIA_VISIBLE_DEVICES=void)."""
    host = host or gpu.DEFAULT
    s = host.slots[slot]
    doc = training(spec, images, verifier, egress)
    node = {**doc["services"]["g1"], **copy.deepcopy(GPU_NODE), "image": images["runtime-cuda"]}
    node["deploy"] = {"resources": {"reservations": {"devices": [
        {"driver": "nvidia", "device_ids": list(s.uuids), "capabilities": ["gpu"]}]}}}  # fmt: skip
    if s.cpuset:  # the slot's own CPUs on its GPUs' NUMA node; `cpus` keeps the quota the same on every host
        node["cpuset"] = s.cpuset
    node.setdefault("environment", {})["OCB_GPU_BUDGET_GB"] = str(host.mem_budget_gb)
    doc["services"]["g1"] = deep_merge(node, spec.hardware.services.get("g1", {}))
    for name, svc in doc["services"].items():
        if name != "g1":
            svc["runtime"] = "runc"
    doc["volumes"]["ckpt"] = {}  # GPU checkpoints are large: a disk volume, not the tmpfs store
    return doc


def compose(
    spec: TaskSpec,
    images: dict[str, str],
    verifier: bool,
    egress: bool = False,
    slot: int = 0,
    host: gpu.Host | None = None,
) -> dict:
    """Every service sits on one internal network: no route to the internet. `egress` (net variant) gives the
    agent's workstation, and only it, a second network with a route out."""
    if spec.substrate == "gpu":
        return gpu_training(spec, images, verifier, egress and not verifier, slot, host)
    build = serving if spec.substrate == "serving" else training
    return build(spec, images, verifier, egress and not verifier)
