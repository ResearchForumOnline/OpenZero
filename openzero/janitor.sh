#!/bin/bash
# OPENZERO // SOVEREIGN JANITOR PROTOCOL
# Self-preservation: Prune visual cortex data to prevent storage exhaustion.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${SCRIPT_DIR}/static"
LOG_PATH="${SCRIPT_DIR}/janitor.log"
MAX_FILES=50

if [ -d "$TARGET_DIR" ]; then
    cd "$TARGET_DIR" || exit
    
    # Count existing visual snapshots
    FILE_COUNT=$(ls -1 *.png 2>/dev/null | wc -l)

    if [ "$FILE_COUNT" -gt "$MAX_FILES" ]; then
        # Identify and purge older files, retaining only the freshest $MAX_FILES
        ls -t *.png | tail -n +$((MAX_FILES + 1)) | xargs -I {} rm -f {}
        echo "[$(date)] SYSTEM: Purged $((FILE_COUNT - MAX_FILES)) stale visual snapshots to preserve lattice integrity." >> "${LOG_PATH}"
    fi
fi
