#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/dist"
MODELS_PATH="${OLLAMA_MODELS:-}"
WITH_VOICE="false"
BUNDLE_BASENAME="openzero_offline_release"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --models-path)
            MODELS_PATH="$2"
            shift 2
            ;;
        --with-voice)
            WITH_VOICE="true"
            shift
            ;;
        *)
            echo "Unknown flag: $1"
            exit 1
            ;;
    esac
done

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1"
        exit 1
    fi
}

detect_models_path() {
    local candidate
    for candidate in \
        "${MODELS_PATH}" \
        "${HOME}/.ollama/models" \
        "/usr/share/ollama/.ollama/models" \
        "/var/lib/ollama/.ollama/models" \
        "/root/.ollama/models"; do
        if [[ -n "${candidate}" && -d "${candidate}" && ( -d "${candidate}/blobs" || -d "${candidate}/manifests" ) ]]; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done
    return 1
}

download_node_runtime() {
    local node_version node_arch node_url node_target

    node_version="$(node --version | sed 's/^v//')"
    case "$(uname -m)" in
        x86_64) node_arch="x64" ;;
        aarch64|arm64) node_arch="arm64" ;;
        *)
            echo "Unsupported Node runtime architecture: $(uname -m)"
            exit 1
            ;;
    esac

    node_url="https://nodejs.org/dist/v${node_version}/node-v${node_version}-linux-${node_arch}.tar.xz"
    node_target="${BUNDLE_DIR}/offline_assets/node/node-v${node_version}-linux-${node_arch}.tar.xz"
    curl -fsSL "${node_url}" -o "${node_target}"
}

pack_pm2() {
    local pm2_version
    pm2_version="$(pm2 --version 2>/dev/null | tail -n 1 | tr -d '\r')"
    if [[ -z "${pm2_version}" ]]; then
        echo "Unable to detect PM2 version. Install PM2 before building the offline bundle."
        exit 1
    fi

    (
        cd "${TMPDIR}"
        npm pack "pm2@${pm2_version}" --silent >/dev/null
        cp pm2-*.tgz "${BUNDLE_DIR}/offline_assets/npm/"
    )
}

copy_project_tree() {
    mkdir -p "${BUNDLE_DIR}"
    tar -C "${SCRIPT_DIR}" -cf - \
        --exclude='./.git' \
        --exclude='./.runtime' \
        --exclude='./brain/venv' \
        --exclude='./dist' \
        --exclude='./uploads/*' \
        --exclude='./static/screenshots/*' \
        --exclude='./security/*' \
        --exclude='./__pycache__' \
        --exclude='./brain/__pycache__' \
        --exclude='./hivemind/__pycache__' \
        --exclude='./moltbot/node_modules/.cache' \
        --exclude='./*.tar.gz' \
        --exclude='./*.zip' \
        --exclude='./.env' \
        . | tar -xf - -C "${BUNDLE_DIR}"
}

prepare_python_wheels() {
    python3 -m pip wheel --wheel-dir "${BUNDLE_DIR}/offline_assets/wheels" -r "${SCRIPT_DIR}/requirements.txt"
    if [[ "${WITH_VOICE}" == "true" ]]; then
        printf 'faster-whisper==1.2.0\n' > "${BUNDLE_DIR}/offline_assets/voice_requirements.txt"
        python3 -m pip wheel --wheel-dir "${BUNDLE_DIR}/offline_assets/wheels" -r "${BUNDLE_DIR}/offline_assets/voice_requirements.txt"
    fi
}

prepare_node_modules() {
    if [[ ! -d "${BUNDLE_DIR}/moltbot/node_modules" ]]; then
        npm install express puppeteer --prefix "${BUNDLE_DIR}/moltbot"
    fi
}

prepare_ollama_binary() {
    local ollama_bin

    ollama_bin="$(command -v ollama || true)"
    if [[ -z "${ollama_bin}" ]]; then
        echo "Ollama is required on the builder node so the offline bundle can carry a working local runtime."
        exit 1
    fi

    cp "${ollama_bin}" "${BUNDLE_DIR}/offline_assets/ollama/ollama"
    chmod +x "${BUNDLE_DIR}/offline_assets/ollama/ollama"
}

prepare_models() {
    local source_models

    source_models="$(detect_models_path)" || {
        echo "Unable to find an Ollama model store. Pull gemma4:e4b on this builder node first, or rerun with sudo plus --models-path /path/to/models."
        exit 1
    }

    cp -a "${source_models}/." "${BUNDLE_DIR}/offline_assets/models/"
}

prepare_browser_asset() {
    local chrome_deb
    chrome_deb="${SCRIPT_DIR}/google-chrome-stable_current_amd64.deb"

    if [[ -f "${chrome_deb}" ]]; then
        cp "${chrome_deb}" "${BUNDLE_DIR}/offline_assets/browser/"
    elif [[ "$(uname -m)" == "x86_64" ]]; then
        curl -fsSL "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb" \
            -o "${BUNDLE_DIR}/offline_assets/browser/google-chrome-stable_current_amd64.deb"
    fi
}

write_manifest() {
    local manifest_path models_listing
    manifest_path="${BUNDLE_DIR}/offline_assets/BUNDLE_MANIFEST.txt"
    models_listing="Unavailable"

    if command -v ollama >/dev/null 2>&1; then
        models_listing="$(ollama list 2>/dev/null || echo "Unavailable")"
    fi

    cat > "${manifest_path}" <<EOF
OPENZERO OFFLINE RELEASE MANIFEST
Built: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
Builder: $(whoami)@$(hostname)
Source: ${SCRIPT_DIR}
Voice Wheels Included: ${WITH_VOICE}
Primary Bundle Name: ${BUNDLE_BASENAME}.tar.gz

CONTENTS
- OpenZero source tree with no private .env or security directory
- Python wheelhouse for runtime installation
- Local Node.js runtime archive
- PM2 npm package tarball
- Moltbot node_modules
- Ollama binary
- Local Ollama model store
- Optional Chrome .deb if available

OLLAMA MODELS DETECTED
${models_listing}
EOF
}

package_bundle() {
    local timestamped_bundle latest_bundle

    mkdir -p "${OUTPUT_DIR}"
    latest_bundle="${OUTPUT_DIR}/${BUNDLE_BASENAME}.tar.gz"
    timestamped_bundle="${OUTPUT_DIR}/${BUNDLE_BASENAME}_$(date +%Y%m%d_%H%M%S).tar.gz"

    tar -C "${TMPDIR}" -czf "${timestamped_bundle}" "${BUNDLE_BASENAME}"
    cp "${timestamped_bundle}" "${latest_bundle}"
    sha256sum "${timestamped_bundle}" | tee "${timestamped_bundle}.sha256" >/dev/null
    sha256sum "${latest_bundle}" | tee "${latest_bundle}.sha256" >/dev/null

    echo "Offline bundle ready:"
    echo "  ${timestamped_bundle}"
    echo "  ${latest_bundle}"
    echo "Upload ${latest_bundle} to your web root if you want a stable public offline download URL."
}

require_cmd tar
require_cmd curl
require_cmd python3
require_cmd node
require_cmd npm
require_cmd pm2

TMPDIR="$(mktemp -d)"
trap 'rm -rf "${TMPDIR}"' EXIT
BUNDLE_DIR="${TMPDIR}/${BUNDLE_BASENAME}"

mkdir -p \
    "${BUNDLE_DIR}/offline_assets/wheels" \
    "${BUNDLE_DIR}/offline_assets/node" \
    "${BUNDLE_DIR}/offline_assets/npm" \
    "${BUNDLE_DIR}/offline_assets/ollama" \
    "${BUNDLE_DIR}/offline_assets/models" \
    "${BUNDLE_DIR}/offline_assets/browser"

copy_project_tree
prepare_python_wheels
prepare_node_modules
download_node_runtime
pack_pm2
prepare_ollama_binary
prepare_models
prepare_browser_asset
write_manifest
package_bundle
