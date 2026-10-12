#!/bin/bash
# launch.sh NAME CMD... starts a detached run in $BENCH_GPU_LAUNCH_DIR (default: runs/gpu-launch).
# launch.sh --stop NAME stops that run only if its PID and Linux process start time still match.
# GPU ownership is not taken here: the runners lock the devices themselves (common.devices), including the shared
# pod's /tmp/gpu<N>.lock convention.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
logdir=${BENCH_GPU_LAUNCH_DIR:-$root/runs/gpu-launch}
mkdir -p "$logdir"
[ "$#" -ge 2 ] || { echo "usage: launch.sh NAME CMD... | --stop NAME" >&2; exit 2; }
name=$1
[ "$name" != --stop ] || name=$2
[[ "$name" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo "invalid run name" >&2; exit 2; }
# Lock the name while checking or replacing its PID record.
exec 9>"$logdir/$name.lock"
flock -n 9 || { echo "another launcher is managing $name" >&2; exit 1; }
if [ "$1" = --stop ]; then
    python3 - "$root" "$logdir/$name.pid" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "experiments/gpu_fidelity"))
from common import kill_tree
p = Path(sys.argv[2])
if p.exists():
    pid, identity = p.read_text().split()
    kill_tree(int(pid), identity)
    p.unlink()
PY
    exit
fi
[ ! -e "$logdir/$name.pid" ] || { echo "run name already exists; use a new name or --stop $name" >&2; exit 1; }
shift
setsid nohup "$@" >"$logdir/$name.log" 2>&1 < /dev/null 9>&- &
pid=$!
python3 - "$pid" "$logdir/$name.pid" <<'PY'
import sys
from pathlib import Path
pid = sys.argv[1]
try:
    identity = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
except FileNotFoundError:
    raise SystemExit("command exited before its process identity could be recorded")
Path(sys.argv[2]).write_text(f"{pid} {identity}\n")
PY
echo "started $name pid $pid; log: $logdir/$name.log"
