#!/bin/bash
set -euo pipefail

MODE="${1:-server}"
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_USER="$(whoami)"

sudo tee /etc/systemd/system/openzero.service >/dev/null <<SERVICE
[Unit]
Description=OpenZero boot ignition
After=network.target

[Service]
Type=oneshot
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=/bin/bash ${INSTALL_DIR}/ignite.sh --headless
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SERVICE

sudo tee /etc/systemd/system/openzero-watchdog.service >/dev/null <<SERVICE
[Unit]
Description=OpenZero self-healing watchdog
After=openzero.service

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/openzero_watchdog.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable openzero.service openzero-watchdog.service
sudo systemctl restart openzero.service openzero-watchdog.service

if [ "${MODE}" = "desktop" ]; then
    echo "Desktop mode enabled. OpenZero UI will open when ignite.sh runs without --headless."
fi
