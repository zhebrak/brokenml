"""GPU host slots from nvidia-smi output (no GPU needed)."""

from __future__ import annotations

import pytest

from bench.gpu import DEFAULT, parse_host

GPUS = """0, GPU-aaa, NVIDIA A100-SXM4-80GB
1, GPU-bbb, NVIDIA A100-SXM4-80GB
2, GPU-ccc, NVIDIA A100-SXM4-80GB
3, GPU-ddd, NVIDIA A100-SXM4-80GB"""

TOPO_NVLINK = """\tGPU0\tGPU1\tGPU2\tGPU3\tNIC0\tCPU Affinity\tNUMA Affinity\tGPU NUMA ID
GPU0\t X \tNV12\tNV12\tNV12\tSYS\t0-31\t0\t\tN/A
GPU1\tNV12\t X \tNV12\tNV12\tSYS\t0-31\t0\t\tN/A
GPU2\tNV12\tNV12\t X \tNV12\tSYS\t32-63\t1\t\tN/A
GPU3\tNV12\tNV12\tNV12\t X \tSYS\t32-63\t1\t\tN/A
NIC0\tSYS\tSYS\tSYS\tSYS\t X
"""


def test_nvlink_pairs_become_slots_with_their_numa_cpus():
    host = parse_host(GPUS, TOPO_NVLINK, "580.65.06")
    assert host.gpu_class == "NVIDIA A100-SXM4-80GB/NV12/r580"
    assert [s.uuids for s in host.slots] == [["GPU-aaa", "GPU-bbb"], ["GPU-ccc", "GPU-ddd"]]
    assert [s.cpuset for s in host.slots] == ["0,1,2,3,4,5,6,7", "32,33,34,35,36,37,38,39"]


def test_pairs_across_sockets_are_not_slots():
    topo = TOPO_NVLINK.replace("GPU0\t X \tNV12", "GPU0\t X \tSYS").replace(
        "GPU2\tNV12\tNV12\t X \tNV12", "GPU2\tNV12\tNV12\t X \tPIX"
    )
    host = parse_host(GPUS, topo, "580.1")
    assert [s.uuids for s in host.slots] == [["GPU-ccc", "GPU-ddd"]] and host.gpu_class.endswith("/PIX/r580")


def test_mixed_models_are_refused():
    with pytest.raises(ValueError, match="mixed"):
        parse_host(GPUS.replace("3, GPU-ddd, NVIDIA A100-SXM4-80GB", "3, GPU-ddd, NVIDIA H100"), TOPO_NVLINK, "580")


def test_without_a_host_file_tasks_render_for_gpus_0_and_1():
    assert DEFAULT.slots[0].uuids == ["0", "1"] and DEFAULT.gpu_class == "unknown"


def test_slots_on_one_numa_node_get_disjoint_cpus():
    topo = TOPO_NVLINK.replace("\t32-63\t1", "\t0-31\t0")  # all four GPUs on NUMA node 0
    host = parse_host(GPUS, topo, "580")
    a, b = (set(map(int, s.cpuset.split(","))) for s in host.slots)
    assert len(a) == len(b) == 8 and not a & b


def test_no_cpu_affinity_means_no_cpuset():
    topo = TOPO_NVLINK.replace("\t0-31\t0", "\tN/A\t0").replace("\t32-63\t1", "\tN/A\t1")
    assert [s.cpuset for s in parse_host(GPUS, topo, "580").slots] == [None, None]
