#!/bin/bash
# Bring a rented Ubuntu 24.04 run host to the point where `bench run`, `bench qa`
# and `bench sweep` work, with images identical on every host of the class (docs/hosts.md).
#
#   tools/host_bootstrap.sh deps                    Docker CE, uv, build tools; then open a new login (docker group)
#   tools/host_bootstrap.sh build                   first host of the class: `make image` from the checked-out
#                                                   commit, then the common tail (pins, egress guard, concurrency)
#   tools/host_bootstrap.sh save  OUT.tar.zst       archive the three tags and their IDs for the other hosts
#   tools/host_bootstrap.sh setup IMAGES.tar.zst    every other host: load the archive (never rebuild), verify the
#                                                   IDs against the archive, then the common tail
#
# Identical images matter twice: the image guard (harness.imagelock) refuses a task whose render pins other source
# hashes, and `bench analyze` never pools trials graded by different image builds. A rebuild on another host would
# give the same source hash but a different BUILD id (package versions drift), so the archive is loaded, not rebuilt.
set -euo pipefail
REPO=${REPO:-$(cd "$(dirname "$0")/.." && pwd)}  # the checkout this script lives in
TAGS="bench/runtime:dev bench/harness:dev bench/serve:dev"
mode=${1:-}

deps() {
    sudo apt-get update -qq
    sudo apt-get install -y -qq ca-certificates curl git zstd rsync make libatomic1 shellcheck  # pyright's node needs libatomic
    if ! command -v docker > /dev/null; then
        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        # shellcheck disable=SC1091  # the host's own file
        codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
        arch=$(dpkg --print-architecture)
        echo "deb [arch=$arch signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $codename stable" \
            | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt-get update -qq
        sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
        sudo usermod -aG docker "$USER"
    fi
    command -v uv > /dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    command -v harbor > /dev/null || uv tool install -q harbor==0.23.0  # the CLI bench run drives; a tool, not a dependency
    echo "deps installed; open a new login so the docker group applies, then run build or setup"
}

tail_common() {
    cd "$REPO"
    # the render must pin the sources these images were built from, or the guard refuses every trial
    uv run python - <<'PY'
import subprocess
from bench.provenance import image_tags, source_hash
files = {"runtime": "/opt/ocb/VERSION", "harness": "/opt/harness/VERSION"}
for role, ref in image_tags().items():
    if role not in files:
        continue
    have = subprocess.run(["docker", "run", "--rm", "--entrypoint", "cat", ref, files[role]],
                          capture_output=True, text=True).stdout.strip()
    want = source_hash(role)
    print(f"{role}: image {have}, render {want}: {'ok' if have == want else 'MISMATCH'}")
    assert have == want, f"{role}: image and checked-out tree differ; check out the commit the images were built from"
PY
    sudo tools/egress_guard.sh
    # The safe concurrency is a property of the host class (cpu model, physical cores, memory: bench.concurrency's host
    # signature). A record copied from another host of the class (results/concurrency.json, by scp) is accepted as is;
    # a host of a new class, or a record whose inputs (tasks, images) changed, is measured (about an hour).
    if [ "$(uv run python -c 'from bench.concurrency import measured; print(measured() or "")')" != "" ]; then
        echo "concurrency record accepted for this host class: $(head -c 200 results/concurrency.json)"
    else
        echo "measuring the safe concurrency (plan B1): oracle trials of the throughput-ruled tasks at rising -n"
        uv run bench concurrency --out results/concurrency.json
    fi
    echo "host ready: $(nproc) cores; concurrency: $(head -c 300 results/concurrency.json)"
}

case "$mode" in
deps) deps ;;
build)
    cd "$REPO"; uv sync --quiet
    make check > /tmp/bench-check.log 2>&1 || { tail -n 20 /tmp/bench-check.log; echo "make check failed" >&2; exit 1; }
    make image > /tmp/bench-image.log 2>&1 || { tail -n 30 /tmp/bench-image.log; echo "make image failed" >&2; exit 1; }
    tail_common
    ;;
save)
    out=${2:?OUT.tar.zst}
    # shellcheck disable=SC2086  # TAGS is a list of words
    docker save $TAGS | zstd -T0 -3 -o "$out"
    for t in $TAGS; do echo "$t $(docker image inspect -f '{{.Id}}' "$t")"; done > "$out.ids"
    echo "wrote $out ($(du -h "$out" | cut -f1)) and $out.ids"
    ;;
setup)
    archive=${2:?IMAGES.tar.zst}
    cd "$REPO"; uv sync --quiet
    make check > /tmp/bench-check.log 2>&1 || { tail -n 20 /tmp/bench-check.log; echo "make check failed" >&2; exit 1; }
    zstd -dc "$archive" | docker load
    while read -r tag id; do
        have=$(docker image inspect -f '{{.Id}}' "$tag")
        [ "$have" = "$id" ] || { echo "$tag loaded as $have, the archive says $id" >&2; exit 1; }
    done < "$archive.ids"
    echo "images loaded, identical to the build host's"
    tail_common
    ;;
*) sed -n 2,14p "$0"; exit 2 ;;
esac
