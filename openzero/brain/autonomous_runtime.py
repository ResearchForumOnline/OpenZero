"""Persistent, bounded run state for OpenZero's unattended agent loop.

This module intentionally does not execute tools or call a model.  It owns the
durable control plane: checkpoints, budgets, approvals, stop/revoke state, and
redacted traces.  Keeping policy here makes it deterministic and independently
testable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
import threading
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple


RUN_ID_RE = re.compile(r"^[a-f0-9]{32}$")
TERMINAL_STATUSES = {"completed", "stopped", "revoked", "error"}
RESUMABLE_STATUSES = {"queued", "running", "interrupted", "paused", "paused_budget"}

DEFAULT_BUDGETS = {
    "max_steps": 12,
    "max_model_calls": 12,
    "max_tool_calls": 10,
    "max_elapsed_seconds": 1800,
    "max_consecutive_errors": 3,
}
HARD_BUDGET_CAPS = {
    "max_steps": 32,
    "max_model_calls": 32,
    "max_tool_calls": 24,
    "max_elapsed_seconds": 14400,
    "max_consecutive_errors": 5,
}

# These actions can modify remote systems, destroy data, represent the operator,
# or establish persistent access.  A model may propose them, but it may not run
# them until the operator supplies a short-lived approval for that exact action.
CONFIRMATION_REQUIRED_ACTIONS = {
    "bash": "raw shell execution can have arbitrary or persistent effects",
    "ssh_command": "remote command execution changes or controls another system",
    "scp_put": "uploading to another system is an external write",
    "remove_path": "deletion can be difficult to recover",
    "speak": "speech is a representational action audible to other people",
}

# An OpenZero run is a root task.  There is deliberately no model-callable action
# that creates another autonomous run.  These names remain blocked if a future
# parser accidentally exposes one.
SELF_REPLICATION_ACTIONS = {
    "create_run",
    "spawn_run",
    "spawn_agent",
    "fork_agent",
    "schedule_agent",
}
REPLAY_SAFE_ACTIONS = {
    "list_dir",
    "tree",
    "read_file",
    "search",
    "zip_list",
    "fetch_url",
    "web_search",
    "moltbot_browse",
    "browse",
    "osint",
    "skills",
}
PERSISTENT_ACCESS_PATH_MARKERS = (
    "/.ssh/authorized_keys",
    "\\.ssh\\authorized_keys",
    "/etc/cron",
    "/var/spool/cron",
    "/etc/systemd/",
    "/.config/systemd/",
    "/etc/init.d/",
    "/etc/rc.local",
    "/.config/autostart/",
    "\\startup\\",
)

SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|authorization|bearer|cookie|credential|password|passwd|"
    r"private[_-]?key|secret|sudo[_-]?pass|token)",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
        r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(
        r"(?i)((?:[\"']?)(?:api[_-]?key|authorization|cookie|credential|password|passwd|"
        r"private[_-]?key|secret|sudo[_-]?pass|token)(?:[\"']?)\s*[:=]\s*)"
        r"(?:[\"'][^\"'\r\n]+[\"']|[^\s,;]+)"
    ),
    re.compile(r"(?i)(https?://[^:/@\s]+:)[^@\s]+(@)"),
    re.compile(r"(?i)(--?(?:api[_-]?key|password|passwd|secret|token)\s+)[^\s]+"),
    re.compile(r"\b(?:oz_|gh[pousr]_|hf_|sk-)[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}\b"),
)


def utc_timestamp(now: Optional[float] = None) -> str:
    value = time.time() if now is None else float(now)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))


def redact_text(value: Any, limit: int = 16000) -> str:
    """Remove common credentials from persisted state and trace text."""

    text = str(value or "")
    for index, pattern in enumerate(SECRET_PATTERNS):
        if index == 2:
            text = pattern.sub(r"\1[REDACTED]", text)
        elif index == 3:
            text = pattern.sub(r"\1[REDACTED]\2", text)
        elif index == 4:
            text = pattern.sub(r"\1[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    if len(text) > limit:
        text = text[: max(0, limit - 16)].rstrip() + "\n...[truncated]..."
    return text


def sanitize_value(value: Any, limit: int = 16000) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            cleaned[key_text] = "[REDACTED]" if SECRET_KEY_RE.search(key_text) else sanitize_value(item, limit=limit)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [sanitize_value(item, limit=limit) for item in value[:200]]
    if isinstance(value, str):
        return redact_text(value, limit=limit)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(value, limit=limit)


def normalize_budgets(raw: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    supplied = raw if isinstance(raw, dict) else {}
    result: Dict[str, int] = {}
    for key, default in DEFAULT_BUDGETS.items():
        try:
            value = int(supplied.get(key, default))
        except (TypeError, ValueError):
            value = default
        result[key] = max(1, min(value, HARD_BUDGET_CAPS[key]))
    return result


def action_fingerprint(action_name: str, payload: Any) -> str:
    canonical = json.dumps(
        {"action": str(action_name or "").strip().lower(), "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8", errors="replace")).hexdigest()


def action_policy(action_name: str, payload: Any = None) -> Tuple[str, str]:
    normalized = str(action_name or "").strip().lower()
    if normalized in SELF_REPLICATION_ACTIONS:
        return "blocked", "autonomous runs cannot create, fork, or schedule more autonomous runs"
    payload_text = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, default=str).lower()
    if normalized in {"bash", "ssh_command"} and (
        "/api/agent/runs" in payload_text
        or re.search(r"\b(?:spawn_agent|spawn_run|fork_agent|schedule_agent|create_autonomous_run)\b", payload_text)
    ):
        return "blocked", "a model-controlled tool cannot create or schedule autonomous runs"
    if normalized in CONFIRMATION_REQUIRED_ACTIONS:
        return "confirmation_required", CONFIRMATION_REQUIRED_ACTIONS[normalized]
    if normalized in {"write_file", "append_file", "replace_text", "mkdir", "zip_extract"}:
        normalized_path_text = payload_text.replace("\\\\", "\\")
        if any(marker.lower() in normalized_path_text for marker in PERSISTENT_ACCESS_PATH_MARKERS):
            return "confirmation_required", "the target path can establish persistent access or startup execution"
    return "allowed", ""


class AutonomousRunStore:
    """Atomic JSON checkpoints plus a bounded, redacted JSONL trace."""

    def __init__(self, root_dir: str, max_trace_bytes: int = 512 * 1024):
        self.root_dir = os.path.abspath(root_dir)
        self.runs_dir = os.path.join(self.root_dir, "runs")
        self.traces_dir = os.path.join(self.root_dir, "traces")
        self.max_trace_bytes = max(4096, int(max_trace_bytes))
        self._lock = threading.RLock()
        os.makedirs(self.runs_dir, exist_ok=True)
        os.makedirs(self.traces_dir, exist_ok=True)

    @staticmethod
    def _validate_run_id(run_id: str) -> str:
        value = str(run_id or "").strip().lower()
        if not RUN_ID_RE.fullmatch(value):
            raise ValueError("Invalid autonomous run id.")
        return value

    def _state_path(self, run_id: str) -> str:
        return os.path.join(self.runs_dir, f"{self._validate_run_id(run_id)}.json")

    def _trace_path(self, run_id: str) -> str:
        return os.path.join(self.traces_dir, f"{self._validate_run_id(run_id)}.jsonl")

    @staticmethod
    def _atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".openzero-run-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)

    def create(
        self,
        objective: str,
        comp_mode: str = "hybrid",
        agent_mode: str = "terminal",
        budgets: Optional[Dict[str, Any]] = None,
        auto_resume: bool = True,
        owner_session: str = "",
    ) -> Dict[str, Any]:
        run_id = uuid.uuid4().hex
        now = time.time()
        state = {
            "id": run_id,
            "status": "queued",
            "objective": redact_text(objective, limit=24000),
            "current_prompt": redact_text(objective, limit=24000),
            "last_safe_result": "",
            "comp_mode": str(comp_mode or "hybrid")[:32],
            "agent_mode": str(agent_mode or "terminal")[:32],
            "budgets": normalize_budgets(budgets),
            "usage": {
                "steps": 0,
                "model_calls": 0,
                "tool_calls": 0,
                "consecutive_errors": 0,
                "elapsed_seconds": 0,
            },
            "created_at": utc_timestamp(now),
            "created_at_epoch": now,
            "updated_at": utc_timestamp(now),
            "updated_at_epoch": now,
            "started_at_epoch": 0.0,
            "last_heartbeat_epoch": 0.0,
            "finished_at": "",
            "auto_resume": bool(auto_resume),
            "owner_session": hashlib.sha256(str(owner_session or "").encode("utf-8")).hexdigest()[:16]
            if owner_session
            else "",
            "stop_requested": False,
            "revoked": False,
            "resume_count": 0,
            "pending_action": None,
            "approval": None,
            "inflight_action": None,
            "trace_truncated": False,
        }
        with self._lock:
            self._atomic_write_json(self._state_path(run_id), state)
            self.append_trace(run_id, "run_created", status="queued", budgets=state["budgets"], auto_resume=bool(auto_resume))
        return dict(state)

    def get(self, run_id: str) -> Dict[str, Any]:
        path = self._state_path(run_id)
        with self._lock:
            if not os.path.exists(path):
                return {}
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}

    def update(self, run_id: str, **updates: Any) -> Dict[str, Any]:
        with self._lock:
            state = self.get(run_id)
            if not state:
                raise KeyError(f"Autonomous run not found: {run_id}")
            now = time.time()
            cleaned = sanitize_value(updates)
            state.update(cleaned)
            state["updated_at"] = utc_timestamp(now)
            state["updated_at_epoch"] = now
            started = float(state.get("started_at_epoch") or 0.0)
            if started:
                usage = dict(state.get("usage") or {})
                usage["elapsed_seconds"] = max(0, int(now - started))
                state["usage"] = usage
            self._atomic_write_json(self._state_path(run_id), state)
            return dict(state)

    def append_trace(self, run_id: str, event: str, **fields: Any) -> bool:
        path = self._trace_path(run_id)
        entry = {
            "at": utc_timestamp(),
            "event": str(event or "event")[:80],
            **sanitize_value(fields, limit=8000),
        }
        encoded = (json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        with self._lock:
            current_size = os.path.getsize(path) if os.path.exists(path) else 0
            if current_size + len(encoded) > self.max_trace_bytes:
                state = self.get(run_id)
                if state and not state.get("trace_truncated"):
                    marker = json.dumps(
                        {"at": utc_timestamp(), "event": "trace_limit_reached"},
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode("utf-8") + b"\n"
                    if current_size + len(marker) <= self.max_trace_bytes:
                        with open(path, "ab") as handle:
                            handle.write(marker)
                            handle.flush()
                            os.fsync(handle.fileno())
                    self.update(run_id, trace_truncated=True)
                return False
            with open(path, "ab") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        return True

    def trace_tail(self, run_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        path = self._trace_path(run_id)
        if not os.path.exists(path):
            return []
        with self._lock:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()[-max(1, min(int(limit or 50), 200)) :]
        events = []
        for line in lines:
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        return events

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        items = []
        for name in os.listdir(self.runs_dir):
            if not name.endswith(".json"):
                continue
            run_id = name[:-5]
            if not RUN_ID_RE.fullmatch(run_id):
                continue
            state = self.get(run_id)
            if state:
                items.append(state)
        items.sort(key=lambda item: float(item.get("updated_at_epoch") or 0.0), reverse=True)
        return items[: max(1, min(int(limit or 50), 200))]

    @staticmethod
    def public_state(state: Dict[str, Any], include_objective: bool = False) -> Dict[str, Any]:
        if not state:
            return {}
        payload = {
            "id": state.get("id"),
            "status": state.get("status"),
            "agent_mode": state.get("agent_mode"),
            "comp_mode": state.get("comp_mode"),
            "skill_ids": [str(item) for item in state.get("skill_ids") or []],
            "budgets": dict(state.get("budgets") or {}),
            "usage": dict(state.get("usage") or {}),
            "created_at": state.get("created_at"),
            "updated_at": state.get("updated_at"),
            "finished_at": state.get("finished_at"),
            "auto_resume": bool(state.get("auto_resume")),
            "stop_requested": bool(state.get("stop_requested")),
            "revoked": bool(state.get("revoked")),
            "resume_count": int(state.get("resume_count") or 0),
            "pending_action": sanitize_value(state.get("pending_action")),
            "inflight_action": sanitize_value(state.get("inflight_action")),
            "trace_truncated": bool(state.get("trace_truncated")),
        }
        if include_objective:
            payload["objective"] = redact_text(state.get("objective", ""), limit=24000)
            payload["last_safe_result"] = redact_text(state.get("last_safe_result", ""), limit=8000)
        return payload

    def budget_guard(self, run_id: str, now: Optional[float] = None) -> Tuple[bool, str]:
        state = self.get(run_id)
        if not state:
            return False, "run_not_found"
        if state.get("revoked") or state.get("status") == "revoked":
            return False, "revoked"
        if state.get("stop_requested"):
            return False, "stop_requested"
        budgets = normalize_budgets(state.get("budgets"))
        usage = dict(state.get("usage") or {})
        current = time.time() if now is None else float(now)
        started = float(state.get("started_at_epoch") or current)
        checks = (
            ("max_elapsed_seconds", max(0, int(current - started))),
            ("max_steps", int(usage.get("steps") or 0)),
            ("max_model_calls", int(usage.get("model_calls") or 0)),
            ("max_tool_calls", int(usage.get("tool_calls") or 0)),
            ("max_consecutive_errors", int(usage.get("consecutive_errors") or 0)),
        )
        for key, used in checks:
            if used >= budgets[key]:
                return False, key
        return True, ""

    def start_or_resume(self, run_id: str) -> Dict[str, Any]:
        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        if state.get("revoked"):
            raise ValueError("A revoked autonomous run cannot be resumed.")
        if state.get("status") == "completed":
            raise ValueError("A completed autonomous run cannot be resumed.")
        now = time.time()
        started = float(state.get("started_at_epoch") or 0.0) or now
        state = self.update(
            run_id,
            status="running",
            stop_requested=False,
            started_at_epoch=started,
            last_heartbeat_epoch=now,
            finished_at="",
            resume_count=int(state.get("resume_count") or 0) + (1 if state.get("status") != "queued" else 0),
        )
        self.append_trace(run_id, "run_started", resume_count=state.get("resume_count", 0))
        return state

    def checkpoint(
        self,
        run_id: str,
        *,
        current_prompt: Optional[str] = None,
        last_safe_result: Optional[str] = None,
        usage_delta: Optional[Dict[str, int]] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        usage = dict(state.get("usage") or {})
        for key, delta in (usage_delta or {}).items():
            if key in usage:
                usage[key] = max(0, int(usage.get(key) or 0) + int(delta))
        updates: Dict[str, Any] = {
            "usage": usage,
            "last_heartbeat_epoch": time.time(),
        }
        if current_prompt is not None:
            updates["current_prompt"] = redact_text(current_prompt, limit=24000)
        if last_safe_result is not None:
            updates["last_safe_result"] = redact_text(last_safe_result, limit=8000)
        if status:
            updates["status"] = status
        return self.update(run_id, **updates)

    def finish(self, run_id: str, status: str, result: str = "", reason: str = "") -> Dict[str, Any]:
        normalized = status if status in TERMINAL_STATUSES | {"paused", "paused_budget", "awaiting_confirmation"} else "error"
        state = self.update(
            run_id,
            status=normalized,
            last_safe_result=redact_text(result, limit=8000),
            finished_at=utc_timestamp() if normalized in TERMINAL_STATUSES else "",
            pending_action=None if normalized in TERMINAL_STATUSES else self.get(run_id).get("pending_action"),
            approval=None if normalized in TERMINAL_STATUSES else self.get(run_id).get("approval"),
            inflight_action=None if normalized in TERMINAL_STATUSES else self.get(run_id).get("inflight_action"),
        )
        self.append_trace(run_id, "run_status", status=normalized, reason=reason, result=result)
        return state

    def request_stop(self, run_id: str) -> Dict[str, Any]:
        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        if state.get("status") in TERMINAL_STATUSES:
            return state
        state = self.update(run_id, stop_requested=True, auto_resume=False, status="stopping")
        self.append_trace(run_id, "stop_requested")
        return state

    def revoke(self, run_id: str) -> Dict[str, Any]:
        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        state = self.update(
            run_id,
            revoked=True,
            stop_requested=True,
            auto_resume=False,
            status="revoked",
            pending_action=None,
            approval=None,
            finished_at=utc_timestamp(),
        )
        self.append_trace(run_id, "run_revoked")
        return state

    def pause_for_approval(
        self,
        run_id: str,
        action_name: str,
        fingerprint: str,
        summary: str,
        reason: str,
    ) -> Dict[str, Any]:
        pending = {
            "action": str(action_name or "")[:80],
            "fingerprint": str(fingerprint or "")[:64],
            "summary": redact_text(summary, limit=1000),
            "reason": redact_text(reason, limit=500),
            "requested_at": utc_timestamp(),
        }
        state = self.update(run_id, status="awaiting_confirmation", pending_action=pending, approval=None)
        self.append_trace(run_id, "confirmation_required", pending_action=pending)
        return state

    def approve(self, run_id: str, fingerprint: str, ttl_seconds: int = 300) -> Dict[str, Any]:
        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        if state.get("revoked"):
            raise ValueError("A revoked autonomous run cannot be approved.")
        pending = dict(state.get("pending_action") or {})
        supplied = str(fingerprint or "").strip().lower()
        if not supplied or not re.fullmatch(r"[a-f0-9]{64}", supplied):
            raise ValueError("A valid pending action fingerprint is required.")
        if supplied != pending.get("fingerprint"):
            raise ValueError("Approval fingerprint does not match the pending action.")
        expires_at = time.time() + max(30, min(int(ttl_seconds or 300), 600))
        approval = {
            "fingerprint": supplied,
            "action": pending.get("action"),
            "expires_at_epoch": expires_at,
            "expires_at": utc_timestamp(expires_at),
            "consumed": False,
        }
        state = self.update(run_id, approval=approval, status="paused", stop_requested=False)
        self.append_trace(run_id, "confirmation_granted", action=pending.get("action"), expires_at=approval["expires_at"])
        return state

    def consume_approval(self, run_id: str, fingerprint: str) -> bool:
        state = self.get(run_id)
        approval = dict(state.get("approval") or {}) if state else {}
        if not approval or approval.get("consumed"):
            return False
        if time.time() > float(approval.get("expires_at_epoch") or 0.0):
            self.update(run_id, approval=None)
            self.append_trace(run_id, "confirmation_expired")
            return False
        if not hmac.compare_digest(str(fingerprint), str(approval.get("fingerprint") or "")):
            return False
        approval["consumed"] = True
        self.update(run_id, approval=approval, pending_action=None)
        self.append_trace(run_id, "confirmation_consumed", action=approval.get("action"))
        return True

    def mark_action_started(self, run_id: str, action_name: str, fingerprint: str, summary: str) -> Dict[str, Any]:
        action = str(action_name or "").strip().lower()
        inflight = {
            "action": action,
            "fingerprint": str(fingerprint or "")[:64],
            "summary": redact_text(summary, limit=1000),
            "replay_safe": action in REPLAY_SAFE_ACTIONS,
            "started_at": utc_timestamp(),
        }
        state = self.update(run_id, inflight_action=inflight)
        self.append_trace(run_id, "tool_started", inflight_action=inflight)
        return state

    def clear_inflight_action(self, run_id: str) -> Dict[str, Any]:
        state = self.update(run_id, inflight_action=None)
        self.append_trace(run_id, "tool_checkpointed")
        return state

    def recoverable(self) -> List[Dict[str, Any]]:
        recovered = []
        for state in self.list(limit=200):
            status = str(state.get("status") or "")
            if status == "running":
                inflight = dict(state.get("inflight_action") or {})
                if inflight and not inflight.get("replay_safe"):
                    state = self.update(
                        state["id"],
                        status="interrupted_action",
                        auto_resume=False,
                        current_prompt=(
                            "The previous process stopped while a non-replay-safe tool was in flight. "
                            "Its outcome is unknown. Inspect the target before deciding whether to resume."
                        ),
                    )
                    self.append_trace(
                        state["id"],
                        "process_restart_during_action",
                        inflight_action=inflight,
                        auto_resume=False,
                    )
                else:
                    state = self.update(
                        state["id"],
                        status="interrupted",
                        inflight_action=None,
                        current_prompt=(
                            "The previous process stopped during a replay-safe read. Re-check that read, then continue "
                            "toward the original objective."
                            if inflight
                            else state.get("current_prompt", "")
                        ),
                    )
                    self.append_trace(state["id"], "process_restart_detected", inflight_action=inflight or None)
            if (
                state.get("auto_resume")
                and not state.get("revoked")
                and not state.get("stop_requested")
                and state.get("status") in RESUMABLE_STATUSES
            ):
                allowed, _ = self.budget_guard(state["id"])
                if allowed:
                    recovered.append(state)
        return recovered
