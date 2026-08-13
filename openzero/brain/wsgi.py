"""Production WSGI entrypoint for OpenZero.

Gunicorn imports this module instead of executing ``brain/app.py`` directly.
The application recovery and heartbeat hooks normally live behind app.py's
``__main__`` guard, so initialise them once for the single worker used by the
supported service configuration.
"""

from __future__ import annotations

import threading

from brain.app import app, heartbeat_loop, recover_autonomous_runs


_runtime_lock = threading.Lock()
_runtime_started = False


def _start_runtime() -> None:
    global _runtime_started
    with _runtime_lock:
        if _runtime_started:
            return
        recover_autonomous_runs()
        threading.Thread(
            target=heartbeat_loop,
            name="openzero-heartbeat",
            daemon=True,
        ).start()
        _runtime_started = True


_start_runtime()

# Some WSGI tooling looks for ``application`` by convention.
application = app
