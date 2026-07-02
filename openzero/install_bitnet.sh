#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${BASE_DIR}/.runtime/bitnet"
REPO_DIR="${RUNTIME_DIR}/BitNet"
VENV_DIR="${RUNTIME_DIR}/venv"
LOG_DIR="${RUNTIME_DIR}/logs"
MODEL_ROOT="${BASE_DIR}/.runtime/bitnet-models"
MODEL_SUBDIR="BitNet-b1.58-2B-4T"
MODEL_DIR="${MODEL_ROOT}/${MODEL_SUBDIR}"
MODEL_FILE="${MODEL_DIR}/ggml-model-i2_s.gguf"
TOOLCHAIN_DIR="${RUNTIME_DIR}/toolchain"
ENV_FILE="${BASE_DIR}/.env"

BITNET_REPO_URL="${BITNET_REPO_URL:-https://github.com/microsoft/BitNet.git}"
BITNET_HF_REPO="${BITNET_HF_REPO:-microsoft/bitnet-b1.58-2B-4T-gguf}"
BITNET_MODEL_ALIAS="${BITNET_MODEL_ALIAS:-bitnet-b1.58-2b-4t}"
BITNET_QUANT_TYPE="${BITNET_QUANT_TYPE:-i2_s}"
BITNET_CONTEXT_WINDOW="${BITNET_CONTEXT_WINDOW:-4096}"

ACTION="install"
ACTIVATE="false"
OUTPUT_JSON="false"
QUIET="false"

log() {
  if [[ "${QUIET}" != "true" ]]; then
    echo "$@"
  fi
}

json_escape() {
  python3 - "$1" <<'PY'
import json, sys
print(json.dumps(sys.argv[1]))
PY
}

write_env_defaults() {
  python3 - "${ENV_FILE}" "${BITNET_MODEL_ALIAS}" "${MODEL_FILE}" "${BITNET_HF_REPO}" "${BITNET_CONTEXT_WINDOW}" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
model_alias = sys.argv[2]
model_path = sys.argv[3]
hf_repo = sys.argv[4]
ctx = sys.argv[5]

current = {}
if env_path.exists():
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        current[key] = value

current["LOCAL_ENGINE"] = "bitnet"
current["BITNET_ENABLED"] = "true"
current["BITNET_MODEL_ALIAS"] = model_alias
current["BITNET_MODEL_ID"] = hf_repo
current["BITNET_MODEL_PATH"] = model_path
current["BITNET_CONTEXT_WINDOW"] = ctx
current["ACTIVE_MODEL"] = model_alias

env_path.parent.mkdir(parents=True, exist_ok=True)
env_path.write_text("\n".join(f"{key}={value}" for key, value in sorted(current.items())) + "\n", encoding="utf-8")
PY
}

reset_env_to_ollama() {
  python3 - "${ENV_FILE}" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
current = {}
if env_path.exists():
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        current[key] = value

current["LOCAL_ENGINE"] = "ollama"
current["BITNET_ENABLED"] = "false"
current.setdefault("ACTIVE_MODEL", "gemma4:e4b")
if (current.get("ACTIVE_MODEL") or "").lower().startswith("bitnet"):
    current["ACTIVE_MODEL"] = "gemma4:e4b"

env_path.parent.mkdir(parents=True, exist_ok=True)
env_path.write_text("\n".join(f"{key}={value}" for key, value in sorted(current.items())) + "\n", encoding="utf-8")
PY
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

install_prereqs_if_possible() {
  local missing=()
  for cmd in git cmake python3; do
    if ! command_exists "${cmd}"; then
      missing+=("${cmd}")
    fi
  done

  if command_exists clang || command_exists clang-19 || command_exists clang-18; then
    :
  else
    missing+=("clang")
  fi

  if [[ ${#missing[@]} -eq 0 ]]; then
    return 0
  fi

  log "BitNet prerequisites missing: ${missing[*]}"
  if command_exists apt-get && ( [[ "${EUID:-$(id -u)}" -eq 0 ]] || sudo -n true >/dev/null 2>&1 ); then
    log "Attempting to install BitNet prerequisites via apt-get..."
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
      apt-get update
      apt-get install -y git cmake python3 python3-venv python3-pip build-essential curl wget
    else
      sudo -n apt-get update
      sudo -n apt-get install -y git cmake python3 python3-venv python3-pip build-essential curl wget
    fi
  fi
}

pick_clang() {
  local chosen=""
  for candidate in clang clang-19 clang-18; do
    if command_exists "${candidate}"; then
      chosen="${candidate}"
      break
    fi
  done
  if [[ -z "${chosen}" ]]; then
    return 1
  fi
  echo "${chosen}"
}

prepare_toolchain() {
  local clang_bin
  clang_bin="$(pick_clang)"
  mkdir -p "${TOOLCHAIN_DIR}"
  ln -sf "$(command -v "${clang_bin}")" "${TOOLCHAIN_DIR}/clang"
  if command_exists "${clang_bin/clang/clang++}"; then
    ln -sf "$(command -v "${clang_bin/clang/clang++}")" "${TOOLCHAIN_DIR}/clang++"
  elif command_exists clang++; then
    ln -sf "$(command -v clang++)" "${TOOLCHAIN_DIR}/clang++"
  else
    return 1
  fi
  export PATH="${TOOLCHAIN_DIR}:${PATH}"
  export CC="${TOOLCHAIN_DIR}/clang"
  export CXX="${TOOLCHAIN_DIR}/clang++"
}

ensure_repo() {
  mkdir -p "${RUNTIME_DIR}" "${LOG_DIR}" "${MODEL_ROOT}"
  if [[ ! -d "${REPO_DIR}/.git" ]]; then
    git clone --recursive "${BITNET_REPO_URL}" "${REPO_DIR}"
  else
    git -C "${REPO_DIR}" pull --ff-only
    git -C "${REPO_DIR}" submodule update --init --recursive
  fi
}

ensure_venv() {
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    python3 -m venv "${VENV_DIR}"
  fi
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip
  "${VENV_DIR}/bin/pip" install -r "${REPO_DIR}/requirements.txt"
  "${VENV_DIR}/bin/pip" install huggingface_hub
}

download_model_snapshot() {
  mkdir -p "${MODEL_DIR}"
  "${VENV_DIR}/bin/python" - "${BITNET_HF_REPO}" "${MODEL_DIR}" "${BITNET_QUANT_TYPE}" <<'PY'
from huggingface_hub import snapshot_download
import sys

repo_id = sys.argv[1]
local_dir = sys.argv[2]
quant_type = sys.argv[3]
filename = f"ggml-model-{quant_type}.gguf"
snapshot_download(
    repo_id=repo_id,
    local_dir=local_dir,
    allow_patterns=[filename, "README.md"],
)
PY
}

install_bitnet() {
  install_prereqs_if_possible
  ensure_repo
  ensure_venv
  prepare_toolchain
  download_model_snapshot
  pushd "${REPO_DIR}" >/dev/null
  "${VENV_DIR}/bin/python" setup_env.py \
    --model-dir "${MODEL_DIR}" \
    --quant-type "${BITNET_QUANT_TYPE}" \
    --use-pretuned \
    --log-dir "${LOG_DIR}"
  popd >/dev/null

  if [[ ! -f "${MODEL_FILE}" ]]; then
    echo "BitNet model file was not produced at ${MODEL_FILE}" >&2
    exit 1
  fi
}

remove_bitnet() {
  rm -rf "${RUNTIME_DIR}" "${MODEL_DIR}"
  reset_env_to_ollama
}

status_payload() {
  local ready="false"
  local status_value="error"
  [[ -x "${VENV_DIR}/bin/python" && -f "${MODEL_FILE}" ]] && ready="true"
  [[ "${ready}" == "true" ]] && status_value="success"
  if [[ "${OUTPUT_JSON}" == "true" ]]; then
    printf '{'
    printf '"status":"%s",' "${status_value}"
    printf '"ready":%s,' "${ready}"
    printf '"repo_dir":%s,' "$(json_escape "${REPO_DIR}")"
    printf '"venv_python":%s,' "$(json_escape "${VENV_DIR}/bin/python")"
    printf '"model_file":%s,' "$(json_escape "${MODEL_FILE}")"
    printf '"model_alias":%s,' "$(json_escape "${BITNET_MODEL_ALIAS}")"
    printf '"hf_repo":%s,' "$(json_escape "${BITNET_HF_REPO}")"
    printf '"message":%s' "$(json_escape "$( [[ "${ready}" == "true" ]] && echo "BitNet runtime is ready." || echo "BitNet runtime is not ready yet." )")"
    printf '}\n'
  else
    log "BitNet ready: ${ready}"
    log "Repo: ${REPO_DIR}"
    log "Model: ${MODEL_FILE}"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install|--repair|--update) ACTION="install" ;;
    --remove|--uninstall) ACTION="remove" ;;
    --activate) ACTIVATE="true" ;;
    --json) OUTPUT_JSON="true" ;;
    --quiet) QUIET="true" ;;
    *)
      echo "Unknown flag: $1" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ "${ACTION}" == "install" ]]; then
  install_bitnet
  if [[ "${ACTIVATE}" == "true" ]]; then
    write_env_defaults
  fi
  status_payload
  exit 0
fi

remove_bitnet
if [[ "${OUTPUT_JSON}" == "true" ]]; then
  printf '{"status":"success","ready":false,"removed":true}\n'
else
  log "BitNet runtime removed."
fi
