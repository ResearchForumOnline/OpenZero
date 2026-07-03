import os
from typing import Dict


DEFAULTS: Dict[str, str] = {
    "OPENZERO_VERSION": "5.4.0",
    "OPENZERO_DOMAIN": "https://openzero.talktoai.org",
    "OPENZERO_HIVE_URL": "https://openzero.talktoai.org/api/hive",
    "OPENZERO_HIVE_MODE": "standalone",
    "OPENZERO_HIVE_MIRRORS": "",
    "OPENZERO_HIVE_LOCAL_SPOOL_ENABLED": "true",
    "OPENZERO_HIVE_LOCAL_SPOOL_PATH": "security/hive_spool.json",
    "OPENZERO_HIVE_REPLAY_BATCH": "25",
    "OPENZERO_HIVE_SEARCH_MODE": "merge",
    "OPENZERO_HIVE_REMOTE_LOOKUP_ENABLED": "false",
    "OPENZERO_HIVE_REMOTE_SEARCH_FANOUT": "1",
    "OPENZERO_HIVE_SEARCH_TIMEOUT": "2",
    "OPENZERO_HIVE_PUSH_TIMEOUT": "4",
    "OPENZERO_HIVE_BACKGROUND_PUSH": "false",
    "OPENZERO_HIVE_SHARE_MODE": "manual",
    "OPENZERO_HIVE_BLOCK_RISKY_CONTENT": "true",
    "OPENZERO_HIVE_SHARE_VOICE_EVENTS": "false",
    "OPENZERO_HIVE_REMOTE_LOOKUP_BACKLOG_LIMIT": "8",
    "OPENZERO_HIVE_ENDPOINT_RETRY_COOLDOWN_SECONDS": "120",
    "OPENZERO_LOCAL_LEARNING_ENABLED": "true",
    "OPENZERO_LOCAL_LEARNING_TERMINAL": "false",
    "OPENZERO_AUTOMATION_ENABLED": "true",
    "OPENZERO_LOW_CPU_MODE": "true",
    "OPENZERO_CPU_PROFILE": "balanced",
    "OPENZERO_OLLAMA_THREADS": "0",
    "OPENZERO_OLLAMA_NUM_BATCH": "512",
    "OPENZERO_OLLAMA_KEEP_ALIVE": "10m",
    "BITNET_THREADS": "0",
    "ACTIVE_MODEL": "gemma4:e4b",
    "LOCAL_ENGINE": "ollama",
    "COMP_MODE": "hybrid",
    "VISION_ENABLED": "true",
    "HIVE_MIND_ENABLED": "false",
    "FEE_OZ_COINS": "0.0",
    "FEE_ZERO_COINS": "0.0",
    "OZ_TOKEN_CA": "86mnqW1TcHiFVSHHgHDf4htzs4qEGW9nr3Uzz5GjttXk",
    "SOLANA_ADDRESS": "5dZeB2SdAyBuwnexMCcSQeCqKUpbCotcqyDB13UMAnqN",
    "PAID_HIVE_ENABLED": "false",
    "PAID_HIVE_ADDRESS": "",
    "PAID_HIVE_FREE_BOOST": "true",
    "PAID_HIVE_MIN_BALANCE": "0",
    "PAID_HIVE_STAKE_MULTIPLIER": "1.0",
    "VOICE_ENABLED": "false",
    "VOICE_AUTO_LISTEN": "false",
    "VOICE_STT_MODEL": "base",
    "VOICE_TTS_ENABLED": "false",
    "VOICE_TTS_VOICE": "en_GB-alan-medium",
    "VOICE_OUTPUT_DIR": "voice",
    "P_GOOD_THRESHOLD": "0.10",
    "JANITOR_PROTOCOL_ENABLED": "true",
    "WATCHDOG_ENABLED": "true",
    "OLLAMA_AUTO_REPAIR_ENABLED": "true",
    "OLLAMA_AUTO_REPAIR_INTERVAL_MINUTES": "30",
    "OLLAMA_AUTO_UPDATE_INTERVAL_HOURS": "72",
    "BITNET_ENABLED": "false",
    "BITNET_MODEL_ID": "microsoft/bitnet-b1.58-2B-4T-gguf",
    "BITNET_MODEL_ALIAS": "bitnet-b1.58-2b-4t",
    "BITNET_MODEL_PATH": ".runtime/bitnet-models/BitNet-b1.58-2B-4T/ggml-model-i2_s.gguf",
    "BITNET_CONTEXT_WINDOW": "4096",
    "BITNET_AUTO_UPDATE_INTERVAL_HOURS": "168",
    "OPENZERO_API_ENABLED": "false",
    "OPENZERO_API_KEY_HASH": "",
    "OPENZERO_API_KEY_HINT": "",
    "NODE_LABEL": "",
    "NODE_ROLE": "general",
    "NODE_BENCHMARK": "0.0",
    "NODE_CONTEXT_WINDOW": "8192",
    "NODE_RAM_GB": "0",
    "NODE_RECOMMENDED_MODEL": "gemma4:e4b",
    "GROQ_API_KEY": "",
    "SERPER_API_KEY": "",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "SUDO_PASS": "",
}


def base_dir_from_file(anchor_file: str) -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(anchor_file)))


def env_path_for(base_dir: str) -> str:
    return os.path.join(base_dir, ".env")


def load_env(base_dir: str) -> Dict[str, str]:
    env = dict(DEFAULTS)
    env_path = env_path_for(base_dir)
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    profile = resource_profile(env)
    env.setdefault("NODE_RAM_GB", str(profile["ram_gb"]))
    env.setdefault("NODE_CONTEXT_WINDOW", str(profile["context_window"]))
    env.setdefault("NODE_RECOMMENDED_MODEL", profile["recommended_model"])
    return env


def save_env_value(base_dir: str, key: str, value: str) -> Dict[str, str]:
    env = load_env(base_dir)
    env[key] = sanitize_env_value(value)
    env_path = env_path_for(base_dir)
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()

    with open(env_path, "w", encoding="utf-8") as handle:
        replaced = False
        for raw_line in lines:
            if raw_line.strip().startswith(f"{key}="):
                handle.write(f"{key}={env[key]}\n")
                replaced = True
            else:
                handle.write(raw_line)
        if not replaced:
            handle.write(f"{key}={env[key]}\n")
    return load_env(base_dir)


def save_env_values(base_dir: str, updates: Dict[str, str]) -> Dict[str, str]:
    env = load_env(base_dir)
    env.update({key: sanitize_env_value(value) for key, value in updates.items()})
    env_path = env_path_for(base_dir)
    with open(env_path, "w", encoding="utf-8") as handle:
        for key in sorted(env.keys()):
            handle.write(f"{key}={env[key]}\n")
    return load_env(base_dir)


def sanitize_env_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def env_bool(env: Dict[str, str], key: str, default: bool = False) -> bool:
    raw = env.get(key, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on", "enabled"}


def env_float(env: Dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(env.get(key, default))
    except (TypeError, ValueError):
        return default


def env_int(env: Dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(float(env.get(key, default)))
    except (TypeError, ValueError):
        return default


def cpu_performance_profile(env: Dict[str, str]) -> Dict[str, object]:
    try:
        import psutil

        cores = psutil.cpu_count(logical=True) or os.cpu_count() or 2
    except Exception:
        cores = os.cpu_count() or 2

    cores = max(1, int(cores))
    profile = (env.get("OPENZERO_CPU_PROFILE") or "balanced").strip().lower()
    if profile in {"max", "full", "turbo"}:
        threads = cores
    elif profile in {"compact", "low", "quiet"}:
        threads = min(cores, 4)
    else:
        threads = max(1, cores - (1 if cores > 2 else 0))

    requested_threads = env_int(env, "OPENZERO_OLLAMA_THREADS", 0)
    if requested_threads > 0:
        threads = min(cores, max(1, requested_threads))

    bitnet_threads = env_int(env, "BITNET_THREADS", 0)
    if bitnet_threads <= 0:
        bitnet_threads = threads

    num_batch = min(4096, max(64, env_int(env, "OPENZERO_OLLAMA_NUM_BATCH", 512)))
    keep_alive = (env.get("OPENZERO_OLLAMA_KEEP_ALIVE") or "10m").strip() or "10m"

    return {
        "cpu_cores": cores,
        "profile": profile,
        "threads": threads,
        "bitnet_threads": min(cores, max(1, bitnet_threads)),
        "num_batch": num_batch,
        "keep_alive": keep_alive,
    }


def resource_profile(env: Dict[str, str]) -> Dict[str, object]:
    try:
        import psutil

        ram_gb = max(1, round(psutil.virtual_memory().total / (1024 ** 3)))
    except Exception:
        ram_gb = env_int(env, "NODE_RAM_GB", 16)

    if ram_gb < 12:
        recommended_model = "gemma4:e2b"
        context_window = 8192
        node_tier = "compact"
    elif ram_gb < 48:
        recommended_model = "gemma4:e4b"
        context_window = 12288
        node_tier = "baseline"
    else:
        recommended_model = "gemma4:e4b"
        context_window = 16384
        node_tier = "heavy"

    active_model = env.get("ACTIVE_MODEL") or recommended_model
    return {
        "ram_gb": ram_gb,
        "recommended_model": recommended_model,
        "active_model": active_model,
        "context_window": context_window,
        "node_tier": node_tier,
    }
