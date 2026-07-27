"""Deterministic, progressively disclosed OpenZero skill catalog.

Catalog metadata is cheap to load. Full SKILL.md instructions and references are
only read after a skill is selected.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


CATALOG_ROOT = Path(__file__).resolve().parent
TOKEN_RE = re.compile(r"[a-z0-9]+")

TOOL_CAPABILITIES = {
    "list_dir": ("filesystem.read",),
    "tree": ("filesystem.read",),
    "read_file": ("filesystem.read",),
    "search": ("filesystem.read",),
    "write_file": ("filesystem.write",),
    "append_file": ("filesystem.write",),
    "replace_text": ("filesystem.write",),
    "mkdir": ("filesystem.write",),
    "remove_path": ("destructive.delete",),
    "zip_list": ("archive.read", "filesystem.read"),
    "zip_extract": ("archive.read", "archive.write", "filesystem.write"),
    "zip_create": ("archive.write", "filesystem.read", "filesystem.write"),
    "fetch_url": ("network.read",),
    "web_search": ("network.read",),
    "moltbot_browse": ("browser.inspect", "network.read"),
    "ssh_command": ("remote.read",),
    "scp_get": ("filesystem.write", "remote.read"),
    "scp_put": ("filesystem.read", "remote.write"),
    "bash": ("process.run",),
    "osint": ("network.read",),
    "browse": ("browser.inspect", "network.read"),
    "speak": ("voice.output",),
    "skills": (),
}

TASK_SCOPE_TERMS = {
    "filesystem.write": {
        "add",
        "build",
        "change",
        "create",
        "copy",
        "download",
        "edit",
        "fix",
        "generate",
        "implement",
        "make",
        "patch",
        "rename",
        "save",
        "update",
        "write",
    },
    "archive.write": {"archive", "backup", "bundle", "extract", "package", "unzip", "zip"},
    "process.run": {
        "build",
        "check",
        "deploy",
        "diagnose",
        "fix",
        "install",
        "run",
        "setup",
        "test",
        "update",
        "verify",
    },
    "remote.write": {
        "change",
        "configure",
        "copy",
        "deploy",
        "fix",
        "install",
        "patch",
        "restart",
        "setup",
        "update",
        "upload",
    },
    "remote.restart": {"reload", "restart", "start", "stop"},
    "browser.navigate": {"browse", "navigate", "open", "visit"},
    "browser.interact": {"choose", "click", "fill", "select", "type"},
    "browser.type_nonsensitive": {"fill", "input", "type", "write"},
    "document.convert": {"convert", "extract", "read", "summarize"},
    "voice.output": {"read aloud", "say", "speak", "voice"},
}


class CatalogError(RuntimeError):
    """Raised for malformed or unsafe catalog access."""


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError(f"Could not load {path}: {error}") from error
    if not isinstance(payload, dict):
        raise CatalogError(f"Expected a JSON object in {path}.")
    return payload


def _catalog_root(root: Path | str | None = None) -> Path:
    return Path(root or CATALOG_ROOT).resolve()


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise CatalogError(f"Catalog path escapes its root: {relative}") from error
    return candidate


def load_catalog(root: Path | str | None = None) -> Dict[str, Any]:
    """Load ordered manifest metadata without loading skill instructions."""

    catalog_root = _catalog_root(root)
    index = _read_json(catalog_root / "catalog.json")
    skills: List[Dict[str, Any]] = []
    for skill_id in index.get("skills", []):
        manifest_path = _safe_child(catalog_root, f"{skill_id}/manifest.json")
        manifest = _read_json(manifest_path)
        item = dict(manifest)
        item["_catalog_order"] = len(skills)
        skills.append(item)
    return {
        "schema_version": index.get("schema_version"),
        "permission_model": dict(index.get("permission_model") or {}),
        "capability_vocabulary": list(index.get("capability_vocabulary") or []),
        "skills": skills,
    }


def _tokens(value: str) -> set[str]:
    tokens = set(TOKEN_RE.findall(str(value or "").lower()))
    tokens.update(token[:-1] for token in list(tokens) if len(token) > 4 and token.endswith("s"))
    return tokens


def _search_score(skill: Mapping[str, Any], query: str) -> int:
    query_clean = str(query or "").strip().lower()
    if not query_clean:
        return 1
    query_tokens = _tokens(query_clean)
    skill_id = str(skill.get("id") or "").lower()
    name = str(skill.get("name") or "").lower()
    triggers = " ".join(str(item) for item in skill.get("triggers") or []).lower()
    summary = f"{skill.get('summary', '')} {skill.get('description', '')}".lower()
    score = 0
    if query_clean == skill_id or query_clean == name:
        score += 100
    if query_clean in skill_id or query_clean in name:
        score += 30
    score += 12 * len(query_tokens & _tokens(f"{skill_id} {name}"))
    score += 6 * len(query_tokens & _tokens(triggers))
    score += 2 * len(query_tokens & _tokens(summary))
    return score


def search_catalog(query: str = "", limit: int = 8, root: Path | str | None = None) -> List[Dict[str, Any]]:
    """Return stable, relevance-ranked manifest metadata."""

    limit = max(1, min(int(limit or 8), 20))
    skills = load_catalog(root)["skills"]
    ranked = [(_search_score(skill, query), int(skill["_catalog_order"]), skill) for skill in skills]
    if str(query or "").strip():
        ranked = [row for row in ranked if row[0] > 0]
    ranked.sort(key=lambda row: (-row[0], row[1], str(row[2].get("id") or "")))
    return [dict(row[2]) for row in ranked[:limit]]


def select_skill_ids(query: str, limit: int = 2, root: Path | str | None = None) -> List[str]:
    return [str(item["id"]) for item in search_catalog(query, limit=limit, root=root)]


def get_skill_detail(
    skill_id: str,
    references: Sequence[str] | None = None,
    root: Path | str | None = None,
) -> Dict[str, Any]:
    """Load one skill body and only explicitly requested references."""

    catalog_root = _catalog_root(root)
    manifests = {str(item["id"]): item for item in load_catalog(catalog_root)["skills"]}
    if skill_id not in manifests:
        raise CatalogError(f"Unknown skill: {skill_id}")
    manifest = dict(manifests[skill_id])
    skill_root = _safe_child(catalog_root, skill_id)
    entrypoint = str(manifest.get("entrypoint") or "SKILL.md")
    instructions_path = _safe_child(skill_root, entrypoint)
    try:
        instructions = instructions_path.read_text(encoding="utf-8")
    except OSError as error:
        raise CatalogError(f"Could not read {skill_id} instructions: {error}") from error

    allowed_references = set(str(item) for item in manifest.get("references") or [])
    loaded_references: Dict[str, str] = {}
    for relative in references or []:
        if relative not in allowed_references:
            raise CatalogError(f"Reference is not declared by {skill_id}: {relative}")
        reference_path = _safe_child(skill_root, relative)
        try:
            loaded_references[relative] = reference_path.read_text(encoding="utf-8")
        except OSError as error:
            raise CatalogError(f"Could not read {skill_id}/{relative}: {error}") from error
    manifest.pop("_catalog_order", None)
    return {
        **manifest,
        "instructions": instructions,
        "loaded_references": loaded_references,
    }


def _public_manifest(skill: Mapping[str, Any]) -> Dict[str, Any]:
    item = {key: value for key, value in skill.items() if not key.startswith("_")}
    return item


def skill_catalog_payload(query: str = "", limit: int = 8, root: Path | str | None = None) -> Dict[str, Any]:
    items = [_public_manifest(item) for item in search_catalog(query, limit=limit, root=root)]
    return {
        "status": "success",
        "schema_version": 1,
        "skills": items,
        "count": len(items),
        "progressive_disclosure": "Use a skill id to load its SKILL.md; references load only when requested.",
    }


def compact_catalog_text(query: str = "", limit: int = 8, root: Path | str | None = None) -> str:
    lines = []
    for item in search_catalog(query, limit=limit, root=root):
        permissions = item.get("permissions") or {}
        budgets = item.get("budgets") or {}
        confirm = ",".join(permissions.get("confirm") or []) or "none"
        lines.append(
            f"- {item['name']} [{item['id']}]: {item['summary']} "
            f"risk={item.get('risk_class')}; "
            f"tools={','.join(item.get('tools') or [])}; "
            f"budget={budgets.get('max_steps')} steps/{budgets.get('max_seconds')}s; "
            f"confirm={confirm}"
        )
    return "\n".join(lines)


def runtime_skill_context(skill_ids: Iterable[str], root: Path | str | None = None) -> str:
    """Load concise selected guidance while leaving references undisclosed."""

    blocks = []
    for skill_id in skill_ids:
        detail = get_skill_detail(str(skill_id), root=root)
        permissions = detail.get("permissions") or {}
        budgets = detail.get("budgets") or {}
        blocks.append(
            f"[SKILL {detail['id']}]\n"
            f"Risk: {detail.get('risk_class')} — {detail.get('risk_summary')}\n"
            f"Budget: {budgets.get('max_steps')} steps, {budgets.get('max_tool_calls')} tool calls, "
            f"{budgets.get('max_seconds')} seconds.\n"
            f"Allowed: {', '.join(permissions.get('allow') or []) or 'none'}.\n"
            f"Task-scoped: {', '.join(permissions.get('task_scoped') or []) or 'none'}.\n"
            f"Fresh confirmation: {', '.join(permissions.get('confirm') or []) or 'none'}.\n"
            f"{detail['instructions']}"
        )
    return "\n\n".join(blocks)


def runtime_skill_budgets(
    skill_ids: Sequence[str],
    requested: Mapping[str, Any] | None = None,
    root: Path | str | None = None,
) -> Dict[str, int]:
    """Translate skill limits into autonomous-runtime budgets and clamp requests."""

    manifests = {str(item["id"]): item for item in load_catalog(root)["skills"]}
    selected = [manifests[item] for item in skill_ids if item in manifests]
    if selected:
        limits = {
            "max_steps": min(int(item["budgets"]["max_steps"]) for item in selected),
            "max_model_calls": min(int(item["budgets"]["max_steps"]) for item in selected),
            "max_tool_calls": min(int(item["budgets"]["max_tool_calls"]) for item in selected),
            "max_elapsed_seconds": min(int(item["budgets"]["max_seconds"]) for item in selected),
            "max_consecutive_errors": 3,
        }
    else:
        limits = {
            "max_steps": 4,
            "max_model_calls": 4,
            "max_tool_calls": 3,
            "max_elapsed_seconds": 180,
            "max_consecutive_errors": 2,
        }
    supplied = requested if isinstance(requested, Mapping) else {}
    result: Dict[str, int] = {}
    for key, limit in limits.items():
        try:
            value = int(supplied.get(key, limit))
        except (TypeError, ValueError):
            value = limit
        result[key] = max(1, min(value, limit))
    return result


def legacy_skill_catalog(root: Path | str | None = None) -> List[Dict[str, str]]:
    """Return the old app.py catalog shape for compatibility."""

    items = []
    for skill in load_catalog(root)["skills"]:
        schemas = skill.get("tool_schemas") or []
        primary = schemas[0] if schemas else {}
        required = ", ".join(str(item) for item in primary.get("required") or [])
        optional = ", ".join(str(item) for item in primary.get("optional") or [])
        schema_summary = str(primary.get("action") or "skills")
        if required:
            schema_summary += f"(required: {required}"
            schema_summary += f"; optional: {optional})" if optional else ")"
        items.append(
            {
                "id": str(skill["id"]),
                "name": str(skill["name"]),
                "triggers": ", ".join(str(item) for item in skill.get("triggers") or []),
                "tool": schema_summary,
                "notes": str(skill.get("summary") or skill.get("description") or ""),
            }
        )
    return items


def permission_decision(
    skill: Mapping[str, Any],
    capability: str,
    task_authorized: bool = False,
) -> Dict[str, str]:
    permissions = skill.get("permissions") or {}
    if capability in (permissions.get("confirm") or []):
        return {"decision": "confirm", "reason": f"{capability} requires fresh human confirmation."}
    if capability in (permissions.get("task_scoped") or []):
        if task_authorized:
            return {"decision": "allow", "reason": f"{capability} is authorized by the current task."}
        return {"decision": "confirm", "reason": f"The current task did not clearly authorize {capability}."}
    if capability in (permissions.get("allow") or []):
        return {"decision": "allow", "reason": f"{capability} is read-only or locally bounded for this skill."}
    return {"decision": "deny", "reason": f"{capability} is not granted to this skill."}


def _task_authorizes(task_text: str, capability: str) -> bool:
    text = str(task_text or "").lower()
    return any(term in text for term in TASK_SCOPE_TERMS.get(capability, set()))


def _ssh_capability(payload: Mapping[str, Any]) -> str:
    command = str(payload.get("command") or "").strip().lower()
    read_prefixes = (
        "cat ",
        "df ",
        "docker ps",
        "du ",
        "find ",
        "free ",
        "git diff",
        "git log",
        "git status",
        "head ",
        "journalctl ",
        "ls",
        "pm2 list",
        "pm2 status",
        "ps ",
        "pwd",
        "stat ",
        "systemctl is-",
        "systemctl status",
        "tail ",
        "uname",
        "uptime",
        "whoami",
    )
    if command and command.startswith(read_prefixes) and not re.search(r"[>|;&]|\brm\b|\bmv\b|\btee\b", command):
        return "remote.read"
    return "remote.write"


def tool_permission_decision(
    skill_ids: Sequence[str],
    action: str,
    payload: Mapping[str, Any] | None,
    task_text: str,
    root: Path | str | None = None,
) -> Dict[str, str]:
    action_name = str(action or "").strip().lower()
    capabilities = (
        (_ssh_capability(payload or {}),)
        if action_name == "ssh_command"
        else TOOL_CAPABILITIES.get(action_name)
    )
    if capabilities is None:
        return {"decision": "deny", "reason": f"No capability mapping exists for tool action {action_name}."}
    if not capabilities:
        return {
            "decision": "allow",
            "reason": "Catalog discovery is read-only.",
            "capability": "",
            "capabilities": "",
        }

    manifests = {str(item["id"]): item for item in load_catalog(root)["skills"]}
    candidates = [manifests[item] for item in skill_ids if item in manifests and action_name in (manifests[item].get("tools") or [])]
    if not candidates:
        return {
            "decision": "deny",
            "reason": f"No selected skill grants the {action_name} tool.",
            "capability": ",".join(capabilities),
            "capabilities": ",".join(capabilities),
        }

    per_skill = []
    for skill in candidates:
        outcomes = [
            permission_decision(skill, capability, task_authorized=_task_authorizes(task_text, capability))
            for capability in capabilities
        ]
        if any(outcome["decision"] == "deny" for outcome in outcomes):
            decision = "deny"
        elif any(outcome["decision"] == "confirm" for outcome in outcomes):
            decision = "confirm"
        else:
            decision = "allow"
        per_skill.append((decision, outcomes))

    for wanted in ("allow", "confirm", "deny"):
        for decision, outcomes in per_skill:
            if decision == wanted:
                reasons = " ".join(outcome["reason"] for outcome in outcomes)
                joined = ",".join(capabilities)
                return {
                    "decision": decision,
                    "reason": reasons,
                    "capability": joined,
                    "capabilities": joined,
                }
    joined = ",".join(capabilities)
    return {"decision": "deny", "reason": "No permission decision was available.", "capability": joined, "capabilities": joined}


def budget_decision(skill_ids: Sequence[str], usage: Mapping[str, int | float], root: Path | str | None = None) -> Dict[str, str]:
    manifests = {str(item["id"]): item for item in load_catalog(root)["skills"]}
    selected = [manifests[item] for item in skill_ids if item in manifests]
    if not selected:
        return {"decision": "stop", "reason": "No valid skill was selected."}
    checks = (
        ("steps", "max_steps"),
        ("tool_calls", "max_tool_calls"),
        ("elapsed_seconds", "max_seconds"),
        ("output_chars", "max_output_chars"),
    )
    for used_key, limit_key in checks:
        limit = min(int((item.get("budgets") or {}).get(limit_key) or 0) for item in selected)
        used = float(usage.get(used_key) or 0)
        if limit <= 0 or used >= limit:
            return {"decision": "stop", "reason": f"Skill budget reached: {used_key}={used:g}, limit={limit}."}
    return {"decision": "continue", "reason": "Skill budget remains."}
