#!/bin/bash
set -euo pipefail

INSTALL_DIR="${HOME}/openzero"
VERSION="0.3.1"
RELEASE_BASE_URL="${OPENZERO_RELEASE_BASE_URL:-https://github.com/ResearchForumOnline/OpenZero/releases/download/v7.3.0}"
ARCHIVE_NAME="OpenZero-Tab-Pilot-v${VERSION}.zip"
MODEL="hf.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF:Q5_K_M"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir) INSTALL_DIR="$2"; shift ;;
        --model) MODEL="$2"; shift ;;
        *) echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
    shift
done

if [[ ! -f "${INSTALL_DIR}/brain/app.py" ]]; then
    echo "OpenZero was not found at ${INSTALL_DIR}." >&2
    exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT
curl -fsSL "${RELEASE_BASE_URL}/${ARCHIVE_NAME}" -o "${STAGE}/${ARCHIVE_NAME}"
curl -fsSL "${RELEASE_BASE_URL}/${ARCHIVE_NAME}.sha256" -o "${STAGE}/${ARCHIVE_NAME}.sha256"

python3 - "${STAGE}" "${INSTALL_DIR}" "${ARCHIVE_NAME}" "${VERSION}" <<'PY'
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath

stage, install_dir = map(Path, sys.argv[1:3])
archive_name, version = sys.argv[3:5]
fields = (stage / (archive_name + ".sha256")).read_text(encoding="ascii").split()
if len(fields) != 2 or fields[1] != archive_name or len(fields[0]) != 64:
    raise SystemExit("Invalid extension checksum file.")
digest = hashlib.sha256((stage / archive_name).read_bytes()).hexdigest()
if digest != fields[0].lower():
    raise SystemExit("Extension checksum mismatch.")
payload = stage / "extension"
with zipfile.ZipFile(stage / archive_name) as package:
    for entry in package.infolist():
        name = PurePosixPath(entry.filename)
        if name.is_absolute() or ".." in name.parts or "\\" in entry.filename or ":" in entry.filename:
            raise SystemExit("Unsafe extension archive path.")
        if (entry.external_attr >> 16) & 0o170000 == 0o120000:
            raise SystemExit("Extension archive must not contain symlinks.")
    package.extractall(payload)
manifest = json.loads((payload / "manifest.json").read_text(encoding="utf-8"))
if manifest.get("version") != version:
    raise SystemExit("Extension version does not match the release.")
target = install_dir / "extensions" / ("tab-pilot-" + version)
if target.exists():
    raise SystemExit(f"Target already exists; review it before replacing: {target}")
target.parent.mkdir(parents=True, exist_ok=True)
shutil.move(str(payload), str(target))
print(f"Verified extension prepared at: {target}")
PY

echo "Finish in Brave or another Chromium browser:"
echo "1. Open the browser's extension settings and enable Developer mode."
echo "2. Choose Load unpacked: ${INSTALL_DIR}/extensions/tab-pilot-${VERSION}"
echo "3. Generate a scoped Tab Pilot token in the local OpenZero panel."
echo "4. Paste it into extension Options; endpoint http://127.0.0.1:1024, model ${MODEL}."
echo "No browser-wide policy or mandatory central update service is installed."
echo "For a remote node, use your own SSH tunnel; never send tokens over plain remote HTTP."
