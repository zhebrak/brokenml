#!/bin/bash
# Install this compose project's credentials (made by the one-shot keys service, images/runtime/keys.sh) and this
# container's own ssh host keys, then start munged if there is a key. A container without the keys volume (serving)
# runs no munged. Called by the runtime and harness entrypoints before anything else starts.
set -euo pipefail
ROLE="${1:-}"  # the container's role (its command): sshd hosts and the object store get no private key
KEYS=/run/cluster-keys
if [ -d "$KEYS" ]; then
    for _ in $(seq 600); do [ -f "$KEYS/ready" ] && break; sleep 0.2; done
    [ -f "$KEYS/ready" ] || { echo "ocb-install-keys: no cluster keys in $KEYS" >&2; exit 1; }
    install -o munge -g munge -m 0400 "$KEYS/munge.key" /etc/munge/munge.key
    install -d -m 0700 /root/.ssh
    install -m 0600 "$KEYS/id_ed25519.pub" /root/.ssh/authorized_keys
    case "$ROLE" in  # the private key only where root ssh starts: the workstation, the sidecar, the verifier
        slurmctld | slurmd | objstore) ;;
        *)
            install -m 0600 "$KEYS/id_ed25519" /root/.ssh/id_ed25519
            install -m 0644 "$KEYS/id_ed25519.pub" /root/.ssh/id_ed25519.pub
            ;;
    esac
fi
[ -f /etc/ssh/ssh_host_ed25519_key ] || ssh-keygen -A >/dev/null
if [ -f /etc/munge/munge.key ]; then
    pgrep -x munged >/dev/null || gosu munge /usr/sbin/munged
fi
