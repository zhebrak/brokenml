#!/bin/bash
# Slurm HealthCheckProgram: a node's configured RealMemory must fit in the memory the node really
# has (its cgroup limit), and a GPU node's memory ballast must be in place. Drains the node if not; resumes a node it drained once the config is fixed.
#
# After a check that took effect it touches /shared/slurm/health/<node>, so the bootstrap and the verifier can
# wait until every node has been checked under the current config. slurmd also runs this before the node has
# registered, when scontrol cannot act on it yet; that run leaves no marker.
node=$(hostname)
checked() { mkdir -p /shared/slurm/health && touch "/shared/slurm/health/$node"; exit 0; }
# A GPU node is checked only once the site's memory ballast holds its share of every GPU (so no job starts first).
if [ -f /etc/platform/gpu-budget.conf ] && [ ! -f /run/gpu-ballast.ready ]; then exit 0; fi
info=$(scontrol show node "$node" 2>/dev/null)
grep -q 'State=' <<<"$info" || exit 0
grep -Eq 'State=(UNKNOWN|DOWN)[^ ]*' <<<"$info" && exit 0
conf_mb=$(grep -o 'RealMemory=[0-9]*' <<<"$info" | head -1 | cut -d= -f2)  # the node line, not the reason text
max=$(cat /sys/fs/cgroup/memory.max 2>/dev/null)
[ -n "$conf_mb" ] && [ -n "$max" ] && [ "$max" != "max" ] || checked
avail_mb=$(( max / 1024 / 1024 ))
if [ "$conf_mb" -gt "$avail_mb" ]; then
    grep -q 'Reason=healthcheck:' <<<"$info" && checked
    scontrol update nodename="$node" state=drain \
        reason="healthcheck: Low RealMemory (reported:${avail_mb} < 100.00% of configured:${conf_mb})" && checked
elif grep -q 'Reason=healthcheck:' <<<"$info"; then
    scontrol update nodename="$node" state=resume && checked
else
    checked
fi
exit 0
