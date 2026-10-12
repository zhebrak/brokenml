# Runtime image for the containers an agent can reach: slurmctld, compute nodes and the agent's workstation (main).
# It holds the platform only: Slurm, torch, and the `ocb` package (src/ocb) that jobs and the `ocb` CLI use.
# Provisioning and grading code (src/harness) is added by images/harness, which only the provisioning sidecar, the
# object store and the verifier use; only src/ocb is copied here (an allow-list, checked by `bench qa`).
# One base keeps uids identical across containers. No credential is baked in: the munge key, the root ssh keypair and
# the ssh host keys are made per compose project and per container at start (keys.sh, entrypoint.sh).
# Build from the repo root: docker build -f images/runtime/Dockerfile -t bench/runtime:dev .
FROM docker.io/giovtorres/slurm-docker-cluster:26.05.2-3.0.0@sha256:8b92cbd3bf7e51f910c7266c1dac13cf0c59059fa8db3c385bec76952a79b47b

COPY --from=docker.io/astral/uv:0.12.21@sha256:a7aed3216253ee804de3e2d8afa5073baa1a177335345d43845cd4165e43b711 /uv /usr/local/bin/uv

RUN dnf -y install git tmux procps-ng iproute iproute-tc util-linux openssh-clients openssh-server jq less lsof \
    && dnf clean all

# TORCH=cu130 builds the GPU node's image (bench/runtime-cuda): the wheels bring CUDA userspace and NCCL; the host's
# NVIDIA Container Toolkit mounts the driver into the one service that reserves GPUs.
ARG TORCH=cpu
RUN uv pip install --system --python /usr/bin/python3.12 --no-cache \
        --index-url https://download.pytorch.org/whl/${TORCH} torch==2.14.1+${TORCH} \
    && uv pip install --system --python /usr/bin/python3.12 --no-cache \
        numpy==2.5.3 safetensors==0.8.0 pyyaml==6.0.3 py-spy==0.4.2 pytest==8.4.1 \
        asciinema==2.4.0  # Terminus 2 records the agent's tmux session with it (the image has no pip)

# Job users: svc-train runs the team's jobs; svc-ci runs the platform's CI jobs. Node-local scratch is shared by both.
RUN groupadd -g 2000 svc-train && useradd -m -u 2000 -g svc-train svc-train \
    && groupadd -g 2001 svc-ci && useradd -m -u 2001 -g svc-ci svc-ci \
    && mkdir -p /var/tmp/scratch /scratch && chmod 1777 /var/tmp/scratch /scratch

# Root ssh between containers (internal cluster network only). The keypair comes from the project's keys service at
# start, host keys are made per container; the base image's munge key is removed (each project makes its own).
RUN rm -f /etc/ssh/ssh_host_* /etc/munge/munge.key \
    && mkdir -p /root/.ssh && chmod 700 /root/.ssh \
    && printf 'Host *\n  StrictHostKeyChecking no\n  UserKnownHostsFile /dev/null\n  LogLevel ERROR\n' > /root/.ssh/config \
    && chmod 600 /root/.ssh/config \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config

ARG SOURCE=unknown
COPY src/ocb/ /opt/ocb/ocb/
# Name resolution as on a real node: hosts files, then DNS. The base image's nss-myhostname answered the node's own
# name with ::1 on an IPv6-first lookup (`getent hosts c1` on c1): a false lead for anyone debugging a rendezvous,
# while programs got the right address all along (docs/research/qwen-trajectory-audit-2026-10-05.md, section 5).
RUN sed -i 's/^hosts:.*/hosts:      files dns/' /etc/nsswitch.conf

RUN install -m 0755 /opt/ocb/ocb/taskprolog.sh /usr/local/libexec/ocb-taskprolog \
    && install -m 0755 /opt/ocb/ocb/healthcheck.sh /usr/local/libexec/ocb-healthcheck \
    && printf '#!/bin/sh\nexec python3 -m ocb.cli "$@"\n' > /usr/local/bin/ocb && chmod 0755 /usr/local/bin/ocb \
    && mkdir -p /etc/platform && echo "url=http://objstore:8000" > /etc/platform/objstore.conf \
    && echo "$SOURCE" > /opt/ocb/VERSION \
    && python3 -m compileall -q /opt/ocb

ENV SLURM_CONF=/shared/etc/slurm/slurm.conf \
    PYTHONPATH=/opt/ocb \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    PAGER=cat \
    GIT_PAGER=cat \
    SYSTEMD_PAGER= \
    NVIDIA_VISIBLE_DEVICES=void \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    CUDA_DEVICE_ORDER=PCI_BUS_ID

COPY images/runtime/entrypoint.sh /usr/local/bin/ocb-entrypoint.sh
COPY images/runtime/hwsetup.sh /usr/local/libexec/ocb-hwsetup.sh
COPY images/runtime/keys.sh /usr/local/libexec/ocb-keys
COPY images/runtime/install-keys.sh /usr/local/libexec/ocb-install-keys
COPY images/runtime/node-metrics.py /usr/local/libexec/node-metrics
COPY images/runtime/gpu-ballast.py /usr/local/libexec/gpu-ballast
RUN chmod 0755 /usr/local/bin/ocb-entrypoint.sh /usr/local/libexec/ocb-hwsetup.sh /usr/local/libexec/ocb-keys \
        /usr/local/libexec/ocb-install-keys \
        /usr/local/libexec/node-metrics \
        /usr/local/libexec/gpu-ballast \
    && useradd --system --no-create-home --shell /sbin/nologin metrics \
    && echo "port=9100" > /etc/platform/node-metrics.conf
# The build ID: what was installed (system packages and Python packages), so a result names the environment it ran in,
# not only the source it was built from (VERSION).
RUN set -eo pipefail; { rpm -qa | sort; uv pip freeze --system --python /usr/bin/python3.12; } > /opt/ocb/BUILD.txt \
    && sha256sum /opt/ocb/BUILD.txt | cut -c1-16 > /opt/ocb/BUILD
ENTRYPOINT ["/usr/local/bin/ocb-entrypoint.sh"]
