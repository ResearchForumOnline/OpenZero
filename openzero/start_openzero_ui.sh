#!/bin/bash
trap "kill 0" EXIT

echo ">>> WAKING UP OLLAMA..."
ollama serve > /dev/null 2>&1 &
sleep 5

echo ">>> WAKING UP MOLTBOT..."
cd $HOME/openzero/moltbot && node moltbot.js > /dev/null 2>&1 &

echo ">>> STARTING BRAIN (PORT 1024)..."
cd $HOME/openzero/brain && source venv/bin/activate && python3 app.py
