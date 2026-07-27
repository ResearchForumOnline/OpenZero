#!/bin/bash
set -euo pipefail

INSTALL_DIR="${HOME}/openzero"
EXTENSION_ID="bjjhckhjkjodankbndllgloanjnfmlmo"
UPDATE_MANIFEST_URL="https://openzero.talktoai.org/downloads/tab-pilot-updates.xml"
CRX_URL="https://openzero.talktoai.org/downloads/OpenZero-Tab-Pilot-Brave-v0.2.0.crx"
MODEL="openzerogemma:latest"
POLICY_DIR="/etc/brave/policies/managed"
POLICY_PATH="${POLICY_DIR}/openzero-tab-pilot.json"

if [[ -f "./brain/app.py" && -f "./.env" ]]; then
    INSTALL_DIR="$(pwd)"
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)
            INSTALL_DIR="$2"
            shift
            ;;
        --model)
            MODEL="$2"
            shift
            ;;
        *)
            echo "Unknown flag: $1" >&2
            exit 1
            ;;
    esac
    shift
done

if ! command -v brave-browser-stable >/dev/null 2>&1 && ! command -v brave-browser >/dev/null 2>&1; then
    echo "Brave is not installed. Tab Pilot policy was not changed."
    exit 2
fi
if [[ ! -f "${INSTALL_DIR}/brain/app.py" ]]; then
    echo "OpenZero was not found at ${INSTALL_DIR}." >&2
    exit 1
fi

curl -fsS "${UPDATE_MANIFEST_URL}" >/dev/null
curl -fsS --range 0-31 "${CRX_URL}" >/dev/null

PAIR_RESPONSE="$(mktemp)"
POLICY_TEMP="$(mktemp)"
trap 'rm -f "${PAIR_RESPONSE}" "${POLICY_TEMP}"' EXIT

ready="false"
for _ in $(seq 1 45); do
    if curl -fsS -X POST \
        -H "Content-Type: application/json" \
        -d '{"action":"rotate"}' \
        -o "${PAIR_RESPONSE}" \
        http://127.0.0.1:1024/api/tab-pilot/key; then
        ready="true"
        break
    fi
    sleep 1
done
if [[ "${ready}" != "true" ]]; then
    echo "OpenZero did not become ready on 127.0.0.1:1024." >&2
    exit 1
fi

python3 - "${PAIR_RESPONSE}" "${POLICY_TEMP}" "${EXTENSION_ID}" "${UPDATE_MANIFEST_URL}" "${MODEL}" <<'PY'
import json
import os
import sys

response_path, policy_path, extension_id, update_url, model = sys.argv[1:]
payload = json.loads(open(response_path, encoding="utf-8").read())
token = str(payload.get("api_key") or "")
if not token.startswith("oztp_") or len(token) < 32:
    raise SystemExit("OpenZero did not return a valid scoped Tab Pilot token.")
policy = {
    "ExtensionInstallForcelist": [f"{extension_id};{update_url}"],
    "3rdparty": {
        "extensions": {
            extension_id: {
                "policy": {
                    "apiBaseUrl": "http://127.0.0.1:1024",
                    "apiKey": token,
                    "model": model,
                }
            }
        }
    },
}
with open(policy_path, "w", encoding="utf-8", newline="\n") as handle:
    json.dump(policy, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.chmod(policy_path, 0o600)
PY

sudo install -d -m 755 "${POLICY_DIR}"
sudo install -m 644 "${POLICY_TEMP}" "${POLICY_PATH}"

echo "OpenZero Tab Pilot managed installation is configured."
echo "Extension ID: ${EXTENSION_ID}"
echo "Policy: ${POLICY_PATH}"
echo "Brave will install it automatically; restart Brave if it does not appear within a minute."
