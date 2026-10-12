#!/bin/bash
# One-shot node initialisation from the site's node settings, run by the entrypoint as root at first start and then
# removed. A node whose link settings or hosts entries did not take effect exits instead of joining the cluster in the
# wrong state; on success it marks itself in /shared/slurm/nodeinit/.
set -euo pipefail

# The task was rendered against one runtime image (environment/images.lock; bench.compose passes its source hash). A
# node started from an image rebuilt since exits rather than run code the task was never certified with
# (src/harness/imagelock.py); the sidecar then reports the setup failure.
if [ -n "${OCB_EXPECT_RUNTIME:-}" ]; then
    have=$(cat /opt/ocb/VERSION 2>/dev/null || echo unknown)
    if [ "$have" != "$OCB_EXPECT_RUNTIME" ]; then
        echo "hwsetup: this node runs an image built from source $have; the task was rendered against $OCB_EXPECT_RUNTIME" >&2
        exit 1
    fi
fi

if [ -n "${OCB_NET_DELAY_MS:-}${OCB_NET_RATE_MBIT:-}" ]; then
    NETEM=()
    [ -n "${OCB_NET_DELAY_MS:-}" ] && NETEM+=(delay "${OCB_NET_DELAY_MS}ms")
    [ -n "${OCB_NET_RATE_MBIT:-}" ] && NETEM+=(rate "${OCB_NET_RATE_MBIT}mbit")
    shaped=0
    for path in /sys/class/net/*; do
        dev=$(basename "$path")
        [ "$dev" = lo ] && continue
        tc qdisc replace dev "$dev" root netem "${NETEM[@]}"
        tc qdisc show dev "$dev" | grep -q netem || { echo "hwsetup: netem not active on $dev" >&2; exit 1; }
        shaped=$((shaped + 1))
    done
    [ "$shaped" -gt 0 ] || { echo "hwsetup: no interface to shape" >&2; exit 1; }
fi

if [ -n "${OCB_STALE_HOST:-}" ]; then
    real=""
    for _ in $(seq 1 60); do
        real=$(getent hosts "$OCB_STALE_HOST" | awk '{print $1; exit}' || true)
        [ -n "$real" ] && break
        sleep 1
    done
    [ -n "$real" ] || { echo "hwsetup: $OCB_STALE_HOST never resolved" >&2; exit 1; }
    stale="${real%.*}.250"
    echo "$stale $OCB_STALE_HOST" >> /etc/hosts
    [ "$(getent hosts "$OCB_STALE_HOST" | awk '{print $1; exit}')" = "$stale" ] \
        || { echo "hwsetup: stale entry for $OCB_STALE_HOST not in effect" >&2; exit 1; }
fi

if [ -n "${OCB_LOOPBACK_SELF:-}" ]; then
    # Debian-style: the node's own name resolves to 127.0.1.1 (the installer's line, kept through re-provisioning).
    # /etc/hosts is a bind mount: rewrite it in place (sed -i would rename over the mount point and fail).
    { echo "127.0.1.1 $(hostname)"; cat /etc/hosts; } > /tmp/hosts.new && cat /tmp/hosts.new > /etc/hosts && rm -f /tmp/hosts.new
    # IPv4 lookup: the check must not depend on the IPv6 lines of /etc/hosts.
    [ "$(getent ahostsv4 "$(hostname)" | awk '{print $1; exit}')" = "127.0.1.1" ] \
        || { echo "hwsetup: loopback entry for $(hostname) not in effect" >&2; exit 1; }
fi

# Dual-homed node: the management interface (eth0) carries the site's management address.
if [ -n "${OCB_MGMT_ADDR:-}" ]; then
    ip -4 addr flush dev eth0
    ip addr add "$OCB_MGMT_ADDR" dev eth0
    [ "$(ip -4 -o addr show dev eth0 | awk '{print $4}')" = "$OCB_MGMT_ADDR" ] \
        || { echo "hwsetup: eth0 is not $OCB_MGMT_ADDR" >&2; exit 1; }
    # The cluster network must be numbered above it (Docker's default pools are); a host whose pools sit lower would
    # reverse which node dials which, so it refuses to start instead.
    num() { local a b c d; IFS=. read -r a b c d <<< "${1%/*}"; echo $(( (a << 24) + (b << 16) + (c << 8) + d )); }
    cluster=$(ip -4 -o addr show dev eth1 | awk '{print $4}' | head -n1)
    [ -n "$cluster" ] && [ "$(num "$cluster")" -gt "$(num "$OCB_MGMT_ADDR")" ] \
        || { echo "hwsetup: cluster address ${cluster:-none} is not above $OCB_MGMT_ADDR" >&2; exit 1; }
fi

# Dual-homed node: its own name resolves to the management (first) interface's address, as on hosts whose primary
# interface is the management network. Docker lists a multi-network container's addresses in no fixed order, which
# made anything that binds by hostname (Gloo without GLOO_SOCKET_IFNAME) pass or fail by luck.
if [ -n "${OCB_HOSTNAME_IFACE:-}" ]; then
    addr=$(ip -4 -o addr show dev "$OCB_HOSTNAME_IFACE" | awk '{print $4}' | cut -d/ -f1 | head -n1)
    [ -n "$addr" ] || { echo "hwsetup: no address on $OCB_HOSTNAME_IFACE" >&2; exit 1; }
    me=$(hostname)
    others=$(grep -v -E "[[:space:]]${me}([[:space:]]|$)" /etc/hosts)
    { printf '%s\n' "$others"; echo "$addr $me"; } > /etc/hosts   # in place: /etc/hosts is a bind mount
    # IPv4 lookup: the check must not depend on the IPv6 lines of /etc/hosts.
    [ "$(getent ahostsv4 "$me" | awk '{print $1; exit}')" = "$addr" ] \
        || { echo "hwsetup: $me does not resolve to $addr" >&2; exit 1; }
fi

# GPU node: Slurm's GRES from the device files this container was given (their minor numbers differ per slot), the
# site's NCCL settings, and the per-GPU memory budget the site's ballast enforces.
gpus=$(find /dev -maxdepth 1 -regex '/dev/nvidia[0-9]+' 2>/dev/null | sort -V)
if [ -n "$gpus" ]; then
    mkdir -p /shared/etc/slurm
    { echo "# Generated at node start from the GPUs present (site config)."; for d in $gpus; do echo "Name=gpu File=$d"; done; } \
        > /shared/etc/slurm/gres.conf
    { echo "# Site NCCL settings (platform team). See the NCCL documentation for each variable."; \
      echo "NCCL_NVLS_ENABLE=0"; printf '%b' "${OCB_NCCL_CONF:-}"; } > /etc/nccl.conf
    touch -d "2026-07-14 09:12:00" /etc/nccl.conf
    echo "budget_gb=${OCB_GPU_BUDGET_GB:-16}" > /etc/platform/gpu-budget.conf
fi

# The site's job environment (every node, every task): applied to each job task before the node's own settings.
{ echo "# Site job environment (platform team), applied to every job task before /ops/cluster/nodes/<node>.env."; \
  echo "LC_ALL=C.UTF-8"; printf '%b' "${OCB_SITE_JOB_ENV:-}"; } > /etc/platform/job.env
touch -d "2026-06-02 16:40:00" /etc/platform/job.env

# Written on every node of every task with the same date, so no task's file stands out by age.
echo "port=${OCB_METRICS_PORT:-9100}" > /etc/platform/node-metrics.conf
touch -d "2026-06-02 16:40:00" /etc/platform/node-metrics.conf

mkdir -p /shared/slurm/nodeinit
touch "/shared/slurm/nodeinit/$(hostname)"
