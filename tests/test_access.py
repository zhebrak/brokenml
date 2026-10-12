"""The access classifier (bench.access): one set of rules for what each arm's commands needed."""

from __future__ import annotations

import pytest

from bench.access import classify, refusals


@pytest.mark.parametrize(
    ("command", "kinds"),
    [
        ("ocb submit train", {"test-loop"}),
        ("cd /ops && sbatch jobs/train/launch.sbatch", {"test-loop"}),
        ("srun -N1 hostname", {"test-loop"}),
        ("bash /ops/jobs/train/submit.sh", {"test-loop"}),
        ("python3 -m ocb.serving http://engine:8080 --save /tmp/a.json", {"test-loop"}),
        ('curl -s -X POST -d \'{"prompt": "hi"}\' http://engine:8080/completion', {"test-loop"}),
        ("scancel 12", {"live-write"}),
        ("scontrol update NodeName=c2 State=RESUME", {"live-write"}),
        ("scontrol -o show job 12", {"read"}),
        ("ocb cluster apply", {"live-write"}),
        ("pkill -f train.py", {"live-write"}),
        ("touch /shared/engine/restart", {"live-write"}),
        ("ssh c1 'pkill -f train'", {"live-write", "node-shell"}),
        ("ssh c2 \"sed -i 's/16/1/' /etc/platform/job.env\"", {"live-write", "node-shell"}),
        ("ssh root@c1 tc qdisc show dev eth0", {"node-shell"}),
        ("ssh -o BatchMode=yes c1 cat /sys/fs/cgroup/memory.events", {"node-shell"}),
        ("for n in c1 c2; do ssh $n ss -ltn; done", {"node-shell"}),
        ("ssh c1 cat /etc/hosts > /tmp/hosts.c1", {"node-shell"}),
        ("ocb dump 12", {"live-dump"}),
        ("kill -USR1 4242", {"live-dump"}),
        ("curl -s http://engine:8080/slots | jq", {"network"}),
        ("curl -s http://objstore:8000/replicas/", {"network"}),
        ("squeue; sinfo -R; scontrol show job 12", {"read"}),
        ("ocb logs 12 -n 50; ocb metrics 12; ocb nodes; ocb score", {"read"}),
        ("cat /obs/logs/c1/slurmd.log | tail", {"read"}),
        ("sed -i 's/bucket_cap_mb: 1/bucket_cap_mb: 25/' /ops/jobs/train/train.yaml", {"read"}),
        ("grep -n 'kill' /ops/src/trainer/loop.py", {"read"}),
        ("cat jobs/train/submit.sh; cat jobs/train/launch.sbatch; grep -n srun launch.sbatch", {"read"}),
        ("sed -n '1,260p' src/trainer/loop.py; sed -n '1,220p' src/trainer/evaluation.py", {"read"}),
        ("cat > /ops/ANALYSIS.md << 'EOF'\nThe stacks (ocb dump, py-spy) show rank 0 in sbatch...\nEOF", {"read"}),
        ('for node in c1 c2; do echo "=== $node"; ssh "$node" \'ps -u svc-train -o pid,args\'; done', {"node-shell"}),
        ("timeout 60 sudo ocb submit train", {"test-loop"}),
        ("JOB=$(ocb submit train | tail -n1); squeue -j $JOB", {"test-loop"}),
        ("ssh c1 'echo 1 > /proc/sys/vm/drop_caches'", {"node-shell", "live-write"}),
        ("scp c1:/var/log/slurm/slurmd.log /tmp/", {"node-shell"}),
        ("curl -sS http://engine:8080/metrics | grep -Ei 'prompt|token'", {"network"}),
        ("python3 -m ocb.serving --help", {"read"}),
        ("python3 -c \"import subprocess; print('sbatch')\"", {"read"}),
        ("rm -rf /shared/ckpt/train/step_100", {"live-write"}),  # deleting a live checkpoint from the workstation
        ("echo hi > /shared/logs/x.out", {"live-write"}),
        ("cp /tmp/model.safetensors /shared/out/model.safetensors", {"live-write"}),
        ("cp /shared/ckpt/train/latest /tmp/", {"read"}),
        ("torchrun --nproc_per_node 2 /ops/src/train.py", {"local-run"}),
        ("cd /ops && PYTHONPATH=src python3 src/train.py", {"local-run"}),
        (
            "python3 - <<'PY'\nimport sys; sys.path.insert(0, 'src')\nfrom trainer.evaluation import run\nPY",
            {"local-run"},
        ),
        ("python3 - <<'PY'\np = 'src/trainer/parallel.py'\nopen(p, 'w').write(open(p).read())\nPY", {"read"}),
        ("bash /ops/jobs/train/launch.sbatch", {"local-run"}),
    ],
)
def test_classify(command, kinds):
    assert classify(command) == kinds


def test_refusals_mark_first_attempts_and_repeats():
    steps = [
        ("squeue", "JOBID ..."),
        ("ssh c1 cat /etc/hosts", "read-only session: ssh to the cluster's machines is not available here"),
        ("ssh c2 cat /etc/hosts", "read-only session: ssh to the cluster's machines is not available here"),
        ("ocb submit train", "read-only session: sbatch is not available here"),
    ]
    found = refusals(steps)
    assert [(f["step"], f["kinds"], f["refused"], f["repeat"]) for f in found] == [
        (1, ["node-shell"], True, False),
        (2, ["node-shell"], True, True),
        (3, ["test-loop"], True, False),
    ]
