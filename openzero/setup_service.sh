#!/bin/bash
set -euo pipefail

MODE="${1:-server}"
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIRECTORY_OWNER="$(stat -c '%U' "${INSTALL_DIR}")"
SERVICE_USER="${OPENZERO_SERVICE_USER:-${SUDO_USER:-${DIRECTORY_OWNER}}}"
if [[ -z "${SERVICE_USER}" ]] || [[ "${SERVICE_USER}" == "root" ]]; then
    echo "Refusing to install OpenZero services as root. Set OPENZERO_SERVICE_USER to an unprivileged account." >&2
    exit 1
fi
if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    echo "OpenZero service account does not exist: ${SERVICE_USER}" >&2
    exit 1
fi
SERVICE_GROUP="$(id -gn "${SERVICE_USER}")"
NODE_BIN="${INSTALL_DIR}/.runtime/node/bin/node"
if [[ ! -x "${NODE_BIN}" ]]; then
    NODE_BIN="$(command -v node 2>/dev/null || true)"
fi
if [[ -z "${NODE_BIN}" ]] || [[ ! -x "${NODE_BIN}" ]]; then
    echo "Node.js is required for the OpenZero browser operator." >&2
    exit 1
fi

for writable_dir in \
    "${INSTALL_DIR}/.runtime" \
    "${INSTALL_DIR}/.runtime/vision-home" \
    "${INSTALL_DIR}/models" \
    "${INSTALL_DIR}/security" \
    "${INSTALL_DIR}/uploads" \
    "${INSTALL_DIR}/voice"; do
    # setup_service.sh is often invoked by root during managed deployment.
    # Create only the bounded runtime directories and ensure the unprivileged
    # service account—not root—owns the directory entry.
    sudo install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 "${writable_dir}"
done

python_works_for_service_user() {
    local candidate="$1"
    if [[ ! -x "${candidate}" ]]; then
        return 1
    fi
    if [[ "$(id -un)" == "${SERVICE_USER}" ]]; then
        "${candidate}" -c 'import flask, flask_socketio, gunicorn' >/dev/null 2>&1
    else
        sudo -u "${SERVICE_USER}" -H "${candidate}" \
            -c 'import flask, flask_socketio, gunicorn' >/dev/null 2>&1
    fi
}

PYTHON_BIN=""
for candidate in \
    "${OPENZERO_PYTHON_BIN:-}" \
    "${INSTALL_DIR}/.runtime/venv/bin/python" \
    "$(command -v python3 2>/dev/null || true)"; do
    if [[ -n "${candidate}" ]] && python_works_for_service_user "${candidate}"; then
        PYTHON_BIN="${candidate}"
        break
    fi
done
if [[ -z "${PYTHON_BIN}" ]]; then
    echo "Gunicorn and Flask must be importable by ${SERVICE_USER}. Install the pinned OpenZero requirements first." >&2
    exit 1
fi

sudo tee /etc/systemd/system/openzero-brain.service >/dev/null <<SERVICE
[Unit]
Description=OpenZero Gunicorn application
Wants=network-online.target ollama.service
After=network-online.target ollama.service
RequiresMountsFor=${INSTALL_DIR}/models

[Service]
Type=exec
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory="${INSTALL_DIR}"
Environment=PYTHONUNBUFFERED=1
Environment=PATH=${INSTALL_DIR}/.runtime/venv/bin:${INSTALL_DIR}/.runtime/bin:${INSTALL_DIR}/.runtime/node/bin:${INSTALL_DIR}/.runtime/npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
UMask=0077
ExecStart="${PYTHON_BIN}" -m gunicorn --worker-class gthread --workers 1 --threads 32 --bind 127.0.0.1:1024 --access-logfile - --error-logfile - --log-level info brain.wsgi:app
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGTERM
LimitNOFILE=65536

# The web process has no reason to acquire privilege or modify the host OS.
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths="${INSTALL_DIR}" "${INSTALL_DIR}/models"
CapabilityBoundingSet=
AmbientCapabilities=
LockPersonality=yes
ProtectClock=yes
ProtectControlGroups=yes
ProtectKernelLogs=yes
ProtectKernelModules=yes
ProtectKernelTunables=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictRealtime=yes
RestrictSUIDSGID=yes
SystemCallArchitectures=native

[Install]
WantedBy=multi-user.target
SERVICE

sudo tee /etc/systemd/system/openzero-vision.service >/dev/null <<SERVICE
[Unit]
Description=OpenZero browser-operator service
Wants=network-online.target
After=network-online.target

[Service]
Type=exec
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory="${INSTALL_DIR}"
Environment=HOME=${INSTALL_DIR}/.runtime/vision-home
Environment=PATH=${INSTALL_DIR}/.runtime/node/bin:${INSTALL_DIR}/.runtime/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
UMask=0077
ExecStart="${NODE_BIN}" "${INSTALL_DIR}/moltbot/moltbot.js"
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGTERM
LimitNOFILE=65536

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths="${INSTALL_DIR}" "${INSTALL_DIR}/models"
CapabilityBoundingSet=
AmbientCapabilities=
LockPersonality=yes
ProtectClock=yes
ProtectControlGroups=yes
ProtectKernelLogs=yes
ProtectKernelModules=yes
ProtectKernelTunables=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictRealtime=yes
RestrictSUIDSGID=yes
SystemCallArchitectures=native

[Install]
WantedBy=multi-user.target
SERVICE

sudo tee /etc/systemd/system/openzero-watchdog.service >/dev/null <<SERVICE
[Unit]
Description=OpenZero bounded health watchdog
Wants=openzero-brain.service openzero-vision.service
After=openzero-brain.service openzero-vision.service

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory="${INSTALL_DIR}"
Environment=PYTHONUNBUFFERED=1
Environment=PATH=${INSTALL_DIR}/.runtime/venv/bin:${INSTALL_DIR}/.runtime/bin:${INSTALL_DIR}/.runtime/node/bin:${INSTALL_DIR}/.runtime/npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
UMask=0077
ExecStart="${PYTHON_BIN}" "${INSTALL_DIR}/openzero_watchdog.py"
Restart=on-failure
RestartSec=10

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths="${INSTALL_DIR}" "${INSTALL_DIR}/models"
CapabilityBoundingSet=
AmbientCapabilities=
LockPersonality=yes
ProtectClock=yes
ProtectControlGroups=yes
ProtectKernelLogs=yes
ProtectKernelModules=yes
ProtectKernelTunables=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictRealtime=yes
RestrictSUIDSGID=yes
SystemCallArchitectures=native

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
# Retire the former oneshot ignition unit if upgrading an older install.
sudo systemctl disable --now openzero.service 2>/dev/null || true
sudo systemctl enable openzero-brain.service openzero-vision.service openzero-watchdog.service
sudo systemctl restart openzero-vision.service openzero-brain.service openzero-watchdog.service

if [[ "${MODE}" = "desktop" ]]; then
    echo "Desktop mode enabled. OpenZero is ready at http://localhost:1024."
fi
