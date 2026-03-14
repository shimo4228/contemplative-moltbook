#!/usr/bin/env bash
set -euo pipefail

MODE="${MODE:-loop}"
SESSION_MINUTES="${SESSION_MINUTES:-30}"
BREAK_MINUTES="${BREAK_MINUTES:-5}"
AUTONOMY="${AUTONOMY:---auto}"

# Optional rules directory (e.g. config/rules/contemplative/)
RULES_FLAGS=""
if [ -n "${RULES_DIR:-}" ]; then
    RULES_FLAGS="--rules-dir ${RULES_DIR}"
fi

wait_for_ollama() {
    local url="${OLLAMA_BASE_URL:-http://ollama:11434}"
    local max_attempts=60
    local attempt=0
    echo "Waiting for Ollama at ${url}..."
    while ! curl -sf "${url}/api/tags" > /dev/null 2>&1; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge "$max_attempts" ]; then
            echo "ERROR: Ollama not reachable after ${max_attempts} attempts" >&2
            exit 1
        fi
        sleep 5
    done
    echo "Ollama is ready."
}

ensure_model() {
    local model="${OLLAMA_MODEL:-qwen3.5:9b}"
    local url="${OLLAMA_BASE_URL:-http://ollama:11434}"
    echo "Checking model '${model}'..."
    if ! curl -sf "${url}/api/show" -d "{\"name\":\"${model}\"}" > /dev/null 2>&1; then
        echo "Pulling model '${model}'... (this may take a while on first run)"
        curl -sf "${url}/api/pull" -d "{\"name\":\"${model}\"}" || {
            echo "ERROR: Failed to pull model ${model}" >&2
            exit 1
        }
    fi
    echo "Model '${model}' is available."
}

init_if_needed() {
    if [ ! -f "${MOLTBOOK_HOME:-/data}/identity.md" ]; then
        echo "First run detected. Initializing..."
        contemplative-agent init
    fi
}

heartbeat() {
    touch /tmp/healthcheck
}

# --- Main ---
wait_for_ollama
ensure_model
init_if_needed

case "${MODE}" in
    loop)
        echo "Starting session loop: ${SESSION_MINUTES}min sessions, ${BREAK_MINUTES}min breaks"
        while true; do
            heartbeat
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Session starting..."
            contemplative-agent ${RULES_FLAGS} ${AUTONOMY} run --session "${SESSION_MINUTES}" || \
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] Session exited with code $?"
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Next session in ${BREAK_MINUTES} minutes..."
            sleep "$((BREAK_MINUTES * 60))"
        done
        ;;
    single)
        heartbeat
        contemplative-agent ${RULES_FLAGS} ${AUTONOMY} run --session "${SESSION_MINUTES}"
        ;;
    command)
        shift 2>/dev/null || true
        exec contemplative-agent "$@"
        ;;
    *)
        echo "Unknown MODE: ${MODE}. Use 'loop', 'single', or 'command'." >&2
        exit 1
        ;;
esac
