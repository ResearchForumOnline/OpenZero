#!/bin/bash
# OPENZERO: Hugging Face -> Ollama Bridge

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS_DIR="${SCRIPT_DIR}/models"
NEW_MODEL_NAME=$1
GGUF_FILE=$2

mkdir -p "$MODELS_DIR"

if [ -z "$NEW_MODEL_NAME" ] || [ -z "$GGUF_FILE" ]; then
    echo ">>> OPENZERO LOCAL MODEL BRIDGE <<<"
    echo "Files currently resting in $MODELS_DIR:"
    ls -lh "$MODELS_DIR"/*.gguf 2>/dev/null | awk '{print " -", $9, "(" $5 ")"}'
    echo ""
    echo "USAGE: ./hf_bridge.sh [NAME_FOR_OLLAMA] [FILE_NAME.gguf]"
    echo "Example: ./hf_bridge.sh shafire shafire-9b-q4.gguf"
    exit 1
fi

if [ ! -f "$MODELS_DIR/$GGUF_FILE" ]; then
    echo "GGUF file not found in $MODELS_DIR: $GGUF_FILE"
    echo "Native Ollama pulls (for example gemma4:e4b) live in Ollama's own model store."
    echo "This bridge is only for custom GGUF files copied into ./models."
    exit 1
fi

echo ">>> Injecting $GGUF_FILE into Lattice as '$NEW_MODEL_NAME'..."
echo "FROM $MODELS_DIR/$GGUF_FILE" > /tmp/Modelfile
ollama create $NEW_MODEL_NAME -f /tmp/Modelfile
rm -f /tmp/Modelfile

echo ">>> INJECTION COMPLETE."
echo "You can now update your UI settings to use ACTIVE_MODEL=$NEW_MODEL_NAME"
