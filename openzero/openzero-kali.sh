#!/bin/bash
set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}>>> OPENZERO KALIZERO CONVERSION STARTING...${NC}"

if [ -f /etc/debian_version ]; then
    sudo apt-get update
    sudo apt-get install -y nmap sqlmap hydra gobuster ffuf john tcpdump net-tools
fi

cd "$HOME/openzero" || exit 1

if [ -f .env ]; then
    python3 - <<'PY'
from pathlib import Path

env_path = Path(".env")
lines = {}
if env_path.exists():
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in raw and not raw.startswith("#"):
            key, value = raw.split("=", 1)
            lines[key] = value

lines["NODE_ROLE"] = "security"
lines["WATCHDOG_ENABLED"] = "true"
lines["JANITOR_PROTOCOL_ENABLED"] = "true"

env_path.write_text("\n".join(f"{key}={value}" for key, value in sorted(lines.items())) + "\n", encoding="utf-8")
PY
fi

echo -e "${GREEN}>>> KALIZERO MODE READY. Role set to security and pentest toolset installed.${NC}"
