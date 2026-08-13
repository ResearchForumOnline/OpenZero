#!/bin/bash
set -euo pipefail

# Compatibility entrypoint retained for older documentation and automation.
# The primary installer owns dependency installation, verified release staging,
# the unprivileged runtime venv, and hardened systemd services.  Keeping a
# second deployment implementation here previously bypassed those controls and
# could launch duplicate PM2 processes.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${OPENZERO_INSTALL_DIR:-${SCRIPT_DIR}}"

echo ">>> deploy_node.sh now delegates to the verified OpenZero installer."
exec "${SCRIPT_DIR}/install.sh" --server --dir "${INSTALL_DIR}" "$@"
