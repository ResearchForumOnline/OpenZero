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
from urllib.parse import urlsplit, urlunsplit


RUN_ID_RE = re.compile(r"^[a-f0-9]{32}$")
TERMINAL_STATUSES = {"completed", "stopped", "revoked", "error"}
RESUMABLE_STATUSES = {"queued", "running", "interrupted", "paused", "paused_budget"}
PENDING_APPROVAL_MAX_AGE_SECONDS = 600

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
ULTRA_DEFAULT_BUDGETS = {
    "max_steps": 24,
    "max_model_calls": 24,
    "max_tool_calls": 20,
    "max_elapsed_seconds": 3600,
    "max_consecutive_errors": 3,
}
ULTRA_HARD_BUDGET_CAPS = {
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


def normalize_autonomy_profile(value: Any) -> str:
    return "ultra" if str(value or "").strip().lower() == "ultra" else "standard"


def normalize_budgets(
    raw: Optional[Dict[str, Any]] = None,
    profile: str = "standard",
) -> Dict[str, int]:
    autonomy_profile = normalize_autonomy_profile(profile)
    defaults = ULTRA_DEFAULT_BUDGETS if autonomy_profile == "ultra" else DEFAULT_BUDGETS
    caps = ULTRA_HARD_BUDGET_CAPS if autonomy_profile == "ultra" else HARD_BUDGET_CAPS
    supplied = raw if isinstance(raw, dict) else {}
    result: Dict[str, int] = {}
    for key, default in defaults.items():
        try:
            value = int(supplied.get(key, default))
        except (TypeError, ValueError):
            value = default
        result[key] = max(1, min(value, caps[key]))
    return result


def incomplete_action_promise_reason(raw_reply: str) -> str:
    """Reject future-action prose that would otherwise be mistaken for completion."""

    text = str(raw_reply or "").strip()
    if not text:
        return "The model returned an empty response instead of a completed result or operator action."
    if re.search(
        r"<(?:tool|bash|osint|browse|speak)>.*?</(?:tool|bash|osint|browse|speak)>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        return ""
    intent_text = re.sub(
        r"\bi(?:\s+(?:will|shall)|['’]ll)\s+not\b[^.;\n]*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    future_intent = re.search(
        r"(?:\bi(?:\s+(?:will|shall|am\s+going\s+to)|['’]ll)\b|"
        r"\bnext\s*,?\s+i(?:\s+will|['’]ll)\b|"
        r"let\s+me|"
        r"proceed(?:ing)?\s+to|"
        r"will\s+now)\b",
        intent_text,
        flags=re.IGNORECASE,
    )
    pending_action = re.search(
        r"\b(?:browse|call|check|click|continue|execute|fill|inspect|navigate|open|"
        r"press|run|select|submit|type|use|verify|visit)\b",
        intent_text,
        flags=re.IGNORECASE,
    )
    if future_intent and pending_action:
        return (
            "The model described a future operator action but did not issue a tool call or provide "
            "evidence that the action completed."
        )
    return ""


SCHEME_BROWSER_TARGET_RE = re.compile(r"\bhttps?://[^\s<>'\"]+", re.IGNORECASE)
BARE_BROWSER_TARGET_RE = re.compile(
    r"(?<![@\w])("
    r"(?:localhost(?::\d{1,5})?|"
    r"(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?|"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(?::\d{1,5})?)"
    r"(?:[/?#][^\s<>'\"]*)?"
    r")",
    re.IGNORECASE,
)


def _trim_browser_target_candidate(candidate: str) -> str:
    value = str(candidate or "").strip()
    while value and value[-1] in ".,;:!?":
        value = value[:-1]
    for opener, closer in (("(", ")"), ("[", "]"), ("{", "}")):
        while value.endswith(closer) and value.count(closer) > value.count(opener):
            value = value[:-1]
    return value


def objective_browser_target(raw_text: str) -> str:
    """Return one normalized HTTP(S) target from the authoritative objective."""

    text = str(raw_text or "")
    match = SCHEME_BROWSER_TARGET_RE.search(text)
    is_bare = False
    if not match:
        match = BARE_BROWSER_TARGET_RE.search(text)
        is_bare = True
    if not match:
        return ""
    if is_bare and re.search(
        r"[a-z][a-z0-9+.-]*://\s*$",
        text[: match.start()],
        flags=re.IGNORECASE,
    ):
        return ""
    candidate = _trim_browser_target_candidate(match.group(0))
    if not candidate:
        return ""
    if is_bare:
        authority = candidate.split("/", 1)[0]
        hostname = authority.rsplit("@", 1)[-1].split(":", 1)[0].lower()
        scheme = "http" if hostname in {"localhost", "127.0.0.1", "0.0.0.0"} else "https"
        candidate = f"{scheme}://{candidate}"
    try:
        parts = urlsplit(candidate)
        port = parts.port
        hostname = (parts.hostname or "").encode("idna").decode("ascii").lower()
    except (TypeError, ValueError, UnicodeError):
        return ""
    if parts.scheme.lower() not in {"http", "https"} or not hostname:
        return ""
    if parts.username or parts.password:
        return ""
    formatted_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{formatted_host}:{port}" if port is not None else formatted_host
    return urlunsplit(
        (parts.scheme.lower(), netloc, parts.path, parts.query, parts.fragment)
    )


def _browser_target_key(raw_value: str) -> Tuple[str, str, int, str, str]:
    target = objective_browser_target(raw_value)
    if not target:
        return ("", "", 0, "", "")
    try:
        parts = urlsplit(target)
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except (TypeError, ValueError):
        return ("", "", 0, "", "")
    path = parts.path.rstrip("/") or "/"
    return (parts.scheme.lower(), (parts.hostname or "").lower(), port, path, parts.query)


def browser_target_matches(expected: str, observed: str) -> bool:
    expected_key = _browser_target_key(expected)
    observed_key = _browser_target_key(observed)
    return bool(expected_key[1] and expected_key == observed_key)


def browser_final_target_compatible(expected: str, observed: str) -> bool:
    """Allow same-site redirects while rejecting unrelated final origins."""

    expected_target = objective_browser_target(expected)
    observed_target = objective_browser_target(observed)
    if not expected_target or not observed_target:
        return False
    try:
        expected_parts = urlsplit(expected_target)
        observed_parts = urlsplit(observed_target)
        expected_host = (expected_parts.hostname or "").lower()
        observed_host = (observed_parts.hostname or "").lower()
        expected_port = expected_parts.port
        observed_port = observed_parts.port
    except (TypeError, ValueError):
        return False
    if (
        expected_parts.scheme.lower() == "https"
        and observed_parts.scheme.lower() != "https"
    ):
        return False
    host_compatible = (
        expected_host == observed_host
        or observed_host.endswith(f".{expected_host}")
        or expected_host.endswith(f".{observed_host}")
    )
    if not host_compatible:
        return False
    if expected_port is not None and expected_port not in {80, 443}:
        return expected_port == observed_port
    return observed_port is None or observed_port in {80, 443}


def requires_tab_pilot_evidence(objective: str) -> bool:
    text = str(objective or "").strip()
    if not text or re.match(
        r"^(?:describe|explain|how|tell\s+me\s+how|what|why)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            r"\bbrave\b|\btab\s+pilot\b|"
            r"\b(?:current|existing|already[- ]open)\s+(?:browser\s+)?tab\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def browser_element_matches_objective(objective: str, element_label: str) -> bool:
    """Bind explicit click-like requests to the inspected element's public label."""

    text = str(objective or "").strip().lower()
    label = str(element_label or "").strip().lower()
    match = re.search(
        r"\b(?:choos(?:e|ing)|click(?:ing)?|press(?:ing)?|select(?:ing)?|"
        r"submit(?:ting)?|tap(?:ping)?|toggl(?:e|ing))\b"
        r"\s+(?:the\s+)?(?:button|link|option|control|item)?\s*"
        r"(?P<target>[^.;\n]{1,120})",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return True
    target = str(match.group("target") or "")
    target = re.split(
        r"\b(?:on|at|using|from|then|and\s+then)\b",
        target,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    target = target.strip(" \t\r\n\"'`()[]{}")
    stop_words = {
        "a",
        "an",
        "button",
        "control",
        "it",
        "item",
        "link",
        "my",
        "option",
        "please",
        "that",
        "the",
        "this",
        "your",
    }
    expected_words = [
        item for item in re.findall(r"[a-z0-9]+", target) if item not in stop_words
    ]
    if not expected_words:
        return True
    if not label:
        return False
    label_words = re.findall(r"[a-z0-9]+", label)
    expected_compact = "".join(expected_words)
    label_compact = "".join(label_words)
    return (
        set(expected_words).issubset(set(label_words))
        or (expected_compact and expected_compact in label_compact)
    )


def browser_text_digest(value: Any) -> str:
    """Return a domain-separated digest without persisting typed browser text."""

    encoded = str(value if value is not None else "").encode(
        "utf-8", errors="surrogatepass"
    )
    return hashlib.sha256(b"openzero-browser-text-v1\0" + encoded).hexdigest()


_BROWSER_INTERACTION_WORD = (
    r"(?:choos(?:e|ing)|click(?:ing)?|enter(?:ing)?|fill(?:ing)?|press(?:ing)?|"
    r"select(?:ing)?|submit(?:ting)?|tap(?:ping)?|toggl(?:e|ing)|typ(?:e|ing))"
)
_BROWSER_TYPE_WORD_RE = re.compile(
    r"^(?:enter(?:ing)?|fill(?:ing)?|typ(?:e|ing))$", re.IGNORECASE
)
_BROWSER_ACTION_CLAUSE_SPLIT_RE = re.compile(
    rf"(?:\b(?:and\s+then|then|next|after\s+that)\b|[;\n]+|"
    rf",\s*(?=(?:and\s+)?{_BROWSER_INTERACTION_WORD}\b)|"
    rf"\band\s+(?={_BROWSER_INTERACTION_WORD}\b))",
    re.IGNORECASE,
)
_BROWSER_ACTION_WORD_RE = re.compile(
    rf"\b(?P<verb>{_BROWSER_INTERACTION_WORD})\b", re.IGNORECASE
)


def _positive_browser_objective(objective: str) -> str:
    return re.sub(
        rf"\b(?:do\s+not|don't|never|without)\s+{_BROWSER_INTERACTION_WORD}\b"
        r"[^.;\n]*?(?=\b(?:but|instead)\b|[.;\n]|$)",
        "",
        str(objective or ""),
        flags=re.IGNORECASE,
    )


def _trim_action_argument(value: str) -> str:
    cleaned = re.sub(
        r"\s+(?:on|at|using|from)\s+https?://\S+\s*$",
        "",
        str(value or "").strip(),
        flags=re.IGNORECASE,
    ).strip(" \t\r\n.,;:!?")
    if (
        len(cleaned) >= 2
        and cleaned[0] == cleaned[-1]
        and cleaned[0] in {"'", '"', "`"}
    ):
        cleaned = cleaned[1:-1]
    return cleaned.strip()


def _label_words(value: str, *, field: bool = False) -> List[str]:
    ignored = {
        "a", "an", "button", "control", "it", "item", "link", "my",
        "option", "please", "that", "the", "this", "your",
    }
    if field:
        ignored.update({"box", "field", "input", "textbox"})
    return [
        item for item in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if item not in ignored
    ]


def _browser_field_matches(expected_field: str, observed_label: str) -> bool:
    expected_words = _label_words(expected_field, field=True)
    observed_words = _label_words(observed_label, field=True)
    if not expected_words or not observed_words:
        return False
    return (
        set(expected_words).issubset(set(observed_words))
        or "".join(expected_words) in "".join(observed_words)
    )


def _parse_type_expectation(clause: str, verb: str, rest: str) -> Dict[str, Any]:
    value = ""
    field = ""
    if str(verb or "").lower().startswith("fill"):
        match = re.match(
            r"^(?:in\s+)?(?P<field>.+?)\s+with\s+(?P<value>.+)$",
            rest,
            flags=re.IGNORECASE,
        )
        if match:
            field = _trim_action_argument(match.group("field"))
            value = _trim_action_argument(match.group("value"))
    if not value or not field:
        match = re.match(
            r"^(?P<value>.+?)\s+(?:in|into)\s+(?P<field>.+)$",
            rest,
            flags=re.IGNORECASE,
        )
        if match:
            value = _trim_action_argument(match.group("value"))
            field = _trim_action_argument(match.group("field"))
    return {
        "action_name": "moltbot_type",
        "clause": str(clause or "").strip(),
        "field": field,
        "text_length": len(value),
        "text_digest": browser_text_digest(value) if value else "",
        "parse_complete": bool(value and field),
    }


def _expected_browser_actions(objective: str) -> List[Dict[str, Any]]:
    expected: List[Dict[str, Any]] = []
    for clause in _BROWSER_ACTION_CLAUSE_SPLIT_RE.split(
        _positive_browser_objective(objective)
    ):
        match = _BROWSER_ACTION_WORD_RE.search(clause)
        if not match:
            continue
        verb = str(match.group("verb") or "")
        rest = str(clause[match.end() :] or "").strip()
        if _BROWSER_TYPE_WORD_RE.fullmatch(verb):
            expected.append(_parse_type_expectation(clause, verb, rest))
        else:
            expected.append({
                "action_name": "moltbot_click",
                "clause": str(clause[match.start() :] or "").strip(),
                "parse_complete": True,
            })
    return expected


def _browser_action_ledger(proof: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_actions = proof.get("browser_actions")
    if isinstance(raw_actions, list):
        actions = [dict(item) for item in raw_actions[:64] if isinstance(item, dict)]
        for action in actions:
            action.setdefault(
                "owner_run_id", str(proof.get("browser_owner_run_id") or "")
            )
        return actions
    if not proof.get("browser_action"):
        return []
    return [{
        "action_name": proof.get("browser_action_name"),
        "element_id": proof.get("browser_element_id"),
        "element_label": proof.get("browser_element_label"),
        "element_risk": proof.get("browser_element_risk"),
        "element_href": proof.get("browser_element_href"),
        "source_snapshot_id": proof.get("browser_source_snapshot_id"),
        "snapshot_id": proof.get("browser_snapshot_id"),
        "verification": proof.get("browser_verification"),
        "state_changed": proof.get("browser_state_changed"),
        "owner_run_id": proof.get("browser_owner_run_id"),
        "typed_text_length": proof.get("browser_typed_text_length"),
        "typed_text_digest": proof.get("browser_typed_text_digest"),
        "legacy": True,
    }]


def _verified_browser_action(entry: Dict[str, Any], expected_run_id: str) -> bool:
    owner = str(
        entry.get("owner_run_id") or entry.get("browser_owner_run_id") or ""
    )
    source_snapshot = str(entry.get("source_snapshot_id") or "").strip()
    post_snapshot = str(entry.get("snapshot_id") or "").strip()
    return bool(
        str(entry.get("element_id") or "").strip()
        and post_snapshot
        and (entry.get("legacy") or (source_snapshot and source_snapshot != post_snapshot))
        and str(entry.get("verification") or "") == "post_action_inspection"
        and entry.get("state_changed") is True
        and (not expected_run_id or owner == str(expected_run_id))
    )


def _browser_action_sequence_reason(
    expected_actions: List[Dict[str, Any]],
    observed_actions: List[Dict[str, Any]],
    expected_run_id: str,
) -> str:
    cursor = 0
    prior_matched_snapshot_id = ""
    for step_index, expected in enumerate(expected_actions, start=1):
        expected_name = str(expected.get("action_name") or "")
        if expected_name == "moltbot_type" and not expected.get("parse_complete"):
            return (
                f"Browser action step {step_index} does not identify both the text "
                "and destination field precisely enough to verify."
            )
        matched = False
        binding_error = ""
        while cursor < len(observed_actions):
            observed = observed_actions[cursor]
            cursor += 1
            if str(observed.get("action_name") or "") != expected_name:
                continue
            if not _verified_browser_action(observed, expected_run_id):
                binding_error = (
                    f"Browser action step {step_index} lacks run-bound post-action evidence."
                )
                continue
            source_snapshot_id = str(observed.get("source_snapshot_id") or "")
            if (
                prior_matched_snapshot_id
                and source_snapshot_id != prior_matched_snapshot_id
            ):
                binding_error = f"Browser action step {step_index} is not chained to the previous action snapshot."
                continue
            label = str(observed.get("element_label") or "")
            if expected_name == "moltbot_click":
                if not browser_element_matches_objective(
                    str(expected.get("clause") or ""), label
                ):
                    binding_error = (
                        f"Browser click step {step_index} targeted a different element."
                    )
                    continue
            else:
                if not _browser_field_matches(str(expected.get("field") or ""), label):
                    binding_error = (
                        f"Browser typing step {step_index} targeted a different field."
                    )
                    continue
                try:
                    observed_length = int(observed.get("typed_text_length"))
                except (TypeError, ValueError, OverflowError):
                    observed_length = -1
                if (
                    observed_length != int(expected.get("text_length") or 0)
                    or not hmac.compare_digest(
                        str(observed.get("typed_text_digest") or ""),
                        str(expected.get("text_digest") or ""),
                    )
                ):
                    binding_error = (
                        f"Browser typing step {step_index} entered different text."
                    )
                    continue
            matched = True
            prior_matched_snapshot_id = str(observed.get("snapshot_id") or "")
            break
        if not matched:
            return binding_error or (
                f"The verified browser action does not match ordered action step {step_index}."
            )
    return ""


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
    if normalized in {"moltbot_click", "moltbot_type"} and isinstance(payload, dict):
        element = payload.get("_element") if isinstance(payload.get("_element"), dict) else {}
        risk = str(element.get("risk") or "").strip().lower()
        if risk == "blocked_sensitive":
            return "blocked", "Moltbot blocks password, payment, secret, upload, token, and CAPTCHA controls"
        if risk in {"consequential", "cross_origin", "personal_data"}:
            reasons = {
                "consequential": "the inspected browser control can submit, publish, purchase, sign in, or change an account",
                "cross_origin": "the inspected browser control leaves the currently inspected site",
                "personal_data": "the inspected browser control handles personal data",
            }
            return "confirmation_required", reasons[risk]
    if normalized in {"write_file", "append_file", "replace_text", "mkdir", "zip_extract"}:
        normalized_path_text = payload_text.replace("\\\\", "\\")
        if any(marker.lower() in normalized_path_text for marker in PERSISTENT_ACCESS_PATH_MARKERS):
            return "confirmation_required", "the target path can establish persistent access or startup execution"
    return "allowed", ""


def _atomic_store_transition(method):
    """Serialize a complete read-check-write store transition."""

    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    wrapped.__name__ = getattr(method, "__name__", "atomic_store_transition")
    wrapped.__doc__ = getattr(method, "__doc__", None)
    return wrapped


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
        autonomy_profile: str = "standard",
        auto_resume: bool = True,
        owner_session: str = "",
    ) -> Dict[str, Any]:
        run_id = uuid.uuid4().hex
        now = time.time()
        normalized_profile = normalize_autonomy_profile(autonomy_profile)
        state = {
            "id": run_id,
            "status": "queued",
            "objective": redact_text(objective, limit=24000),
            "current_prompt": redact_text(objective, limit=24000),
            "last_safe_result": "",
            "comp_mode": str(comp_mode or "hybrid")[:32],
            "agent_mode": str(agent_mode or "terminal")[:32],
            "autonomy_profile": normalized_profile,
            "budgets": normalize_budgets(budgets, profile=normalized_profile),
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
            self.append_trace(
                run_id,
                "run_created",
                status="queued",
                autonomy_profile=normalized_profile,
                budgets=state["budgets"],
                auto_resume=bool(auto_resume),
            )
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
            # The profile is part of the run's original authority envelope.
            # Resumes and internal updates may adjust budgets inside that
            # envelope, but cannot silently switch Standard and Ultra.
            cleaned.pop("autonomy_profile", None)
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
            "autonomy_profile": normalize_autonomy_profile(state.get("autonomy_profile")),
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
        budgets = normalize_budgets(
            state.get("budgets"),
            profile=normalize_autonomy_profile(state.get("autonomy_profile")),
        )
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

    @_atomic_store_transition
    def start_or_resume(self, run_id: str) -> Dict[str, Any]:
        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        status = str(state.get("status") or "")
        if state.get("revoked") or status == "revoked":
            raise ValueError("A revoked autonomous run cannot be resumed.")
        if status in TERMINAL_STATUSES:
            raise ValueError("A terminal autonomous run must be explicitly queued before startup.")
        if state.get("stop_requested") or status == "stopping":
            raise ValueError("A stopping autonomous run cannot be started.")
        now = time.time()
        started = float(state.get("started_at_epoch") or 0.0) or now
        state = self.update(
            run_id,
            status="running",
            started_at_epoch=started,
            last_heartbeat_epoch=now,
            finished_at="",
            resume_count=int(state.get("resume_count") or 0) + (1 if state.get("status") != "queued" else 0),
        )
        self.append_trace(run_id, "run_started", resume_count=state.get("resume_count", 0))
        return state

    @_atomic_store_transition
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

    @_atomic_store_transition
    def checkpoint_action_result(
        self,
        run_id: str,
        *,
        current_prompt: str,
        last_safe_result: str,
        usage_delta: Optional[Dict[str, int]] = None,
        completion_evidence: Optional[Dict[str, Any]] = None,
        clear_inflight: bool = False,
        preserve_approved_queue: bool = False,
    ) -> Dict[str, Any]:
        """Durably checkpoint one tool result before clearing its replay guard."""

        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        stale_approval_worker = bool(
            preserve_approved_queue
            and str(state.get("status") or "") in {"queued", "running"}
            and state.get("approval")
            and not state.get("stop_requested")
            and not state.get("revoked")
        )
        if stale_approval_worker:
            self.append_trace(
                run_id,
                "stale_approval_checkpoint_ignored",
                status=state.get("status"),
            )
            return state

        usage = dict(state.get("usage") or {})
        for key, delta in (usage_delta or {}).items():
            if key in usage:
                usage[key] = max(0, int(usage.get(key) or 0) + int(delta))
        updates: Dict[str, Any] = {
            "current_prompt": redact_text(current_prompt, limit=24000),
            "last_safe_result": redact_text(last_safe_result, limit=8000),
            "usage": usage,
            "last_heartbeat_epoch": time.time(),
        }
        if completion_evidence is not None:
            updates["completion_evidence"] = completion_evidence
        inflight_cleared = bool(clear_inflight and state.get("inflight_action"))
        if clear_inflight:
            updates["inflight_action"] = None
        state = self.update(run_id, **updates)
        self.append_trace(
            run_id,
            "tool_checkpointed",
            inflight_cleared=inflight_cleared,
            completion_evidence_recorded=completion_evidence is not None,
        )
        return state

    @_atomic_store_transition
    def finish(self, run_id: str, status: str, result: str = "", reason: str = "") -> Dict[str, Any]:
        normalized = status if status in TERMINAL_STATUSES | {"paused", "paused_budget", "awaiting_confirmation"} else "error"
        current = self.get(run_id)
        if current.get("revoked") and normalized != "revoked":
            return current
        if (
            normalized == "awaiting_confirmation"
            and str(current.get("status") or "") in {"queued", "running"}
            and current.get("approval")
            and not current.get("stop_requested")
        ):
            self.append_trace(
                run_id,
                "stale_awaiting_confirmation_finish_ignored",
                status=current.get("status"),
            )
            return current
        if current.get("stop_requested") and normalized not in {"stopped", "revoked"}:
            normalized = "stopped"
        is_terminal = normalized in TERMINAL_STATUSES
        inflight = dict(current.get("inflight_action") or {})
        preserve_ambiguous_inflight = (
            bool(inflight) and not inflight.get("replay_safe")
        )
        state = self.update(
            run_id,
            status=normalized,
            last_safe_result=redact_text(result, limit=8000),
            finished_at=utc_timestamp() if is_terminal else "",
            pending_action=None if is_terminal else current.get("pending_action"),
            approval=None if is_terminal else current.get("approval"),
            inflight_action=(
                current.get("inflight_action")
                if preserve_ambiguous_inflight or not is_terminal
                else None
            ),
        )
        self.append_trace(run_id, "run_status", status=normalized, reason=reason, result=result)
        return state

    @_atomic_store_transition
    def request_stop(self, run_id: str) -> Dict[str, Any]:
        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        if state.get("status") in TERMINAL_STATUSES:
            return state
        state = self.update(run_id, stop_requested=True, auto_resume=False, status="stopping")
        self.append_trace(run_id, "stop_requested")
        return state

    @_atomic_store_transition
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

    @_atomic_store_transition
    def pause_for_approval(
        self,
        run_id: str,
        action_name: str,
        fingerprint: str,
        summary: str,
        reason: str,
    ) -> Dict[str, Any]:
        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        if state.get("revoked") or state.get("stop_requested") or state.get("status") in {
            "stopping", "stopped", "completed", "revoked", "error"
        }:
            raise ValueError("A stopped or terminal run cannot request approval.")
        pending = {
            "action": str(action_name or "")[:80],
            "fingerprint": str(fingerprint or "")[:64],
            "summary": redact_text(summary, limit=1000),
            "reason": redact_text(reason, limit=500),
            "requested_at": utc_timestamp(),
            "requested_at_epoch": time.time(),
        }
        state = self.update(run_id, status="awaiting_confirmation", pending_action=pending, approval=None)
        self.append_trace(run_id, "confirmation_required", pending_action=pending)
        return state

    @_atomic_store_transition
    def approve(self, run_id: str, fingerprint: str, ttl_seconds: int = 300) -> Dict[str, Any]:
        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        if state.get("revoked"):
            raise ValueError("A revoked autonomous run cannot be approved.")
        if state.get("stop_requested") or state.get("status") in {
            "stopping", "stopped", "completed", "error"
        }:
            raise ValueError("A stopped or terminal autonomous run cannot be approved.")
        pending = dict(state.get("pending_action") or {})
        supplied = str(fingerprint or "").strip().lower()
        if not supplied or not re.fullmatch(r"[a-f0-9]{64}", supplied):
            raise ValueError("A valid pending action fingerprint is required.")
        if supplied != pending.get("fingerprint"):
            raise ValueError("Approval fingerprint does not match the pending action.")
        try:
            requested_at_epoch = float(pending.get("requested_at_epoch") or 0.0)
        except (TypeError, ValueError, OverflowError):
            requested_at_epoch = 0.0
        now = time.time()
        pending_is_fresh = (
            0 < requested_at_epoch <= now
            and now - requested_at_epoch <= PENDING_APPROVAL_MAX_AGE_SECONDS
        )
        if not pending_is_fresh:
            self.update(run_id, pending_action=None, approval=None, status="paused")
            raise ValueError("The pending browser action expired and must be inspected again.")
        expires_at = now + max(30, min(int(ttl_seconds or 300), 600))
        approval = {
            "fingerprint": supplied,
            "action": pending.get("action"),
            "expires_at_epoch": expires_at,
            "expires_at": utc_timestamp(expires_at),
            "consumed": False,
        }
        state = self.update(run_id, approval=approval, status="paused")
        self.append_trace(run_id, "confirmation_granted", action=pending.get("action"), expires_at=approval["expires_at"])
        return state

    @_atomic_store_transition
    def approve_and_queue(
        self,
        run_id: str,
        fingerprint: str,
        ttl_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Approve one pending fingerprint and queue it as one CAS transition."""

        state = self.approve(run_id, fingerprint, ttl_seconds)
        pending = dict(state.get("pending_action") or {})
        state = self.update(
            run_id,
            current_prompt=(
                "The operator freshly confirmed the exact pending action below. "
                "Reissue that same action only if it is still required for the original "
                "objective; otherwise choose a safer path.\n"
                f"Action: {pending.get('action')}\n"
                f"Fingerprint: {pending.get('fingerprint')}\n"
                f"Summary: {pending.get('summary')}"
            ),
            status="queued",
            auto_resume=True,
            finished_at="",
        )
        self.append_trace(
            run_id,
            "approved_run_queued",
            action=pending.get("action"),
            fingerprint=pending.get("fingerprint"),
        )
        return state

    @_atomic_store_transition
    def queue_for_resume(
        self,
        run_id: str,
        *,
        auto_resume: bool = True,
        budgets: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Queue an explicit resume without racing stop or permanent revocation."""

        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        status = str(state.get("status") or "")
        if state.get("revoked") or status == "revoked":
            raise ValueError("A revoked autonomous run cannot resume.")
        if status == "completed":
            raise ValueError("A completed autonomous run cannot resume.")
        if status in {"running", "stopping"}:
            raise ValueError("An active or stopping autonomous run cannot be queued.")
        inflight = dict(state.get("inflight_action") or {})
        if inflight and not inflight.get("replay_safe"):
            raise ValueError(
                "This run has an ambiguous action outcome; use a fresh inspection or a new run."
            )
        if status == "awaiting_confirmation" and not state.get("approval"):
            raise ValueError("Fresh confirmation is required before this run can resume.")
        updates: Dict[str, Any] = {
            "status": "queued",
            "stop_requested": False,
            "auto_resume": bool(auto_resume),
            "finished_at": "",
        }
        if isinstance(budgets, dict):
            updates["budgets"] = normalize_budgets(
                budgets,
                profile=normalize_autonomy_profile(state.get("autonomy_profile")),
            )
        state = self.update(run_id, **updates)
        self.append_trace(run_id, "run_queued_for_resume", auto_resume=bool(auto_resume))
        return state

    @_atomic_store_transition
    def consume_approval(self, run_id: str, fingerprint: str) -> bool:
        state = self.get(run_id)
        if not state:
            return False
        if (
            state.get("revoked")
            or state.get("stop_requested")
            or str(state.get("status") or "") != "running"
        ):
            return False
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

    @_atomic_store_transition
    def mark_action_started(self, run_id: str, action_name: str, fingerprint: str, summary: str) -> Dict[str, Any]:
        state = self.get(run_id)
        if not state:
            raise KeyError(f"Autonomous run not found: {run_id}")
        status = str(state.get("status") or "")
        if (
            state.get("revoked")
            or state.get("stop_requested")
            or status != "running"
        ):
            raise ValueError(
                "The autonomous run is stopped, revoked, or no longer running; "
                "the proposed action was not dispatched."
            )
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


def required_operator_evidence_reason(
    objective: str,
    skill_ids: Any,
    evidence: Any = None,
    expected_run_id: str = "",
) -> str:
    """Require verified browser evidence for an explicit browser objective."""

    selected = {str(item or "").strip() for item in (skill_ids or [])}
    if "browser-tabs" not in selected:
        return ""
    text = str(objective or "").strip().lower()
    if not text or re.match(
        r"^(?:describe|explain|how|tell\s+me\s+how|what|why)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return ""
    has_target = bool(
        re.search(r"https?://|\b[a-z0-9.-]+\.[a-z]{2,}(?:[/:]\S*)?", text)
        or re.search(r"\b(?:browser|page|site|tab|website|workspace)\b", text)
    )
    interaction_word = _BROWSER_INTERACTION_WORD
    positive_text = re.sub(
        rf"\b(?:do\s+not|don't|never|without)\s+{interaction_word}\b"
        r"[^.;\n]*?(?=\b(?:but|instead)\b|[.;\n]|$)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    interaction_requested = bool(
        re.search(rf"\b{interaction_word}\b", positive_text, flags=re.IGNORECASE)
    )
    inspection_requested = bool(
        re.search(r"\b(?:browse|check|inspect|navigate|open|read|use|view|visit)\b", text)
    )
    if not has_target or not (inspection_requested or interaction_requested):
        return ""

    proof = evidence if isinstance(evidence, dict) else {}
    evidence_source = str(proof.get("browser_source") or "")
    if evidence_source not in {"moltbot", "tab_pilot"}:
        return "The browser objective has no verified browser-source evidence."
    if requires_tab_pilot_evidence(objective) and evidence_source != "tab_pilot":
        return "This objective requires verified Brave Tab Pilot evidence, not server-side Moltbot evidence."
    expected_target = objective_browser_target(objective)
    if expected_target and not browser_target_matches(
        expected_target, str(proof.get("browser_requested_url") or "")
    ):
        return "The browser evidence is not bound to the URL requested by the objective."
    final_url = str(proof.get("browser_final_url") or "")
    if evidence_source == "moltbot" and not (
        str(proof.get("browser_owner_run_id") or "").strip()
        and objective_browser_target(final_url)
    ):
        return "The Moltbot evidence lacks a browser owner or observed final URL."
    if (
        evidence_source == "moltbot"
        and expected_run_id
        and str(proof.get("browser_owner_run_id") or "") != str(expected_run_id)
    ):
        return "The Moltbot evidence belongs to a different autonomous run."
    final_target_allowed = not expected_target or browser_final_target_compatible(
        expected_target, final_url
    )
    normalized_final_target = objective_browser_target(final_url)
    https_downgrade = bool(
        expected_target
        and normalized_final_target
        and urlsplit(expected_target).scheme.lower() == "https"
        and urlsplit(normalized_final_target).scheme.lower() != "https"
    )
    if (
        not final_target_allowed
        and not https_downgrade
        and proof.get("browser_action")
        and str(proof.get("browser_element_risk") or "") == "cross_origin"
    ):
        final_target_allowed = browser_final_target_compatible(
            str(proof.get("browser_element_href") or ""), final_url
        )
    if not final_target_allowed:
        return "The observed browser final URL is unrelated to the requested target."

    snapshot_id = str(proof.get("browser_snapshot_id") or "").strip()
    if interaction_requested and not (
        proof.get("browser_action")
        and snapshot_id
        and str(proof.get("browser_element_id") or "").strip()
        and str(proof.get("browser_verification") or "") == "post_action_inspection"
        and proof.get("browser_state_changed") is True
    ):
        return "The browser objective requires a verified observable browser action, but none has completed."
    if interaction_requested:
        sequence_reason = _browser_action_sequence_reason(
            _expected_browser_actions(objective),
            _browser_action_ledger(proof),
            expected_run_id if evidence_source == "moltbot" else "",
        )
        if sequence_reason:
            return sequence_reason
    if not interaction_requested and not (
        snapshot_id and (proof.get("browser_inspection") or proof.get("browser_action"))
    ):
        return "The browser objective requires a verified browser inspection, but none has completed."
    return ""
