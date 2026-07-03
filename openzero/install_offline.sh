#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="server"
ENABLE_VOICE="false"
ENABLE_BITNET="false"
INSTALL_DIR="${SCRIPT_DIR}"
OPENZERO_DEFAULT_MODEL="gemma4:e4b"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --server) MODE="server" ; shift ;;
        --desktop) MODE="desktop" ; shift ;;
        --voice) ENABLE_VOICE="true" ; shift ;;
        --bitnet) ENABLE_BITNET="true" ; shift ;;
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown flag: $1"
            exit 1
            ;;
    esac
done

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is required on the offline target before OpenZero can be installed."
    exit 1
fi

mkdir -p "${INSTALL_DIR}"

if [[ "${INSTALL_DIR}" != "${SCRIPT_DIR}" ]]; then
    tar -C "${SCRIPT_DIR}" -cf - . | tar -xf - -C "${INSTALL_DIR}"
fi

export PATH="${INSTALL_DIR}/.runtime/bin:${INSTALL_DIR}/.runtime/node/bin:${INSTALL_DIR}/.runtime/npm-global/bin:${PATH}"

mkdir -p "${INSTALL_DIR}/.runtime" "${INSTALL_DIR}/.runtime/bin" "${INSTALL_DIR}/.runtime/npm-global"

NODE_ARCHIVE="$(find "${INSTALL_DIR}/offline_assets/node" -maxdepth 1 -name 'node-v*-linux-*.tar.*' | head -n 1)"
if [[ -n "${NODE_ARCHIVE}" ]]; then
    rm -rf "${INSTALL_DIR}/.runtime/node"
    mkdir -p "${INSTALL_DIR}/.runtime/node"
    tar -xf "${NODE_ARCHIVE}" -C "${INSTALL_DIR}/.runtime/node" --strip-components=1
    ln -sf "${INSTALL_DIR}/.runtime/node/bin/node" "${INSTALL_DIR}/.runtime/bin/node"
    ln -sf "${INSTALL_DIR}/.runtime/node/bin/npm" "${INSTALL_DIR}/.runtime/bin/npm"
    ln -sf "${INSTALL_DIR}/.runtime/node/bin/npx" "${INSTALL_DIR}/.runtime/bin/npx"
fi

PM2_TGZ="$(find "${INSTALL_DIR}/offline_assets/npm" -maxdepth 1 -name 'pm2-*.tgz' | head -n 1)"
if [[ -n "${PM2_TGZ}" ]]; then
    npm install -g --prefix "${INSTALL_DIR}/.runtime/npm-global" "${PM2_TGZ}"
    ln -sf "${INSTALL_DIR}/.runtime/npm-global/bin/pm2" "${INSTALL_DIR}/.runtime/bin/pm2"
    ln -sf "${INSTALL_DIR}/.runtime/npm-global/bin/pm2-runtime" "${INSTALL_DIR}/.runtime/bin/pm2-runtime"
fi

python3 -m ensurepip --upgrade >/dev/null 2>&1 || true
python3 -m pip install --upgrade pip --break-system-packages >/dev/null 2>&1 || python3 -m pip install --user --upgrade pip
python3 -m pip install --no-index --find-links "${INSTALL_DIR}/offline_assets/wheels" -r "${INSTALL_DIR}/requirements.txt" --break-system-packages \
    || python3 -m pip install --user --no-index --find-links "${INSTALL_DIR}/offline_assets/wheels" -r "${INSTALL_DIR}/requirements.txt"

if [[ "${ENABLE_VOICE}" == "true" && -f "${INSTALL_DIR}/offline_assets/voice_requirements.txt" ]]; then
    python3 -m pip install --no-index --find-links "${INSTALL_DIR}/offline_assets/wheels" -r "${INSTALL_DIR}/offline_assets/voice_requirements.txt" --break-system-packages \
        || python3 -m pip install --user --no-index --find-links "${INSTALL_DIR}/offline_assets/wheels" -r "${INSTALL_DIR}/offline_assets/voice_requirements.txt"
fi

if [[ -f "${INSTALL_DIR}/offline_assets/ollama/ollama" ]]; then
    mkdir -p "${INSTALL_DIR}/.runtime/ollama"
    ln -sfn "${INSTALL_DIR}/offline_assets/ollama/ollama" "${INSTALL_DIR}/.runtime/ollama/ollama"
    chmod +x "${INSTALL_DIR}/offline_assets/ollama/ollama"
fi

if [[ -d "${INSTALL_DIR}/offline_assets/models" ]]; then
    mkdir -p "${INSTALL_DIR}/.runtime"
    ln -sfn "${INSTALL_DIR}/offline_assets/models" "${INSTALL_DIR}/.runtime/ollama-models"
fi

if [[ -x "${INSTALL_DIR}/.runtime/ollama/ollama" ]]; then
    export OLLAMA_MODELS="${INSTALL_DIR}/.runtime/ollama-models"
    for candidate in gemma4:e4b gemma4:e2b gemma3:12b gemma3:4b; do
        if "${INSTALL_DIR}/.runtime/ollama/ollama" list 2>/dev/null | grep -Fq "${candidate}"; then
            OPENZERO_DEFAULT_MODEL="${candidate}"
            break
        fi
    done
fi

if [[ -f "${INSTALL_DIR}/offline_assets/browser/google-chrome-stable_current_amd64.deb" && -x "$(command -v dpkg || true)" ]]; then
    sudo dpkg -i "${INSTALL_DIR}/offline_assets/browser/google-chrome-stable_current_amd64.deb" || true
fi

touch "${INSTALL_DIR}/.env"
python3 - <<PY
from pathlib import Path

env_path = Path(r"${INSTALL_DIR}") / ".env"
defaults = {
    "OPENZERO_VERSION": "5.4.0",
    "OPENZERO_DOMAIN": "https://openzero.talktoai.org",
    "OPENZERO_HIVE_URL": "https://openzero.talktoai.org/api/hive",
    "OPENZERO_HIVE_MODE": "standalone",
    "OPENZERO_HIVE_MIRRORS": "",
    "OPENZERO_HIVE_LOCAL_SPOOL_ENABLED": "true",
    "OPENZERO_HIVE_LOCAL_SPOOL_PATH": "security/hive_spool.json",
    "OPENZERO_HIVE_REPLAY_BATCH": "25",
    "OPENZERO_HIVE_SEARCH_MODE": "merge",
    "OPENZERO_HIVE_REMOTE_LOOKUP_ENABLED": "false",
    "OPENZERO_HIVE_REMOTE_LOOKUP_BACKLOG_LIMIT": "8",
    "OPENZERO_HIVE_ENDPOINT_RETRY_COOLDOWN_SECONDS": "120",
    "OPENZERO_HIVE_SHARE_MODE": "manual",
    "OPENZERO_HIVE_BLOCK_RISKY_CONTENT": "true",
    "OPENZERO_LOCAL_LEARNING_ENABLED": "true",
    "OPENZERO_LOCAL_LEARNING_TERMINAL": "false",
    "OPENZERO_AUTOMATION_ENABLED": "true",
    "OPENZERO_LOW_CPU_MODE": "true",
    "OPENZERO_CPU_PROFILE": "balanced",
    "OPENZERO_OLLAMA_THREADS": "0",
    "OPENZERO_OLLAMA_NUM_BATCH": "512",
    "OPENZERO_OLLAMA_KEEP_ALIVE": "10m",
    "BITNET_THREADS": "0",
    "OPENZERO_OFFLINE_BUNDLE": "true",
    "ACTIVE_MODEL": "${OPENZERO_DEFAULT_MODEL}",
    "LOCAL_ENGINE": "ollama",
    "COMP_MODE": "local",
    "VISION_ENABLED": "true",
    "HIVE_MIND_ENABLED": "false",
    "FEE_OZ_COINS": "0.0",
    "FEE_ZERO_COINS": "0.0",
    "OZ_TOKEN_CA": "86mnqW1TcHiFVSHHgHDf4htzs4qEGW9nr3Uzz5GjttXk",
    "PAID_HIVE_ENABLED": "false",
    "PAID_HIVE_FREE_BOOST": "true",
    "VOICE_ENABLED": "false",
    "VOICE_TTS_ENABLED": "false",
    "VOICE_AUTO_LISTEN": "false",
    "VOICE_STT_MODEL": "base",
    "VOICE_TTS_BACKEND": "piper",
    "VOICE_TTS_VOICE": "en_GB-alan-medium",
    "VOICEBOX_ENABLED": "false",
    "VOICEBOX_URL": "http://127.0.0.1:17493",
    "VOICEBOX_PROFILE": "",
    "VOICEBOX_ENGINE": "auto",
    "VOICEBOX_LANGUAGE": "en",
    "VOICEBOX_PERSONALITY": "false",
    "VOICEBOX_FALLBACK_PIPER": "true",
    "VOICEBOX_TIMEOUT_SECONDS": "180",
    "OLLAMA_AUTO_REPAIR_ENABLED": "true",
    "OLLAMA_AUTO_REPAIR_INTERVAL_MINUTES": "30",
    "OLLAMA_AUTO_UPDATE_INTERVAL_HOURS": "72",
    "BITNET_ENABLED": "false",
    "BITNET_MODEL_ID": "microsoft/bitnet-b1.58-2B-4T-gguf",
    "BITNET_MODEL_ALIAS": "bitnet-b1.58-2b-4t",
    "BITNET_MODEL_PATH": ".runtime/bitnet-models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf",
    "BITNET_CONTEXT_WINDOW": "4096",
    "BITNET_AUTO_UPDATE_INTERVAL_HOURS": "168",
    "WATCHDOG_ENABLED": "true",
    "JANITOR_PROTOCOL_ENABLED": "true",
}

current = {}
if env_path.exists():
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in raw and not raw.startswith("#"):
            key, value = raw.split("=", 1)
            current[key] = value

for key, value in defaults.items():
    current.setdefault(key, value)

if "${ENABLE_VOICE}" == "true":
    current["VOICE_ENABLED"] = "true"
    current["VOICE_TTS_ENABLED"] = "true"

env_path.write_text("\n".join(f"{key}={value}" for key, value in sorted(current.items())) + "\n", encoding="utf-8")
PY

cd "${INSTALL_DIR}"
chmod +x ignite.sh setup_service.sh janitor.sh openzero-kali.sh build_offline_release.sh install_offline.sh update.sh install_bitnet.sh

if command -v systemctl >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
    ./setup_service.sh "${MODE}" || true
fi

if [[ "${ENABLE_BITNET}" == "true" ]]; then
    if ./install_bitnet.sh --install --activate; then
        echo "BitNet add-on installed and activated."
    else
        echo "BitNet add-on did not complete cleanly. OpenZero will continue on the Gemma/Ollama lane unless you repair BitNet later."
    fi
fi

python3 "${INSTALL_DIR}/openzero_doctor.py" --repair-runtime --quiet >/dev/null 2>&1 || true
./ignite.sh --headless
if [[ "${MODE}" == "desktop" ]]; then
    ./ignite.sh
fi

echo "OpenZero offline install complete."
echo "Panel: http://localhost:1024"
