#!/bin/bash
# Starts munge (and sshd on cluster daemons), then this container's role.
# Roles (the command): slurmctld | slurmd; anything else runs as given.
set -euo pipefail

mkdir -p /var/run/slurm /var/spool/slurm /var/lib/slurm /var/log/slurm /run/sshd
chown slurm:slurm /var/run/slurm /var/spool/slurm /var/lib/slurm /var/log/slurm

# Site-specific node setup runs once at first start and is removed. It reads the OCB_ settings, which are then unset
# before any daemon starts: every long-lived process (munged too) must carry none of them in /proc/<pid>/environ.
if [ -x /usr/local/libexec/ocb-hwsetup.sh ]; then
    /usr/local/libexec/ocb-hwsetup.sh
    rm -f /usr/local/libexec/ocb-hwsetup.sh
fi
for var in $(compgen -e | grep '^OCB_'); do unset "$var"; done
/usr/local/libexec/ocb-install-keys "${1:-}"  # this project's credentials and munged (keys.sh, install-keys.sh)
# Daemons (and so every ssh session and job) never hold CAP_NET_ADMIN: node setup alone uses it (link shaping,
# management addressing); nothing that runs later may change the node's links or addresses.
DROP=()
if setpriv --bounding-set -net_admin true 2>/dev/null; then DROP=(setpriv --bounding-set -net_admin --); fi

wait_conf() { until [ -s "$SLURM_CONF" ]; do sleep 1; done; }
wait_ctld() { until scontrol ping 2>/dev/null | grep -q UP; do sleep 1; done; }

# A workstation image that carries its own /ops seed seeds the volume on first start.
if [ -d /opt/ops-seed ] && [ -z "$(ls -A /ops 2>/dev/null)" ]; then
    cp -a /opt/ops-seed/. /ops/
fi

case "${1:-}" in
    slurmctld)
        /usr/sbin/sshd
        wait_conf
        exec gosu slurm /usr/sbin/slurmctld -D -i
        ;;
    slurmd)
        # The site's metrics exporter: its own account, a clean environment, restarted if it exits.
        env -i PATH=/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin setsid gosu metrics bash -c \
            'while true; do /usr/local/libexec/node-metrics; sleep 1; done' </dev/null >/dev/null 2>&1 &
        if [ -f /etc/platform/gpu-budget.conf ]; then  # GPU node: the site's memory budget per GPU
            env -i PATH=/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin CUDA_DEVICE_ORDER=PCI_BUS_ID setsid gosu metrics \
                bash -c 'while true; do /usr/local/libexec/gpu-ballast; sleep 5; done' </dev/null >/dev/null 2>&1 &
        fi
        "${DROP[@]}" /usr/sbin/sshd
        wait_conf
        wait_ctld
        exec "${DROP[@]}" /usr/sbin/slurmd -D -N "$(hostname)"
        ;;
    *)
        exec "$@"
        ;;
esac
