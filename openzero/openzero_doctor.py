import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import time
from typing import Dict, List
from urllib.error import URLError
from urllib.request import urlopen


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.join(BASE_DIR, "brain") not in sys.path:
    sys.path.insert(0, os.path.join(BASE_DIR, "brain"))

from brain.integrity import ensure_integrity_state, integrity_status, protected_paths  # noqa: E402
from brain.openzero_config import DEFAULTS, env_bool, env_int, load_env, resource_profile, save_env_values  # noqa: E402


RUNTIME_STATE_PATH = os.path.join(BASE_DIR, "security", "runtime_state.json")
RUNTIME_OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
BITNET_INSTALL_SCRIPT = os.path.join(BASE_DIR, "install_bitnet.sh")
BITNET_DEFAULT_ALIAS = "bitnet-b1.58-2b-4t"
CURRENT_DEFAULT_LOCAL_MODEL = DEFAULTS["ACTIVE_MODEL"]
LOCAL_MODEL_CANDIDATES_SMALL = [CURRENT_DEFAULT_LOCAL_MODEL, "openzerogemma:latest", "gemma4:e2b", "gemma3:4b"]
LOCAL_MODEL_CANDIDATES_BASE = [CURRENT_DEFAULT_LOCAL_MODEL, "openzerogemma:latest", "gemma4:e4b", "gemma4:e2b"]
LOCAL_MODEL_CANDIDATES_HEAVY = [CURRENT_DEFAULT_LOCAL_MODEL, "openzerogemma:latest", "gemma4:26b", "gemma3:12b"]
LOCAL_MODEL_CANDIDATES_ULTRA = [CURRENT_DEFAULT_LOCAL_MODEL, "openzerogemma:latest", "gemma4:31b", "gemma4:26b"]
LEGACY_LOCAL_MODEL_MAP = {
    "gemma2": "openzerogemma:latest",
    "gemma2:2b": "openzerogemma:latest",
    "gemma2:9b": "openzerogemma:latest",
    "qwen2.5:14b": "openzerogemma:latest",
    "qwen2.5:32b": "openzerogemma:latest",
    "qwenq8": "openzerogemma:latest",
    "qwenq8:latest": "openzerogemma:latest",
}
LOCAL_MODEL_HINT_PREFIXES = ("hf.co/", "gemma", "qwenq8", "phi", "mistral", "llama", "deepseek", "codestral", "bitnet")
CLOUD_MODEL_HINT_PREFIXES = ("groq/", "openai/", "qwen/", "meta/", "gemini", "claude", "gpt", "compound")


def run_command(command: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(command, shell=True, text=True, capture_output=True, timeout=timeout, check=False)


def runtime_candidates(env: Dict[str, str]) -> List[str]:
    profile = resource_profile(env)
    ram_gb = int(profile["ram_gb"])
    if ram_gb < 12:
        profile_candidates = LOCAL_MODEL_CANDIDATES_SMALL
    elif ram_gb < 24:
        profile_candidates = LOCAL_MODEL_CANDIDATES_BASE
    elif ram_gb < 48:
        profile_candidates = LOCAL_MODEL_CANDIDATES_HEAVY
    else:
        profile_candidates = LOCAL_MODEL_CANDIDATES_ULTRA

    ordered = [
        env.get("ACTIVE_MODEL", ""),
        env.get("NODE_RECOMMENDED_MODEL", ""),
        *profile_candidates,
    ]
    result = []
    for candidate in ordered:
        normalized = normalize_local_model(candidate)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def normalize_local_model(model_name: str) -> str:
    normalized = (model_name or "").strip()
    if not normalized:
        return ""
    return LEGACY_LOCAL_MODEL_MAP.get(normalized.lower(), normalized)


def bitnet_selected(env: Dict[str, str]) -> bool:
    engine = (env.get("LOCAL_ENGINE") or "ollama").strip().lower()
    active_model = normalize_local_model(env.get("ACTIVE_MODEL", ""))
    return engine == "bitnet" or active_model == BITNET_DEFAULT_ALIAS


def bitnet_status(env: Dict[str, str]) -> Dict[str, object]:
    model_path = env.get("BITNET_MODEL_PATH") or ".runtime/bitnet-models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf"
    if not os.path.isabs(model_path):
        model_path = os.path.join(BASE_DIR, model_path)
    venv_python = os.path.join(BASE_DIR, ".runtime", "bitnet", "venv", "bin", "python")
    return {
        "selected": bitnet_selected(env),
        "ready": os.path.exists(model_path) and os.path.exists(venv_python),
        "model_path": model_path,
        "venv_python": venv_python,
        "install_script": BITNET_INSTALL_SCRIPT,
    }


def ollama_cli_path() -> str:
    local_runtime = os.path.join(BASE_DIR, ".runtime", "ollama", "ollama")
    if os.path.exists(local_runtime):
        return local_runtime
    return shutil.which("ollama") or ""


def ollama_environment() -> Dict[str, str]:
    env = os.environ.copy()
    bundled_models = os.path.join(BASE_DIR, ".runtime", "ollama-models")
    if os.path.isdir(bundled_models):
        env["OLLAMA_MODELS"] = bundled_models
    return env


def ollama_api_status(timeout: int = 4) -> Dict[str, object]:
    status = {"reachable": False, "models": [], "error": ""}
    try:
        with urlopen(RUNTIME_OLLAMA_TAGS_URL, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = []
        for item in payload.get("models", []):
            name = item.get("name") or ""
            if name:
                models.append(normalize_local_model(name))
        status["reachable"] = True
        status["models"] = sorted(set(models))
    except Exception as error:  # noqa: BLE001
        status["error"] = str(error)
    return status


def list_ollama_models() -> List[str]:
    api_state = ollama_api_status()
    if api_state["reachable"] and api_state["models"]:
        return api_state["models"]

    cli_path = ollama_cli_path()
    if not cli_path:
        return []

    result = subprocess.run([cli_path, "list"], text=True, capture_output=True, timeout=60, check=False, env=ollama_environment())
    if result.returncode != 0:
        return []

    models = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.strip().split()
        if parts:
            models.append(normalize_local_model(parts[0]))
    return sorted(set(models))


def choose_installed_model(installed: List[str], env: Dict[str, str]) -> str:
    installed_set = set(installed)
    for candidate in runtime_candidates(env):
        if candidate in installed_set:
            return candidate
    for candidate in installed:
        if model_is_localish(candidate):
            return candidate
    return installed[0] if installed else ""


def model_is_probably_cloud(model_name: str) -> bool:
    normalized = (model_name or "").strip().lower()
    if not normalized:
        return False
    # Ollama uses Hugging Face repository references such as
    # ``hf.co/org/repo:quant`` as local runtime names.  The slash is not proof
    # of a cloud API dependency.
    if normalized.startswith("hf.co/"):
        return False
    if "/" in normalized:
        return True
    if normalized.startswith(CLOUD_MODEL_HINT_PREFIXES):
        return True
    if normalized.endswith(("-versatile", "-instant", "-preview", "-latest")) and ":" not in normalized:
        return True
    return False


def model_is_localish(model_name: str) -> bool:
    normalized = (model_name or "").strip().lower()
    if not normalized:
        return False
    if normalized in LEGACY_LOCAL_MODEL_MAP:
        return True
    if normalized.startswith(LOCAL_MODEL_HINT_PREFIXES):
        return True
    if ":" in normalized and not model_is_probably_cloud(normalized):
        return True
    return False


def ensure_local_ollama_process() -> List[Dict[str, str]]:
    logs: List[Dict[str, str]] = []
    if ollama_api_status()["reachable"]:
        return logs

    local_runtime = os.path.join(BASE_DIR, ".runtime", "ollama", "ollama")
    pm2_path = shutil.which("pm2") or os.path.join(BASE_DIR, ".runtime", "bin", "pm2")
    if os.path.exists(local_runtime) and os.path.exists(pm2_path):
        run_command("pm2 delete zero-ollama", timeout=30)
        command = (
            f'OLLAMA_MODELS={shlex.quote(os.path.join(BASE_DIR, ".runtime", "ollama-models"))} '
            f'pm2 start {shlex.quote(local_runtime)} --name zero-ollama --interpreter none -- serve'
        )
        result = run_command(command, timeout=120)
        logs.append({"step": "start-local-ollama", "output": (result.stdout or result.stderr).strip()})
        for _ in range(15):
            if ollama_api_status()["reachable"]:
                return logs
            time.sleep(2)

    logs.append(
        {
            "step": "system-ollama-manual-required",
            "output": (
                "System service changes are outside the OpenZero runtime. "
                "Use the host's audited administrator or deployment process."
            ),
        }
    )
    return logs


def upgrade_ollama_runtime() -> List[Dict[str, str]]:
    return [
        {
            "step": "ollama-upgrade-manual-required",
            "output": (
                "Automatic operating-system upgrades are disabled. Update Ollama through "
                "the host's audited administrator or managed-deployment process."
            ),
        }
    ]


def pull_model(model_name: str, timeout: int = 7200) -> Dict[str, object]:
    cli_path = ollama_cli_path()
    if not cli_path:
        return {"ok": False, "output": "Ollama CLI not found."}
    result = subprocess.run(
        [cli_path, "pull", model_name],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        env=ollama_environment(),
    )
    output = (result.stdout or result.stderr or "").strip()
    return {"ok": result.returncode == 0, "output": output}


def repair_runtime(auto_update: bool = True) -> Dict[str, object]:
    env = load_env(BASE_DIR)
    profile = resource_profile(env)
    saved_model = normalize_local_model(env.get("ACTIVE_MODEL", ""))
    candidates = runtime_candidates(env)
    logs: List[Dict[str, str]] = []

    if bitnet_selected(env):
        bitnet = bitnet_status(load_env(BASE_DIR))
        if not bitnet["ready"]:
            logs.append(
                {
                    "step": "bitnet-install-manual-required",
                    "output": (
                        "Automatic BitNet installation is disabled in the doctor. "
                        "Use the explicit administrator-approved installer workflow."
                    ),
                }
            )
        report = {
            "saved_model": saved_model,
            "effective_model": env.get("BITNET_MODEL_ALIAS", BITNET_DEFAULT_ALIAS),
            "recommended_model": profile["recommended_model"],
            "installed_models": [env.get("BITNET_MODEL_ALIAS", BITNET_DEFAULT_ALIAS)] if bitnet["ready"] else [],
            "api_reachable": bitnet["ready"],
            "api_error": "" if bitnet["ready"] else "BitNet runtime is not ready.",
            "did_upgrade_ollama": False,
            "logs": logs,
            "status": "healthy" if bitnet["ready"] else "degraded",
            "env_model": load_env(BASE_DIR).get("ACTIVE_MODEL", ""),
            "engine": "bitnet",
        }
        os.makedirs(os.path.dirname(RUNTIME_STATE_PATH), exist_ok=True)
        with open(RUNTIME_STATE_PATH, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
        return report

    logs.extend(ensure_local_ollama_process())
    installed = list_ollama_models()
    target_model = ""

    if saved_model and saved_model in installed and model_is_localish(saved_model):
        target_model = saved_model
    if not target_model:
        target_model = choose_installed_model(installed, env)

    did_upgrade = False
    if not target_model:
        for candidate in candidates:
            pulled = pull_model(candidate)
            logs.append({"step": f"pull {candidate}", "output": str(pulled["output"])})
            if pulled["ok"]:
                installed = list_ollama_models()
                target_model = candidate if candidate in installed else choose_installed_model(installed, env)
                break
            lower_output = str(pulled["output"]).lower()
            if auto_update and not did_upgrade and (
                "requires a newer version of ollama" in lower_output or "pull model manifest: 412" in lower_output
            ):
                logs.extend(upgrade_ollama_runtime())
                break

    api_state = ollama_api_status()
    updates = {
        "NODE_RAM_GB": str(profile["ram_gb"]),
        "NODE_CONTEXT_WINDOW": str(profile["context_window"]),
        "NODE_RECOMMENDED_MODEL": profile["recommended_model"],
    }

    manage_active_model = not model_is_probably_cloud(saved_model) or model_is_localish(saved_model) or not saved_model
    if target_model and manage_active_model and saved_model != target_model:
        updates["ACTIVE_MODEL"] = target_model

    env_after = save_env_values(BASE_DIR, {**env, **updates}) if updates else env
    report = {
        "saved_model": saved_model,
        "effective_model": target_model or saved_model or profile["recommended_model"],
        "recommended_model": profile["recommended_model"],
        "installed_models": installed,
        "api_reachable": api_state["reachable"],
        "api_error": api_state["error"],
        "did_upgrade_ollama": did_upgrade,
        "logs": logs,
        "status": "healthy" if api_state["reachable"] and (target_model or saved_model or model_is_probably_cloud(saved_model)) else "degraded",
        "env_model": env_after.get("ACTIVE_MODEL", ""),
        "engine": "ollama",
    }
    os.makedirs(os.path.dirname(RUNTIME_STATE_PATH), exist_ok=True)
    with open(RUNTIME_STATE_PATH, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    return report


def ensure_directories() -> Dict[str, bool]:
    required = ["uploads", "static", "templates", "moltbot", "brain", "hivemind", "security"]
    created = {}
    for name in required:
        path = os.path.join(BASE_DIR, name)
        existed = os.path.exists(path)
        os.makedirs(path, exist_ok=True)
        created[name] = not existed
    return created


def ensure_env_defaults() -> Dict[str, str]:
    current = load_env(BASE_DIR)
    updates = {}
    for key, value in DEFAULTS.items():
        if key not in current:
            updates[key] = value
    if updates:
        return save_env_values(BASE_DIR, {**current, **updates})
    return current


def ensure_permissions() -> Dict[str, str]:
    changed = {}
    for path in protected_paths(BASE_DIR):
        if not os.path.exists(path):
            continue
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            changed[path] = "0600"
        except OSError:
            changed[path] = "skipped"
    for script in ["ignite.sh", "install.sh", "update.sh", "setup_service.sh", "janitor.sh", "openzero-kali.sh"]:
        path = os.path.join(BASE_DIR, script)
        if not os.path.exists(path):
            continue
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            changed[path] = "0700"
        except OSError:
            changed[path] = "skipped"
    return changed


def doctor_report(run_runtime_repair: bool = False) -> Dict[str, object]:
    directories = ensure_directories()
    env_state = ensure_env_defaults()
    permissions = ensure_permissions()
    integrity = ensure_integrity_state(BASE_DIR)
    status = integrity_status(BASE_DIR)
    runtime = repair_runtime(auto_update=True) if run_runtime_repair else {
        "saved_model": normalize_local_model(env_state.get("ACTIVE_MODEL", "")),
        "recommended_model": resource_profile(env_state)["recommended_model"],
        "installed_models": [env_state.get("BITNET_MODEL_ALIAS", BITNET_DEFAULT_ALIAS)] if bitnet_selected(env_state) and bitnet_status(env_state)["ready"] else list_ollama_models(),
        "api_reachable": bitnet_status(env_state)["ready"] if bitnet_selected(env_state) else ollama_api_status()["reachable"],
        "status": "checked",
        "engine": "bitnet" if bitnet_selected(env_state) else "ollama",
    }
    return {
        "directories": directories,
        "env_keys": len(env_state),
        "permissions": permissions,
        "integrity": integrity,
        "status": status,
        "runtime": runtime,
    }


def main() -> None:
    args = set(sys.argv[1:])
    report = doctor_report(run_runtime_repair="--repair-runtime" in args)
    if "--json" in args:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif "--quiet" not in args:
        print("OPENZERO DOCTOR")
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
