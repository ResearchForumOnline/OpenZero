#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

select_python() {
    local candidate
    for candidate in \
        "${OPENZERO_PYTHON_BIN:-}" \
        "${SCRIPT_DIR}/.runtime/venv/bin/python" \
        "$(command -v python3 2>/dev/null || true)"; do
        if [[ -n "${candidate}" ]] && [[ -x "${candidate}" ]] && \
           "${candidate}" -c 'import flask, flask_socketio, gunicorn' >/dev/null 2>&1; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done
    return 1
}

if ! PYTHON_BIN="$(select_python)"; then
    echo "A Python environment containing Flask, Flask-SocketIO, and Gunicorn is required." >&2
    exit 1
fi

cd "${SCRIPT_DIR}"
exec "${PYTHON_BIN}" -m gunicorn \
    --worker-class gthread \
    --workers 1 \
    --threads "${OPENZERO_GUNICORN_THREADS:-32}" \
    --bind 127.0.0.1:1024 \
    --access-logfile - \
    --error-logfile - \
    --log-level "${OPENZERO_GUNICORN_LOG_LEVEL:-info}" \
    brain.wsgi:app
