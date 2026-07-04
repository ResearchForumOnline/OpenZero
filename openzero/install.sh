#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'
CYAN='\033[0;36m'
GOLD='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

MODE="server"
ENABLE_KALI="false"
ENABLE_ISO="false"
ENABLE_VOICE="false"
ENABLE_BITNET="false"
INSTALL_DIR="${HOME}/openzero"
RELEASE_URL="https://openzero.talktoai.org/openzero_release.zip"
TORRENT_URL="https://openzero.talktoai.org/ZeroMint_OS_v1.0.torrent"
OPENZERO_DEFAULT_MODEL="gemma4:e4b"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --server) MODE="server" ;;
        --desktop) MODE="desktop" ;;
        --update) ;;
        --kali) ENABLE_KALI="true" ;;
        --iso) ENABLE_ISO="true" ;;
        --voice) ENABLE_VOICE="true" ;;
        --bitnet) ENABLE_BITNET="true" ;;
        --dir)
            INSTALL_DIR="$2"
            shift
            ;;
        *)
            echo -e "${RED}Unknown flag: $1${NC}"
            exit 1
            ;;
    esac
    shift
done

echo -e "${GREEN}"
echo "███████ ███████ ██████  ██████"
echo "   ███  ██      ██   ██ ██  ██"
echo "  ███   █████   ██████  ██  ██"
echo " ███    ██      ██   ██ ██  ██"
echo "███████ ███████ ██   ██ ██████"
echo -e "${NC}"
echo -e "${CYAN}>>> OPENZERO 5.4 INSTALLER // MODE=${MODE^^} // KALI=${ENABLE_KALI^^} // ISO=${ENABLE_ISO^^} // BITNET=${ENABLE_BITNET^^}${NC}"

ensure_linux_packages() {
    if [ -f /etc/debian_version ]; then
        sudo apt-get update
        sudo apt-get install -y curl wget unzip git cmake build-essential python3 python3-venv python3-pip nodejs ffmpeg net-tools tmux
        if [ "${MODE}" = "desktop" ]; then
            sudo apt-get install -y xdg-utils
        fi
    elif [ -f /etc/redhat-release ]; then
        sudo yum install -y curl wget unzip git cmake gcc gcc-c++ make python3 python3-pip nodejs ffmpeg net-tools tmux
    else
        echo -e "${GOLD}Unsupported distro auto-package path. Continuing with existing tools.${NC}"
    fi

    if ! command -v npm >/dev/null 2>&1; then
        echo -e "${RED}npm is not available after installing nodejs. Install a Node.js build that includes npm, then rerun OpenZero.${NC}"
        exit 1
    fi
}

install_ollama() {
    echo -e "${CYAN}Refreshing Ollama with the official Linux installer...${NC}"
    curl -fsSL https://ollama.com/install.sh | sh
    sudo systemctl daemon-reload || true
    sudo systemctl enable ollama || true
    sudo systemctl restart ollama || sudo systemctl start ollama || true

    for attempt in $(seq 1 20); do
        if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            break
        fi
        sleep 2
    done

    echo -e "${CYAN}Pulling the preferred Gemma local track...${NC}"
    if ollama pull gemma4:e4b; then
        OPENZERO_DEFAULT_MODEL="gemma4:e4b"
    elif ollama pull gemma4:e2b; then
        OPENZERO_DEFAULT_MODEL="gemma4:e2b"
    elif ollama pull gemma3:12b; then
        OPENZERO_DEFAULT_MODEL="gemma3:12b"
    elif ollama pull gemma3:4b; then
        OPENZERO_DEFAULT_MODEL="gemma3:4b"
    else
        echo -e "${RED}Automatic Gemma pull failed.${NC}"
        echo -e "${GOLD}OpenZero will still install, but you should use the panel's Update Ollama / Repair Local Brain tools after first boot.${NC}"
    fi
}

prepare_release() {
    mkdir -p "${INSTALL_DIR}"
    cd "${INSTALL_DIR}"
    rm -rf brain hivemind knowledge moltbot static templates uploads zeromath openzero_watchdog.py openzero-kali.sh openzero_doctor.py security
    curl -fsSL -o openzero_release.zip "${RELEASE_URL}"
    unzip -o -q openzero_release.zip
    rm -f openzero_release.zip
}

install_python_dependencies() {
    cd "${INSTALL_DIR}"
    python3 -m pip install --upgrade pip --break-system-packages
    python3 -m pip install -r requirements.txt --break-system-packages
    if [ "${ENABLE_VOICE}" = "true" ]; then
        python3 -m pip install faster-whisper --break-system-packages || true
    fi
}

install_node_dependencies() {
    cd "${INSTALL_DIR}"
    sudo npm install -g pm2
    npm install express puppeteer --prefix moltbot
}

install_bitnet_runtime() {
    cd "${INSTALL_DIR}"
    if [[ ! -x "./install_bitnet.sh" ]]; then
        echo -e "${RED}BitNet installer helper is missing from this release.${NC}"
        return 1
    fi
    echo -e "${CYAN}Installing the optional Microsoft BitNet 1-bit lane...${NC}"
    if ! ./install_bitnet.sh --install --activate; then
        echo -e "${GOLD}BitNet install did not complete cleanly. OpenZero will keep the Gemma/Ollama lane active unless you repair BitNet later from the panel.${NC}"
        return 1
    fi
}

write_env_defaults() {
    cd "${INSTALL_DIR}"
    touch .env
    python3 - <<PY
from pathlib import Path

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
    "ACTIVE_MODEL": "${OPENZERO_DEFAULT_MODEL}",
    "LOCAL_ENGINE": "ollama",
    "COMP_MODE": "hybrid",
    "VISION_ENABLED": "true",
    "HIVE_MIND_ENABLED": "false",
    "FEE_OZ_COINS": "0.0",
    "FEE_ZERO_COINS": "0.0",
    "OZ_TOKEN_CA": "",
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

env_path = Path(".env")
current = {}
if env_path.exists():
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in raw and not raw.startswith("#"):
            key, value = raw.split("=", 1)
            current[key] = value

for key, value in defaults.items():
    current.setdefault(key, value)

env_path.write_text("\n".join(f"{key}={value}" for key, value in sorted(current.items())) + "\n", encoding="utf-8")
PY
    if [ "${ENABLE_VOICE}" = "true" ]; then
        sed -i 's/^VOICE_ENABLED=.*/VOICE_ENABLED=true/' .env
        sed -i 's/^VOICE_TTS_ENABLED=.*/VOICE_TTS_ENABLED=true/' .env
    fi
}

install_services() {
    cd "${INSTALL_DIR}"
    chmod +x ignite.sh janitor.sh openzero-kali.sh setup_service.sh update.sh install_bitnet.sh
    python3 openzero_doctor.py --json >/dev/null || true
    python3 openzero_doctor.py --repair-runtime --quiet >/dev/null || true
    ./setup_service.sh "${MODE}"
}

start_openzero() {
    cd "${INSTALL_DIR}"
    ./ignite.sh --headless
    if [ "${MODE}" = "desktop" ]; then
        ./ignite.sh
    fi
}

install_iso_bonus() {
    if [ "${ENABLE_ISO}" = "true" ]; then
        cd "${INSTALL_DIR}"
        curl -fsSL -o ZeroMint_OS_v1.0.torrent "${TORRENT_URL}" || true
        echo -e "${GOLD}Downloaded ZeroMint torrent descriptor to ${INSTALL_DIR}/ZeroMint_OS_v1.0.torrent${NC}"
    fi
}

ensure_linux_packages
prepare_release
install_python_dependencies
install_node_dependencies
install_ollama
write_env_defaults
install_services
if [ "${ENABLE_BITNET}" = "true" ]; then
    install_bitnet_runtime || true
fi

if [ "${ENABLE_KALI}" = "true" ]; then
    "${INSTALL_DIR}/openzero-kali.sh"
fi

install_iso_bonus
start_openzero

echo -e "${GREEN}>>> OPENZERO 5.4 ONLINE${NC}"
echo -e "${CYAN}Super Panel: http://localhost:1024${NC}"
echo -e "${CYAN}Manual: https://openzero.talktoai.org/manual${NC}"
echo -e "${CYAN}Offline builder: ${INSTALL_DIR}/build_offline_release.sh${NC}"
