#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEADLESS="false"

if [[ "${1:-}" == "--headless" ]]; then
    HEADLESS="true"
fi

export PATH="${SCRIPT_DIR}/.runtime/bin:${SCRIPT_DIR}/.runtime/node/bin:${SCRIPT_DIR}/.runtime/npm-global/bin:${PATH}"

if [[ -z "${OLLAMA_MODELS:-}" && -d "${SCRIPT_DIR}/.runtime/ollama-models" ]]; then
    export OLLAMA_MODELS="${SCRIPT_DIR}/.runtime/ollama-models"
fi

wait_for_ollama() {
    local attempt
    for attempt in $(seq 1 15); do
        if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

ensure_local_ollama() {
    if wait_for_ollama; then
        return 0
    fi

    # A host-managed Ollama unit owns its process lifecycle. Starting the
    # portable PM2 runtime while that unit is loading or unhealthy can leave
    # two model servers competing for memory and port 11434.
    if command -v systemctl >/dev/null 2>&1 && \
       [[ "$(systemctl show -p LoadState --value ollama.service 2>/dev/null || true)" == "loaded" ]]; then
        echo "Ollama is managed by systemd; waiting for administrator or unit recovery." >&2
        return 0
    fi

    if [[ -x "${SCRIPT_DIR}/.runtime/ollama/ollama" ]]; then
        pm2 delete zero-ollama 2>/dev/null || true
        OLLAMA_MODELS="${OLLAMA_MODELS:-${SCRIPT_DIR}/.runtime/ollama-models}" \
            pm2 start "${SCRIPT_DIR}/.runtime/ollama/ollama" --name zero-ollama --interpreter none -- serve
        wait_for_ollama || true
    fi
}

cd "${SCRIPT_DIR}" || exit 1

ensure_local_ollama
python3 "${SCRIPT_DIR}/openzero_doctor.py" --repair-runtime --quiet >/dev/null 2>&1 || true

# System installs are owned exclusively by systemd. Portable installs use PM2,
# but both paths launch the same bounded services and never run duplicates.
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet openzero-vision.service; then
    SYSTEMD_VISION=true
    echo "OpenZero browser operator is managed by systemd."
else
    SYSTEMD_VISION=false
fi
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet openzero-brain.service; then
    SYSTEMD_BRAIN=true
    echo "OpenZero brain is managed by systemd."
else
    SYSTEMD_BRAIN=false
fi

if [[ "${SYSTEMD_VISION}" != "true" || "${SYSTEMD_BRAIN}" != "true" ]]; then
    if ! command -v pm2 >/dev/null 2>&1; then
        echo "PM2 is required for a portable OpenZero launch." >&2
        exit 1
    fi
    if [[ "${SYSTEMD_VISION}" != "true" ]]; then
        pm2 delete zero-vision 2>/dev/null || true
        pm2 start moltbot/moltbot.js --name zero-vision
    fi
    if [[ "${SYSTEMD_BRAIN}" != "true" ]]; then
        pm2 delete zero-brain 2>/dev/null || true
        pm2 start "${SCRIPT_DIR}/run_brain.sh" --name zero-brain --interpreter bash
    fi
    pm2 save
fi

if [[ "${HEADLESS}" != "true" ]]; then
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open http://localhost:1024 >/dev/null 2>&1 &
    elif command -v sensible-browser >/dev/null 2>&1; then
        sensible-browser http://localhost:1024 >/dev/null 2>&1 &
    else
        echo "OpenZero ready at http://localhost:1024"
    fi
fi

echo "OpenZero ignition complete."
