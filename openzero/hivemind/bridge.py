import hashlib
import json
import os
import re
import socket
import subprocess
import time
from typing import Dict, List, Optional

import requests
from colorama import Fore, Style
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from brain.openzero_config import env_bool, env_float, env_int, resource_profile, save_env_value


HIVE_ENABLED = False
HIVE_SERVER_URL = "https://openzero.talktoai.org/api/hive"
HIVE_SERVER_URLS = [HIVE_SERVER_URL]
HIVE_MODE = "standalone"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIVATE_KEY_PATH = os.path.join(BASE_DIR, "node_private.pem")
PUBLIC_KEY_PATH = os.path.join(BASE_DIR, "node_public.pem")
MAX_LOCAL_KNOWLEDGE = 500
MAX_LOCAL_NODES = 250
MAX_HIVE_PROMPT_CHARS = 1200
MAX_HIVE_ANSWER_CHARS = 4000
HIVE_SHARE_MODES = {"private", "manual", "auto_safe"}
HIGH_RISK_HIVE_PATTERNS = [
    r"<\s*/?\s*script\b",
    r"javascript\s*:",
    r"on(?:error|load|click|mouseover)\s*=",
    r"\b(?:curl|wget)\b[^\n|;]{0,220}\|\s*(?:sh|bash|zsh|python|perl|ruby)\b",
    r"\brm\s+-rf\s+/(?:\s|$)",
    r"\b(?:nc|ncat|socat)\b[^\n]{0,120}\b(?:-e|/bin/sh|/bin/bash)\b",
    r"\b(?:reverse shell|metasploit|meterpreter|keylogger|ransomware|dropper)\b",
    r"\b(?:seed phrase|mnemonic phrase|private key|wallet\.dat)\b",
    r"\b(?:steal|drain|exfiltrate|grab|take)\b[^\n]{0,80}\b(?:wallet|crypto|token|seed|key)\b",
    r"\b(?:disable|bypass)\b[^\n]{0,80}\b(?:auth|firewall|2fa|mfa|antivirus|defender)\b",
]
_private_key = None
_node_capabilities: Dict[str, object] = {
    "id": hashlib.md5(f"{socket.gethostname()}-{time.time()}".encode()).hexdigest()[:12],
    "compute": "cpu",
    "public_key": "",
    "fee_oz_coins": 0.0,
    "status": "standby",
}
_last_registration = 0.0
_endpoint_health: Dict[str, Dict[str, object]] = {}
_runtime_env: Dict[str, str] = {}


def _utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _share_mode(config: Dict[str, str]) -> str:
    mode = (config.get("OPENZERO_HIVE_SHARE_MODE", "manual") or "manual").strip().lower()
    return mode if mode in HIVE_SHARE_MODES else "manual"


def _normalize_hive_text(value: object, max_chars: int) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = re.sub(r"\s{3,}", "  ", text).strip()
    return text[:max_chars]


def _redact_sensitive_hive_text(text: str) -> str:
    text = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", "[REDACTED PRIVATE KEY]", text, flags=re.I | re.S)
    text = re.sub(r"\b(?:[a-z]+ ){11,23}[a-z]+\b", "[REDACTED POSSIBLE SEED PHRASE]", text, flags=re.I)
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED EMAIL]", text)
    text = re.sub(r"\b(?:\+?\d[\d .()-]{8,}\d)\b", "[REDACTED PHONE]", text)
    return text


def _hive_text_risk(prompt: str, answer: str = "") -> List[str]:
    text = f"{prompt}\n{answer}"
    reasons = []
    for pattern in HIGH_RISK_HIVE_PATTERNS:
        if re.search(pattern, text, flags=re.I | re.S):
            reasons.append(pattern)
    return reasons


def _prepare_public_hive_payload(
    prompt: str,
    answer: str,
    config: Dict[str, str],
    metadata: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    metadata = dict(metadata or {})
    prompt = _redact_sensitive_hive_text(_normalize_hive_text(prompt, MAX_HIVE_PROMPT_CHARS))
    answer = _redact_sensitive_hive_text(_normalize_hive_text(answer, MAX_HIVE_ANSWER_CHARS))
    risks = _hive_text_risk(prompt, answer)
    manual_share = bool(metadata.get("manual_share"))

    if risks and env_bool(config, "OPENZERO_HIVE_BLOCK_RISKY_CONTENT", True):
        return {
            "ok": False,
            "message": "Public Hive sharing was blocked by the local safety filter. The local chat can continue; only the public/federated contribution was withheld.",
            "risk_level": "blocked",
            "reasons": risks,
        }

    visibility = "public" if manual_share else "private"
    metadata.update(
        {
            "manual_share": manual_share,
            "visibility": visibility,
            "privacy_filter": "openzero-hive-privacy-v1",
            "risk_level": "review" if risks else "low",
        }
    )
    return {
        "ok": True,
        "prompt": prompt,
        "answer": answer,
        "metadata": metadata,
        "visibility": visibility,
        "risk_level": metadata["risk_level"],
    }


def _bounded_timeout(raw_value, default: int, minimum: int = 1, maximum: int = 30) -> int:
    try:
        parsed = int(float(raw_value))
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _safe_psutil_snapshot():
    try:
        import psutil

        memory = psutil.virtual_memory()
        cpu_count = psutil.cpu_count(logical=True) or 1
        return {
            "ram_gb": round(memory.total / (1024 ** 3), 2),
            "ram_percent": memory.percent,
            "cpu_count": cpu_count,
        }
    except Exception:
        return {"ram_gb": 0, "ram_percent": 0, "cpu_count": 1}


def _split_mirror_urls(raw_value: str) -> List[str]:
    if not raw_value:
        return []
    tokens = []
    for chunk in raw_value.replace(";", ",").replace("\n", ",").split(","):
        token = chunk.strip()
        if token:
            tokens.append(token)
    deduped = []
    seen = set()
    for token in tokens:
        if token not in seen:
            deduped.append(token)
            seen.add(token)
    return deduped


def _configured_hive_urls(config: Dict[str, str]) -> List[str]:
    primary = (config.get("OPENZERO_HIVE_URL", HIVE_SERVER_URL) or "").strip()
    urls = []
    if primary:
        urls.append(primary)
    urls.extend(_split_mirror_urls(config.get("OPENZERO_HIVE_MIRRORS", "")))

    deduped = []
    seen = set()
    for url in urls:
        if url not in seen:
            deduped.append(url)
            seen.add(url)
    return deduped


def _set_runtime_network(config: Dict[str, str]) -> None:
    global HIVE_SERVER_URL, HIVE_SERVER_URLS, HIVE_MODE, _runtime_env

    _runtime_env = dict(config)
    HIVE_MODE = (config.get("OPENZERO_HIVE_MODE", "standalone") or "standalone").strip().lower()
    if HIVE_MODE not in {"standalone", "federated", "local"}:
        HIVE_MODE = "standalone"

    urls = _configured_hive_urls(config)
    if urls:
        HIVE_SERVER_URL = urls[0]
        HIVE_SERVER_URLS = urls
    else:
        HIVE_SERVER_URL = ""
        HIVE_SERVER_URLS = []

    if HIVE_MODE == "local":
        HIVE_SERVER_URLS = []


def _spool_enabled(config: Dict[str, str]) -> bool:
    return env_bool(config, "OPENZERO_HIVE_LOCAL_SPOOL_ENABLED", True)


def _remote_lookup_enabled(config: Dict[str, str]) -> bool:
    return env_bool(config, "OPENZERO_HIVE_REMOTE_LOOKUP_ENABLED", True)


def _search_timeout(config: Dict[str, str]) -> int:
    return _bounded_timeout(env_int(config, "OPENZERO_HIVE_SEARCH_TIMEOUT", 2), 2, minimum=1, maximum=12)


def _push_timeout(config: Dict[str, str]) -> int:
    return _bounded_timeout(env_int(config, "OPENZERO_HIVE_PUSH_TIMEOUT", 4), 4, minimum=2, maximum=20)


def _remote_lookup_backlog_limit(config: Dict[str, str]) -> int:
    return _bounded_timeout(env_int(config, "OPENZERO_HIVE_REMOTE_LOOKUP_BACKLOG_LIMIT", 8), 8, minimum=0, maximum=500)


def _endpoint_retry_cooldown(config: Dict[str, str]) -> int:
    return _bounded_timeout(
        env_int(config, "OPENZERO_HIVE_ENDPOINT_RETRY_COOLDOWN_SECONDS", 120),
        120,
        minimum=0,
        maximum=3600,
    )


def _spool_path(config: Dict[str, str]) -> str:
    raw_path = config.get("OPENZERO_HIVE_LOCAL_SPOOL_PATH", "security/hive_spool.json").strip()
    if os.path.isabs(raw_path):
        return raw_path
    return os.path.join(BASE_DIR, raw_path)


def _empty_spool() -> Dict[str, object]:
    return {
        "version": "federation-v1",
        "queued_events": [],
        "local_knowledge": [],
        "local_nodes": {},
    }


def _read_spool(config: Dict[str, str]) -> Dict[str, object]:
    if not _spool_enabled(config):
        return _empty_spool()

    path = _spool_path(config)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        spool = _empty_spool()
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(spool, handle, indent=2)
        return spool

    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError("invalid spool root")
    except Exception:
        loaded = _empty_spool()
    loaded.setdefault("queued_events", [])
    loaded.setdefault("local_knowledge", [])
    loaded.setdefault("local_nodes", {})
    return loaded


def _write_spool(config: Dict[str, str], spool: Dict[str, object]) -> None:
    if not _spool_enabled(config):
        return
    path = _spool_path(config)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(spool, handle, indent=2)


def _record_local_node(config: Dict[str, str], capabilities: Dict[str, object]) -> None:
    if not _spool_enabled(config):
        return
    spool = _read_spool(config)
    local_nodes = spool.setdefault("local_nodes", {})
    local_nodes[capabilities["id"]] = {
        **capabilities,
        "last_seen_local": _utc_timestamp(),
    }
    # Trim to most recent nodes if this ever grows large.
    if len(local_nodes) > MAX_LOCAL_NODES:
        ordered = sorted(
            local_nodes.values(),
            key=lambda item: item.get("updated_at", 0),
            reverse=True,
        )[:MAX_LOCAL_NODES]
        spool["local_nodes"] = {item["id"]: item for item in ordered}
    _write_spool(config, spool)


def _record_local_knowledge(config: Dict[str, str], payload: Dict[str, object], node_id: str) -> None:
    if not _spool_enabled(config):
        return
    spool = _read_spool(config)
    local_knowledge = spool.setdefault("local_knowledge", [])
    local_knowledge.append(
        {
            "node_id": node_id,
            "event_type": payload.get("event_type", "knowledge"),
            "hash": payload.get("hash", ""),
            "prompt": payload.get("prompt", ""),
            "answer": payload.get("answer", ""),
            "p_good": payload.get("p_good", 0.1),
            "metadata": payload.get("metadata", {}),
            "timestamp": _utc_timestamp(),
        }
    )
    spool["local_knowledge"] = local_knowledge[-MAX_LOCAL_KNOWLEDGE:]
    _write_spool(config, spool)


def _queue_event(config: Dict[str, str], action: str, payload: Dict[str, object], target_urls: List[str], reason: str) -> None:
    if not _spool_enabled(config):
        return
    spool = _read_spool(config)
    queued = spool.setdefault("queued_events", [])
    queued.append(
        {
            "action": action,
            "payload": payload,
            "target_urls": target_urls,
            "queued_at": _utc_timestamp(),
            "reason": reason,
        }
    )
    spool["queued_events"] = queued[-MAX_LOCAL_KNOWLEDGE:]
    _write_spool(config, spool)


def _mark_endpoint(url: str, ok: bool, detail: str = "") -> None:
    state = _endpoint_health.setdefault(url, {"status": "unknown", "last_ok": 0.0, "last_error": "", "updated_at": 0.0})
    state["status"] = "online" if ok else "offline"
    state["updated_at"] = time.time()
    if ok:
        state["last_ok"] = time.time()
        state["last_error"] = ""
    else:
        state["last_error"] = detail


def _remote_lookup_state(config: Dict[str, str]) -> Dict[str, object]:
    spool = _read_spool(config)
    queued_events = len(spool.get("queued_events", []))
    backlog_limit = _remote_lookup_backlog_limit(config)
    enabled = _remote_lookup_enabled(config)
    reason = ""

    if HIVE_MODE == "local":
        enabled = False
        reason = "Hive is in local continuity mode."
    elif not HIVE_ENABLED:
        enabled = False
        reason = "Hive is paused on this node."
    elif not _remote_lookup_enabled(config):
        enabled = False
        reason = "Remote Hive lookup is disabled for local-first operation."
    elif backlog_limit and queued_events >= backlog_limit:
        enabled = False
        reason = f"Remote Hive lookup is paused while {queued_events} unsent events are queued locally."

    return {
        "enabled": enabled,
        "queued_events": queued_events,
        "backlog_limit": backlog_limit,
        "reason": reason,
    }


def _search_target_urls(config: Dict[str, str]) -> List[str]:
    cooldown = _endpoint_retry_cooldown(config)
    now = time.time()
    available = []
    for url in HIVE_SERVER_URLS:
        state = _endpoint_health.get(url, {})
        if (
            state.get("status") == "offline"
            and cooldown
            and now - float(state.get("updated_at") or 0.0) < cooldown
        ):
            continue
        available.append(url)
    return available


def _post_endpoint(url: str, action: str, payload: Dict[str, object], timeout: int = 10) -> Dict[str, object]:
    try:
        response = requests.post(f"{url}?action={action}", json=payload, timeout=timeout)
        data = response.json()
        ok = data.get("status") == "success"
        _mark_endpoint(url, ok, "" if ok else data.get("message", "request failed"))
        return {"url": url, "ok": ok, "data": data}
    except Exception as error:
        _mark_endpoint(url, False, str(error))
        return {"url": url, "ok": False, "data": {"status": "error", "message": str(error)}}


def _get_endpoint(url: str, action: str, timeout: int = 8) -> Dict[str, object]:
    try:
        response = requests.get(f"{url}?action={action}", timeout=timeout)
        data = response.json()
        ok = data.get("status") == "success"
        _mark_endpoint(url, ok, "" if ok else data.get("message", "request failed"))
        return {"url": url, "ok": ok, "data": data}
    except Exception as error:
        _mark_endpoint(url, False, str(error))
        return {"url": url, "ok": False, "data": {"status": "error", "message": str(error)}}


def _deliver_payload(action: str, payload: Dict[str, object], config: Dict[str, str], timeout: int = 10) -> Dict[str, object]:
    urls = list(HIVE_SERVER_URLS)
    if HIVE_MODE == "local" or not urls:
        return {
            "status": "success",
            "mode": "local",
            "message": "Stored in local federation spool only.",
            "federation": federation_status(config),
        }

    results = [_post_endpoint(url, action, payload, timeout=timeout) for url in urls]
    successes = [item for item in results if item["ok"]]
    failed_urls = [item["url"] for item in results if not item["ok"]]
    if failed_urls:
        _queue_event(config, action, payload, failed_urls, "remote endpoint unavailable")

    if successes:
        return {
            "status": "success",
            "mode": HIVE_MODE,
            "message": f"{len(successes)}/{len(results)} Hive endpoints accepted {action}.",
            "federation": federation_status(config),
            "results": [item["data"] for item in results],
        }
    return {
        "status": "error",
        "mode": HIVE_MODE,
        "message": f"No Hive endpoints accepted {action}. Event queued locally.",
        "federation": federation_status(config),
        "results": [item["data"] for item in results],
    }


def _replay_queue(config: Dict[str, str]) -> Dict[str, object]:
    if not _spool_enabled(config):
        return {"status": "skipped", "message": "Local federation spool disabled.", "replayed": 0, "remaining": 0}
    if HIVE_MODE == "local" or not HIVE_SERVER_URLS:
        return {"status": "skipped", "message": "No remote Hive targets available.", "replayed": 0, "remaining": 0}

    spool = _read_spool(config)
    queued = list(spool.get("queued_events", []))
    if not queued:
        return {"status": "success", "message": "No queued federation events.", "replayed": 0, "remaining": 0}

    batch = env_int(config, "OPENZERO_HIVE_REPLAY_BATCH", 25)
    replayed = 0
    remaining = []
    for item in queued[:batch]:
        target_urls = item.get("target_urls") or list(HIVE_SERVER_URLS)
        failed_urls = []
        any_success = False
        for url in target_urls:
            result = _post_endpoint(url, item.get("action", "contribute"), item.get("payload", {}), timeout=8)
            if result["ok"]:
                any_success = True
            else:
                failed_urls.append(url)
        if failed_urls:
            item["target_urls"] = failed_urls
            remaining.append(item)
        elif any_success:
            replayed += 1
        else:
            remaining.append(item)

    remaining.extend(queued[batch:])
    spool["queued_events"] = remaining
    _write_spool(config, spool)
    return {
        "status": "success",
        "message": "Federation replay cycle complete.",
        "replayed": replayed,
        "remaining": len(remaining),
    }


def clear_queued_events(config: Dict[str, str]) -> Dict[str, object]:
    if not _spool_enabled(config):
        return {"status": "skipped", "message": "Local federation spool disabled.", "cleared": 0, "remaining": 0}

    spool = _read_spool(config)
    cleared = len(spool.get("queued_events", []))
    spool["queued_events"] = []
    _write_spool(config, spool)
    return {
        "status": "success",
        "message": "Cleared local unsent Hive events.",
        "cleared": cleared,
        "remaining": 0,
    }


def clear_local_knowledge(config: Dict[str, str]) -> Dict[str, object]:
    if not _spool_enabled(config):
        return {"status": "skipped", "message": "Local federation spool disabled.", "cleared": 0, "remaining": 0}

    spool = _read_spool(config)
    cleared = len(spool.get("local_knowledge", []))
    spool["local_knowledge"] = []
    _write_spool(config, spool)
    return {
        "status": "success",
        "message": "Cleared local lattice knowledge cache.",
        "cleared": cleared,
        "remaining": 0,
    }


def _local_search(prompt: str, minimum_p_good: float, config: Dict[str, str]) -> Optional[str]:
    spool = _read_spool(config)
    query_hash = hashlib.md5(prompt.encode()).hexdigest()
    candidates = []
    for item in spool.get("local_knowledge", []):
        if float(item.get("p_good", 0.0)) < minimum_p_good:
            continue
        if item.get("hash") == query_hash or item.get("prompt") == prompt:
            candidates.append(item)
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    answer = str(candidates[0].get("answer") or "")
    if _hive_text_risk(answer):
        return None
    return answer


def _merge_status_payloads(config: Dict[str, str], endpoint_results: List[Dict[str, object]]) -> Dict[str, object]:
    nodes: Dict[str, Dict[str, object]] = {}
    knowledge: List[Dict[str, object]] = []
    seen_knowledge = set()

    spool = _read_spool(config)
    for node_id, node in spool.get("local_nodes", {}).items():
        nodes[node_id] = dict(node)

    for item in spool.get("local_knowledge", []):
        key = (item.get("node_id"), item.get("hash"), item.get("timestamp"))
        if key not in seen_knowledge:
            knowledge.append(dict(item))
            seen_knowledge.add(key)

    for result in endpoint_results:
        data = result.get("data", {})
        for node in data.get("nodes", []):
            node_id = node.get("node_id") or node.get("id")
            if not node_id:
                continue
            existing = nodes.get(node_id)
            candidate_seen = node.get("last_seen", "")
            existing_seen = existing.get("last_seen", "") if existing else ""
            if existing is None or candidate_seen >= existing_seen:
                nodes[node_id] = dict(node)

        for item in data.get("knowledge", []):
            key = (item.get("node_id"), item.get("hash"), item.get("timestamp"))
            if key not in seen_knowledge:
                knowledge.append(dict(item))
                seen_knowledge.add(key)

    knowledge.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return {
        "status": "success",
        "mode": HIVE_MODE,
        "nodes": list(nodes.values()),
        "knowledge": knowledge[:40],
        "federation": federation_status(config),
    }


def load_or_generate_keys():
    global _private_key

    if os.path.exists(PRIVATE_KEY_PATH):
        try:
            with open(PRIVATE_KEY_PATH, "rb") as key_file:
                _private_key = serialization.load_pem_private_key(key_file.read(), password=None)
        except Exception:
            _private_key = None

    if _private_key is None:
        print(f"{Fore.YELLOW}[CRYPTO] Generating OpenZero RSA keypair...{Style.RESET_ALL}")
        _private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with open(PRIVATE_KEY_PATH, "wb") as handle:
            handle.write(
                _private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        public_key = _private_key.public_key()
        with open(PUBLIC_KEY_PATH, "wb") as handle:
            handle.write(
                public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )

    public_key = _private_key.public_key()
    _node_capabilities["public_key"] = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def sign_payload(data: Dict[str, object]) -> str:
    if _private_key is None:
        load_or_generate_keys()
    try:
        message = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
        signature = _private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
        return signature.hex()
    except Exception:
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _detect_compute_type() -> str:
    try:
        output = subprocess.check_output("nvidia-smi -L", shell=True, stderr=subprocess.DEVNULL, text=True)
        if output.strip():
            return "gpu"
    except Exception:
        pass
    return "cpu"


def _score_probability_of_goodness(prompt: str, answer: str, config: Dict[str, str]) -> float:
    text = f"{prompt}\n{answer}".lower()
    score = 0.55
    positive_signals = [
        "fix",
        "help",
        "document",
        "secure",
        "verify",
        "backup",
        "health",
        "recover",
        "install",
        "explain",
    ]
    risky_signals = ["malware", "exfiltrate", "phish", "steal", "wipe", "disable auth", "rm -rf /"]

    for token in positive_signals:
        if token in text:
            score += 0.03
    for token in risky_signals:
        if token in text:
            score -= 0.25

    threshold = env_float(config, "P_GOOD_THRESHOLD", 0.10)
    score = max(threshold, min(score, 0.99))
    return round(score, 3)


def _build_capabilities(config: Dict[str, str]) -> Dict[str, object]:
    load_or_generate_keys()
    _set_runtime_network(config)
    snapshot = _safe_psutil_snapshot()
    profile = resource_profile(config)
    node_label = config.get("NODE_LABEL") or socket.gethostname()

    _node_capabilities.update(
        {
            "id": _node_capabilities.get("id") or hashlib.md5(node_label.encode()).hexdigest()[:12],
            "node_label": node_label,
            "hostname": socket.gethostname(),
            "role": config.get("NODE_ROLE", "general"),
            "compute": _detect_compute_type(),
            "cpu_count": snapshot["cpu_count"],
            "ram_gb": profile["ram_gb"],
            "ram_percent": snapshot["ram_percent"],
            "context_window": profile["context_window"],
            "recommended_model": profile["recommended_model"],
            "active_model": config.get("ACTIVE_MODEL", profile["recommended_model"]),
            "node_tier": profile["node_tier"],
            "fee_oz_coins": env_float(config, "FEE_OZ_COINS", env_float(config, "FEE_ZERO_COINS", 0.0)),
            "oz_token_ca": config.get("OZ_TOKEN_CA", ""),
            "solana_address": config.get("SOLANA_ADDRESS", ""),
            "paid_hive_enabled": env_bool(config, "PAID_HIVE_ENABLED"),
            "paid_hive_address": config.get("PAID_HIVE_ADDRESS", ""),
            "paid_hive_free_boost": env_bool(config, "PAID_HIVE_FREE_BOOST", True),
            "paid_hive_min_balance": env_float(config, "PAID_HIVE_MIN_BALANCE", 0.0),
            "paid_hive_stake_multiplier": env_float(config, "PAID_HIVE_STAKE_MULTIPLIER", 1.0),
            "voice_enabled": env_bool(config, "VOICE_ENABLED"),
            "janitor_protocol_enabled": env_bool(config, "JANITOR_PROTOCOL_ENABLED", True),
            "watchdog_enabled": env_bool(config, "WATCHDOG_ENABLED", True),
            "operator_modes": ["chat", "terminal"],
            "operator_tools": [
                "bash",
                "files",
                "search",
                "archives",
                "browse",
                "moltbot_browser",
                "web_search",
                "osint",
                "ssh_scp",
                "voice",
                "skills_registry",
                "local_learning",
            ],
            "structured_operator_actions": True,
            "browser_enabled": True,
            "serper_enabled": bool(config.get("SERPER_API_KEY")),
            "remote_ops_enabled": True,
            "automation_enabled": env_bool(config, "OPENZERO_AUTOMATION_ENABLED", True),
            "local_learning_enabled": env_bool(config, "OPENZERO_LOCAL_LEARNING_ENABLED", True),
            "low_cpu_mode": env_bool(config, "OPENZERO_LOW_CPU_MODE", True),
            "p_good_threshold": env_float(config, "P_GOOD_THRESHOLD", 0.10),
            "node_benchmark": env_float(config, "NODE_BENCHMARK", 0.0),
            "status": "online" if HIVE_ENABLED else "standby",
            "hive_mode": HIVE_MODE,
            "hive_endpoints": list(HIVE_SERVER_URLS),
            "updated_at": int(time.time()),
        }
    )
    return dict(_node_capabilities)


def init_hive(config: Dict[str, str]) -> None:
    global HIVE_ENABLED

    HIVE_ENABLED = env_bool(config, "HIVE_MIND_ENABLED")
    capabilities = _build_capabilities(config)
    _record_local_node(config, capabilities)

    if not HIVE_ENABLED:
        print(f"{Fore.YELLOW}[HIVE MIND] OpenZero Hive disabled. Running local-only.{Style.RESET_ALL}")
        return

    replay_result = _replay_queue(config)
    if replay_result.get("replayed"):
        print(
            f"{Fore.CYAN}[FEDERATION] Replayed {replay_result['replayed']} queued Hive events. "
            f"Remaining: {replay_result['remaining']}{Style.RESET_ALL}"
        )

    print(
        f"{Fore.MAGENTA}[HIVE MIND] Syncing to OpenZero lattice... "
        f"mode={HIVE_MODE} endpoints={len(HIVE_SERVER_URLS) or 1}{Style.RESET_ALL}"
    )
    response = _register(capabilities, config)
    if response.get("status") == "success":
        print(f"{Fore.GREEN}[HIVE MIND] Identity verified. OpenZero lattice link established.{Style.RESET_ALL}")
    else:
        print(
            f"{Fore.RED}[HIVE MIND] Registration failed: {response.get('message', 'unknown error')}{Style.RESET_ALL}"
        )


def _register(capabilities: Dict[str, object], config: Dict[str, str]) -> Dict[str, object]:
    global _last_registration

    _record_local_node(config, capabilities)
    response = _deliver_payload("register", capabilities, config, timeout=10)
    if response.get("status") == "success":
        _last_registration = time.time()
    return response


def refresh_registration(config: Dict[str, str], force: bool = False) -> Dict[str, object]:
    if not HIVE_ENABLED:
        return {"status": "skipped", "message": "Hive disabled"}
    if not force and (time.time() - _last_registration) < 300:
        return {"status": "cached", "message": "Recent registration still valid"}
    capabilities = _build_capabilities(config)
    return _register(capabilities, config)


def replay_queued_events(config: Dict[str, str]) -> Dict[str, object]:
    _set_runtime_network(config)
    return _replay_queue(config)


def set_compute_fee(amount: float, config: Optional[Dict[str, str]] = None) -> None:
    fee = float(amount)
    _node_capabilities["fee_oz_coins"] = fee
    if config is not None:
        save_env_value(BASE_DIR, "FEE_OZ_COINS", fee)
        config["FEE_OZ_COINS"] = str(fee)
        config["FEE_ZERO_COINS"] = str(fee)
        _build_capabilities(config)
    if HIVE_ENABLED and config is not None:
        _register(dict(_node_capabilities), config)


def set_hive_state(state: bool, config: Optional[Dict[str, str]] = None) -> Dict[str, object]:
    global HIVE_ENABLED

    HIVE_ENABLED = bool(state)
    _node_capabilities["status"] = "online" if HIVE_ENABLED else "standby"
    if config is not None:
        save_env_value(BASE_DIR, "HIVE_MIND_ENABLED", HIVE_ENABLED)
        config["HIVE_MIND_ENABLED"] = "true" if HIVE_ENABLED else "false"
        _build_capabilities(config)
    if HIVE_ENABLED and config is not None:
        return _register(dict(_node_capabilities), config)
    return {"status": "success", "message": "Hive disabled locally"}


def search_hive_knowledge(prompt: str, minimum_p_good: float = 0.10) -> Optional[str]:
    local_config = dict(_runtime_env) or {
        "OPENZERO_HIVE_LOCAL_SPOOL_ENABLED": "true",
        "OPENZERO_HIVE_LOCAL_SPOOL_PATH": "security/hive_spool.json",
    }
    local_answer = _local_search(prompt, minimum_p_good, local_config)
    if local_answer:
        return local_answer
    lookup_state = _remote_lookup_state(local_config)
    if not lookup_state["enabled"]:
        return local_answer

    search_timeout = _search_timeout(local_config)
    fanout = max(1, env_int(local_config, "OPENZERO_HIVE_REMOTE_SEARCH_FANOUT", 1))
    target_urls = _search_target_urls(local_config)
    if not target_urls:
        return local_answer

    answers = []
    for url in target_urls[:fanout]:
        try:
            response = requests.post(
                f"{url}?action=search",
                json={"query": prompt, "minimum_p_good": minimum_p_good},
                timeout=search_timeout,
            )
            data = response.json()
            ok = data.get("status") == "success"
            _mark_endpoint(url, ok, "" if ok else data.get("message", "search failed"))
            if ok and data.get("data"):
                candidate = str(data.get("data") or "")
                if _hive_text_risk(candidate):
                    _mark_endpoint(url, False, "Remote Hive search result failed local safety filter")
                    continue
                answers.append(candidate)
        except Exception as error:
            _mark_endpoint(url, False, str(error))

    if answers:
        return answers[0]
    return local_answer


def learn_locally(prompt: str, answer: str, config: Dict[str, str], metadata: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    if not env_bool(config, "OPENZERO_LOCAL_LEARNING_ENABLED", True):
        return {"status": "skipped", "message": "Local learning disabled."}
    if not _spool_enabled(config):
        return {"status": "skipped", "message": "Local federation spool disabled."}

    metadata = dict(metadata or {})
    prompt_clean = _redact_sensitive_hive_text(_normalize_hive_text(prompt, MAX_HIVE_PROMPT_CHARS))
    answer_clean = _redact_sensitive_hive_text(_normalize_hive_text(answer, MAX_HIVE_ANSWER_CHARS))
    if not prompt_clean or not answer_clean:
        return {"status": "skipped", "message": "Nothing useful to learn."}

    risks = _hive_text_risk(prompt_clean, answer_clean)
    risk_level = "review" if risks else "low"
    if risks and env_bool(config, "OPENZERO_HIVE_BLOCK_RISKY_CONTENT", True):
        answer_clean = (
            "Local-only safety note: this exchange was useful to the local node but was withheld "
            "from public Hive sharing because it matched public-sharing risk filters. Continue locally "
            "with defensive, authorized, or administrative framing."
        )

    payload = {
        "event_type": "local_knowledge",
        "hash": hashlib.md5(prompt_clean.encode()).hexdigest(),
        "prompt": prompt_clean,
        "answer": answer_clean,
        "node_type": _node_capabilities.get("compute", "cpu"),
        "metadata": {
            **metadata,
            "visibility": "local_only",
            "source": metadata.get("source", "local_learning"),
            "privacy_filter": "openzero-local-learning-v1",
            "risk_reasons": risks[:3],
        },
        "visibility": "local_only",
        "risk_level": risk_level,
        "p_good": _score_probability_of_goodness(prompt_clean, answer_clean, config),
    }
    _record_local_knowledge(config, payload, _node_capabilities.get("id", "local"))
    return {
        "status": "success",
        "message": "Learned locally. Nothing was published to remote Hive.",
        "risk_level": risk_level,
    }


def broadcast_to_hive(prompt: str, answer: str, config: Dict[str, str], metadata: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    if not HIVE_ENABLED:
        return {"status": "skipped", "message": "Hive disabled"}

    metadata = dict(metadata or {})
    share_mode = _share_mode(config)
    manual_share = bool(metadata.get("manual_share"))
    if share_mode == "private" or (share_mode == "manual" and not manual_share):
        return {
            "status": "skipped",
            "message": "Hive chat sharing is private/manual. Nothing was sent to remote Hive.",
            "share_mode": share_mode,
        }

    prepared = _prepare_public_hive_payload(prompt, answer, config, metadata)
    if not prepared.get("ok"):
        return {
            "status": "blocked",
            "message": prepared.get("message", "Hive share blocked by local safety filter."),
            "risk_level": prepared.get("risk_level", "blocked"),
        }

    payload = {
        "event_type": "knowledge",
        "hash": hashlib.md5(prepared["prompt"].encode()).hexdigest(),
        "prompt": prepared["prompt"],
        "answer": prepared["answer"],
        "node_type": _node_capabilities.get("compute", "cpu"),
        "metadata": prepared["metadata"],
        "visibility": prepared["visibility"],
        "risk_level": prepared["risk_level"],
        "p_good": _score_probability_of_goodness(prepared["prompt"], prepared["answer"], config),
    }
    signature = sign_payload(payload)
    final_data = {
        "node_id": _node_capabilities["id"],
        "data": payload,
        "signature": signature,
    }
    _record_local_knowledge(config, payload, _node_capabilities["id"])
    return _deliver_payload("contribute", final_data, config, timeout=_push_timeout(config))


def broadcast_voice_event(text: str, config: Dict[str, str]) -> Dict[str, object]:
    if not HIVE_ENABLED:
        return {"status": "skipped", "message": "Hive disabled"}
    if not env_bool(config, "OPENZERO_HIVE_SHARE_VOICE_EVENTS", False):
        return {"status": "skipped", "message": "Voice-to-Hive sharing is disabled by default."}

    payload = {
        "event_type": "voice",
        "hash": hashlib.md5(text.encode()).hexdigest(),
        "prompt": "voice_event",
        "answer": text,
        "node_type": _node_capabilities.get("compute", "cpu"),
        "metadata": {"voice_enabled": env_bool(config, "VOICE_ENABLED")},
        "p_good": env_float(config, "P_GOOD_THRESHOLD", 0.10),
    }
    signature = sign_payload(payload)
    final_data = {
        "node_id": _node_capabilities["id"],
        "data": payload,
        "signature": signature,
    }
    _record_local_knowledge(config, payload, _node_capabilities["id"])
    return _deliver_payload("contribute", final_data, config, timeout=_push_timeout(config))


def fetch_remote_status() -> Dict[str, object]:
    local_config = dict(_runtime_env) or {
        "OPENZERO_HIVE_LOCAL_SPOOL_ENABLED": "true",
        "OPENZERO_HIVE_LOCAL_SPOOL_PATH": "security/hive_spool.json",
        "OPENZERO_HIVE_REPLAY_BATCH": "25",
    }
    if HIVE_MODE == "local":
        return _merge_status_payloads(local_config, [])
    if not HIVE_ENABLED:
        return {"status": "skipped", "nodes": [], "knowledge": []}

    endpoint_results = [_get_endpoint(url, "status", timeout=8) for url in HIVE_SERVER_URLS]
    successes = [item for item in endpoint_results if item["ok"]]
    if successes:
        return _merge_status_payloads(local_config, successes)
    merged = _merge_status_payloads(local_config, [])
    merged["status"] = "error"
    merged["message"] = "All remote Hive endpoints unavailable. Showing local federation spool."
    return merged


def federation_status(config: Optional[Dict[str, str]] = None) -> Dict[str, object]:
    config = config or dict(_runtime_env) or {
        "OPENZERO_HIVE_LOCAL_SPOOL_ENABLED": "true",
        "OPENZERO_HIVE_LOCAL_SPOOL_PATH": "security/hive_spool.json",
        "OPENZERO_HIVE_REPLAY_BATCH": "25",
    }
    spool = _read_spool(config)
    lookup_state = _remote_lookup_state(config)
    return {
        "mode": HIVE_MODE,
        "primary_url": HIVE_SERVER_URL,
        "mirror_urls": list(HIVE_SERVER_URLS[1:]),
        "endpoint_health": dict(_endpoint_health),
        "queued_events": len(spool.get("queued_events", [])),
        "local_knowledge_events": len(spool.get("local_knowledge", [])),
        "local_nodes": len(spool.get("local_nodes", {})),
        "spool_path": _spool_path(config),
        "remote_lookup_enabled": bool(lookup_state["enabled"]),
        "remote_lookup_requested": bool(_remote_lookup_enabled(config)),
        "remote_lookup_backlog_limit": int(lookup_state["backlog_limit"]),
        "remote_lookup_reason": lookup_state["reason"],
        "search_timeout_seconds": _search_timeout(config),
        "endpoint_retry_cooldown_seconds": _endpoint_retry_cooldown(config),
        "share_mode": _share_mode(config),
        "chat_sharing": "manual approval required" if _share_mode(config) == "manual" else _share_mode(config),
        "risky_content_filter": env_bool(config, "OPENZERO_HIVE_BLOCK_RISKY_CONTENT", True),
    }


def current_capabilities() -> Dict[str, object]:
    return dict(_node_capabilities)


def status_snapshot(config: Optional[Dict[str, str]] = None) -> Dict[str, object]:
    snapshot = _safe_psutil_snapshot()
    response = {
        "hive_enabled": HIVE_ENABLED,
        "last_registration": _last_registration,
        "node": dict(_node_capabilities),
        "ram_percent": snapshot["ram_percent"],
        "federation": federation_status(config),
    }
    if config is not None:
        response["resource_profile"] = resource_profile(config)
    return response
