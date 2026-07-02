import base64
import hashlib
import hmac
import json
import os
import stat
from typing import Dict, List

from cryptography.fernet import Fernet, InvalidToken


SECURITY_DIR_NAME = "security"
MASTER_KEY_NAME = "openzero_master.key"
ETHICS_POLICY_NAME = "ethics_policy.json"
ETHICS_LOCK_NAME = "ethics_policy.lock"
ETHICS_SIG_NAME = "ethics_policy.sig"
INTEGRITY_MANIFEST_NAME = "integrity_manifest.json"


DEFAULT_ETHICS_POLICY = {
    "policy_name": "OpenZero Ethics Lock",
    "version": "5.4.0",
    "immutable_claim": "tamper-evident-not-absolute",
    "core_rules": [
        "Protect operator data and privacy by default.",
        "Prefer local execution and air-gapped operation.",
        "Reject destructive actions without explicit operator intent.",
        "Require Probability-of-Goodness threshold alignment before Hive broadcast.",
        "Treat signatures and local vault material as sensitive.",
    ],
    "notes": [
        "This policy is signed and mirrored into an encrypted lock file.",
        "A system owner with full disk access can still replace files, so this is tamper-evident rather than magically immutable.",
    ],
}


def security_dir(base_dir: str) -> str:
    path = os.path.join(base_dir, SECURITY_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def master_key_path(base_dir: str) -> str:
    return os.path.join(security_dir(base_dir), MASTER_KEY_NAME)


def ethics_policy_path(base_dir: str) -> str:
    return os.path.join(security_dir(base_dir), ETHICS_POLICY_NAME)


def ethics_lock_path(base_dir: str) -> str:
    return os.path.join(security_dir(base_dir), ETHICS_LOCK_NAME)


def ethics_sig_path(base_dir: str) -> str:
    return os.path.join(security_dir(base_dir), ETHICS_SIG_NAME)


def integrity_manifest_path(base_dir: str) -> str:
    return os.path.join(security_dir(base_dir), INTEGRITY_MANIFEST_NAME)


def _chmod_private(path: str) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def load_or_create_master_key(base_dir: str) -> bytes:
    path = master_key_path(base_dir)
    if os.path.exists(path):
        key = open(path, "rb").read().strip()
    else:
        key = Fernet.generate_key()
        with open(path, "wb") as handle:
            handle.write(key)
    _chmod_private(path)
    return key


def _fernet(base_dir: str) -> Fernet:
    return Fernet(load_or_create_master_key(base_dir))


def _sign_bytes(base_dir: str, payload: bytes) -> str:
    key = load_or_create_master_key(base_dir)
    digest = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return digest


def _canonical_json(data: Dict) -> bytes:
    return json.dumps(data, indent=2, sort_keys=True).encode("utf-8")


def _write_json(path: str, data: Dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def ensure_ethics_lock(base_dir: str, policy: Dict = None) -> Dict[str, object]:
    policy = policy or DEFAULT_ETHICS_POLICY
    policy_path = ethics_policy_path(base_dir)
    lock_path = ethics_lock_path(base_dir)
    sig_path = ethics_sig_path(base_dir)

    if not os.path.exists(policy_path):
        _write_json(policy_path, policy)

    with open(policy_path, "r", encoding="utf-8") as handle:
        current_policy = json.load(handle)

    payload = _canonical_json(current_policy)
    signature = _sign_bytes(base_dir, payload)
    encrypted = _fernet(base_dir).encrypt(payload)

    with open(sig_path, "w", encoding="utf-8") as handle:
        handle.write(signature)
    with open(lock_path, "wb") as handle:
        handle.write(encrypted)

    _chmod_private(policy_path)
    _chmod_private(sig_path)
    _chmod_private(lock_path)
    return {"status": "sealed", "signature": signature}


def verify_or_restore_ethics_lock(base_dir: str) -> Dict[str, object]:
    ensure_ethics_lock(base_dir, DEFAULT_ETHICS_POLICY)
    policy_path = ethics_policy_path(base_dir)
    lock_path = ethics_lock_path(base_dir)
    sig_path = ethics_sig_path(base_dir)

    try:
        payload = open(policy_path, "rb").read()
        saved_signature = open(sig_path, "r", encoding="utf-8").read().strip()
        current_signature = _sign_bytes(base_dir, payload)
        if saved_signature == current_signature:
            return {"status": "ok", "tampered": False}
    except OSError:
        pass

    try:
        encrypted = open(lock_path, "rb").read()
        restored = _fernet(base_dir).decrypt(encrypted)
        with open(policy_path, "wb") as handle:
            handle.write(restored)
        with open(sig_path, "w", encoding="utf-8") as handle:
            handle.write(_sign_bytes(base_dir, restored))
        _chmod_private(policy_path)
        _chmod_private(sig_path)
        return {"status": "restored", "tampered": True}
    except (OSError, InvalidToken):
        return {"status": "error", "tampered": True}


def seal_json(base_dir: str, name: str, data: Dict) -> str:
    path = os.path.join(security_dir(base_dir), f"{name}.enc")
    payload = _canonical_json(data)
    token = _fernet(base_dir).encrypt(payload)
    with open(path, "wb") as handle:
        handle.write(token)
    _chmod_private(path)
    return path


def unseal_json(base_dir: str, name: str) -> Dict:
    path = os.path.join(security_dir(base_dir), f"{name}.enc")
    token = open(path, "rb").read()
    payload = _fernet(base_dir).decrypt(token)
    return json.loads(payload.decode("utf-8"))


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_integrity_manifest(base_dir: str, paths: List[str]) -> Dict[str, str]:
    manifest = {}
    for path in paths:
        if os.path.exists(path):
            manifest[os.path.relpath(path, base_dir)] = file_sha256(path)
    _write_json(integrity_manifest_path(base_dir), manifest)
    return manifest


def verify_integrity_manifest(base_dir: str, paths: List[str]) -> Dict[str, object]:
    manifest_path = integrity_manifest_path(base_dir)
    if not os.path.exists(manifest_path):
        return {"status": "missing", "tampered": []}
    recorded = json.load(open(manifest_path, "r", encoding="utf-8"))
    tampered = []
    for path in paths:
        rel = os.path.relpath(path, base_dir)
        if not os.path.exists(path):
            tampered.append(rel)
            continue
        if recorded.get(rel) != file_sha256(path):
            tampered.append(rel)
    return {"status": "ok" if not tampered else "tampered", "tampered": tampered}


def protected_paths(base_dir: str) -> List[str]:
    return [
        os.path.join(base_dir, "brain", "app.py"),
        os.path.join(base_dir, "brain", "openzero_config.py"),
        os.path.join(base_dir, "brain", "voice_stack.py"),
        os.path.join(base_dir, "brain", "integrity.py"),
        os.path.join(base_dir, "hivemind", "bridge.py"),
        os.path.join(base_dir, "zero_core.py"),
        ethics_policy_path(base_dir),
    ]


def ensure_integrity_state(base_dir: str) -> Dict[str, object]:
    ethics = verify_or_restore_ethics_lock(base_dir)
    manifest = build_integrity_manifest(base_dir, protected_paths(base_dir))
    return {"ethics": ethics, "manifest_entries": len(manifest)}


def integrity_status(base_dir: str) -> Dict[str, object]:
    ethics = verify_or_restore_ethics_lock(base_dir)
    manifest = verify_integrity_manifest(base_dir, protected_paths(base_dir))
    return {
        "ethics": ethics,
        "manifest": manifest,
        "security_dir": security_dir(base_dir),
        "tamper_evident": True,
        "absolute_immutability": False,
    }
