"""Opt-in direct peer notes: no bootstrap, coordinator, remote tools or inference.

Each ordinary OpenZero node runs this same service. Secrets remain in private
runtime state; received text stays in a review inbox and is never executed.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
from urllib.parse import urlsplit

import requests
from flask import Response, jsonify, request

SCHEMA = "openzero-peer-notes-v1"
MAX_PEERS = 8
MAX_NOTES = 256
MAX_BATCH = 12
MAX_BODY = 128_000
MAX_STATE = 6_000_000
TOKEN_PREFIX = "ozpeer_"


class PeerError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def token_hash(value):
    return hashlib.sha256(("openzero-peer-receive-v1:" + value).encode()).hexdigest()


def validate_origin(value):
    """Operator-selected origin only; no credentials, fragments or service paths."""
    if not isinstance(value, str) or len(value) > 500:
        raise PeerError("Supply a valid peer origin.")
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        if (parsed.scheme not in {"http", "https"} or not host
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"} or not (0 < (parsed.port or 443) < 65536)):
            raise ValueError()
        host = host.lower()
        if host in {"metadata.google.internal", "metadata", "instance-data"}:
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and (address.is_link_local or address.is_multicast or address.is_unspecified):
            raise ValueError()
        if parsed.scheme == "http" and not (host == "localhost" or address and address.is_loopback):
            raise PeerError("Remote peers require HTTPS. Use an SSH loopback tunnel for HTTP nodes.")
        return value.strip().rstrip("/")
    except (ValueError, TypeError):
        raise PeerError("Peer origins require HTTPS (or HTTP loopback), with no embedded credentials or path.")


def validate_content(content):
    if not isinstance(content, dict) or set(content) != {"schema", "kind", "title", "text"}:
        raise PeerError("Peer notes must contain only schema, kind, title and text.")
    if content["schema"] != SCHEMA or content["kind"] != "note":
        raise PeerError("Unsupported peer note format.")
    if not isinstance(content["title"], str) or not isinstance(content["text"], str):
        raise PeerError("Peer notes contain text only.")
    if not content["text"].strip() or len(content["title"]) > 160 or len(content["text"]) > 8000:
        raise PeerError("Notes require 1–8000 text characters and a title of at most 160 characters.")
    if len(canonical(content)) > 16_000 or "\x00" in content["text"] + content["title"]:
        raise PeerError("Peer note exceeds the byte limit or contains an invalid character.")
    return content


def validate_event(event):
    if not isinstance(event, dict) or set(event) != {"id", "content", "created_at"}:
        raise PeerError("Invalid peer event fields.")
    content = validate_content(event["content"])
    expected = hashlib.sha256(canonical(content)).hexdigest()
    if not isinstance(event["id"], str) or not hmac.compare_digest(event["id"], expected):
        raise PeerError("Peer note content digest does not match.")
    stamp = event["created_at"]
    if not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or not math.isfinite(stamp) or stamp < 0 or stamp > time.time() + 300:
        raise PeerError("Invalid peer note timestamp.")
    return event


def bounded_events(events, envelope):
    """Fit the actual UTF-8 JSON wire body, keeping the newest notes first."""
    selected = []
    for event in reversed(events[-MAX_BATCH:]):
        candidate = [event, *selected]
        if len(canonical({**envelope, "events": candidate})) <= MAX_BODY:
            selected = candidate
    return selected


class PeerMesh:
    def __init__(self, root, outbound=None, filter_note=None):
        self.root = Path(root).absolute()
        self.path = self.root / "mesh.json"
        self.lock = threading.RLock()
        self.sync_lock = threading.Lock()
        self.outbound = outbound or self._http_exchange
        self.filter_note = filter_note
        self.rate_start = time.monotonic()
        self.rate_count = 0

    def _check_paths(self):
        # Reject symlinks in every existing ancestor, including the runtime root.
        for path in [self.root, *self.root.parents, self.path]:
            if path.is_symlink() or path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & 1024:
                raise PeerError("Peer storage must not contain symbolic links.")
        if self.path.exists() and (not self.path.is_file() or self.path.stat().st_nlink != 1):
            raise PeerError("Peer state must be a regular unlinked file.")

    def _load(self):
        self._check_paths()
        if not self.path.exists():
            return {"schema": SCHEMA, "enabled": False, "receive_hash": "", "peers": [], "published": [], "inbox": [], "last_sync": None}
        if self.path.stat().st_size > MAX_STATE:
            raise PeerError("Peer state exceeds its size limit.")
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema") != SCHEMA:
            raise PeerError("Invalid peer state; preserve it and repair it locally.")
        return value

    def _save(self, state):
        self._check_paths()
        data = canonical(state)
        if len(data) > MAX_STATE:
            raise PeerError("Peer storage limit reached.")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._check_paths()
        descriptor, name = tempfile.mkstemp(prefix=".mesh-", dir=self.root)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(name, 0o600)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def status(self):
        with self.lock:
            state = self._load()
            return {"schema": SCHEMA, "enabled": state["enabled"], "coordinator": None,
                    "receive_key_exists": bool(state["receive_hash"]),
                    "peers": [{"id": peer["id"], "label": peer["label"], "origin": peer["origin"]} for peer in state["peers"]],
                    "published_count": len(state["published"]), "inbox_count": len(state["inbox"]),
                    "last_sync": state["last_sync"], "limits": {"peers": MAX_PEERS, "notes": MAX_NOTES, "batch": MAX_BATCH},
                    "automatic_sharing": False, "remote_execution": False,
                    "published": state["published"][-40:], "inbox": state["inbox"][-40:]}

    def configure(self, enabled):
        if not isinstance(enabled, bool):
            raise PeerError("Enabled must be true or false.")
        with self.lock:
            state = self._load()
            state["enabled"] = enabled
            self._save(state)
        return self.status()

    def rotate_receive_key(self, revoke=False):
        token = "" if revoke else TOKEN_PREFIX + secrets.token_urlsafe(32)
        with self.lock:
            state = self._load()
            state["receive_hash"] = token_hash(token) if token else ""
            self._save(state)
        return {"receive_key": token, "message": "Copy this once for trusted peers; it grants note exchange only." if token else "Receive key revoked."}

    def authorized(self, token):
        with self.lock:
            state = self._load()
            return bool(state["enabled"] and isinstance(token, str) and len(token) <= 256 and state["receive_hash"]
                        and hmac.compare_digest(token_hash(token), state["receive_hash"]))

    def add_peer(self, label, origin, token):
        origin = validate_origin(origin)
        if not isinstance(label, str) or not label.strip() or len(label) > 80:
            raise PeerError("Supply a peer label of 1–80 characters.")
        if not isinstance(token, str) or not token.startswith(TOKEN_PREFIX) or not 32 <= len(token) <= 256 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
            raise PeerError("Supply the recipient node's dedicated ozpeer receive key.")
        identifier = hashlib.sha256(origin.encode()).hexdigest()[:24]
        with self.lock:
            state = self._load()
            peers = [peer for peer in state["peers"] if peer["id"] != identifier]
            if len(peers) >= MAX_PEERS:
                raise PeerError("Peer limit reached; remove an old peer first.")
            peers.append({"id": identifier, "label": label.strip(), "origin": origin, "token": token})
            state["peers"] = peers
            self._save(state)
        return self.status()

    def remove_peer(self, identifier):
        with self.lock:
            state = self._load()
            state["peers"] = [peer for peer in state["peers"] if peer["id"] != identifier]
            self._save(state)
        return self.status()

    def publish(self, title, text, consent):
        if consent is not True:
            raise PeerError("Explicit consent is required to make this text available to peers.")
        content = validate_content({"schema": SCHEMA, "kind": "note", "title": title, "text": text})
        # Conservative obvious-secret redaction is additional to the host's filter.
        def redact(value):
            value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}", "Bearer [REDACTED]", value)
            value = re.sub(r"(?i)\b(?:api[_ -]?key|password|secret|access[_ -]?token)\s*[:=]\s*[^\s,;]+", "[REDACTED CREDENTIAL]", value)
            return re.sub(r"\b(?:ozpeer_|oztp_|oz_|sk-|ghp_|github_pat_)[A-Za-z0-9_-]{16,}", "[REDACTED TOKEN]", value)
        content["title"], content["text"] = redact(content["title"]), redact(content["text"])
        if self.filter_note:
            filtered = self.filter_note(content["title"], content["text"])
            if not filtered.get("ok"):
                raise PeerError("The local public-sharing privacy/safety filter withheld this note.")
            content = validate_content({"schema": SCHEMA, "kind": "note", "title": filtered["prompt"], "text": filtered["answer"]})
        event = {"id": hashlib.sha256(canonical(content)).hexdigest(), "content": content, "created_at": time.time()}
        with self.lock:
            state = self._load()
            if not any(item["id"] == event["id"] for item in state["published"]):
                if len(state["published"]) >= MAX_NOTES:
                    raise PeerError("Published-note limit reached; remove old notes before publishing more.")
                state["published"].append(event)
                self._save(state)
        return {"id": event["id"], "content": content, "message": "Prepared locally for explicitly requested peer exchange."}

    def delete_note(self, identifier, inbox=False):
        with self.lock:
            state = self._load()
            name = "inbox" if inbox else "published"
            state[name] = [event for event in state[name] if event["id"] != identifier]
            self._save(state)
        return self.status()

    def _receive(self, events, source):
        if not isinstance(events, list) or len(events) > MAX_BATCH:
            raise PeerError("Peer exchange exceeds its batch limit.")
        validated = [validate_event(event) for event in events]
        with self.lock:
            state = self._load()
            known = {event["id"] for event in state["published"] + state["inbox"]}
            added = 0
            for event in validated:
                if event["id"] in known:
                    continue
                if len(state["inbox"]) >= MAX_NOTES:
                    break
                state["inbox"].append({**event, "received_from": source, "received_at": time.time(), "review_required": True})
                known.add(event["id"])
                added += 1
            self._save(state)
            return added

    def exchange(self, payload):
        if not isinstance(payload, dict) or set(payload) != {"schema", "events"} or payload["schema"] != SCHEMA:
            raise PeerError("Unsupported peer exchange format.")
        with self.lock:
            state = self._load()
            if not state["enabled"]:
                raise PeerError("Peer exchange is disabled.")
            now = time.monotonic()
            if now - self.rate_start > 60:
                self.rate_start, self.rate_count = now, 0
            self.rate_count += 1
            if self.rate_count > 120:
                raise PeerError("Peer receive rate limit reached.")
            added = self._receive(payload["events"], "authenticated direct peer")
            # Inbox records are deliberately never relayed to other peers.
            envelope = {"schema": SCHEMA, "received": added}
            return {**envelope, "events": bounded_events(self._load()["published"], envelope)}

    @staticmethod
    def _http_exchange(peer, payload):
        session = requests.Session()
        session.trust_env = False
        try:
            deadline = time.monotonic() + 6
            body = canonical(payload)
            if len(body) > MAX_BODY:
                raise PeerError("Peer request exceeds its wire-byte budget.")
            with session.post(validate_origin(peer["origin"]) + "/api/peers/exchange", data=body,
                              headers={"Authorization": "Bearer " + peer["token"], "Content-Type": "application/json"}, timeout=(2, 3),
                              allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise PeerError("Peer rejected the exchange (check enablement and its receive key).")
                raw = bytearray()
                # One-byte chunks make the elapsed guard observable even when a
                # peer dribbles less than a large requested chunk indefinitely.
                for chunk in response.iter_content(1):
                    if time.monotonic() > deadline:
                        raise PeerError("Peer response exceeded its time limit.")
                    raw.extend(chunk)
                    if len(raw) > MAX_BODY:
                        raise PeerError("Peer response exceeds the byte limit.")
                return json.loads(raw)
        finally:
            session.close()

    def sync(self, consent, peer_ids=None, note_ids=None):
        if consent is not True:
            raise PeerError("Explicit consent is required for this network exchange.")
        if not self.sync_lock.acquire(blocking=False):
            raise PeerError("A peer exchange is already running.")
        try:
            with self.lock:
                state = self._load()
                if not state["enabled"]:
                    raise PeerError("Peer exchange is disabled; local chat remains available.")
                peers = state["peers"]
                if peer_ids is not None:
                    if not isinstance(peer_ids, list) or len(peer_ids) > MAX_PEERS or any(not isinstance(item, str) for item in peer_ids):
                        raise PeerError("Invalid peer selection.")
                    peers = [peer for peer in peers if peer["id"] in peer_ids]
                if not peers:
                    raise PeerError("Add or select a trusted peer first.")
                events = state["published"]
                if note_ids is not None:
                    if not isinstance(note_ids, list) or len(note_ids) > MAX_BATCH or any(not isinstance(item, str) for item in note_ids):
                        raise PeerError("Invalid note selection.")
                    events = [event for event in events if event["id"] in note_ids]
                events = bounded_events(events, {"schema": SCHEMA})
            results = []
            for peer in peers:
                # Re-read permissions between peers; disabling cancels future requests.
                with self.lock:
                    current = self._load()
                    if not current["enabled"] or not any(item["id"] == peer["id"] and item["token"] == peer["token"] for item in current["peers"]):
                        break
                    current_ids = {event["id"] for event in current["published"]}
                    events = [event for event in events if event["id"] in current_ids]
                try:
                    response = self.outbound(peer, {"schema": SCHEMA, "events": events})
                    if not isinstance(response, dict) or response.get("schema") != SCHEMA:
                        raise PeerError("Peer returned an unsupported protocol.")
                    with self.lock:
                        if not self._load()["enabled"]:
                            break
                        added = self._receive(response.get("events"), peer["label"])
                    results.append({"peer_id": peer["id"], "ok": True, "received": added})
                except Exception:
                    # Never return provider exception strings, URLs or bearer tokens.
                    results.append({"peer_id": peer["id"], "ok": False, "message": "Exchange failed; verify peer availability, HTTPS and receive key."})
            with self.lock:
                state = self._load()
                state["last_sync"] = {"time": time.time(), "results": results, "sent_notes": len(events)}
                self._save(state)
            return {"status": "success" if results and all(item["ok"] for item in results) else "partial", "results": results, "sent_notes": len(events)}
        finally:
            self.sync_lock.release()


def register_peer_routes(app, root, owner_authorized, filter_note=None, outbound=None):
    mesh = PeerMesh(root, outbound=outbound, filter_note=filter_note)

    def data():
        if request.content_length is not None and request.content_length > MAX_BODY:
            raise PeerError("Peer request exceeds the byte limit.")
        if request.mimetype != "application/json":
            raise PeerError("Peer requests require JSON.")
        raw = request.stream.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise PeerError("Peer request exceeds the byte limit.")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise PeerError("Peer requests require a JSON object.")
        return value

    def respond(fn, receive=False):
        try:
            if receive:
                # Cross-site browser requests are never peer-to-peer authority.
                if request.headers.get("Origin") or request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
                    return jsonify({"error": "Direct authenticated peer requests only."}), 403
                authorization = request.headers.get("Authorization", "")
                token = authorization[7:] if authorization.startswith("Bearer ") else ""
                if not mesh.authorized(token):
                    return jsonify({"error": "Peer disabled or receive key invalid."}), 401
            elif not owner_authorized():
                return jsonify({"error": "Owner authorization required."}), 403
            result = fn()
            # Protocol bytes use UTF-8 consistently with outbound byte budgets.
            return Response(canonical(result), mimetype="application/json") if receive else jsonify(result)
        except PeerError as error:
            return jsonify({"error": str(error)}), 400
        except (ValueError, TypeError, KeyError, OSError):
            return jsonify({"error": "Peer request or storage invalid. Check the declared limits and local configuration."}), 400

    app.add_url_rule("/api/peers/status", "peer_status", lambda: respond(mesh.status), methods=["GET"])
    app.add_url_rule("/api/peers/config", "peer_config", lambda: respond(lambda: mesh.configure(data().get("enabled"))), methods=["POST"])
    app.add_url_rule("/api/peers/key", "peer_key", lambda: respond(lambda: mesh.rotate_receive_key(data().get("revoke") is True)), methods=["POST"])
    app.add_url_rule("/api/peers/add", "peer_add", lambda: respond(lambda: mesh.add_peer(**{key: data_value for key, data_value in data().items() if key in {"label", "origin", "token"}})), methods=["POST"])
    app.add_url_rule("/api/peers/remove", "peer_remove", lambda: respond(lambda: mesh.remove_peer(data().get("id"))), methods=["POST"])
    app.add_url_rule("/api/peers/publish", "peer_publish", lambda: respond(lambda: mesh.publish(**{key: data_value for key, data_value in data().items() if key in {"title", "text", "consent"}})), methods=["POST"])
    app.add_url_rule("/api/peers/sync", "peer_sync", lambda: respond(lambda: mesh.sync(**{key: data_value for key, data_value in data().items() if key in {"consent", "peer_ids", "note_ids"}})), methods=["POST"])
    app.add_url_rule("/api/peers/delete", "peer_delete", lambda: respond(lambda: mesh.delete_note(data().get("id"))), methods=["POST"])
    app.add_url_rule("/api/peers/inbox/delete", "peer_inbox_delete", lambda: respond(lambda: mesh.delete_note(data().get("id"), inbox=True)), methods=["POST"])
    app.add_url_rule("/api/peers/exchange", "peer_exchange", lambda: respond(lambda: mesh.exchange(data()), receive=True), methods=["POST"])
    return mesh
