#!/bin/bash
# OPENZERO: Sync System Password with Agent Brain

echo ">>> SOVEREIGN NODE PASSWORD PROTOCOL <<<"
echo -n "Enter your NEW password for user 'zero' and the Agent: "
read -s NEW_PASS
echo

# 1. Change the underlying Linux OS Password
echo "zero:$NEW_PASS" | sudo chpasswd
if [ $? -eq 0 ]; then
    echo "[SUCCESS] Linux System password updated."
else
    echo "[FAILED] You must run this script with sudo privileges."
    exit 1
fi

# 2. Inject the new password into the Agent's .env memory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ENV_FILE="$SCRIPT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    if grep -q "SUDO_PASS=" "$ENV_FILE"; then
        # Update existing entry
        sed -i "s/^SUDO_PASS=.*/SUDO_PASS=$NEW_PASS/" "$ENV_FILE"
    else
        # Add new entry
        echo "SUDO_PASS=$NEW_PASS" >> "$ENV_FILE"
    fi
    echo "[SUCCESS] Agent Brain synchronized with new root permissions."
else
    echo "[WARNING] .env file not found at $ENV_FILE. Skipping synchronization."
fi
echo ">>> Restarting Lattice..."
pm2 restart zero-brain
