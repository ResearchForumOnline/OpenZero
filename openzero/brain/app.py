import json
import hashlib
import hmac
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import zipfile
from html import unescape
from typing import Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import psutil
import requests
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import hivemind.bridge as hive  # noqa: E402
from integrity import ensure_integrity_state, integrity_status, seal_json  # noqa: E402
from openzero_config import cpu_performance_profile, env_bool, load_env, resource_profile, save_env_value, save_env_values  # noqa: E402
from voice_stack import VoiceStack  # noqa: E402


UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
MODELS_FOLDER = os.path.join(BASE_DIR, "models")
SECURITY_FOLDER = os.path.join(BASE_DIR, "security")
CUSTOM_MODEL_REGISTRY_PATH = os.path.join(SECURITY_FOLDER, "custom_models.json")
HF_BRIDGE_PATH = os.path.join(BASE_DIR, "hf_bridge.sh")
BITNET_INSTALL_SCRIPT = os.path.join(BASE_DIR, "install_bitnet.sh")
BITNET_RUNTIME_DIR = os.path.join(BASE_DIR, ".runtime", "bitnet")
BITNET_REPO_DIR = os.path.join(BITNET_RUNTIME_DIR, "BitNet")
BITNET_VENV_PYTHON = os.path.join(BITNET_RUNTIME_DIR, "venv", "bin", "python")
BITNET_MODEL_ROOT = os.path.join(BASE_DIR, ".runtime", "bitnet-models")
BITNET_DEFAULT_MODEL_ID = "microsoft/bitnet-b1.58-2B-4T-gguf"
BITNET_DEFAULT_MODEL_ALIAS = "bitnet-b1.58-2b-4t"
BITNET_DEFAULT_MODEL_FILE = os.path.join(BITNET_MODEL_ROOT, "BitNet-b1.58-2B-4T", "ggml-model-i2_s.gguf")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MODELS_FOLDER, exist_ok=True)
os.makedirs(SECURITY_FOLDER, exist_ok=True)

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),
    template_folder=os.path.join(BASE_DIR, "templates"),
)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
socketio = SocketIO(app, async_mode="threading")

HOSTNAME = socket.gethostname()
LATEST_UPLOAD_CONTENT = ""
CHAT_HISTORY = []
LAST_SHAREABLE_EXCHANGE: Dict[str, object] = {}
LAST_SHAREABLE_EXCHANGE_LOCK = threading.Lock()
MAX_HISTORY = 12
RUNTIME_LOCK = threading.Lock()
RUNTIME: Dict[str, object] = {}
RUN_STATE_LOCK = threading.Lock()
RUN_STATE: Dict[str, Dict[str, object]] = {}
LAST_RUNTIME_SELF_HEAL_AT = 0.0
RUNTIME_SELF_HEAL_COOLDOWN_SECONDS = 1800
OPERATOR_MAX_LOOPS = 8
OPERATOR_RESULT_LIMIT = 12000
OPERATOR_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".runtime",
}


def emit_agent_log(message: str, session_id: str = "") -> None:
    payload = {"data": str(message or "").strip()}
    if session_id:
        socketio.emit("agent_log", payload, to=session_id)
    else:
        socketio.emit("agent_log", payload)


def emit_agent_state(session_id: str, running: bool, status: str, message: str = "") -> None:
    socketio.emit(
        "agent_state",
        {"running": bool(running), "status": str(status or "idle"), "message": str(message or "").strip()},
        to=session_id,
    )


def set_run_state(session_id: str, **updates) -> Dict[str, object]:
    sid = str(session_id or "").strip()
    if not sid:
        return {}
    with RUN_STATE_LOCK:
        state = dict(RUN_STATE.get(sid) or {})
        state.update(updates)
        RUN_STATE[sid] = state
        return dict(state)


def get_run_state(session_id: str) -> Dict[str, object]:
    sid = str(session_id or "").strip()
    if not sid:
        return {}
    with RUN_STATE_LOCK:
        return dict(RUN_STATE.get(sid) or {})


def is_stop_requested(session_id: str) -> bool:
    return bool(get_run_state(session_id).get("stop_requested"))


def clear_run_state(session_id: str) -> None:
    sid = str(session_id or "").strip()
    if not sid:
        return
    with RUN_STATE_LOCK:
        RUN_STATE.pop(sid, None)


ZERO_SYSTEM_PROMPT = """You are OpenZero, a sovereign local-first AI operator also known as Agent Zero.
Mission:
- Help users who may know nothing about the system.
- Keep actions aligned to OpenZero only.
- Prefer safe, local, offline-capable workflows.
- Explain what you are doing in plain language before dense jargon.

Available operator tool tags:
- <tool>{"action":"list_dir","path":"."}</tool> for structured local operator actions.
- Structured tool actions available: list_dir, tree, read_file, write_file, append_file, replace_text, search, mkdir, remove_path, zip_list, zip_extract, zip_create, fetch_url, web_search, ssh_command, scp_put, scp_get.
- <bash>command</bash> for terminal actions.
- <osint>target</osint> for Serper-backed recon when configured.
- <browse>url</browse> for Moltbot webpage text extraction.
- <speak>text</speak> for local Piper speech output.

OpenZero 5.4 rules:
- Never mention deprecated branding.
- Respect the Probability of Goodness threshold.
- If the user asks for current, latest, research, URLs, docs, prices, downloads, or facts that may change, use web_search or fetch_url before answering.
- If the user asks to view, inspect, open, browse, screenshot, or read a live webpage, prefer Moltbot browser extraction.
- If unsure which tool exists, call the skills tool and continue.
- Assume the operator wants complete steps, not partial snippets.
- Keep data local unless the selected computation mode explicitly uses cloud routing.
- If the request is clear enough to execute, do the work and report real paths, outputs, and next checks.
- Prefer structured file/archive/web tools before falling back to raw shell.
- Use <bash> for package managers, git, systemctl, ssh edge cases, or anything the structured tools do not cover.
- Never pretend a command, file edit, download, or archive action happened if you did not actually execute it.
"""

TERMINAL_SYSTEM_PROMPT = """You are OpenZero Terminal, the root-operator autopilot mode for this node.
Carry tasks through autonomously when the request is clear. Do the work instead of asking the operator to type commands.
Prefer the structured operator tool channel first:
- <tool>{"action":"list_dir","path":"."}</tool>
- <tool>{"action":"read_file","path":"relative/or/absolute/path","start_line":1,"end_line":120}</tool>
- <tool>{"action":"write_file","path":"relative/or/absolute/path","content":"..."}</tool>
- <tool>{"action":"append_file","path":"relative/or/absolute/path","content":"..."}</tool>
- <tool>{"action":"replace_text","path":"relative/or/absolute/path","old":"...","new":"..."}</tool>
- <tool>{"action":"search","path":".","pattern":"needle"}</tool>
- <tool>{"action":"mkdir","path":"new-folder"}</tool>
- <tool>{"action":"remove_path","path":"old-folder","recursive":true}</tool>
- <tool>{"action":"zip_list","path":"archive.zip"}</tool>
- <tool>{"action":"zip_extract","path":"archive.zip","dest":"target-folder"}</tool>
- <tool>{"action":"zip_create","source":"folder-or-file","dest":"bundle.zip"}</tool>
- <tool>{"action":"fetch_url","url":"https://example.com"}</tool>
- <tool>{"action":"web_search","query":"best zero trust docs"}</tool>
- <tool>{"action":"moltbot_browse","url":"https://example.com"}</tool>
- <tool>{"action":"skills","query":"web or server task"}</tool>
- <tool>{"action":"ssh_command","host":"example.com","user":"root","port":22,"command":"uname -a"}</tool>
- <tool>{"action":"scp_put","host":"example.com","user":"root","port":22,"source":"local.file","destination":"/remote/path"}</tool>
- <tool>{"action":"scp_get","host":"example.com","user":"root","port":22,"source":"/remote/file","destination":"local.file"}</tool>
Use <bash>command</bash> only when the structured operator channel is not enough.
Keep commands explicit, factual, and one logical step at a time.
When you need to speak locally, use <speak>text</speak>.
"""

SKILL_CATALOG = [
    {
        "id": "web_search",
        "name": "Web Search",
        "triggers": "latest, current, research, compare, docs, downloads, pricing, public facts",
        "tool": '<tool>{"action":"web_search","query":"search terms","max_results":6}</tool>',
        "notes": "Uses Serper when configured and falls back to a lightweight public web search when possible.",
    },
    {
        "id": "fetch_url",
        "name": "Read URL",
        "triggers": "read this link, summarize page, check docs, inspect release page",
        "tool": '<tool>{"action":"fetch_url","url":"https://example.com"}</tool>',
        "notes": "Fast text extraction without launching the browser.",
    },
    {
        "id": "moltbot_browse",
        "name": "Moltbot Browser",
        "triggers": "open page, browse, screenshot, inspect UI, website is dynamic",
        "tool": '<tool>{"action":"moltbot_browse","url":"https://example.com"}</tool>',
        "notes": "Uses the local headless Chrome service and saves a dashboard screenshot when available.",
    },
    {
        "id": "files",
        "name": "Files And Code",
        "triggers": "check files, edit, search code, create folder, read logs",
        "tool": '<tool>{"action":"search","path":".","pattern":"needle"}</tool>',
        "notes": "Use list_dir, tree, read_file, write_file, append_file, replace_text, search, mkdir.",
    },
    {
        "id": "archives",
        "name": "Archives",
        "triggers": "zip, unzip, backup, inspect archive, create package",
        "tool": '<tool>{"action":"zip_create","source":"folder","dest":"backup.zip"}</tool>',
        "notes": "Use zip_list, zip_extract, and zip_create before raw shell archive commands.",
    },
    {
        "id": "server_ops",
        "name": "Server Ops",
        "triggers": "ssh, server, deploy, check logs, copy remote file",
        "tool": '<tool>{"action":"ssh_command","host":"server","user":"root","port":22,"command":"uptime"}</tool>',
        "notes": "Uses local SSH/SCP clients and configured keys. Keep secrets out of prompts.",
    },
    {
        "id": "voice",
        "name": "Voice",
        "triggers": "speak, read aloud, transcribe, voice reply",
        "tool": '<speak>Text to speak locally.</speak>',
        "notes": "Uses local voice stack when installed and enabled. Piper is the lightweight offline TTS lane; Voicebox can be selected for cloned profiles, Kokoro/LuxTTS-style engines, and local studio speech.",
    },
]

CLOUD_MODEL_NAMES = {
    "groq/compound",
    "groq/compound-large",
    "openai/gpt-oss-120b",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "llama-3.3-70b-versatile",
    "qwen/qwen3-32b",
}

LOCAL_MODEL_PRESETS = [
    {
        "id": "gemma4:e2b",
        "label": "Gemma 4 Edge 2B",
        "tier": "compact",
        "ram_hint": "Best for lower-RAM nodes and lightweight laptops.",
    },
    {
        "id": "gemma4:e4b",
        "label": "Gemma 4 Edge 4B",
        "tier": "baseline",
        "ram_hint": "CPU-first default for most OpenZero installs.",
    },
    {
        "id": "gemma4:26b",
        "label": "Gemma 4 26B",
        "tier": "balanced",
        "ram_hint": "Optional heavyweight tier for stronger boxes. Not the default CPU lane.",
    },
    {
        "id": "gemma4:31b",
        "label": "Gemma 4 31B",
        "tier": "heavy",
        "ram_hint": "Optional heavyweight tier for high-memory nodes. Expect slower CPU inference.",
    },
    {
        "id": "gemma3:4b",
        "label": "Gemma 3 4B",
        "tier": "compat",
        "ram_hint": "Compatibility track for older Ollama installs and lighter nodes.",
    },
    {
        "id": "gemma3:12b",
        "label": "Gemma 3 12B",
        "tier": "compat",
        "ram_hint": "Compatibility track for older Ollama installs with more headroom.",
    },
]

BITNET_MODEL_PRESETS = [
    {
        "id": BITNET_DEFAULT_MODEL_ALIAS,
        "hf_repo": BITNET_DEFAULT_MODEL_ID,
        "label": "BitNet 1-bit 2B4T",
        "tier": "cpu-efficient",
        "ram_hint": "Optional Microsoft 1-bit CPU lane for older or lower-power systems. Separate runtime from Ollama.",
        "context_window": 4096,
    }
]

GEMMA4_MODEL_IDS = ["gemma4:e2b", "gemma4:e4b", "gemma4:26b", "gemma4:31b"]
GEMMA_COMPAT_MODEL_IDS = ["gemma3:4b", "gemma3:12b"]

LEGACY_LOCAL_MODEL_MAP = {
    "gemma2": "gemma4:e4b",
    "gemma2:2b": "gemma4:e2b",
    "gemma2:9b": "gemma4:e4b",
    "qwen2.5:14b": "gemma4:e4b",
    "qwen2.5:32b": "gemma4:e4b",
    "qwenq8": "gemma4:e4b",
    "qwenq8:latest": "gemma4:e4b",
    "bitnet": BITNET_DEFAULT_MODEL_ALIAS,
    "bitnet-b1.58-2b-4t": BITNET_DEFAULT_MODEL_ALIAS,
    "microsoft/bitnet-b1.58-2b-4t": BITNET_DEFAULT_MODEL_ALIAS,
}


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def format_bytes(size_bytes: int) -> str:
    size = float(max(0, size_bytes))
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(size_bytes)} B"


def empty_custom_model_registry() -> Dict[str, object]:
    return {"version": "openzero-custom-models-v1", "models": {}}


def load_custom_model_registry() -> Dict[str, object]:
    registry = empty_custom_model_registry()
    try:
        with open(CUSTOM_MODEL_REGISTRY_PATH, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            registry.update(loaded)
    except Exception:
        pass

    if not isinstance(registry.get("models"), dict):
        registry["models"] = {}
    return registry


def save_custom_model_registry(registry: Dict[str, object]) -> None:
    os.makedirs(os.path.dirname(CUSTOM_MODEL_REGISTRY_PATH), exist_ok=True)
    with open(CUSTOM_MODEL_REGISTRY_PATH, "w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2, sort_keys=True)


def register_custom_model(model_name: str, gguf_file: str, source_url: str) -> None:
    registry = load_custom_model_registry()
    models = registry.setdefault("models", {})
    models[model_name] = {
        "model_name": model_name,
        "gguf_file": gguf_file,
        "source_url": source_url,
        "updated_at": utc_timestamp(),
    }
    save_custom_model_registry(registry)


def prune_custom_model_registry(model_names: Optional[List[str]] = None, gguf_file: str = "") -> int:
    registry = load_custom_model_registry()
    models = registry.setdefault("models", {})
    removed = 0
    names_to_remove = set(model_names or [])

    for alias, meta in list(models.items()):
        if alias in names_to_remove or (gguf_file and meta.get("gguf_file") == gguf_file):
            models.pop(alias, None)
            removed += 1

    if removed:
        save_custom_model_registry(registry)
    return removed


def is_cloud_model(model_name: str) -> bool:
    normalized = (model_name or "").strip().lower()
    return normalized in CLOUD_MODEL_NAMES


def normalize_local_model_name(model_name: str) -> str:
    normalized = (model_name or "").strip()
    return LEGACY_LOCAL_MODEL_MAP.get(normalized.lower(), normalized)


def is_bitnet_model(model_name: str) -> bool:
    normalized = normalize_local_model_name(model_name).lower()
    return normalized == BITNET_DEFAULT_MODEL_ALIAS


def local_engine_from(config: Dict[str, str]) -> str:
    engine = (config.get("LOCAL_ENGINE") or "ollama").strip().lower()
    if engine == "bitnet" or is_bitnet_model(config.get("ACTIVE_MODEL", "")):
        return "bitnet"
    return "ollama"


def bitnet_model_path(config: Dict[str, str]) -> str:
    configured = (config.get("BITNET_MODEL_PATH") or "").strip()
    if not configured:
        return BITNET_DEFAULT_MODEL_FILE
    return configured if os.path.isabs(configured) else os.path.join(BASE_DIR, configured)


def bitnet_context_window(config: Dict[str, str]) -> int:
    try:
        return max(1024, min(4096, int(float(config.get("BITNET_CONTEXT_WINDOW") or 4096))))
    except (TypeError, ValueError):
        return 4096


def bitnet_status(config: Optional[Dict[str, str]] = None) -> Dict[str, object]:
    current = config or current_config()
    model_path = bitnet_model_path(current)
    ready = bool(os.path.exists(model_path) and os.path.exists(BITNET_VENV_PYTHON))
    return {
        "selected": local_engine_from(current) == "bitnet",
        "enabled": env_bool(current, "BITNET_ENABLED", False),
        "ready": ready,
        "engine": "bitnet",
        "model_alias": current.get("BITNET_MODEL_ALIAS") or BITNET_DEFAULT_MODEL_ALIAS,
        "model_id": current.get("BITNET_MODEL_ID") or BITNET_DEFAULT_MODEL_ID,
        "model_path": model_path,
        "repo_dir": BITNET_REPO_DIR,
        "venv_python": BITNET_VENV_PYTHON,
        "context_window": bitnet_context_window(current),
        "install_script": BITNET_INSTALL_SCRIPT,
        "message": (
            "BitNet runtime is ready."
            if ready
            else "BitNet runtime is not ready yet. Install the optional 1-bit add-on first."
        ),
    }


def effective_local_context_window(config: Dict[str, str], profile: Dict[str, object]) -> int:
    if local_engine_from(config) == "bitnet":
        return bitnet_context_window(config)
    return int(profile["context_window"])


def groq_model_for(config: Dict[str, str]) -> str:
    active_model = (config.get("ACTIVE_MODEL") or "").strip()
    return active_model if is_cloud_model(active_model) else "groq/compound-large"


def local_model_for(config: Dict[str, str], profile: Dict[str, object]) -> str:
    return resolve_local_model_selection(config, profile, include_ollama_status=False)["model"]


def ollama_api_ready(timeout: int = 8) -> bool:
    try:
        response = requests.get("http://127.0.0.1:11434/api/tags", timeout=timeout)
        response.raise_for_status()
        return True
    except Exception:
        return False


def ollama_cli_path() -> str:
    return shutil.which("ollama") or ""


def ollama_version_status() -> Dict[str, object]:
    cli_path = ollama_cli_path()
    if not cli_path:
        return {
            "available": False,
            "reachable": ollama_api_ready(timeout=3),
            "version": "",
            "raw": "",
            "message": "Ollama CLI was not found on PATH.",
        }
    try:
        result = subprocess.run(
            [cli_path, "--version"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        raw = (result.stdout or result.stderr or "").strip()
        match = re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)
        return {
            "available": True,
            "reachable": ollama_api_ready(timeout=3),
            "version": match.group(1) if match else "",
            "raw": raw,
            "message": "" if result.returncode == 0 else (raw or "ollama --version failed."),
        }
    except Exception as error:
        return {
            "available": True,
            "reachable": ollama_api_ready(timeout=3),
            "version": "",
            "raw": "",
            "message": str(error),
        }


def preferred_local_model_candidates(profile: Dict[str, object]) -> list[str]:
    ram_gb = int(profile.get("ram_gb") or 0)
    if ram_gb < 12:
        return ["gemma4:e2b", "gemma3:4b", "gemma4:e4b", "gemma3:12b", "gemma4:26b"]
    if ram_gb < 24:
        return ["gemma4:e4b", "gemma4:e2b", "gemma3:12b", "gemma3:4b", "gemma4:26b"]
    if ram_gb < 48:
        return ["gemma4:e4b", "gemma4:e2b", "gemma3:12b", "gemma4:26b", "gemma4:31b"]
    return ["gemma4:e4b", "gemma4:e2b", "gemma3:12b", "gemma4:26b", "gemma4:31b"]


def choose_installed_local_model(installed: set[str], profile: Dict[str, object]) -> str:
    for candidate in preferred_local_model_candidates(profile):
        if candidate in installed:
            return candidate
    if installed:
        return sorted(installed)[0]
    return preferred_local_model_candidates(profile)[0]


def resolve_local_model_selection(
    config: Dict[str, str], profile: Dict[str, object], include_ollama_status: bool = True
) -> Dict[str, object]:
    if local_engine_from(config) == "bitnet":
        status = bitnet_status(config)
        raw_active = (config.get("ACTIVE_MODEL") or "").strip()
        warning = ""
        if raw_active and normalize_local_model_name(raw_active) != status["model_alias"]:
            warning = f"Saved local model `{raw_active}` is being normalized to `{status['model_alias']}`."
        if not status["ready"]:
            warning = (
                f"{status['message']} OpenZero can fall back to Ollama if Gemma is installed, but BitNet itself needs the optional add-on."
            )
            return {
                "model": status["model_alias"],
                "saved_model": raw_active,
                "normalized_model": status["model_alias"],
                "status": "missing",
                "warning": warning,
                "installed_models": [status["model_alias"]] if status["ready"] else [],
                "preferred_candidates": [status["model_alias"]],
                "ollama": ollama_version_status() if include_ollama_status else {},
            }
        return {
            "model": status["model_alias"],
            "saved_model": raw_active or status["model_alias"],
            "normalized_model": status["model_alias"],
            "status": "ready",
            "warning": warning or "OpenZero is using the BitNet 1-bit CPU lane.",
            "installed_models": [status["model_alias"]],
            "preferred_candidates": [status["model_alias"]],
            "ollama": ollama_version_status() if include_ollama_status else {},
        }

    raw_active = (config.get("ACTIVE_MODEL") or "").strip()
    normalized = normalize_local_model_name(raw_active)
    installed = set(list_ollama_models())
    preferred_candidates = preferred_local_model_candidates(profile)
    version_state = ollama_version_status() if include_ollama_status else {}

    if normalized and normalized in installed:
        warning = ""
        if raw_active and normalized != raw_active:
            warning = f"Saved model `{raw_active}` is being normalized to `{normalized}`."
        return {
            "model": normalized,
            "saved_model": raw_active,
            "normalized_model": normalized,
            "status": "ready",
            "warning": warning,
            "installed_models": sorted(installed),
            "preferred_candidates": preferred_candidates,
            "ollama": version_state,
        }

    if raw_active and raw_active in installed:
        return {
            "model": raw_active,
            "saved_model": raw_active,
            "normalized_model": normalized,
            "status": "ready",
            "warning": "",
            "installed_models": sorted(installed),
            "preferred_candidates": preferred_candidates,
            "ollama": version_state,
        }

    fallback_model = choose_installed_local_model(installed, profile) if installed else preferred_candidates[0]
    if installed:
        if raw_active and not is_cloud_model(raw_active):
            warning = (
                f"Saved local model `{raw_active}` is not installed. "
                f"OpenZero is using `{fallback_model}` until you save or install a new local model."
            )
        else:
            warning = f"OpenZero is using installed local model `{fallback_model}`."
        return {
            "model": fallback_model,
            "saved_model": raw_active,
            "normalized_model": normalized,
            "status": "fallback",
            "warning": warning,
            "installed_models": sorted(installed),
            "preferred_candidates": preferred_candidates,
            "ollama": version_state,
        }

    upgrade_hint = ""
    if version_state.get("available"):
        upgrade_hint = " Re-run `curl -fsSL https://ollama.com/install.sh | sh` if Gemma 4 pulls say Ollama is too old."
    return {
        "model": preferred_candidates[0],
        "saved_model": raw_active,
        "normalized_model": normalized,
        "status": "missing",
        "warning": (
            "No local Ollama model is ready yet. "
            f"Install `{preferred_candidates[0]}` first, or use a Gemma 3 compatibility preset on older Ollama releases."
            f"{upgrade_hint}"
        ),
        "installed_models": [],
        "preferred_candidates": preferred_candidates,
        "ollama": version_state,
    }


def list_ollama_models() -> list[str]:
    try:
        response = requests.get("http://127.0.0.1:11434/api/tags", timeout=8)
        response.raise_for_status()
        return sorted({item["name"] for item in response.json().get("models", []) if item.get("name")})
    except Exception:
        return []


def list_local_gguf_files() -> list[str]:
    files = []
    if not os.path.isdir(MODELS_FOLDER):
        return files
    for entry in sorted(os.listdir(MODELS_FOLDER)):
        if entry.lower().endswith(".gguf"):
            files.append(entry)
    return files


def ollama_modelfile(model_name: str) -> str:
    cli_path = ollama_cli_path()
    if not cli_path or not model_name:
        return ""
    try:
        result = subprocess.run(
            [cli_path, "show", "--modelfile", model_name],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception:
        return ""

    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def infer_custom_model_aliases(ollama_models: Optional[List[str]] = None) -> Dict[str, List[str]]:
    alias_map: Dict[str, List[str]] = {}
    for model_name in ollama_models or list_ollama_models():
        modelfile = ollama_modelfile(model_name)
        if not modelfile:
            continue
        match = re.search(r"^FROM\s+(.+\.gguf)\s*$", modelfile, re.IGNORECASE | re.MULTILINE)
        if not match:
            continue
        gguf_path = match.group(1).strip().strip('"').strip("'")
        gguf_file = os.path.basename(gguf_path)
        aliases = alias_map.setdefault(gguf_file, [])
        if model_name not in aliases:
            aliases.append(model_name)
    return alias_map


def custom_model_inventory(ollama_models: Optional[List[str]] = None) -> List[Dict[str, object]]:
    installed_models = ollama_models or list_ollama_models()
    gguf_files = list_local_gguf_files()
    registry = load_custom_model_registry().get("models", {})
    alias_map = infer_custom_model_aliases(installed_models)
    items: Dict[str, Dict[str, object]] = {}

    for gguf_file in gguf_files:
        path = os.path.join(MODELS_FOLDER, gguf_file)
        size_bytes = os.path.getsize(path) if os.path.exists(path) else 0
        items[gguf_file] = {
            "gguf_file": gguf_file,
            "file_exists": os.path.exists(path),
            "size_bytes": size_bytes,
            "size_label": format_bytes(size_bytes),
            "source_url": "",
            "updated_at": "",
            "aliases": [],
        }

    for alias, meta in registry.items():
        gguf_file = str(meta.get("gguf_file") or "").strip()
        key = gguf_file or alias
        item = items.setdefault(
            key,
            {
                "gguf_file": gguf_file,
                "file_exists": bool(gguf_file and os.path.exists(os.path.join(MODELS_FOLDER, gguf_file))),
                "size_bytes": 0,
                "size_label": "0 B",
                "source_url": "",
                "updated_at": "",
                "aliases": [],
            },
        )
        if gguf_file:
            item["gguf_file"] = gguf_file
            path = os.path.join(MODELS_FOLDER, gguf_file)
            if os.path.exists(path):
                size_bytes = os.path.getsize(path)
                item["file_exists"] = True
                item["size_bytes"] = size_bytes
                item["size_label"] = format_bytes(size_bytes)
        if alias not in item["aliases"]:
            item["aliases"].append(alias)
        if meta.get("source_url") and not item.get("source_url"):
            item["source_url"] = meta.get("source_url", "")
        if meta.get("updated_at"):
            item["updated_at"] = meta.get("updated_at", "")

    for gguf_file, aliases in alias_map.items():
        item = items.setdefault(
            gguf_file,
            {
                "gguf_file": gguf_file,
                "file_exists": os.path.exists(os.path.join(MODELS_FOLDER, gguf_file)),
                "size_bytes": 0,
                "size_label": "0 B",
                "source_url": "",
                "updated_at": "",
                "aliases": [],
            },
        )
        path = os.path.join(MODELS_FOLDER, gguf_file)
        if os.path.exists(path):
            size_bytes = os.path.getsize(path)
            item["file_exists"] = True
            item["size_bytes"] = size_bytes
            item["size_label"] = format_bytes(size_bytes)
        for alias in aliases:
            if alias not in item["aliases"]:
                item["aliases"].append(alias)

    inventory = []
    for key in sorted(items.keys()):
        item = items[key]
        aliases = sorted(item.get("aliases", []))
        inventory.append(
            {
                "id": item.get("gguf_file") or key,
                "gguf_file": item.get("gguf_file") or "",
                "file_exists": bool(item.get("file_exists")),
                "size_bytes": int(item.get("size_bytes") or 0),
                "size_label": item.get("size_label") or "0 B",
                "source_url": item.get("source_url") or "",
                "updated_at": item.get("updated_at") or "",
                "aliases": aliases,
                "primary_alias": aliases[0] if aliases else "",
                "is_orphaned_alias": not bool(item.get("gguf_file")) or not bool(item.get("file_exists")),
            }
        )

    inventory.sort(key=lambda item: (item.get("updated_at") or "", item.get("gguf_file") or item.get("primary_alias") or ""), reverse=True)
    return inventory


def find_custom_model_record(
    inventory: List[Dict[str, object]], model_name: str = "", gguf_file: str = ""
) -> Optional[Dict[str, object]]:
    normalized_model = normalize_local_model_name(model_name)
    for item in inventory:
        if gguf_file and item.get("gguf_file") == gguf_file:
            return item
        aliases = item.get("aliases", [])
        if normalized_model and normalized_model in aliases:
            return item
    return None


def reload_runtime() -> Dict[str, object]:
    config = load_env(BASE_DIR)
    voice = RUNTIME.get("voice")
    if isinstance(voice, VoiceStack):
        voice.refresh(config)
    else:
        voice = VoiceStack(BASE_DIR, config)
    RUNTIME["config"] = config
    RUNTIME["voice"] = voice
    RUNTIME["integrity"] = ensure_integrity_state(BASE_DIR)
    seal_json(
        BASE_DIR,
        "node_state",
        {
            "active_model": config.get("ACTIVE_MODEL"),
            "comp_mode": config.get("COMP_MODE"),
            "hive_enabled": config.get("HIVE_MIND_ENABLED"),
            "voice_enabled": config.get("VOICE_ENABLED"),
            "paid_hive_enabled": config.get("PAID_HIVE_ENABLED"),
            "p_good_threshold": config.get("P_GOOD_THRESHOLD"),
        },
    )
    return RUNTIME


reload_runtime()
hive.init_hive(RUNTIME["config"])


def current_config() -> Dict[str, str]:
    with RUNTIME_LOCK:
        return dict(RUNTIME["config"])


def current_voice() -> VoiceStack:
    with RUNTIME_LOCK:
        return RUNTIME["voice"]


def maybe_trigger_runtime_self_heal(reason: str) -> None:
    global LAST_RUNTIME_SELF_HEAL_AT

    now = time.time()
    if now - LAST_RUNTIME_SELF_HEAL_AT < RUNTIME_SELF_HEAL_COOLDOWN_SECONDS:
        return

    LAST_RUNTIME_SELF_HEAL_AT = now

    def worker() -> None:
        try:
            subprocess.run(
                ["python3", os.path.join(BASE_DIR, "openzero_doctor.py"), "--repair-runtime", "--quiet", "--json"],
                cwd=BASE_DIR,
                text=True,
                capture_output=True,
                timeout=3600,
                check=False,
            )
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def apply_config_updates(updates: Dict[str, str]) -> Dict[str, str]:
    pending = dict(updates)
    active_model = pending.get("ACTIVE_MODEL")
    if active_model and "LOCAL_ENGINE" not in pending:
        normalized_model = normalize_local_model_name(active_model)
        if is_bitnet_model(normalized_model):
            pending["LOCAL_ENGINE"] = "bitnet"
        elif model_is_localish(normalized_model):
            pending["LOCAL_ENGINE"] = "ollama"
    with RUNTIME_LOCK:
        config = save_env_values(BASE_DIR, pending)
        RUNTIME["config"] = config
        RUNTIME["voice"].refresh(config)
    hive.init_hive(config)
    return config


def compact_skill_catalog_text(query: str = "") -> str:
    needle = (query or "").strip().lower()
    selected = []
    for item in SKILL_CATALOG:
        haystack = " ".join(
            [
                item.get("id", ""),
                item.get("name", ""),
                item.get("triggers", ""),
                item.get("notes", ""),
            ]
        ).lower()
        if not needle or needle in haystack or any(token and token in haystack for token in needle.split()):
            selected.append(item)
    if not selected:
        selected = SKILL_CATALOG
    lines = []
    for item in selected[:8]:
        lines.append(f"- {item['name']}: triggers={item['triggers']}; use {item['tool']}")
    return "\n".join(lines)


def skill_catalog_payload(query: str = "") -> Dict[str, object]:
    needle = (query or "").strip().lower()
    items = []
    for item in SKILL_CATALOG:
        haystack = " ".join(
            [
                item.get("id", ""),
                item.get("name", ""),
                item.get("triggers", ""),
                item.get("notes", ""),
            ]
        ).lower()
        if not needle or needle in haystack or any(token and token in haystack for token in needle.split()):
            items.append(dict(item))
    return {
        "status": "success",
        "skills": items or [dict(item) for item in SKILL_CATALOG],
        "count": len(items or SKILL_CATALOG),
    }


def skill_catalog_result(query: str = "") -> str:
    payload = skill_catalog_payload(query)
    lines = []
    for item in payload["skills"]:
        lines.append(
            f"{item['name']}\n"
            f"  Triggers: {item['triggers']}\n"
            f"  Use: {item['tool']}\n"
            f"  Note: {item['notes']}"
        )
    return format_operator_result("OPENZERO SKILLS", "\n\n".join(lines))


def get_system_prompt(agent_mode: str = "chat") -> str:
    config = current_config()
    profile = resource_profile(config)
    cpu_profile = cpu_performance_profile(config)
    active_context = effective_local_context_window(config, profile)
    system_block = TERMINAL_SYSTEM_PROMPT if agent_mode == "terminal" else ZERO_SYSTEM_PROMPT
    return (
        f"{system_block}\n\n"
        f"[NODE]\n"
        f"- Host: {HOSTNAME}\n"
        f"- Active model: {config.get('ACTIVE_MODEL')}\n"
        f"- Recommended model: {profile['recommended_model']}\n"
        f"- RAM tier: {profile['node_tier']} ({profile['ram_gb']} GB)\n"
        f"- Context window: {active_context}\n"
        f"- CPU profile: {cpu_profile['profile']} ({cpu_profile['threads']}/{cpu_profile['cpu_cores']} threads, batch {cpu_profile['num_batch']})\n"
        f"- Hive enabled: {config.get('HIVE_MIND_ENABLED')}\n"
        f"- Voice enabled: {config.get('VOICE_ENABLED')}\n"
        f"- P(G) threshold: {config.get('P_GOOD_THRESHOLD')}\n"
        f"- Local learning: {config.get('OPENZERO_LOCAL_LEARNING_ENABLED')}\n\n"
        f"[COMPACT SKILL CATALOG]\n"
        f"{compact_skill_catalog_text()}\n"
    )


def ask_groq(prompt: str, context: str = "", agent_mode: str = "chat") -> str:
    config = current_config()
    api_key = config.get("GROQ_API_KEY", "")
    if len(api_key) < 10:
        return "[ERROR] Groq API key missing."

    messages = [{"role": "system", "content": f"{get_system_prompt(agent_mode)}\n\nCONTEXT:\n{context[:5000]}"}]
    for item in CHAT_HISTORY[-(MAX_HISTORY * 2):]:
        messages.append(item)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": groq_model_for(config),
        "messages": messages,
        "max_tokens": 32768,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as error:
        return f"[ERROR] Groq routing failed: {error}"


def local_prompt_block(prompt: str, context: str = "", agent_mode: str = "chat") -> str:
    history_block = "\n".join(f"{item['role'].upper()}: {item['content']}" for item in CHAT_HISTORY[-(MAX_HISTORY * 2):])
    upload_block = f"\nUPLOADED FILE DATA:\n{LATEST_UPLOAD_CONTENT[:16000]}" if LATEST_UPLOAD_CONTENT else ""
    return (
        f"{get_system_prompt(agent_mode)}\n\n"
        f"CONTEXT:\n{context[:6000]}"
        f"{upload_block}\n\n"
        f"HISTORY:\n{history_block}\n\n"
        f"USER: {prompt}\nOPENZERO:"
    )


def run_bitnet_installer(activate: bool = True, remove: bool = False) -> Dict[str, object]:
    if not os.path.exists(BITNET_INSTALL_SCRIPT):
        return {"status": "error", "message": "BitNet installer script is missing."}
    command = ["bash", BITNET_INSTALL_SCRIPT]
    if remove:
        command.append("--remove")
    else:
        command.append("--install")
    if activate and not remove:
        command.append("--activate")
    command.append("--json")
    try:
        result = subprocess.run(
            command,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=14400,
            check=False,
        )
    except Exception as error:
        return {"status": "error", "message": f"BitNet runtime action failed: {error}"}

    raw_output = (result.stdout or result.stderr or "").strip()
    payload: Dict[str, object] = {}
    if raw_output:
        try:
            payload = json.loads(raw_output)
        except Exception:
            payload = {"status": "success" if result.returncode == 0 else "error", "message": raw_output}
    if result.returncode != 0:
        return {
            "status": "error",
            "message": payload.get("message") or raw_output or "BitNet runtime action failed.",
            "payload": payload,
        }
    payload.setdefault("status", "success")
    return payload


def ask_ollama_local(prompt: str, context: str = "", agent_mode: str = "chat", config_override: Optional[Dict[str, str]] = None) -> str:
    config = dict(config_override or current_config())
    profile = resource_profile(config)
    resolution = resolve_local_model_selection(config, profile, include_ollama_status=False)
    if resolution["status"] == "missing":
        ollama_state = resolution.get("ollama", {})
        version_label = ollama_state.get("version") or ollama_state.get("raw") or "unknown"
        maybe_trigger_runtime_self_heal("local brain missing")
        return (
            "[ERROR] Local brain is not ready yet.\n"
            f"- Saved model: `{resolution.get('saved_model') or 'none'}`\n"
            f"- Preferred model: `{resolution['model']}`\n"
            f"- Ollama: `{version_label}`\n"
            "- OpenZero has already started a background self-heal pass. You can also use `Update Ollama` or `Repair Local Brain` from the panel."
        )
    final_prompt = local_prompt_block(prompt, context=context, agent_mode=agent_mode)
    cpu_profile = cpu_performance_profile(config)
    payload = {
        "model": resolution["model"],
        "prompt": final_prompt,
        "stream": False,
        "keep_alive": cpu_profile["keep_alive"],
        "options": {
            "num_ctx": effective_local_context_window(config, profile),
            "num_thread": cpu_profile["threads"],
            "num_batch": cpu_profile["num_batch"],
        },
    }
    try:
        response = requests.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=240)
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason or f"HTTP {response.status_code}"
            maybe_trigger_runtime_self_heal(detail)
            return f"[ERROR] Local brain offline: {detail}\n[SELF-HEAL] OpenZero has started an automatic local runtime repair cycle."
        response.raise_for_status()
        return response.json()["response"]
    except Exception as error:
        maybe_trigger_runtime_self_heal(str(error))
        return f"[ERROR] Local brain offline: {error}\n[SELF-HEAL] OpenZero has started an automatic local runtime repair cycle."


def ask_bitnet(prompt: str, context: str = "", agent_mode: str = "chat") -> str:
    config = current_config()
    status = bitnet_status(config)
    if not status["ready"]:
        maybe_trigger_runtime_self_heal("bitnet runtime missing")
        return (
            "[ERROR] BitNet runtime is not ready yet.\n"
            f"- Selected engine: `bitnet`\n"
            f"- Expected model: `{status['model_alias']}`\n"
            f"- Expected model file: `{status['model_path']}`\n"
            "- OpenZero has started a background self-heal pass. You can also use `Install BitNet`, `Repair BitNet`, or `Update OpenZero`."
        )

    final_prompt = local_prompt_block(prompt, context=context, agent_mode=agent_mode)
    cpu_profile = cpu_performance_profile(config)
    command = [
        status["venv_python"],
        os.path.join(status["repo_dir"], "run_inference.py"),
        "-m",
        status["model_path"],
        "-p",
        final_prompt,
        "-c",
        str(status["context_window"]),
        "-n",
        "512",
        "-t",
        str(cpu_profile["bitnet_threads"]),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=status["repo_dir"],
            capture_output=True,
            text=True,
            timeout=480,
            check=False,
        )
    except Exception as error:
        maybe_trigger_runtime_self_heal(str(error))
        return f"[ERROR] BitNet runtime failed: {error}\n[SELF-HEAL] OpenZero has started an automatic BitNet repair cycle."

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "BitNet inference failed.").strip()
        maybe_trigger_runtime_self_heal(detail)
        return f"[ERROR] BitNet runtime failed: {detail}\n[SELF-HEAL] OpenZero has started an automatic BitNet repair cycle."

    output = (result.stdout or "").strip()
    if output.startswith(final_prompt):
        output = output[len(final_prompt):].strip()
    if not output:
        output = (result.stderr or "").strip()
    if not output:
        output = "[ERROR] BitNet returned no output."
    return output


def ask_local(prompt: str, context: str = "", agent_mode: str = "chat") -> str:
    config = current_config()
    if local_engine_from(config) == "bitnet":
        bitnet_runtime = bitnet_status(config)
        if bitnet_runtime["ready"]:
            return ask_bitnet(prompt, context=context, agent_mode=agent_mode)
        profile = resource_profile(config)
        fallback_config = {**config, "LOCAL_ENGINE": "ollama"}
        fallback = resolve_local_model_selection(fallback_config, profile, include_ollama_status=False)
        if fallback["status"] != "missing":
            reply = ask_ollama_local(prompt, context=context, agent_mode=agent_mode, config_override=fallback_config)
            return (
                "[BITNET OFFLINE] OpenZero could not reach the optional BitNet add-on, so it fell back to the Ollama local lane.\n\n"
                + reply
            )
        return ask_bitnet(prompt, context=context, agent_mode=agent_mode)
    return ask_ollama_local(prompt, context=context, agent_mode=agent_mode)


def execute_system_command(command: str, sudo_password: str, timeout: int = 45) -> str:
    command = command.strip()
    if not command:
        return "[ERROR] No command provided."

    process = subprocess.run(command, shell=True, text=True, capture_output=True, timeout=timeout)
    exit_code = process.returncode
    output = process.stdout if exit_code == 0 else process.stderr

    if exit_code != 0 and sudo_password and ("Permission denied" in output or exit_code == 1):
        payload = f"{sudo_password}\n{command}\n"
        retry = subprocess.run(["sudo", "-S", "bash"], input=payload, text=True, capture_output=True, timeout=timeout)
        if retry.returncode == 0:
            return retry.stdout.strip() or "[ROOT OVERRIDE SUCCESS]"
        return retry.stderr.strip()

    return output.strip() or "[Success: command executed with no output]"


def ollama_upgrade_needed(message: str) -> bool:
    text = (message or "").lower()
    return "requires a newer version of ollama" in text or "pull model manifest: 412" in text


def run_ollama_pull(model_name: str, timeout: int = 5400) -> subprocess.CompletedProcess:
    cli_path = ollama_cli_path() or "ollama"
    return subprocess.run(
        [cli_path, "pull", model_name],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def wait_for_ollama_api(timeout_seconds: int = 60) -> bool:
    started = time.time()
    while time.time() - started < timeout_seconds:
        if ollama_api_ready(timeout=3):
            return True
        time.sleep(2)
    return False


def upgrade_ollama_runtime() -> Dict[str, object]:
    config = current_config()
    sudo_password = config.get("SUDO_PASS", "")
    steps = [
        ("Refreshing Ollama with the official installer", "curl -fsSL https://ollama.com/install.sh | sh", 900),
        ("Reloading systemd", "systemctl daemon-reload", 60),
        ("Enabling Ollama", "systemctl enable ollama", 60),
        ("Restarting Ollama", "systemctl restart ollama", 120),
    ]
    logs = []
    for label, command, timeout in steps:
        output = execute_system_command(command, sudo_password, timeout=timeout)
        logs.append({"label": label, "command": command, "output": output})
    ready = wait_for_ollama_api(timeout_seconds=90)
    version_state = ollama_version_status()
    return {
        "status": "success" if ready else "partial",
        "ready": ready,
        "ollama": version_state,
        "logs": logs,
    }


def trim_operator_text(text: str, max_chars: int = OPERATOR_RESULT_LIMIT) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 16].rstrip() + "\n...[truncated]..."


def strip_json_fences(raw_payload: str) -> str:
    payload = (raw_payload or "").strip()
    if payload.startswith("```"):
        payload = re.sub(r"^```(?:json|JSON)?\s*", "", payload)
        payload = re.sub(r"\s*```$", "", payload)
    return payload.strip()


def visible_reply_text(raw_reply: str) -> str:
    cleaned = re.sub(
        r"<(?:bash|osint|browse|speak|tool)>.*?</(?:bash|osint|browse|speak|tool)>",
        "",
        raw_reply or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def resolve_operator_path(raw_path: str) -> str:
    path = unquote(str(raw_path or ".")).strip() or "."
    expanded = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isabs(expanded):
        expanded = os.path.join(BASE_DIR, expanded)
    return os.path.abspath(expanded)


def format_operator_result(title: str, body, language: str = "text") -> str:
    if isinstance(body, (dict, list)):
        text = json.dumps(body, indent=2, ensure_ascii=False)
        language = "json"
    else:
        text = str(body or "").strip()
    text = trim_operator_text(text)
    if "\n" in text or language:
        return f"**[{title}]**\n```{language}\n{text}\n```"
    return f"**[{title}]**\n{text}"


def list_dir_result(path: str) -> str:
    target = resolve_operator_path(path)
    if not os.path.exists(target):
        return format_operator_result("DIR ERROR", f"Path does not exist: {target}")
    if not os.path.isdir(target):
        return format_operator_result("DIR ERROR", f"Not a directory: {target}")

    lines = [target]
    entries = sorted(os.scandir(target), key=lambda entry: (not entry.is_dir(), entry.name.lower()))
    for index, entry in enumerate(entries[:200], start=1):
        try:
            size_label = "<DIR>" if entry.is_dir() else format_bytes(entry.stat().st_size)
        except Exception:
            size_label = "?"
        kind = "DIR " if entry.is_dir() else "FILE"
        suffix = "/" if entry.is_dir() else ""
        lines.append(f"{index:>3}. {kind} {size_label:>10}  {entry.name}{suffix}")
    if len(entries) > 200:
        lines.append(f"... {len(entries) - 200} more entries omitted ...")
    return format_operator_result(f"DIR LIST :: {target}", "\n".join(lines))


def tree_result(path: str, max_depth: int = 3, max_entries: int = 250) -> str:
    target = resolve_operator_path(path)
    if not os.path.exists(target):
        return format_operator_result("TREE ERROR", f"Path does not exist: {target}")
    if not os.path.isdir(target):
        return format_operator_result("TREE ERROR", f"Not a directory: {target}")

    lines = [target]
    emitted = 0

    def walk(current: str, prefix: str, depth: int) -> bool:
        nonlocal emitted
        if depth >= max_depth:
            return False
        try:
            entries = sorted(os.scandir(current), key=lambda entry: (not entry.is_dir(), entry.name.lower()))
        except Exception as error:
            lines.append(f"{prefix}[error opening directory: {error}]")
            return False
        entries = [entry for entry in entries if entry.name not in OPERATOR_SKIP_DIRS]
        for index, entry in enumerate(entries):
            if emitted >= max_entries:
                lines.append(f"{prefix}... tree truncated ...")
                return True
            connector = "└─ " if index == len(entries) - 1 else "├─ "
            child_prefix = prefix + ("   " if index == len(entries) - 1 else "│  ")
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
            emitted += 1
            if entry.is_dir() and walk(entry.path, child_prefix, depth + 1):
                return True
        return False

    walk(target, "", 0)
    return format_operator_result(f"TREE :: {target}", "\n".join(lines))


def read_file_result(path: str, start_line: int = 1, end_line: int = 200) -> str:
    target = resolve_operator_path(path)
    if not os.path.exists(target):
        return format_operator_result("READ ERROR", f"File does not exist: {target}")
    if os.path.isdir(target):
        return format_operator_result("READ ERROR", f"Path is a directory, not a file: {target}")
    try:
        with open(target, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.read().splitlines()
    except Exception as error:
        return format_operator_result("READ ERROR", f"Could not read {target}: {error}")

    start = max(1, int(start_line or 1))
    end = max(start, int(end_line or max(start + 199, start)))
    excerpt = lines[start - 1 : end]
    numbered = [f"{line_number:>5}: {line}" for line_number, line in zip(range(start, start + len(excerpt)), excerpt)]
    if not numbered and not lines:
        numbered = ["[empty file]"]
    elif not numbered:
        numbered = [f"[no lines in requested range; file has {len(lines)} total lines]"]
    return format_operator_result(f"FILE READ :: {target}", "\n".join(numbered))


def write_file_result(path: str, content: str, append: bool = False) -> str:
    target = resolve_operator_path(path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    mode = "a" if append else "w"
    try:
        with open(target, mode, encoding="utf-8", errors="ignore") as handle:
            handle.write(content or "")
    except Exception as error:
        return format_operator_result("WRITE ERROR", f"Could not write {target}: {error}")
    action = "APPENDED" if append else "WROTE"
    size_bytes = len((content or "").encode("utf-8"))
    return format_operator_result(action, f"Path: {target}\nBytes: {size_bytes}")


def replace_text_result(path: str, old: str, new: str, count: int = 0) -> str:
    target = resolve_operator_path(path)
    if not os.path.exists(target):
        return format_operator_result("REPLACE ERROR", f"File does not exist: {target}")
    if os.path.isdir(target):
        return format_operator_result("REPLACE ERROR", f"Path is a directory, not a file: {target}")
    try:
        with open(target, "r", encoding="utf-8", errors="ignore") as handle:
            text = handle.read()
    except Exception as error:
        return format_operator_result("REPLACE ERROR", f"Could not read {target}: {error}")

    if old not in text:
        return format_operator_result("REPLACE RESULT", f"No matches found in {target}")

    replacements = text.count(old)
    if count and count > 0:
        updated = text.replace(old, new, count)
        replacements = min(replacements, count)
    else:
        updated = text.replace(old, new)
    try:
        with open(target, "w", encoding="utf-8", errors="ignore") as handle:
            handle.write(updated)
    except Exception as error:
        return format_operator_result("REPLACE ERROR", f"Could not update {target}: {error}")
    return format_operator_result("REPLACE RESULT", f"Path: {target}\nReplacements: {replacements}")


def search_result(path: str, pattern: str, max_results: int = 20) -> str:
    target = resolve_operator_path(path)
    if not os.path.exists(target):
        return format_operator_result("SEARCH ERROR", f"Path does not exist: {target}")

    query = pattern or ""
    if not query.strip():
        return format_operator_result("SEARCH ERROR", "Missing search pattern.")

    try:
        compiled = re.compile(query, re.IGNORECASE)
    except re.error:
        compiled = re.compile(re.escape(query), re.IGNORECASE)

    candidate_files: List[str] = []
    if os.path.isfile(target):
        candidate_files.append(target)
    else:
        for root, dirs, files in os.walk(target):
            dirs[:] = [entry for entry in dirs if entry not in OPERATOR_SKIP_DIRS]
            for name in files:
                candidate_files.append(os.path.join(root, name))

    results = []
    for file_path in candidate_files:
        if len(results) >= max_results:
            break
        try:
            if os.path.getsize(file_path) > 2_000_000:
                continue
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if compiled.search(line):
                        results.append(f"{file_path}:{line_number}: {line.rstrip()}")
                        if len(results) >= max_results:
                            break
        except Exception:
            continue

    if not results:
        return format_operator_result("SEARCH RESULT", f"No matches for `{query}` under {target}")
    return format_operator_result(f"SEARCH RESULT :: {query}", "\n".join(results))


def mkdir_result(path: str) -> str:
    target = resolve_operator_path(path)
    os.makedirs(target, exist_ok=True)
    return format_operator_result("MKDIR RESULT", f"Directory ready: {target}")


def remove_path_result(path: str, recursive: bool = False) -> str:
    target = resolve_operator_path(path)
    if not os.path.exists(target):
        return format_operator_result("REMOVE RESULT", f"Already absent: {target}")
    try:
        if os.path.isdir(target):
            if recursive:
                shutil.rmtree(target)
            else:
                os.rmdir(target)
        else:
            os.remove(target)
    except Exception as error:
        return format_operator_result("REMOVE ERROR", f"Could not remove {target}: {error}")
    return format_operator_result("REMOVE RESULT", f"Removed: {target}")


def zip_list_result(path: str) -> str:
    target = resolve_operator_path(path)
    if not os.path.exists(target):
        return format_operator_result("ZIP ERROR", f"Archive does not exist: {target}")
    try:
        with zipfile.ZipFile(target, "r") as archive:
            entries = archive.infolist()
            lines = [f"{item.file_size:>10}  {item.filename}" for item in entries[:200]]
            if len(entries) > 200:
                lines.append(f"... {len(entries) - 200} more entries omitted ...")
    except Exception as error:
        return format_operator_result("ZIP ERROR", f"Could not inspect {target}: {error}")
    return format_operator_result(f"ZIP LIST :: {target}", "\n".join(lines) if lines else "[empty archive]")


def zip_extract_result(path: str, dest: str = "") -> str:
    target = resolve_operator_path(path)
    default_dest = os.path.join(os.path.dirname(target), os.path.splitext(os.path.basename(target))[0])
    destination = resolve_operator_path(dest or default_dest)
    os.makedirs(destination, exist_ok=True)
    destination_real = os.path.realpath(destination)
    try:
        with zipfile.ZipFile(target, "r") as archive:
            for member in archive.infolist():
                resolved = os.path.realpath(os.path.join(destination, member.filename))
                if not (resolved == destination_real or resolved.startswith(destination_real + os.sep)):
                    raise ValueError(f"Unsafe archive member path blocked: {member.filename}")
            archive.extractall(destination)
            count = len(archive.infolist())
    except Exception as error:
        return format_operator_result("ZIP ERROR", f"Could not extract {target}: {error}")
    return format_operator_result("ZIP EXTRACT", f"Archive: {target}\nDestination: {destination}\nEntries: {count}")


def zip_create_result(source: str, dest: str = "") -> str:
    source_path = resolve_operator_path(source)
    if not os.path.exists(source_path):
        return format_operator_result("ZIP ERROR", f"Source does not exist: {source_path}")
    if dest:
        destination = resolve_operator_path(dest)
    else:
        stem = os.path.basename(source_path.rstrip("\\/")) or "archive"
        destination = os.path.join(os.path.dirname(source_path), f"{stem}.zip")
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    written = 0
    try:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if os.path.isfile(source_path):
                archive.write(source_path, arcname=os.path.basename(source_path))
                written = 1
            else:
                base_parent = os.path.dirname(source_path)
                for root, _, files in os.walk(source_path):
                    for name in files:
                        file_path = os.path.join(root, name)
                        archive.write(file_path, arcname=os.path.relpath(file_path, base_parent))
                        written += 1
    except Exception as error:
        return format_operator_result("ZIP ERROR", f"Could not create archive {destination}: {error}")
    return format_operator_result("ZIP CREATE", f"Source: {source_path}\nArchive: {destination}\nFiles: {written}")


def extract_page_text(html_body: str) -> str:
    body = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_body or "")
    body = re.sub(r"(?s)<!--.*?-->", " ", body)
    text = re.sub(r"(?s)<[^>]+>", " ", body)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_http_url(raw_url: str) -> str:
    target = (raw_url or "").strip()
    if target and not re.match(r"^[a-z][a-z0-9+.-]*://", target, flags=re.I):
        target = "https://" + target
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return target


def fetch_url_result(url: str) -> str:
    target = normalize_http_url(url)
    if not target:
        return format_operator_result("FETCH ERROR", "Missing or unsupported URL. Use http:// or https://.")
    try:
        response = requests.get(
            target,
            timeout=25,
            headers={"User-Agent": "OpenZero-Agent-Zero/5.4"},
        )
        response.raise_for_status()
    except Exception as error:
        return format_operator_result("FETCH ERROR", f"Could not fetch {target}: {error}")
    title_match = re.search(r"(?is)<title>(.*?)</title>", response.text or "")
    title = unescape(title_match.group(1).strip()) if title_match else ""
    body = extract_page_text(response.text)
    summary = f"URL: {target}"
    if title:
        summary += f"\nTitle: {title}"
    summary += f"\n\n{trim_operator_text(body, 8000) or '[no readable text extracted]'}"
    return format_operator_result("WEB FETCH", summary)


def _duckduckgo_fallback_search(query: str, max_results: int = 6) -> List[Dict[str, str]]:
    if not query.strip():
        return []
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    response = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 OpenZero-Agent-Zero/5.4"},
    )
    response.raise_for_status()
    results = []
    matches = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', response.text, flags=re.I | re.S)
    for raw_link, raw_title in matches:
        link = unescape(raw_link)
        parsed = urlparse(link)
        if parsed.path == "/l/":
            qs = parse_qs(parsed.query)
            link = qs.get("uddg", [link])[0]
        title = extract_page_text(raw_title)
        title = unescape(title).strip()
        if not title or not link:
            continue
        if link.startswith("//"):
            link = "https:" + link
        results.append({"title": title, "link": link, "snippet": ""})
        if len(results) >= max(1, min(int(max_results or 6), 10)):
            break
    return results


def web_search_result(query: str, api_key: str, max_results: int = 6) -> str:
    if len(api_key or "") < 10:
        try:
            organic = _duckduckgo_fallback_search(query, max_results=max_results)
            source_label = "WEB SEARCH :: public fallback"
        except Exception as error:
            return format_operator_result(
                "SEARCH ERROR",
                f"Serper API key missing and public fallback search failed: {error}. Add SERPER_API_KEY for stronger search.",
            )
    else:
        try:
            response = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": max(1, min(int(max_results or 6), 10))},
                timeout=25,
            )
            response.raise_for_status()
            organic = response.json().get("organic", [])[: max(1, min(int(max_results or 6), 10))]
            source_label = f"WEB SEARCH :: {query}"
        except Exception as error:
            return format_operator_result("SEARCH ERROR", f"Web search failed: {error}")
    if not organic:
        return format_operator_result("SEARCH RESULT", f"No web results for `{query}`")
    lines = []
    for index, item in enumerate(organic, start=1):
        title = item.get("title") or "(untitled)"
        link = item.get("link") or ""
        snippet = item.get("snippet") or ""
        lines.append(f"{index}. {title}\n   {link}\n   {snippet}")
    return format_operator_result(source_label, "\n\n".join(lines))


def moltbot_browse_result(url: str) -> str:
    config = current_config()
    if not env_bool(config, "VISION_ENABLED", True):
        return format_operator_result("MOLTBOT OFFLINE", "Moltbot Vision is disabled in the panel. Enable Voice & Vision > Moltbot Vision.")
    target = normalize_http_url(url)
    if not target:
        return format_operator_result("MOLTBOT ERROR", "Missing or unsupported URL. Use http:// or https://.")
    try:
        response = requests.post("http://127.0.0.1:3000/goto", json={"url": target}, timeout=45)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "success":
            screenshot = data.get("screenshot") or "static/vision.png"
            body = f"URL: {target}\nScreenshot: {screenshot}\n\n{data.get('content', '')}"
            return format_operator_result("MOLTBOT BROWSER", body)
        return format_operator_result("MOLTBOT FAILED", data.get("content", "Unknown browser error."))
    except Exception as error:
        return format_operator_result(
            "MOLTBOT FAILED",
            f"{error}\nTry `pm2 restart zero-vision` or use fetch_url/web_search while the browser service recovers.",
        )


def ssh_target(host: str, user: str = "") -> str:
    return f"{user}@{host}" if user else host


def ssh_command_result(host: str, user: str, port: int, command: str) -> str:
    if not host or not command:
        return format_operator_result("SSH ERROR", "Missing host or command.")
    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        return format_operator_result("SSH ERROR", "SSH client not found on this node.")
    cmd = [
        ssh_bin,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-p",
        str(port or 22),
        ssh_target(host, user),
        command,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    except Exception as error:
        return format_operator_result("SSH ERROR", f"SSH command failed: {error}")
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        return format_operator_result("SSH ERROR", output or f"SSH exit code {result.returncode}")
    return format_operator_result("SSH RESULT", output or "[command completed with no output]")


def scp_result(host: str, user: str, port: int, source: str, destination: str, direction: str) -> str:
    if not host or not source or not destination:
        return format_operator_result("SCP ERROR", "Missing host, source, or destination.")
    scp_bin = shutil.which("scp")
    if not scp_bin:
        return format_operator_result("SCP ERROR", "SCP client not found on this node.")

    local_source = resolve_operator_path(source) if direction == "put" else resolve_operator_path(destination)
    if direction == "put" and not os.path.exists(local_source):
        return format_operator_result("SCP ERROR", f"Local source does not exist: {local_source}")

    remote_target = f"{ssh_target(host, user)}:{destination}" if direction == "put" else f"{ssh_target(host, user)}:{source}"
    local_target = resolve_operator_path(destination) if direction == "get" else local_source
    if direction == "get":
        os.makedirs(os.path.dirname(local_target), exist_ok=True)

    cmd = [
        scp_bin,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-P",
        str(port or 22),
    ]
    if direction == "put":
        cmd.extend([local_source, remote_target])
    else:
        cmd.extend([remote_target, local_target])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    except Exception as error:
        return format_operator_result("SCP ERROR", f"SCP transfer failed: {error}")
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        return format_operator_result("SCP ERROR", output or f"SCP exit code {result.returncode}")
    label = "SCP PUT" if direction == "put" else "SCP GET"
    return format_operator_result(label, output or "[transfer completed]")


def run_tool_action(raw_reply: str, session_id: str = "") -> Dict[str, str]:
    config = current_config()
    voice = current_voice()

    match = re.search(r"<tool>(.*?)</tool>", raw_reply, re.DOTALL | re.IGNORECASE)
    if match:
        raw_payload = strip_json_fences(match.group(1))
        try:
            payload = json.loads(raw_payload)
        except Exception as error:
            return {"tool": "tool", "result": format_operator_result("TOOL ERROR", f"Invalid tool payload: {error}")}

        action_name = str(payload.get("action") or payload.get("tool") or "").strip().lower()
        aliases = {
            "ls": "list_dir",
            "scan": "tree",
            "read": "read_file",
            "write": "write_file",
            "append": "append_file",
            "replace": "replace_text",
            "search_files": "search",
            "mkdirs": "mkdir",
            "rm": "remove_path",
            "delete": "remove_path",
            "extract_zip": "zip_extract",
            "create_zip": "zip_create",
            "browse_url": "fetch_url",
            "search_web": "web_search",
            "browse": "moltbot_browse",
            "moltbot": "moltbot_browse",
            "vision": "moltbot_browse",
            "open_page": "moltbot_browse",
            "read_live_page": "moltbot_browse",
            "skill": "skills",
            "capabilities": "skills",
            "ssh": "ssh_command",
            "copy_to_remote": "scp_put",
            "copy_from_remote": "scp_get",
        }
        action_name = aliases.get(action_name, action_name)
        emit_agent_log(f"Executing operator action: {action_name or 'unknown'}", session_id)

        if action_name == "list_dir":
            return {"tool": action_name, "result": list_dir_result(payload.get("path", "."))}
        if action_name == "tree":
            return {
                "tool": action_name,
                "result": tree_result(payload.get("path", "."), int(payload.get("max_depth") or 3), int(payload.get("max_entries") or 250)),
            }
        if action_name == "read_file":
            return {
                "tool": action_name,
                "result": read_file_result(
                    payload.get("path", ""),
                    int(payload.get("start_line") or 1),
                    int(payload.get("end_line") or 200),
                ),
            }
        if action_name == "write_file":
            return {"tool": action_name, "result": write_file_result(payload.get("path", ""), str(payload.get("content") or ""), append=False)}
        if action_name == "append_file":
            return {"tool": action_name, "result": write_file_result(payload.get("path", ""), str(payload.get("content") or ""), append=True)}
        if action_name == "replace_text":
            return {
                "tool": action_name,
                "result": replace_text_result(
                    payload.get("path", ""),
                    str(payload.get("old") or ""),
                    str(payload.get("new") or ""),
                    int(payload.get("count") or 0),
                ),
            }
        if action_name == "search":
            return {
                "tool": action_name,
                "result": search_result(payload.get("path", "."), str(payload.get("pattern") or ""), int(payload.get("max_results") or 20)),
            }
        if action_name == "mkdir":
            return {"tool": action_name, "result": mkdir_result(payload.get("path", ""))}
        if action_name == "remove_path":
            return {
                "tool": action_name,
                "result": remove_path_result(payload.get("path", ""), bool(payload.get("recursive"))),
            }
        if action_name == "zip_list":
            return {"tool": action_name, "result": zip_list_result(payload.get("path", ""))}
        if action_name == "zip_extract":
            return {"tool": action_name, "result": zip_extract_result(payload.get("path", ""), payload.get("dest", ""))}
        if action_name == "zip_create":
            return {"tool": action_name, "result": zip_create_result(payload.get("source", ""), payload.get("dest", ""))}
        if action_name == "fetch_url":
            return {"tool": action_name, "result": fetch_url_result(payload.get("url", ""))}
        if action_name == "web_search":
            return {
                "tool": action_name,
                "result": web_search_result(str(payload.get("query") or ""), config.get("SERPER_API_KEY", ""), int(payload.get("max_results") or 6)),
            }
        if action_name == "moltbot_browse":
            target_url = str(payload.get("url") or payload.get("target") or payload.get("page") or "")
            return {"tool": action_name, "result": moltbot_browse_result(target_url)}
        if action_name == "skills":
            return {"tool": action_name, "result": skill_catalog_result(str(payload.get("query") or ""))}
        if action_name == "ssh_command":
            return {
                "tool": action_name,
                "result": ssh_command_result(
                    str(payload.get("host") or ""),
                    str(payload.get("user") or ""),
                    int(payload.get("port") or 22),
                    str(payload.get("command") or ""),
                ),
            }
        if action_name == "scp_put":
            return {
                "tool": action_name,
                "result": scp_result(
                    str(payload.get("host") or ""),
                    str(payload.get("user") or ""),
                    int(payload.get("port") or 22),
                    str(payload.get("source") or ""),
                    str(payload.get("destination") or ""),
                    "put",
                ),
            }
        if action_name == "scp_get":
            return {
                "tool": action_name,
                "result": scp_result(
                    str(payload.get("host") or ""),
                    str(payload.get("user") or ""),
                    int(payload.get("port") or 22),
                    str(payload.get("source") or ""),
                    str(payload.get("destination") or ""),
                    "get",
                ),
            }
        return {"tool": action_name or "tool", "result": format_operator_result("TOOL ERROR", f"Unsupported action: {action_name or 'missing'}")}

    match = re.search(r"<bash>(.*?)</bash>", raw_reply, re.DOTALL)
    if match:
        command = match.group(1).strip()
        emit_agent_log(f"Executing bash: {command}", session_id)
        result = execute_system_command(command, config.get("SUDO_PASS", ""))
        return {"tool": "bash", "result": f"**[TERMINAL RESULT]**\n```bash\n{result}\n```"}

    match = re.search(r"<osint>(.*?)</osint>", raw_reply, re.DOTALL)
    if match:
        target = match.group(1).strip()
        emit_agent_log(f"Running OSINT on: {target}", session_id)
        serper_key = config.get("SERPER_API_KEY", "")
        if len(serper_key) < 10:
            return {"tool": "osint", "result": "[OSINT FAILED] No Serper API key configured."}
        try:
            query = f'"{target}" (site:linkedin.com OR site:github.com OR site:x.com OR filetype:pdf)'
            response = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                json={"q": query},
                timeout=20,
            )
            response.raise_for_status()
            organic = response.json().get("organic", [])
            return {"tool": "osint", "result": f"**[OSINT RESULT]**\n```json\n{organic[:6]}\n```"}
        except Exception as error:
            return {"tool": "osint", "result": f"[OSINT FAILED] {error}"}

    match = re.search(r"<browse>(.*?)</browse>", raw_reply, re.DOTALL)
    if match:
        url = match.group(1).strip()
        emit_agent_log(f"Moltbot browsing: {url}", session_id)
        return {"tool": "browse", "result": moltbot_browse_result(url)}

    match = re.search(r"<speak>(.*?)</speak>", raw_reply, re.DOTALL)
    if match:
        text = match.group(1).strip()
        emit_agent_log(f"Speaking locally: {text[:60]}...", session_id)
        speech = voice.speak_text(text)
        if speech.get("status") == "success":
            hive.broadcast_voice_event(text, config)
        return {"tool": "speak", "result": f"**[VOICE RESULT]**\n```json\n{speech}\n```"}

    return {}


def maybe_speak_reply(reply: str) -> None:
    config = current_config()
    if not env_bool(config, "VOICE_ENABLED") or not env_bool(config, "VOICE_TTS_ENABLED"):
        return
    plain_reply = re.sub(r"<[^>]+>", "", reply).strip()
    if plain_reply:
        current_voice().speak_text(plain_reply[:400])


def remember_shareable_exchange(prompt: str, reply: str, comp_mode: str, agent_mode: str) -> Dict[str, object]:
    exchange = {
        "id": str(int(time.time() * 1000)),
        "prompt": prompt[:6000],
        "reply": reply[:12000],
        "comp_mode": comp_mode,
        "agent_mode": agent_mode,
        "created_at": int(time.time()),
        "shared": False,
    }
    with LAST_SHAREABLE_EXCHANGE_LOCK:
        LAST_SHAREABLE_EXCHANGE.clear()
        LAST_SHAREABLE_EXCHANGE.update(exchange)
    return exchange


def broadcast_hive_reply(prompt: str, reply: str, comp_mode: str, agent_mode: str) -> None:
    config = current_config()
    if config.get("HIVE_MIND_ENABLED", "false") != "true" or not reply.strip():
        return
    if config.get("OPENZERO_HIVE_SHARE_MODE", "manual").lower() != "auto_safe":
        return
    if agent_mode == "terminal":
        return

    payload_config = dict(config)
    payload_meta = {"agent_mode": agent_mode, "comp_mode": comp_mode, "manual_share": False, "source": "auto_safe"}

    def worker():
        try:
            hive.broadcast_to_hive(prompt, reply, payload_config, metadata=payload_meta)
        except Exception:
            pass

    if env_bool(config, "OPENZERO_HIVE_BACKGROUND_PUSH", True):
        threading.Thread(target=worker, daemon=True).start()
    else:
        worker()


def learn_from_reply(prompt: str, reply: str, comp_mode: str, agent_mode: str, session_id: str = "") -> None:
    config = current_config()
    if not env_bool(config, "OPENZERO_LOCAL_LEARNING_ENABLED", True):
        return
    if agent_mode == "terminal" and not env_bool(config, "OPENZERO_LOCAL_LEARNING_TERMINAL", False):
        return
    if not reply.strip():
        return

    payload_config = dict(config)
    metadata = {
        "agent_mode": agent_mode,
        "comp_mode": comp_mode,
        "source": "finished_agent_reply",
        "terminal_learning": agent_mode == "terminal",
    }

    def worker():
        try:
            result = hive.learn_locally(prompt, reply, payload_config, metadata=metadata)
            if result.get("status") == "success":
                emit_agent_log(f"Local learning updated ({result.get('risk_level', 'low')}).", session_id)
        except Exception as error:
            emit_agent_log(f"Local learning skipped: {error}", session_id)

    if env_bool(config, "OPENZERO_LOW_CPU_MODE", True):
        threading.Thread(target=worker, daemon=True).start()
    else:
        worker()


def openzero_api_hash(token: str) -> str:
    return hashlib.sha256(f"openzero-api:{(token or '').strip()}".encode("utf-8")).hexdigest()


def openzero_api_hint(token: str) -> str:
    token = (token or "").strip()
    if len(token) <= 16:
        return ""
    return f"{token[:7]}...{token[-6:]}"


def openzero_api_error(message: str, status_code: int = 400, error_type: str = "invalid_request_error"):
    return (
        jsonify(
            {
                "error": {
                    "message": str(message or "OpenZero API error."),
                    "type": error_type,
                    "code": None,
                }
            }
        ),
        status_code,
    )


def openzero_bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    match = re.match(r"^\s*Bearer\s+(.+?)\s*$", header, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def openzero_api_authorized(config: Dict[str, str]) -> bool:
    if not env_bool(config, "OPENZERO_API_ENABLED", False):
        return False

    token = openzero_bearer_token()
    if not token:
        return False

    stored_hash = (config.get("OPENZERO_API_KEY_HASH") or "").strip()
    if stored_hash and hmac.compare_digest(openzero_api_hash(token), stored_hash):
        return True

    legacy_plain = (config.get("OPENZERO_API_KEY") or "").strip()
    return bool(legacy_plain and hmac.compare_digest(token, legacy_plain))


def openzero_message_content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text") or ""))
        return "\n".join(chunk for chunk in chunks if chunk.strip())
    return ""


def openzero_messages_to_prompt(messages) -> Dict[str, str]:
    if not isinstance(messages, list):
        return {"system": "", "prompt": ""}

    system_chunks = []
    dialogue = []
    for item in messages[-24:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").strip().lower()
        text = openzero_message_content_to_text(item.get("content"))
        if not text.strip():
            continue
        if role == "system":
            system_chunks.append(text.strip())
        elif role == "assistant":
            dialogue.append(f"ASSISTANT: {text.strip()}")
        else:
            dialogue.append(f"USER: {text.strip()}")

    return {
        "system": "\n\n".join(system_chunks)[-8000:],
        "prompt": "\n".join(dialogue)[-24000:],
    }


def ask_ollama_openai_compatible(messages, requested_model: str = "", max_tokens: int = 1024, temperature: float = 0.6) -> Dict[str, str]:
    config = dict(current_config())
    requested_model = normalize_local_model_name(requested_model or "")
    if requested_model:
        if is_cloud_model(requested_model) or is_bitnet_model(requested_model):
            raise ValueError("OpenZero /v1 API is local Ollama only. Choose an installed Ollama model.")
        installed = set(list_ollama_models())
        if requested_model not in installed:
            raise ValueError(f"Requested OpenZero model is not installed on this node: {requested_model}")
        config["ACTIVE_MODEL"] = requested_model
        config["LOCAL_ENGINE"] = "ollama"

    profile = resource_profile(config)
    resolution = resolve_local_model_selection(config, profile, include_ollama_status=False)
    if resolution["status"] == "missing":
        raise RuntimeError("Local Ollama brain is not ready on this OpenZero node.")

    parts = openzero_messages_to_prompt(messages)
    system_context = parts["system"]
    prompt = parts["prompt"] or "Hello."
    final_prompt = (
        f"{get_system_prompt('chat')}\n\n"
        f"API SYSTEM CONTEXT:\n{system_context}\n\n"
        f"CHAT:\n{prompt}\n\n"
        "OPENZERO:"
    )

    payload = {
        "model": resolution["model"],
        "prompt": final_prompt,
        "stream": False,
        "keep_alive": cpu_profile["keep_alive"],
        "options": {
            "num_ctx": effective_local_context_window(config, profile),
            "num_thread": cpu_profile["threads"],
            "num_batch": cpu_profile["num_batch"],
            "num_predict": max(64, min(int(max_tokens or 1024), 4096)),
            "temperature": max(0.0, min(float(temperature), 2.0)),
        },
    }
    response = requests.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=240)
    if response.status_code >= 400:
        detail = response.text.strip() or response.reason or f"HTTP {response.status_code}"
        maybe_trigger_runtime_self_heal(detail)
        raise RuntimeError(f"Local brain offline: {detail}")
    response.raise_for_status()
    return {"model": resolution["model"], "reply": str(response.json().get("response") or "").strip()}


@app.route("/")
def index():
    return render_template("index.html")


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.route("/landing")
def landing():
    return render_template("landing.html")


@app.route("/manual")
@app.route("/manual.html")
def manual():
    return render_template("manual.html")


@app.route("/api/openzero/key", methods=["POST"])
def rotate_openzero_api_key():
    data = request.json or {}
    action = str(data.get("action") or "rotate").strip().lower()
    if action == "revoke":
        config = apply_config_updates(
            {
                "OPENZERO_API_ENABLED": "false",
                "OPENZERO_API_KEY_HASH": "",
                "OPENZERO_API_KEY_HINT": "",
            }
        )
        return jsonify(
            {
                "status": "success",
                "message": "OpenZero API key revoked.",
                "enabled": env_bool(config, "OPENZERO_API_ENABLED", False),
                "hint": "",
            }
        )

    token = "oz_" + secrets.token_urlsafe(32)
    config = apply_config_updates(
        {
            "OPENZERO_API_ENABLED": "true",
            "OPENZERO_API_KEY_HASH": openzero_api_hash(token),
            "OPENZERO_API_KEY_HINT": openzero_api_hint(token),
        }
    )
    return jsonify(
        {
            "status": "success",
            "message": "OpenZero API key created. Copy it now; it will not be shown again.",
            "api_key": token,
            "hint": config.get("OPENZERO_API_KEY_HINT", ""),
            "enabled": env_bool(config, "OPENZERO_API_ENABLED", False),
        }
    )


@app.route("/v1/chat/completions", methods=["POST"])
def openzero_chat_completions():
    config = current_config()
    if not openzero_api_authorized(config):
        return openzero_api_error("Unauthorized OpenZero API key.", 401, "authentication_error")

    data = request.json or {}
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        return openzero_api_error("messages must be a non-empty array.", 400)

    requested_model = str(data.get("model") or "").strip()
    try:
        max_tokens = int(data.get("max_tokens") or data.get("max_completion_tokens") or 1024)
    except Exception:
        max_tokens = 1024
    try:
        temperature = float(data.get("temperature") if data.get("temperature") is not None else 0.6)
    except Exception:
        temperature = 0.6

    try:
        result = ask_ollama_openai_compatible(messages, requested_model, max_tokens, temperature)
    except ValueError as error:
        return openzero_api_error(str(error), 400)
    except Exception as error:
        return openzero_api_error(str(error), 503, "server_error")

    created = int(time.time())
    return jsonify(
        {
            "id": f"chatcmpl-openzero-{created}",
            "object": "chat.completion",
            "created": created,
            "model": result["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result["reply"]},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }
    )


@app.route("/stats")
def stats():
    config = current_config()
    profile = resource_profile(config)
    local_resolution = resolve_local_model_selection(config, profile, include_ollama_status=False)
    bitnet_runtime = bitnet_status(config)
    hive_state = hive.status_snapshot(config)
    federation = hive_state.get("federation", {})
    hive_label = "OFFLINE"
    if hive_state["hive_enabled"]:
        hive_label = f"{federation.get('mode', 'standalone').upper()} / LIVE"
    display_model = config.get("ACTIVE_MODEL")
    if not is_cloud_model(display_model or ""):
        display_model = local_resolution["model"]
    model_warning = "" if is_cloud_model(config.get("ACTIVE_MODEL", "")) else local_resolution.get("warning", "")
    return jsonify(
        {
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent,
            "mode": config.get("COMP_MODE", "hybrid").upper(),
            "hive": hive_label,
            "identity": HOSTNAME,
            "cwd": BASE_DIR,
            "active_model": display_model,
            "saved_active_model": config.get("ACTIVE_MODEL"),
            "model_warning": model_warning,
            "recommended_model": profile["recommended_model"],
            "node_tier": profile["node_tier"],
            "context_window": effective_local_context_window(config, profile),
            "ram_gb": profile["ram_gb"],
            "local_engine": local_engine_from(config),
            "bitnet_ready": bitnet_runtime["ready"],
            "p_good_threshold": config.get("P_GOOD_THRESHOLD"),
            "integrity": integrity_status(BASE_DIR),
            "hive_mode": federation.get("mode", "standalone"),
            "hive_primary": federation.get("primary_url", ""),
            "hive_mirrors": len(federation.get("mirror_urls", [])),
            "hive_queue": federation.get("queued_events", 0),
            "hive_cache": federation.get("local_knowledge_events", 0),
            "hive_lookup": "ON" if federation.get("remote_lookup_enabled") else "LOCAL-FIRST",
            "hive_share_mode": federation.get("share_mode", "manual"),
        }
    )


@app.route("/api/skills", methods=["GET"])
def get_skills():
    query = request.args.get("query", "")
    config = current_config()
    return jsonify(
        {
            **skill_catalog_payload(query),
            "automation_enabled": env_bool(config, "OPENZERO_AUTOMATION_ENABLED", True),
            "local_learning_enabled": env_bool(config, "OPENZERO_LOCAL_LEARNING_ENABLED", True),
            "vision_enabled": env_bool(config, "VISION_ENABLED", True),
            "serper_enabled": bool(config.get("SERPER_API_KEY")),
            "low_cpu_mode": env_bool(config, "OPENZERO_LOW_CPU_MODE", True),
        }
    )


@app.route("/api/vision/status", methods=["GET"])
def vision_status():
    config = current_config()
    payload = {
        "status": "success",
        "enabled": env_bool(config, "VISION_ENABLED", True),
        "moltbot_url": "http://127.0.0.1:3000/status",
    }
    try:
        response = requests.get("http://127.0.0.1:3000/status", timeout=4)
        payload["moltbot"] = response.json()
    except Exception as error:
        payload["moltbot"] = {"status": "error", "message": str(error)}
    return jsonify(payload)


@app.route("/api/config", methods=["GET"])
def get_config():
    config = current_config()
    profile = resource_profile(config)
    local_resolution = resolve_local_model_selection(config, profile)
    bitnet_runtime = bitnet_status(config)
    saved_active_model = config.get("ACTIVE_MODEL", "")
    effective_active_model = saved_active_model if is_cloud_model(saved_active_model) else local_resolution["model"]
    active_model_warning = "" if is_cloud_model(saved_active_model) else local_resolution["warning"]
    active_model_status = "cloud" if is_cloud_model(saved_active_model) else local_resolution["status"]
    voice_status = current_voice().status()
    hive_state = hive.status_snapshot(config)
    ollama_models = list_ollama_models()
    gguf_files = list_local_gguf_files()
    custom_models = custom_model_inventory(ollama_models)
    return jsonify(
        {
            **config,
            "SAVED_ACTIVE_MODEL": saved_active_model,
            "ACTIVE_MODEL_EFFECTIVE": effective_active_model,
            "ACTIVE_MODEL_WARNING": active_model_warning,
            "ACTIVE_MODEL_STATUS": active_model_status,
            "LOCAL_ENGINE_EFFECTIVE": local_engine_from(config),
            "HAS_GROQ": bool(config.get("GROQ_API_KEY")),
            "HAS_SERPER": bool(config.get("SERPER_API_KEY")),
            "HAS_TELEGRAM": bool(config.get("TELEGRAM_BOT_TOKEN")),
            "HAS_OPENZERO_API_KEY": bool(config.get("OPENZERO_API_KEY_HASH") or config.get("OPENZERO_API_KEY")),
            "OPENZERO_API_KEY_HINT_PUBLIC": config.get("OPENZERO_API_KEY_HINT", ""),
            "PROFILE": profile,
            "LOCAL_MODEL_PRESETS": LOCAL_MODEL_PRESETS,
            "BITNET_MODEL_PRESETS": BITNET_MODEL_PRESETS,
            "BITNET_STATUS": bitnet_runtime,
            "OLLAMA_STATUS": local_resolution["ollama"],
            "LOCAL_MODEL_CANDIDATES": local_resolution["preferred_candidates"],
            "MODEL_STORES": {
                "ollama_store": "Ollama system model store",
                "gguf_folder": MODELS_FOLDER,
                "ollama_models": ollama_models,
                "gguf_files": gguf_files,
                "custom_models": custom_models,
                "custom_registry": CUSTOM_MODEL_REGISTRY_PATH,
            },
            "VOICE_STATUS": voice_status,
            "INTEGRITY_STATUS": integrity_status(BASE_DIR),
            "FEDERATION_STATUS": hive_state.get("federation", {}),
            "HIVE_STATUS": hive_state,
            "NODE_CAPABILITIES": hive.current_capabilities(),
        }
    )


@app.route("/api/integrity/status", methods=["GET"])
def get_integrity_status():
    return jsonify({"status": "success", "integrity": integrity_status(BASE_DIR)})


@app.route("/update_config", methods=["POST"])
def update_config():
    data = request.json or {}
    key = data.get("key")
    value = data.get("value", "")
    if not key:
        return jsonify({"status": "error", "message": "Missing key"}), 400
    config = apply_config_updates({key: value})
    return jsonify({"status": "success", "config": config})


@app.route("/api/config/bulk", methods=["POST"])
def update_config_bulk():
    data = request.json or {}
    updates = data.get("updates", {})
    if not updates:
        return jsonify({"status": "error", "message": "No updates provided"}), 400
    config = apply_config_updates(updates)
    return jsonify({"status": "success", "config": config})


@app.route("/api/models", methods=["GET"])
def get_models():
    models = list_ollama_models()
    gguf_files = list_local_gguf_files()
    custom_models = custom_model_inventory(models)
    profile = resource_profile(current_config())
    bitnet_runtime = bitnet_status()
    return jsonify(
        {
            "status": "success" if (models or gguf_files or custom_models or bitnet_runtime.get("ready")) else "partial",
            "models": models,
            "gguf_files": gguf_files,
            "custom_models": custom_models,
            "bitnet": bitnet_runtime,
            "ollama_status": ollama_version_status(),
            "stores": {
                "ollama_store": "Ollama system model store",
                "gguf_folder": MODELS_FOLDER,
                "custom_registry": CUSTOM_MODEL_REGISTRY_PATH,
            },
            "presets": LOCAL_MODEL_PRESETS,
            "recommended_candidates": preferred_local_model_candidates(profile),
        }
    )


@app.route("/api/bitnet/status", methods=["GET"])
def get_bitnet_status():
    return jsonify({"status": "success", "bitnet": bitnet_status()})


@app.route("/api/bitnet/install", methods=["POST"])
def install_bitnet_runtime():
    payload = run_bitnet_installer(activate=True, remove=False)
    if payload.get("status") != "success":
        return jsonify(payload), 500
    config = current_config()
    updated = apply_config_updates(
        {
            "LOCAL_ENGINE": "bitnet",
            "BITNET_ENABLED": "true",
            "BITNET_MODEL_ID": payload.get("hf_repo", BITNET_DEFAULT_MODEL_ID),
            "BITNET_MODEL_ALIAS": payload.get("model_alias", BITNET_DEFAULT_MODEL_ALIAS),
            "BITNET_MODEL_PATH": payload.get("model_file", BITNET_DEFAULT_MODEL_FILE),
            "BITNET_CONTEXT_WINDOW": str(bitnet_context_window(config)),
            "ACTIVE_MODEL": payload.get("model_alias", BITNET_DEFAULT_MODEL_ALIAS),
        }
    )
    socketio.emit("reload_models", {"reason": "bitnet_installed", "model": updated.get("ACTIVE_MODEL")})
    return jsonify(
        {
            "status": "success",
            "message": "BitNet 1-bit runtime is installed and active. OpenZero can now use the Microsoft CPU-efficient lane.",
            "bitnet": bitnet_status(updated),
            "config": updated,
        }
    )


@app.route("/api/bitnet/repair", methods=["POST"])
def repair_bitnet_runtime():
    payload = run_bitnet_installer(activate=True, remove=False)
    if payload.get("status") != "success":
        return jsonify(payload), 500
    config = apply_config_updates(
        {
            "LOCAL_ENGINE": "bitnet",
            "BITNET_ENABLED": "true",
            "BITNET_MODEL_ID": payload.get("hf_repo", BITNET_DEFAULT_MODEL_ID),
            "BITNET_MODEL_ALIAS": payload.get("model_alias", BITNET_DEFAULT_MODEL_ALIAS),
            "BITNET_MODEL_PATH": payload.get("model_file", BITNET_DEFAULT_MODEL_FILE),
            "ACTIVE_MODEL": payload.get("model_alias", BITNET_DEFAULT_MODEL_ALIAS),
        }
    )
    socketio.emit("reload_models", {"reason": "bitnet_repaired", "model": config.get("ACTIVE_MODEL")})
    return jsonify(
        {
            "status": "success",
            "message": "BitNet runtime repair finished.",
            "bitnet": bitnet_status(config),
            "config": config,
        }
    )


@app.route("/api/bitnet/remove", methods=["POST"])
def remove_bitnet_runtime():
    payload = run_bitnet_installer(activate=False, remove=True)
    if payload.get("status") != "success":
        return jsonify(payload), 500
    profile = resource_profile(current_config())
    fallback = choose_installed_local_model(set(list_ollama_models()), profile)
    updates = {
        "LOCAL_ENGINE": "ollama",
        "BITNET_ENABLED": "false",
        "ACTIVE_MODEL": fallback or preferred_local_model_candidates(profile)[0],
        "NODE_RECOMMENDED_MODEL": fallback or preferred_local_model_candidates(profile)[0],
    }
    config = apply_config_updates(updates)
    socketio.emit("reload_models", {"reason": "bitnet_removed", "model": config.get("ACTIVE_MODEL")})
    return jsonify(
        {
            "status": "success",
            "message": "BitNet add-on removed. OpenZero switched back to the Ollama local lane.",
            "bitnet": bitnet_status(config),
            "config": config,
        }
    )


@app.route("/api/install_local_model", methods=["POST"])
def install_local_model():
    data = request.json or {}
    model_name = normalize_local_model_name(data.get("model", ""))
    allowed = {item["id"] for item in LOCAL_MODEL_PRESETS}
    if model_name not in allowed:
        return jsonify({"status": "error", "message": "Unsupported local model preset."}), 400

    try:
        result = run_ollama_pull(model_name)
    except Exception as error:
        return jsonify({"status": "error", "message": f"Install failed: {error}"}), 500

    auto_upgraded = False
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "ollama pull failed").strip()
        if ollama_upgrade_needed(message):
            upgrade = upgrade_ollama_runtime()
            auto_upgraded = upgrade.get("ready", False)
            if auto_upgraded:
                result = run_ollama_pull(model_name)

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "ollama pull failed").strip()
        if ollama_upgrade_needed(message):
            message = (
                f"{message}\n\n"
                "OpenZero detected an outdated Ollama runtime. Use the `Update Ollama` or `Repair Local Brain` button, "
                "or rerun `curl -fsSL https://ollama.com/install.sh | sh`."
            )
        return jsonify({"status": "error", "message": message, "needs_ollama_upgrade": ollama_upgrade_needed(message)}), 500

    config = apply_config_updates({"ACTIVE_MODEL": model_name, "NODE_RECOMMENDED_MODEL": model_name})
    socketio.emit("reload_models", {"reason": "local_model_installed", "model": model_name})
    return jsonify(
        {
            "status": "success",
            "message": (
                f"{model_name} is installed and ready in the Ollama model store."
                + (" OpenZero also refreshed Ollama first because the local runtime was too old." if auto_upgraded else "")
            ),
            "model": model_name,
            "output": (result.stdout or "").strip(),
            "config": config,
        }
    )


@app.route("/api/ollama/status", methods=["GET"])
def ollama_status():
    return jsonify({"status": "success", "ollama": ollama_version_status(), "models": list_ollama_models()})


@app.route("/api/ollama/upgrade", methods=["POST"])
def ollama_upgrade():
    report = upgrade_ollama_runtime()
    http_code = 200 if report.get("ready") else 500
    message = "Ollama upgrade cycle finished and the local API is reachable." if report.get("ready") else (
        "Ollama upgrade ran, but the local API still is not responding yet."
    )
    return jsonify({"status": "success" if report.get("ready") else "error", "message": message, "report": report}), http_code


@app.route("/api/repair_local_brain", methods=["POST"])
def repair_local_brain():
    config = current_config()
    profile = resource_profile(config)
    upgrade = upgrade_ollama_runtime()
    installed = set(list_ollama_models())
    attempts = []

    for candidate in preferred_local_model_candidates(profile):
        if candidate in installed:
            updated = apply_config_updates({"ACTIVE_MODEL": candidate, "NODE_RECOMMENDED_MODEL": candidate})
            socketio.emit("reload_models", {"reason": "local_model_repaired", "model": candidate})
            return jsonify(
                {
                    "status": "success",
                    "message": f"OpenZero repaired the local brain and switched to `{candidate}`.",
                    "model": candidate,
                    "report": upgrade,
                    "attempts": attempts,
                    "config": updated,
                }
            )

    for candidate in preferred_local_model_candidates(profile):
        result = run_ollama_pull(candidate)
        output = (result.stdout or result.stderr or "").strip()
        attempts.append({"model": candidate, "ok": result.returncode == 0, "output": output})
        if result.returncode == 0:
            updated = apply_config_updates({"ACTIVE_MODEL": candidate, "NODE_RECOMMENDED_MODEL": candidate})
            socketio.emit("reload_models", {"reason": "local_model_repaired", "model": candidate})
            return jsonify(
                {
                    "status": "success",
                    "message": f"OpenZero repaired the local brain and installed `{candidate}`.",
                    "model": candidate,
                    "report": upgrade,
                    "attempts": attempts,
                    "config": updated,
                }
            )

    return jsonify(
        {
            "status": "error",
            "message": (
                "OpenZero could not repair the local brain automatically. "
                "Check the Ollama logs, then rerun the repair after the runtime is healthy."
            ),
            "report": upgrade,
            "attempts": attempts,
        }
    ), 500


@app.route("/api/delete_model", methods=["POST"])
def delete_model():
    data = request.json or {}
    model_name = normalize_local_model_name((data.get("model") or "").strip())
    gguf_file = secure_filename((data.get("gguf_file") or "").strip())
    delete_file = bool(data.get("delete_file"))
    delete_all_aliases = bool(data.get("delete_all_aliases"))

    if is_bitnet_model(model_name):
        return jsonify(
            {
                "status": "error",
                "message": "BitNet is an optional runtime add-on, not an Ollama alias. Use the dedicated Remove BitNet control instead.",
            }
        ), 400

    if not model_name and not gguf_file:
        return jsonify({"status": "error", "message": "Missing model alias or GGUF file."}), 400

    inventory = custom_model_inventory()
    record = find_custom_model_record(inventory, model_name=model_name, gguf_file=gguf_file)
    aliases_to_delete = []
    if model_name:
        aliases_to_delete.append(model_name)
    if record:
        if delete_all_aliases or gguf_file:
            aliases_to_delete.extend(record.get("aliases", []))
        if delete_file and not gguf_file:
            gguf_file = record.get("gguf_file", "")

    aliases_to_delete = sorted({alias for alias in aliases_to_delete if alias})
    if gguf_file and not delete_file and not aliases_to_delete:
        delete_file = True

    removed_aliases = []
    alias_notes = []
    alias_errors = []
    for alias in aliases_to_delete:
        try:
            response = requests.delete("http://127.0.0.1:11434/api/delete", json={"name": alias}, timeout=30)
            if response.status_code in {200, 204}:
                removed_aliases.append(alias)
                continue
            if response.status_code == 404:
                alias_notes.append(f"Ollama alias `{alias}` was already absent.")
                continue
            alias_errors.append(f"Ollama delete for `{alias}` returned {response.status_code}: {(response.text or response.reason).strip()}")
        except Exception as error:
            alias_errors.append(f"Ollama delete for `{alias}` failed: {error}")

    removed_file = ""
    if delete_file and gguf_file:
        file_path = os.path.join(MODELS_FOLDER, gguf_file)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                removed_file = gguf_file
            except Exception as error:
                alias_errors.append(f"Could not remove GGUF file `{gguf_file}`: {error}")
        else:
            alias_notes.append(f"GGUF file `{gguf_file}` was already absent.")

    registry_removed = prune_custom_model_registry(removed_aliases or aliases_to_delete, gguf_file=removed_file or gguf_file)
    if registry_removed and not removed_file and gguf_file:
        alias_notes.append(f"Removed {registry_removed} custom model registry entr{'y' if registry_removed == 1 else 'ies'}.")

    if not removed_aliases and not removed_file and alias_errors:
        return jsonify({"status": "error", "message": " // ".join(alias_errors)}), 500

    fallback_note = ""
    config_update = None
    active_model = normalize_local_model_name(current_config().get("ACTIVE_MODEL", ""))
    if active_model and active_model in set(removed_aliases):
        config = current_config()
        profile = resource_profile(config)
        installed = set(list_ollama_models())
        if installed:
            fallback = choose_installed_local_model(installed, profile)
            config_update = apply_config_updates({"ACTIVE_MODEL": fallback, "NODE_RECOMMENDED_MODEL": fallback})
            fallback_note = f"Active model was removed, so OpenZero switched to `{fallback}`."
        else:
            fallback = preferred_local_model_candidates(profile)[0]
            config_update = apply_config_updates({"ACTIVE_MODEL": fallback, "NODE_RECOMMENDED_MODEL": fallback})
            fallback_note = (
                f"Active model was removed and no other local model is installed, so OpenZero reset to preferred target `{fallback}`."
            )

    socketio.emit("reload_models", {"reason": "model_deleted", "model": model_name, "gguf_file": gguf_file})
    details = []
    if removed_aliases:
        details.append(f"Removed Ollama alias{'es' if len(removed_aliases) != 1 else ''}: {', '.join(f'`{alias}`' for alias in removed_aliases)}.")
    if removed_file:
        details.append(f"Removed GGUF file `{removed_file}` from the local model folder.")
    if alias_notes:
        details.extend(alias_notes)
    if fallback_note:
        details.append(fallback_note)
    if alias_errors:
        details.extend(alias_errors)

    return jsonify(
        {
            "status": "success",
            "message": " ".join(details) or "Model cleanup completed.",
            "removed_aliases": removed_aliases,
            "removed_file": removed_file,
            "config": config_update,
        }
    )


def normalize_gguf_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        return ""
    url = url.replace("/blob/", "/resolve/")
    if "huggingface.co" in url and "download=" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}download=true"
    return url


def filename_from_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    return unquote(os.path.basename(parsed.path))


@app.route("/api/pull_weights", methods=["POST"])
def pull_weights():
    data = request.json or {}
    model_name = secure_filename((data.get("model_name") or "").strip().replace(" ", "-"))
    source_url = normalize_gguf_url(data.get("url", ""))
    requested_filename = secure_filename((data.get("file_name") or "").strip())
    derived_filename = secure_filename(filename_from_url(source_url))
    gguf_filename = requested_filename or derived_filename

    if not model_name:
        return jsonify({"status": "error", "message": "Missing model alias."}), 400
    if not source_url:
        return jsonify({"status": "error", "message": "Missing GGUF download URL."}), 400
    if not gguf_filename:
        return jsonify({"status": "error", "message": "Unable to determine a GGUF filename."}), 400
    if not gguf_filename.lower().endswith(".gguf"):
        return jsonify({"status": "error", "message": "Only GGUF files are supported."}), 400

    target_path = os.path.join(MODELS_FOLDER, gguf_filename)

    try:
        with requests.get(source_url, stream=True, timeout=(20, 1800)) as response:
            response.raise_for_status()
            with open(target_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
    except Exception as error:
        return jsonify({"status": "error", "message": f"Download failed: {error}"}), 500

    try:
        result = subprocess.run(
            ["bash", HF_BRIDGE_PATH, model_name, gguf_filename],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
    except Exception as error:
        return jsonify({"status": "error", "message": f"Injection failed: {error}"}), 500

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Model injection failed.").strip()
        return jsonify({"status": "error", "message": message}), 500

    register_custom_model(model_name, gguf_filename, source_url)
    socketio.emit("reload_models", {"reason": "weights_added", "model": model_name})
    return jsonify(
        {
            "status": "success",
            "message": f"[INJECTION SUCCESS] {model_name} is now available in the model selector.",
            "file_name": gguf_filename,
            "model_name": model_name,
            "output": (result.stdout or "").strip(),
        }
    )


@app.route("/api/upload", methods=["POST"])
def upload_file():
    global LATEST_UPLOAD_CONTENT

    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"status": "error", "message": "Missing filename"}), 400

    filename = secure_filename(file.filename)
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(save_path)
    try:
        with open(save_path, "r", encoding="utf-8", errors="ignore") as handle:
            LATEST_UPLOAD_CONTENT = handle.read()
    except Exception:
        LATEST_UPLOAD_CONTENT = f"Stored {filename} but could not index it as text."
    return jsonify({"status": "success", "filename": filename})


@app.route("/api/clear_memory", methods=["POST"])
def clear_memory():
    global LATEST_UPLOAD_CONTENT
    LATEST_UPLOAD_CONTENT = ""
    return jsonify({"status": "success"})


@app.route("/api/hive/status", methods=["GET"])
def hive_status():
    config = current_config()
    remote = hive.fetch_remote_status()
    local = hive.status_snapshot(config)
    return jsonify({"status": "success", "local": local, "remote": remote})


@app.route("/api/hive/replay", methods=["POST"])
def hive_replay():
    config = current_config()
    result = hive.replay_queued_events(config)
    return jsonify({"status": "success", "result": result, "local": hive.status_snapshot(config)})


@app.route("/api/hive/clear_queue", methods=["POST"])
def hive_clear_queue():
    config = current_config()
    result = hive.clear_queued_events(config)
    return jsonify({"status": "success", "result": result, "local": hive.status_snapshot(config)})


@app.route("/api/hive/clear_local_events", methods=["POST"])
def hive_clear_local_events():
    config = current_config()
    result = hive.clear_local_knowledge(config)
    return jsonify({"status": "success", "result": result, "local": hive.status_snapshot(config)})


@app.route("/api/hive/share_last", methods=["POST"])
def hive_share_last():
    config = current_config()
    if config.get("HIVE_MIND_ENABLED", "false") != "true":
        return jsonify({"status": "error", "message": "Hive is paused. Resume Hive before sharing anything."}), 400

    with LAST_SHAREABLE_EXCHANGE_LOCK:
        exchange = dict(LAST_SHAREABLE_EXCHANGE)

    if not exchange.get("prompt") or not exchange.get("reply"):
        return jsonify({"status": "error", "message": "No finished chat reply is ready to share."}), 404
    if exchange.get("agent_mode") == "terminal":
        return jsonify({"status": "error", "message": "Terminal-mode runs are not shareable to Hive because they can contain commands, paths, secrets, or system output."}), 400

    metadata = {
        "agent_mode": exchange.get("agent_mode", "chat"),
        "comp_mode": exchange.get("comp_mode", config.get("COMP_MODE", "hybrid")),
        "manual_share": True,
        "source": "operator_manual_share",
        "exchange_id": exchange.get("id", ""),
    }
    result = hive.broadcast_to_hive(str(exchange["prompt"]), str(exchange["reply"]), config, metadata=metadata)
    if result.get("status") == "success":
        with LAST_SHAREABLE_EXCHANGE_LOCK:
            LAST_SHAREABLE_EXCHANGE["shared"] = True
        return jsonify({"status": "success", "message": result.get("message", "Last chat was shared to Hive."), "result": result})

    code = 400 if result.get("status") in {"blocked", "skipped"} else 500
    return jsonify({"status": result.get("status", "error"), "message": result.get("message", "Hive share failed."), "result": result}), code


@app.route("/api/hive/pause", methods=["POST"])
def hive_pause():
    config = apply_config_updates({"HIVE_MIND_ENABLED": "false"})
    return jsonify(
        {
            "status": "success",
            "message": "Hive paused. OpenZero will keep working locally without pushing new lattice events.",
            "local": hive.status_snapshot(config),
        }
    )


@app.route("/api/hive/resume", methods=["POST"])
def hive_resume():
    config = apply_config_updates({"HIVE_MIND_ENABLED": "true"})
    return jsonify(
        {
            "status": "success",
            "message": "Hive resumed for node status and federation. Chat sharing still requires manual approval unless you explicitly enable auto-safe sharing.",
            "local": hive.status_snapshot(config),
        }
    )


@app.route("/api/voice/status", methods=["GET"])
def voice_status():
    return jsonify({"status": "success", "voice": current_voice().status()})


@app.route("/api/voice/voicebox/status", methods=["GET"])
def voicebox_status():
    return jsonify(current_voice().voicebox_health())


@app.route("/api/voice/voicebox/profiles", methods=["GET"])
def voicebox_profiles():
    return jsonify(current_voice().voicebox_profiles())


@app.route("/api/voice/speak", methods=["POST"])
def voice_speak():
    data = request.json or {}
    result = current_voice().speak_text(data.get("text", ""))
    return jsonify(result)


@app.route("/api/voice/transcribe", methods=["POST"])
def voice_transcribe():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No audio file uploaded"}), 400
    file = request.files["file"]
    filename = secure_filename(file.filename or "voice_input.wav")
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(save_path)
    result = current_voice().transcribe_file(save_path)
    return jsonify(result)


@socketio.on("user_message")
def handle_message(data):
    session_id = getattr(request, "sid", "")
    config = current_config()
    message = (data or {}).get("message", "").strip()
    if not message:
        emit("agent_reply", {"data": "[ERROR] Empty message received.", "mode": "system"})
        return

    comp_mode = (data or {}).get("comp_mode", config.get("COMP_MODE", "hybrid"))
    agent_mode = (data or {}).get("agent_mode", "chat")
    set_run_state(session_id, running=True, stop_requested=False, started_at=time.time(), mode=agent_mode)
    emit_agent_state(session_id, True, "running", "Agent Zero is executing your request.")
    CHAT_HISTORY.append({"role": "user", "content": message})
    del CHAT_HISTORY[:- (MAX_HISTORY * 2)]

    final_reply = ""
    final_status = "done"

    try:
        cached = hive.search_hive_knowledge(message, minimum_p_good=float(config.get("P_GOOD_THRESHOLD", "0.10")))
        if cached and config.get("HIVE_MIND_ENABLED", "false") == "true":
            emit("agent_reply", {"data": f"**[HIVE CACHE]**\n{cached}", "mode": "system"})

        current_prompt = message
        max_loops = OPERATOR_MAX_LOOPS

        for _ in range(max_loops):
            if is_stop_requested(session_id):
                final_status = "stopped"
                emit_agent_log("Stop requested. Halting Agent Zero after the current safe boundary.", session_id)
                emit("agent_reply", {"data": "**[STOPPED]**\nAgent Zero stopped before taking the next step.", "mode": "system"})
                break

            if comp_mode == "cloud":
                reply = ask_groq(current_prompt, context=LATEST_UPLOAD_CONTENT, agent_mode=agent_mode)
            elif comp_mode == "local":
                reply = ask_local(current_prompt, context=LATEST_UPLOAD_CONTENT, agent_mode=agent_mode)
            else:
                active_model = config.get("ACTIVE_MODEL", "")
                use_cloud = is_cloud_model(active_model)
                reply = ask_groq(current_prompt, context=LATEST_UPLOAD_CONTENT, agent_mode=agent_mode) if use_cloud else ask_local(
                    current_prompt,
                    context=LATEST_UPLOAD_CONTENT,
                    agent_mode=agent_mode,
                )

            if is_stop_requested(session_id):
                final_status = "stopped"
                emit_agent_log("Stop requested. Skipping any further operator actions.", session_id)
                emit("agent_reply", {"data": "**[STOPPED]**\nAgent Zero stopped after the latest model reply.", "mode": "system"})
                break

            action = run_tool_action(reply, session_id=session_id)
            visible_reply = visible_reply_text(reply)
            display_reply = visible_reply or (reply.strip() if not action else "")

            if display_reply:
                emit("agent_reply", {"data": display_reply, "mode": agent_mode})
                CHAT_HISTORY.append({"role": "assistant", "content": display_reply})
                del CHAT_HISTORY[:- (MAX_HISTORY * 2)]
                final_reply = display_reply
            elif action:
                emit_agent_log("Agent Zero selected a local operator tool and is continuing autonomously...", session_id)
            elif reply.strip():
                emit("agent_reply", {"data": reply, "mode": agent_mode})
                CHAT_HISTORY.append({"role": "assistant", "content": reply})
                del CHAT_HISTORY[:- (MAX_HISTORY * 2)]
                final_reply = reply

            if not action:
                break

            if is_stop_requested(session_id):
                final_status = "stopped"
                emit_agent_log("Stop requested before applying the next tool result. Halting now.", session_id)
                emit("agent_reply", {"data": "**[STOPPED]**\nAgent Zero stopped before feeding the next tool result back into the loop.", "mode": "system"})
                break

            emit("agent_reply", {"data": action["result"], "mode": "system"})
            CHAT_HISTORY.append({"role": "user", "content": f"System tool output:\n{action['result']}\nContinue autonomously or finish the task with factual results."})
            del CHAT_HISTORY[:- (MAX_HISTORY * 2)]
            current_prompt = f"System tool output:\n{action['result']}\nContinue autonomously or finish the task with factual results."
            emit_agent_log("Re-entering OpenZero cognitive loop...", session_id)

        if final_reply and final_status != "stopped":
            learn_from_reply(message, final_reply, comp_mode, agent_mode, session_id=session_id)
            remember_shareable_exchange(message, final_reply, comp_mode, agent_mode)
            maybe_speak_reply(final_reply)
            broadcast_hive_reply(message, final_reply, comp_mode, agent_mode)
            if config.get("HIVE_MIND_ENABLED", "false") == "true" and config.get("OPENZERO_HIVE_SHARE_MODE", "manual").lower() == "manual":
                emit("agent_reply", {"data": "**[PRIVACY]**\nThis chat stayed local. Use `SEND LAST CHAT TO HIVE` only if you intentionally want to publish a filtered knowledge contribution.", "mode": "system"})
        elif final_status == "stopped" and not final_reply:
            final_reply = "Stopped by operator."
    except Exception as error:
        final_status = "error"
        emit("agent_reply", {"data": f"**[ERROR]**\n{error}", "mode": "system"})
        emit_agent_log(f"Agent Zero hit an error: {error}", session_id)
    finally:
        clear_run_state(session_id)
        emit_agent_state(session_id, False, final_status, "Agent Zero is idle." if final_status == "done" else f"Agent Zero status: {final_status}")


@socketio.on("stop_agent")
def stop_agent():
    session_id = getattr(request, "sid", "")
    state = get_run_state(session_id)
    if not state.get("running"):
        emit("agent_log", {"data": "No active Agent Zero run is in progress right now."})
        emit_agent_state(session_id, False, "idle", "Agent Zero is idle.")
        return
    set_run_state(session_id, stop_requested=True)
    emit_agent_log("Stop requested. Agent Zero will halt at the next safe boundary.", session_id)
    emit_agent_state(session_id, True, "stopping", "Stop requested. Agent Zero is winding down.")


def heartbeat_loop():
    while True:
        try:
            hive.refresh_registration(current_config())
        except Exception:
            pass
        time.sleep(300)


if __name__ == "__main__":
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=1024, allow_unsafe_werkzeug=True)
