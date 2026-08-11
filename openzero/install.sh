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
ENABLE_BRAVE="auto"
ENABLE_VOICE="false"
ENABLE_BITNET="false"
ENABLE_TAB_PILOT="auto"
SKIP_MODEL="false"
INSTALL_DIR="${HOME}/openzero"
RELEASE_URL="https://openzero.talktoai.org/openzero_release.zip"
RELEASE_CHECKSUM_URL="https://openzero.talktoai.org/openzero_release.zip.sha256"
TORRENT_URL="https://openzero.talktoai.org/ZeroMint_OS_v1.0.torrent"
TAB_PILOT_URL="https://openzero.talktoai.org/tab-pilot"
OPENZERO_DEFAULT_MODEL="hf.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF:Q5_K_M"
OPENZERO_GEMMA_URL="https://huggingface.co/shafire/Zero-Gemma4-E4B-OpenZero-GGUF/resolve/main/Zero-Gemma4-E4B-OpenZero-Q5_K_M-F16-Merged.gguf?download=true"
OPENZERO_GEMMA_FILE="Zero-Gemma4-E4B-OpenZero-Q5_K_M-F16-Merged.gguf"
OPENZERO_GEMMA_SHA256="84fd62ff6c5f0abe14dd2c6135e56800df4bc4a0b9d4cd8d9f26c36b28aa190b"
OPENZERO_GEMMA_SIZE="5865235584"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --server) MODE="server" ;;
        --desktop) MODE="desktop" ;;
        --update) ;;
        --kali) ENABLE_KALI="true" ;;
        --iso) ENABLE_ISO="true" ;;
        --voice) ENABLE_VOICE="true" ;;
        --bitnet) ENABLE_BITNET="true" ;;
        --tab-pilot) ENABLE_TAB_PILOT="true" ;;
        --brave) ENABLE_BRAVE="true" ;;
        --no-brave) ENABLE_BRAVE="false" ;;
        --no-tab-pilot) ENABLE_TAB_PILOT="false" ;;
        --skip-model) SKIP_MODEL="true" ;;
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
echo -e "${CYAN}>>> OPENZERO 7.1 INSTALLER // MODE=${MODE^^} // KALI=${ENABLE_KALI^^} // ISO=${ENABLE_ISO^^} // BITNET=${ENABLE_BITNET^^} // SKIP_MODEL=${SKIP_MODEL^^}${NC}"

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

install_brave_if_requested() {
    if [[ "${ENABLE_TAB_PILOT}" == "false" ]] || [[ "${ENABLE_BRAVE}" == "false" ]]; then
        return 0
    fi
    if command -v brave-browser-stable >/dev/null 2>&1 || command -v brave-browser >/dev/null 2>&1; then
        echo -e "${GREEN}Brave is already installed.${NC}"
        return 0
    fi
    if [[ "${ENABLE_BRAVE}" != "true" ]] && [[ "${MODE}" != "desktop" ]]; then
        echo -e "${GOLD}Brave auto-install is skipped for a headless server. Use --brave to install it here.${NC}"
        return 0
    fi

    local brave_installer
    brave_installer="$(mktemp)"
    echo -e "${CYAN}Downloading Brave's official Linux installer...${NC}"
    if ! curl -fsS https://dl.brave.com/install.sh -o "${brave_installer}"; then
        rm -f "${brave_installer}"
        echo -e "${GOLD}Brave download failed; OpenZero installation will continue.${NC}"
        return 1
    fi
    if ! sh "${brave_installer}"; then
        rm -f "${brave_installer}"
        echo -e "${GOLD}Brave installation failed; OpenZero installation will continue.${NC}"
        return 1
    fi
    rm -f "${brave_installer}"
    command -v brave-browser-stable >/dev/null 2>&1 || command -v brave-browser >/dev/null 2>&1
}

install_openzero_gemma() {
    local model_dir="${INSTALL_DIR}/models"
    local target="${model_dir}/${OPENZERO_GEMMA_FILE}"
    local partial="${target}.part"
    local model_file
    local actual_size

    mkdir -p "${model_dir}"
    if [[ -f "${target}" ]] &&
       [[ "$(stat -c %s "${target}")" == "${OPENZERO_GEMMA_SIZE}" ]] &&
       echo "${OPENZERO_GEMMA_SHA256}  ${target}" | sha256sum -c - >/dev/null 2>&1; then
        echo -e "${GREEN}Verified OpenZero Gemma package already exists.${NC}"
    else
        if [[ -f "${target}" ]]; then
            local invalid_target="${target}.invalid-$(date -u +%Y%m%dT%H%M%SZ)"
            mv "${target}" "${invalid_target}"
            echo -e "${GOLD}Moved an unverified existing package to ${invalid_target}.${NC}"
        fi

        echo -e "${CYAN}Downloading the verified OpenZero Gemma default (about 5.5 GiB)...${NC}"
        if ! curl --fail --location --retry 5 --retry-all-errors --continue-at - \
            --output "${partial}" "${OPENZERO_GEMMA_URL}"; then
            echo -e "${RED}OpenZero Gemma download failed. The resumable partial file was retained.${NC}"
            return 1
        fi

        actual_size="$(stat -c %s "${partial}")"
        if [[ "${actual_size}" != "${OPENZERO_GEMMA_SIZE}" ]]; then
            echo -e "${RED}OpenZero Gemma size mismatch: received ${actual_size}, expected ${OPENZERO_GEMMA_SIZE}.${NC}"
            return 1
        fi
        if ! echo "${OPENZERO_GEMMA_SHA256}  ${partial}" | sha256sum -c -; then
            echo -e "${RED}OpenZero Gemma SHA-256 verification failed.${NC}"
            return 1
        fi
        if [[ "$(head -c 4 "${partial}")" != "GGUF" ]]; then
            echo -e "${RED}OpenZero Gemma file header is not GGUF.${NC}"
            return 1
        fi
        mv "${partial}" "${target}"
    fi

    model_file="$(mktemp)"
    printf 'FROM %s\n' "${target}" > "${model_file}"
    if ! ollama create openzerogemma -f "${model_file}"; then
        rm -f "${model_file}"
        return 1
    fi
    rm -f "${model_file}"
    OPENZERO_DEFAULT_MODEL="openzerogemma:latest"
    return 0
}

install_openzero_ministral() {
    echo -e "${CYAN}Downloading the OpenZero Ministral 8B Runtime Agent default through Ollama (about 6.1 GB)...${NC}"
    if ollama pull "${OPENZERO_DEFAULT_MODEL}"; then
        ollama show "${OPENZERO_DEFAULT_MODEL}" >/dev/null 2>&1
        return $?
    fi
    return 1
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

    if [[ "${SKIP_MODEL}" == "true" ]]; then
        echo -e "${GOLD}Skipping the default model download by request.${NC}"
        return 0
    fi

    if install_openzero_ministral; then
        echo -e "${GREEN}OpenZero Ministral 8B Runtime Agent is installed as the default local model.${NC}"
    else
        echo -e "${GOLD}OpenZero Ministral install failed; trying the verified OpenZero Gemma compatibility fallback.${NC}"
        if install_openzero_gemma; then
            echo -e "${GREEN}OpenZero Gemma is installed as the compatibility fallback.${NC}"
        elif ollama pull gemma4:e4b; then
            OPENZERO_DEFAULT_MODEL="gemma4:e4b"
        elif ollama pull gemma4:e2b; then
            OPENZERO_DEFAULT_MODEL="gemma4:e2b"
        elif ollama pull gemma3:4b; then
            OPENZERO_DEFAULT_MODEL="gemma3:4b"
        else
            echo -e "${RED}Automatic local model installation failed.${NC}"
            echo -e "${GOLD}OpenZero will still install. Use the animated model cards in the panel after first boot.${NC}"
        fi
    fi
}

prepare_release() {
    local stage
    local payload
    local backup
    stage="$(mktemp -d)"
    payload="${stage}/payload"
    backup="${INSTALL_DIR}/backups/update-$(date -u +%Y%m%dT%H%M%SZ)"
    mkdir -p "${payload}" "${INSTALL_DIR}"

    curl -fsSL -o "${stage}/openzero_release.zip" "${RELEASE_URL}"
    curl -fsSL -o "${stage}/openzero_release.zip.sha256" "${RELEASE_CHECKSUM_URL}"
    (
        cd "${stage}"
        sha256sum -c openzero_release.zip.sha256
    )
    unzip -q "${stage}/openzero_release.zip" -d "${payload}"

    python3 - "${payload}" "${INSTALL_DIR}" "${backup}" <<'PY'
from pathlib import Path
import shutil
import sys

payload = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2]).resolve()
backup = Path(sys.argv[3]).resolve()

if not (payload / "brain" / "app.py").is_file() or not (payload / "install.sh").is_file():
    raise SystemExit("Release payload is missing required OpenZero files.")

managed = [path for path in payload.rglob("*") if path.is_file()]
for source in managed:
    relative = source.relative_to(payload)
    destination = target / relative
    if destination.exists() and destination.is_file():
        backup_path = backup / relative
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destination, backup_path)

for source in managed:
    relative = source.relative_to(payload)
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

print(f"Updated {len(managed)} managed files.")
if backup.exists():
    print(f"Rollback copy: {backup}")
PY

    rm -rf "${stage}"
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
    "OPENZERO_VERSION": "7.1.0",
    "OPENZERO_DOMAIN": "https://openzero.talktoai.org",
    "OPENZERO_TAB_PILOT_URL": "${TAB_PILOT_URL}",
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
    "OPENZERO_BIND_HOST": "127.0.0.1",
    "OPENZERO_ALLOW_PUBLIC_BIND": "false",
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

legacy_defaults = {
    "gemma2",
    "gemma2:2b",
    "gemma2:9b",
    "gemma4:e2b",
    "gemma4:e4b",
    "gemma3:4b",
    "gemma3:12b",
}
managed_previous_defaults = legacy_defaults | {
    "openzerogemma:latest",
    "hf.co/shafire/OpenZero-Qwen3-1.7B-Agentic-GGUF:Q4_K_M",
}
if current.get("ACTIVE_MODEL", "") in managed_previous_defaults:
    current["ACTIVE_MODEL"] = "${OPENZERO_DEFAULT_MODEL}"
if current.get("NODE_RECOMMENDED_MODEL", "") in managed_previous_defaults:
    current["NODE_RECOMMENDED_MODEL"] = "${OPENZERO_DEFAULT_MODEL}"

# Version is release metadata, not a private user preference. Always migrate it.
current["OPENZERO_VERSION"] = "7.1.0"

env_path.write_text("\n".join(f"{key}={value}" for key, value in sorted(current.items())) + "\n", encoding="utf-8")
PY
    if [ "${ENABLE_VOICE}" = "true" ]; then
        sed -i 's/^VOICE_ENABLED=.*/VOICE_ENABLED=true/' .env
        sed -i 's/^VOICE_TTS_ENABLED=.*/VOICE_TTS_ENABLED=true/' .env
    fi
}

install_services() {
    cd "${INSTALL_DIR}"
    chmod +x ignite.sh janitor.sh openzero-kali.sh setup_service.sh update.sh install_bitnet.sh install-tab-pilot.sh
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
install_brave_if_requested || true

if [[ "${ENABLE_TAB_PILOT}" != "false" ]] && \
   { command -v brave-browser-stable >/dev/null 2>&1 || command -v brave-browser >/dev/null 2>&1; }; then
    if ! "${INSTALL_DIR}/install-tab-pilot.sh" --dir "${INSTALL_DIR}"; then
        echo -e "${GOLD}Tab Pilot automatic setup did not complete. Use ${TAB_PILOT_URL} for guided setup.${NC}"
    fi
fi

echo -e "${GREEN}>>> OPENZERO 7.1 ONLINE${NC}"
echo -e "${CYAN}Super Panel: http://localhost:1024${NC}"
echo -e "${CYAN}Manual: https://openzero.talktoai.org/manual${NC}"
echo -e "${CYAN}Brave Tab Pilot guided setup: ${TAB_PILOT_URL}${NC}"
echo -e "${CYAN}Offline builder: ${INSTALL_DIR}/build_offline_release.sh${NC}"

if [[ "${MODE}" == "desktop" ]] && [[ "${ENABLE_TAB_PILOT}" != "false" ]] && command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${TAB_PILOT_URL}" >/dev/null 2>&1 || true
fi
