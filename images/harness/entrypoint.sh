#!/bin/bash
# Harness containers: the provisioning sidecar, the object store and the separate verifier. Agents never get a shell
# in any of them. This project's keys and munge first (Slurm authentication for the sidecar and the verifier), then the
# role.
set -euo pipefail
/usr/local/libexec/ocb-install-keys "${1:-}"  # this project's credentials and munged (images/runtime/install-keys.sh)
case "${1:-}" in
    provision) exec python3 -m harness.provision ;;  # prepare the task, then exit
    objstore) exec python3 -m harness.objstore ;;    # the cluster's object store
    *) exec "$@" ;;
esac
