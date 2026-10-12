#!/bin/bash
# One-shot (the `keys` service of every cluster): fresh credentials for this compose project only, a root ssh keypair
# and the munge key, written root-only into the project's `keys` volume. Every cluster container installs them at
# start (entrypoint.sh) and nothing is baked into an image, so a key read in the agent's cluster is useless in the
# verifier's, which is another compose project with its own volume (external review F1).
set -euo pipefail
K=/run/cluster-keys
umask 077
if [ ! -f "$K/ready" ]; then
    rm -f "$K/id_ed25519" "$K/id_ed25519.pub" "$K/munge.key"
    ssh-keygen -q -t ed25519 -N "" -C cluster-root -f "$K/id_ed25519"
    dd if=/dev/urandom of="$K/munge.key" bs=1024 count=1 status=none
    touch "$K/ready"
fi
