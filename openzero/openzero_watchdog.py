import json
import os
import subprocess
import sys
import time
from urllib.request import urlopen


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from brain.openzero_config import env_bool, env_int, load_env  # noqa: E402


LOG_PATH = os.path.join(BASE_DIR, "watchdog.log")
LAST_RUNTIME_REPAIR_AT = 0.0


def write_log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def run(command: str, timeout: int = 120):
    return subprocess.run(command, shell=True, text=True, capture_output=True, timeout=timeout, check=False)


def ollama_api_ready(timeout: int = 3) -> bool:
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=timeout):
            return True
    except Exception:  # noqa: BLE001
        return False


def bitnet_runtime_ready(config) -> bool:
    model_path = (config.get("BITNET_MODEL_PATH") or ".runtime/bitnet-models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf").strip()
    if not os.path.isabs(model_path):
        model_path = os.path.join(BASE_DIR, model_path)
    venv_python = os.path.join(BASE_DIR, ".runtime", "bitnet", "venv", "bin", "python")
    return os.path.exists(model_path) and os.path.exists(venv_python)


def ensure_ollama(config) -> None:
    if ollama_api_ready():
        return

    local_runtime = os.path.join(BASE_DIR, ".runtime", "ollama", "ollama")
    pm2_path = os.path.join(BASE_DIR, ".runtime", "bin", "pm2")
    if os.path.exists(local_runtime) and (os.path.exists(pm2_path) or run("command -v pm2", timeout=10).returncode == 0):
        write_log("ollama api unreachable, attempting local runtime restart via pm2")
        run("pm2 delete zero-ollama", timeout=30)
        command = (
            f'OLLAMA_MODELS="{os.path.join(BASE_DIR, ".runtime", "ollama-models")}" '
            f'pm2 start "{local_runtime}" --name zero-ollama --interpreter none -- serve'
        )
        run(command, timeout=120)
        time.sleep(4)
        if ollama_api_ready():
            return

    status = run("systemctl is-active ollama", timeout=20)
    if status.returncode != 0 or "active" not in status.stdout:
        write_log("ollama inactive, attempting restart")
        run("sudo -n systemctl restart ollama", timeout=120)


def pm2_processes():
    status = run("pm2 jlist", timeout=60)
    if status.returncode != 0 or not status.stdout.strip():
        return []
    try:
        return json.loads(status.stdout)
    except json.JSONDecodeError:
        return []


def ensure_pm2_process(name: str, command: str) -> None:
    processes = pm2_processes()
    for process in processes:
        if process.get("name") == name and process.get("pm2_env", {}).get("status") == "online":
            return
    write_log(f"{name} offline, starting with pm2")
    run(command, timeout=120)
    run("pm2 save", timeout=60)


def ensure_services() -> None:
    os.chdir(BASE_DIR)
    ensure_pm2_process("zero-vision", "pm2 start moltbot/moltbot.js --name zero-vision")
    ensure_pm2_process("zero-brain", "pm2 start brain/app.py --name zero-brain --interpreter python3")


def maybe_run_runtime_repair(config, reason: str, force: bool = False) -> None:
    global LAST_RUNTIME_REPAIR_AT

    if not env_bool(config, "OLLAMA_AUTO_REPAIR_ENABLED", True):
        return

    cooldown_seconds = max(300, env_int(config, "OLLAMA_AUTO_REPAIR_INTERVAL_MINUTES", 30) * 60)
    now = time.time()
    if not force and now - LAST_RUNTIME_REPAIR_AT < cooldown_seconds:
        return

    write_log(f"runtime repair triggered: {reason}")
    run(f'python3 "{os.path.join(BASE_DIR, "openzero_doctor.py")}" --repair-runtime --json --quiet', timeout=3600)
    LAST_RUNTIME_REPAIR_AT = now


def maybe_run_janitor(config) -> None:
    if not env_bool(config, "JANITOR_PROTOCOL_ENABLED", True):
        return
    run(f'"{os.path.join(BASE_DIR, "janitor.sh")}"', timeout=600)


def run_doctor() -> None:
    run(f'python3 "{os.path.join(BASE_DIR, "openzero_doctor.py")}" --json --quiet', timeout=600)


def main() -> None:
    write_log("OpenZero watchdog online")
    last_proactive_runtime_repair = 0.0
    while True:
        config = load_env(BASE_DIR)
        local_engine = (config.get("LOCAL_ENGINE") or "ollama").strip().lower()
        if env_bool(config, "WATCHDOG_ENABLED", True):
            if local_engine != "bitnet":
                ensure_ollama(config)
            ensure_services()

            if local_engine == "bitnet":
                if not bitnet_runtime_ready(config):
                    maybe_run_runtime_repair(config, "bitnet runtime missing")
                else:
                    proactive_interval = max(24, env_int(config, "BITNET_AUTO_UPDATE_INTERVAL_HOURS", 168)) * 3600
                    now = time.time()
                    if now - last_proactive_runtime_repair >= proactive_interval:
                        maybe_run_runtime_repair(config, "scheduled bitnet runtime sweep", force=True)
                        last_proactive_runtime_repair = now
            else:
                if not ollama_api_ready():
                    maybe_run_runtime_repair(config, "ollama api unreachable")
                else:
                    proactive_interval = max(6, env_int(config, "OLLAMA_AUTO_UPDATE_INTERVAL_HOURS", 72)) * 3600
                    now = time.time()
                    if now - last_proactive_runtime_repair >= proactive_interval:
                        maybe_run_runtime_repair(config, "scheduled ollama runtime sweep", force=True)
                        last_proactive_runtime_repair = now

            maybe_run_janitor(config)
            run_doctor()
        time.sleep(60)


if __name__ == "__main__":
    main()
