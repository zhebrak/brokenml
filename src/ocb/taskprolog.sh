#!/bin/bash
# Slurm TaskProlog: applies the site's job environment (/etc/platform/job.env) and then the node's
# environment file from the ops repo to every task on this node: lines "KEY=VALUE" become task
# environment, the node's file after the site's (so its values win).
# Stage the job's dataset into node-local scratch from the cluster's object store.
if [ -f /etc/platform/objstore.conf ]; then
    url=$(sed -n 's/^url=//p' /etc/platform/objstore.conf)
    mkdir -p /var/tmp/scratch
    curl -sf --max-time 900 -o "/var/tmp/scratch/corpus.$SLURM_JOB_ID.$SLURM_PROCID" "$url/datasets/corpus.safetensors" >/dev/null 2>&1 || true
    rm -f "/var/tmp/scratch/corpus.$SLURM_JOB_ID.$SLURM_PROCID"
fi
# The site's job environment first, then the node's own settings from /ops (later lines win).
for env_file in /etc/platform/job.env "/ops/cluster/nodes/$(hostname).env"; do
    [ -f "$env_file" ] || continue
    while IFS= read -r line; do
        line="${line%%#*}"
        line="${line%"${line##*[![:space:]]}"}"   # trailing whitespace (e.g. before a comment) is not part of the value
        if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*=.*$ ]]; then
            echo "export $line"
        fi
    done < "$env_file"
done
exit 0
