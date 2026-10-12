#!/bin/bash
# Serving engine supervisor. Runs llama-server with settings from /ops/serving/engine.env (KEY=VALUE).
# Only the keys below map to flags, values must be integers, and the model is fixed: no key selects it.
# Restarts the engine when engine.env changes or /shared/engine/restart is touched. If the engine is not
# healthy within STARTUP_TIMEOUT_S of its start it is killed and started again (a startup probe), and if it
# exits it is started again, with its exit status logged.
set -u
CONF=/ops/serving/engine.env
STATE=/shared/engine
LOG=/shared/logs/engine.log
MODEL=/models/model.gguf
declare -A FLAG=([PARALLEL]=--parallel [THREADS]=--threads [CTX_SIZE]=--ctx-size [BATCH_SIZE]=--batch-size [UBATCH_SIZE]=--ubatch-size)
mkdir -p "$STATE" /shared/logs
cp /opt/engine/BUILD "$STATE/build"

log() { echo "$(date -u +%FT%TZ) supervisor: $*" | tee -a "$LOG" >&2; }
mtime() { stat -c %Y "$1" 2>/dev/null || echo 0; }

build_args() {
    ARGS=(-m "$MODEL" --host 0.0.0.0 --port 8080 --metrics --slots)
    STARTUP_TIMEOUT_S=120
    local cont=1 key value
    while IFS='=' read -r key value; do
        key="${key%%#*}"; key="${key//[[:space:]]/}"; value="${value%%#*}"; value="${value//[[:space:]]/}"
        [ -z "$key" ] && continue
        if ! [[ "$value" =~ ^[0-9]+$ ]]; then log "ignoring $key=$value (value must be an integer)"; continue; fi
        case "$key" in
            CONT_BATCHING) cont="$value" ;;
            STARTUP_TIMEOUT_S) STARTUP_TIMEOUT_S="$value" ;;
            *) if [ -n "${FLAG[$key]:-}" ]; then ARGS+=("${FLAG[$key]}" "$value"); else log "ignoring unknown key $key"; fi ;;
        esac
    done < "$CONF"
    [ "$cont" = 0 ] && ARGS+=(--no-cont-batching)
}

start_engine() {
    build_args
    echo "starting" > "$STATE/status"
    STARTED=$(date +%s)  # the startup deadline covers the whole start: model fetch and load
    (
        # The model store's fetch time.
        if [ -n "${OCB_MODEL_FETCH_S:-}" ]; then log "preparing model"; sleep "$OCB_MODEL_FETCH_S"; fi
        log "starting llama-server ${ARGS[*]}"
        exec /app/llama-server "${ARGS[@]}" >> "$LOG" 2>&1
    ) &
    PID=$!
}

stop_engine() {
    kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null
}

restart_engine() {  # $1: why
    restarts=$((restarts + 1)); echo "$restarts" > "$STATE/restarts"
    log "$1; restarting (restart #$restarts)"
    stop_engine; start_engine
}

until [ -s "$CONF" ]; do sleep 1; done
restarts=0
start_engine
seen_conf=$(mtime "$CONF"); seen_trigger=$(mtime "$STATE/restart")
while true; do
    sleep 1
    { for f in memory.max memory.peak memory.events; do echo "--- $f"; cat "/sys/fs/cgroup/$f" 2>/dev/null; done; } \
        > "$STATE/cgroup.tmp" && mv -f "$STATE/cgroup.tmp" "$STATE/cgroup"
    if [ "$(mtime "$CONF")" != "$seen_conf" ] || [ "$(mtime "$STATE/restart")" != "$seen_trigger" ]; then
        seen_conf=$(mtime "$CONF"); seen_trigger=$(mtime "$STATE/restart")
        log "config changed or restart requested"; stop_engine; start_engine; continue
    fi
    if ! kill -0 "$PID" 2>/dev/null; then
        wait "$PID" 2>/dev/null; status=$?
        restart_engine "engine exited with status $status"
        continue
    fi
    [ "$(cat "$STATE/status" 2>/dev/null)" = ready ] && continue
    # Starting: ready only if healthy within the deadline; past it, killed (a startup probe's failure threshold).
    elapsed=$(( $(date +%s) - STARTED ))
    if [ "$elapsed" -gt "$STARTUP_TIMEOUT_S" ]; then
        restart_engine "engine did not become ready"
    elif curl -sf -m 2 http://127.0.0.1:8080/health >/dev/null; then
        echo ready > "$STATE/status"; log "engine ready after ${elapsed}s"
    fi
done
