#!/bin/bash
# OPENZERO // SOVEREIGN DEPLOYMENT v4.5
echo ">>> INITIALIZING OPENZERO LATTICE..."

# 1. Install System Deps
sudo apt-get update
sudo apt-get install -y wget nodejs npm python3-pip

# 2. Fix Chrome (The Moltbot Vision Eye)
if ! command -v google-chrome-stable &> /dev/null; then
    wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo dpkg -i google-chrome-stable_current_amd64.deb
    sudo apt-get install -f -y
    sudo ln -sf /usr/bin/google-chrome-stable /usr/bin/chromium
fi

# 3. Process Management
sudo npm install -g pm2
pm2 start moltbot/moltbot.js --name "zero-vision"
pm2 start brain/app.py --name "zero-brain" --interpreter python3
pm2 save
pm2 startup

echo ">>> DEPLOYMENT COMPLETE. ACCESS AT PORT 1024."
