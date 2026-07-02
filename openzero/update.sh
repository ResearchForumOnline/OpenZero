#!/bin/bash
set -euo pipefail

MODE="server"
INSTALL_DIR="${HOME}/openzero"
ENABLE_KALI="false"
ENABLE_ISO="false"
ENABLE_VOICE="false"
ENABLE_BITNET="false"

if [[ -f "./ignite.sh" && -f "./openzero_doctor.py" && -d "./brain" ]]; then
    INSTALL_DIR="$(pwd)"
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --server) MODE="server" ;;
        --desktop) MODE="desktop" ;;
        --kali) ENABLE_KALI="true" ;;
        --iso) ENABLE_ISO="true" ;;
        --voice) ENABLE_VOICE="true" ;;
        --bitnet) ENABLE_BITNET="true" ;;
        --dir)
            INSTALL_DIR="$2"
            shift
            ;;
        *)
            echo "Unknown flag: $1"
            exit 1
            ;;
    esac
    shift
done

ENV_FILE="${INSTALL_DIR}/.env"
if [[ "${ENABLE_BITNET}" != "true" && -f "${ENV_FILE}" ]]; then
    if grep -Eq '^(LOCAL_ENGINE=bitnet|BITNET_ENABLED=true|ACTIVE_MODEL=bitnet-b1\.58-2b-4t)$' "${ENV_FILE}"; then
        ENABLE_BITNET="true"
    fi
fi

TMP_INSTALL_SCRIPT="$(mktemp)"
trap 'rm -f "${TMP_INSTALL_SCRIPT}"' EXIT

curl -fsSL https://openzero.talktoai.org/install.sh -o "${TMP_INSTALL_SCRIPT}"
chmod +x "${TMP_INSTALL_SCRIPT}"

ARGS=( "--${MODE}" "--dir" "${INSTALL_DIR}" )
if [[ "${ENABLE_KALI}" == "true" ]]; then
    ARGS+=( "--kali" )
fi
if [[ "${ENABLE_ISO}" == "true" ]]; then
    ARGS+=( "--iso" )
fi
if [[ "${ENABLE_VOICE}" == "true" ]]; then
    ARGS+=( "--voice" )
fi
if [[ "${ENABLE_BITNET}" == "true" ]]; then
    ARGS+=( "--bitnet" )
fi

exec bash "${TMP_INSTALL_SCRIPT}" "${ARGS[@]}"
