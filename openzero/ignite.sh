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

pm2 delete zero-vision zero-brain 2>/dev/null || true
pm2 start moltbot/moltbot.js --name zero-vision
pm2 start brain/app.py --name zero-brain --interpreter python3
pm2 save

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
