import base64
import hashlib
import hmac
import json
import os
import stat
from pathlib import Path
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
    "version": "7.1.0",
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
        key = Path(path).read_bytes().strip()
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


def ensure_ethics_lock(base_dir: str, policy: Dict = None, reviewed_sha256: str = None) -> Dict[str, object]:
    """Initialize only a known reviewed policy; never bless unknown existing text.

    The shipped default is a known migration baseline. Custom policy migration
    requires an owner to supply that exact reviewed policy explicitly.
    """
    # A previously reviewed custom/legacy policy remains valid across restarts.
    # Verification is read-only and checks the separate signed review baseline.
    existing = verify_or_restore_ethics_lock(base_dir)
    if existing.get("status") == "ok":
        return existing
    trusted = policy if policy is not None else DEFAULT_ETHICS_POLICY
    folder = os.path.join(base_dir, SECURITY_DIR_NAME)
    policy_path = os.path.join(folder, ETHICS_POLICY_NAME)
    expected = hashlib.sha256(_canonical_json(trusted)).hexdigest()
    fresh = not os.path.exists(policy_path)
    if os.path.exists(policy_path):
        try:
            current = json.loads(Path(policy_path).read_text(encoding="utf-8"))
            if hashlib.sha256(_canonical_json(current)).hexdigest() != expected:
                return {"status": "review_required", "tampered": True,
                        "message": "Existing policy differs from the reviewed baseline; nothing was resealed."}
        except (OSError, ValueError, TypeError):
            return {"status": "review_required", "tampered": True}
    else:
        # Partial legacy state is not a fresh installation.
        if any(os.path.exists(os.path.join(folder, name)) for name in (ETHICS_LOCK_NAME, ETHICS_SIG_NAME)):
            return {"status": "review_required", "tampered": True}
        os.makedirs(folder, exist_ok=True)
        _write_json(policy_path, trusted)
    result = verify_or_restore_ethics_lock(base_dir)
    if result.get("status") == "ok":
        return result
    if not fresh and reviewed_sha256 != expected:
        return {"status": "review_required", "tampered": result.get("tampered", True),
                "message": "Existing seals were not rewritten. Explicit reviewed_sha256 is required to migrate or repair."}
    # The bytes were matched to the caller's reviewed baseline before sealing.
    payload = _canonical_json(trusted)
    signature = _sign_bytes(base_dir, payload)
    for name, raw in ((ETHICS_SIG_NAME, signature.encode()), (ETHICS_LOCK_NAME, _fernet(base_dir).encrypt(payload))):
        path = os.path.join(folder, name)
        with open(path, "wb") as handle:handle.write(raw)
        _chmod_private(path)
    _chmod_private(policy_path)
    baseline_payload = expected.encode("ascii")
    _write_json(os.path.join(folder, "ethics_reviewed_baseline.json"), {"sha256": expected, "signature": hmac.new(load_or_create_master_key(base_dir), baseline_payload, hashlib.sha256).hexdigest()})
    return {"status": "initialized_reviewed_policy", "tampered": False,
            "policy_sha256": expected}


def verify_or_restore_ethics_lock(base_dir: str) -> Dict[str, object]:
    """Read-only verification. Historical name retained; no restore or reseal."""
    folder = os.path.join(base_dir, SECURITY_DIR_NAME)
    try:
        payload = _canonical_json(json.loads(Path(folder, ETHICS_POLICY_NAME).read_text(encoding="utf-8")))
        saved_signature = Path(folder, ETHICS_SIG_NAME).read_text(encoding="utf-8").strip()
        key = Path(folder, MASTER_KEY_NAME).read_bytes().strip()
        current_signature = hmac.new(key, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(saved_signature, current_signature):
            return {"status": "tampered", "tampered": True}
        locked = Fernet(key).decrypt(Path(folder, ETHICS_LOCK_NAME).read_bytes())
        if locked != payload:return {"status": "tampered", "tampered": True}
        # Legacy versions resealed on reads: matching signatures alone cannot
        # establish a reviewed custom policy baseline.
        expected = hashlib.sha256(_canonical_json(DEFAULT_ETHICS_POLICY)).hexdigest()
        baseline_path = os.path.join(folder, "ethics_reviewed_baseline.json")
        if os.path.exists(baseline_path):
            baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
            expected = str(baseline.get("sha256", ""))
            if not hmac.compare_digest(str(baseline.get("signature", "")), hmac.new(key, expected.encode("ascii"), hashlib.sha256).hexdigest()):
                return {"status": "tampered", "tampered": True}
        if hashlib.sha256(payload).hexdigest() != expected:
            return {"status": "review_required", "tampered": False,
                    "message": "Custom/legacy policy requires explicit owner baseline review."}
        return {"status": "ok", "tampered": False, "policy_sha256": expected}
    except FileNotFoundError:
        return {"status": "missing", "tampered": True}
    except (OSError, ValueError, TypeError, AttributeError, InvalidToken):
        return {"status": "tampered", "tampered": True}


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
    token = Path(path).read_bytes()
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
    manifest_path = os.path.join(base_dir, SECURITY_DIR_NAME, INTEGRITY_MANIFEST_NAME)
    if not os.path.exists(manifest_path):
        return {"status": "missing", "tampered": []}
    try:
        recorded = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if not isinstance(recorded, dict):raise ValueError("Invalid manifest")
    except (OSError, ValueError):return {"status": "tampered", "tampered": ["manifest"]}
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
        os.path.join(base_dir, SECURITY_DIR_NAME, ETHICS_POLICY_NAME),
    ]


def ensure_integrity_state(base_dir: str) -> Dict[str, object]:
    ethics = ensure_ethics_lock(base_dir)
    manifest = verify_integrity_manifest(base_dir, protected_paths(base_dir))
    return {"ethics": ethics, "manifest": manifest, "migration_review_required": manifest["status"] != "ok"}


def integrity_status(base_dir: str) -> Dict[str, object]:
    ethics = verify_or_restore_ethics_lock(base_dir)
    manifest = verify_integrity_manifest(base_dir, protected_paths(base_dir))
    return {
        "ethics": ethics,
        "manifest": manifest,
        "security_dir": os.path.join(base_dir, SECURITY_DIR_NAME),
        "tamper_evident": True,
        "absolute_immutability": False,
    }
