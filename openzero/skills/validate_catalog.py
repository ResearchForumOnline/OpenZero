"""Validate the OpenZero skill catalog using only the Python standard library."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_.-]+$")
PARAMETER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
MANIFEST_KEYS = {
    "schema_version",
    "id",
    "name",
    "description",
    "version",
    "risk_class",
    "risk_summary",
    "summary",
    "triggers",
    "entrypoint",
    "tools",
    "tool_schemas",
    "permissions",
    "budgets",
    "completion",
    "references",
    "limitations",
}
BUDGET_LIMITS = {
    "max_steps": (1, 100),
    "max_tool_calls": (1, 200),
    "max_seconds": (1, 7200),
    "max_output_chars": (100, 100000),
}
KNOWN_TOOLS = {
    "append_file",
    "bash",
    "browse",
    "fetch_url",
    "list_dir",
    "mkdir",
    "moltbot_browse",
    "moltbot_click",
    "moltbot_type",
    "osint",
    "read_file",
    "remove_path",
    "replace_text",
    "scp_get",
    "scp_put",
    "search",
    "skills",
    "speak",
    "ssh_command",
    "tree",
    "web_search",
    "write_file",
    "zip_create",
    "zip_extract",
    "zip_list",
}


def _json(path: Path, errors: List[str]) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{path}: invalid JSON: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path}: root must be an object")
        return {}
    return value


def _frontmatter(path: Path, errors: List[str]) -> Dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"{path}: cannot read: {error}")
        return {}
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        errors.append(f"{path}: missing opening YAML frontmatter marker")
        return {}
    try:
        close = lines.index("---", 1)
    except ValueError:
        errors.append(f"{path}: missing closing YAML frontmatter marker")
        return {}
    metadata: Dict[str, str] = {}
    for line in lines[1:close]:
        if ":" not in line:
            errors.append(f"{path}: invalid frontmatter line: {line}")
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        try:
            value = json.loads(raw_value) if raw_value.startswith('"') else raw_value
        except json.JSONDecodeError:
            errors.append(f"{path}: invalid quoted frontmatter value for {key}")
            continue
        metadata[key] = str(value)
    if set(metadata) != {"name", "description"}:
        errors.append(f"{path}: frontmatter must contain only name and description")
    if len(lines) > 500:
        errors.append(f"{path}: SKILL.md exceeds 500 lines")
    if len(text) > 20000:
        errors.append(f"{path}: SKILL.md exceeds 20,000 characters")
    return metadata


def validate_catalog(root: Path | str | None = None) -> List[str]:
    root_path = Path(root or Path(__file__).resolve().parent).resolve()
    errors: List[str] = []
    index_path = root_path / "catalog.json"
    index = _json(index_path, errors)
    if index.get("schema_version") != 1:
        errors.append(f"{index_path}: schema_version must be 1")

    skill_ids = index.get("skills")
    if not isinstance(skill_ids, list) or not skill_ids:
        errors.append(f"{index_path}: skills must be a non-empty array")
        skill_ids = []
    if len(skill_ids) != len(set(str(item) for item in skill_ids)):
        errors.append(f"{index_path}: skills must not contain duplicates")

    vocabulary = index.get("capability_vocabulary")
    if not isinstance(vocabulary, list) or not vocabulary:
        errors.append(f"{index_path}: capability_vocabulary must be a non-empty array")
        vocabulary = []
    vocabulary_set = set(str(item) for item in vocabulary)
    if vocabulary != sorted(vocabulary_set):
        errors.append(f"{index_path}: capability_vocabulary must be unique and sorted")
    for capability in vocabulary_set:
        if not CAPABILITY_RE.fullmatch(capability):
            errors.append(f"{index_path}: invalid capability name: {capability}")

    for skill_id_value in skill_ids:
        skill_id = str(skill_id_value)
        if not ID_RE.fullmatch(skill_id):
            errors.append(f"{index_path}: invalid skill id: {skill_id}")
            continue
        skill_root = (root_path / skill_id).resolve()
        try:
            skill_root.relative_to(root_path)
        except ValueError:
            errors.append(f"{index_path}: skill path escapes catalog root: {skill_id}")
            continue
        manifest_path = skill_root / "manifest.json"
        manifest = _json(manifest_path, errors)
        unknown = set(manifest) - MANIFEST_KEYS
        missing = MANIFEST_KEYS - set(manifest)
        if unknown:
            errors.append(f"{manifest_path}: unknown keys: {', '.join(sorted(unknown))}")
        if missing:
            errors.append(f"{manifest_path}: missing keys: {', '.join(sorted(missing))}")
        if manifest.get("schema_version") != 1:
            errors.append(f"{manifest_path}: schema_version must be 1")
        if manifest.get("id") != skill_id:
            errors.append(f"{manifest_path}: id must match folder name {skill_id}")
        if not isinstance(manifest.get("name"), str) or not str(manifest.get("name")).strip():
            errors.append(f"{manifest_path}: name must be a non-empty string")
        if not isinstance(manifest.get("description"), str) or not str(manifest.get("description")).strip():
            errors.append(f"{manifest_path}: description must be a non-empty string")
        if len(str(manifest.get("summary") or "")) > 240:
            errors.append(f"{manifest_path}: summary exceeds 240 characters")
        if manifest.get("risk_class") not in {"low", "medium", "high"}:
            errors.append(f"{manifest_path}: risk_class must be low, medium, or high")
        if not isinstance(manifest.get("risk_summary"), str) or not str(manifest.get("risk_summary")).strip():
            errors.append(f"{manifest_path}: risk_summary must be a non-empty string")
        elif len(str(manifest.get("risk_summary"))) > 240:
            errors.append(f"{manifest_path}: risk_summary exceeds 240 characters")

        for field in ("triggers", "tools", "references", "limitations"):
            value = manifest.get(field)
            if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
                errors.append(f"{manifest_path}: {field} must be an array of non-empty strings")
            elif len(value) != len(set(value)):
                errors.append(f"{manifest_path}: {field} must not contain duplicates")
        unknown_tools = set(manifest.get("tools") or []) - KNOWN_TOOLS
        if unknown_tools:
            errors.append(f"{manifest_path}: unknown tools: {', '.join(sorted(unknown_tools))}")
        schemas = manifest.get("tool_schemas")
        if not isinstance(schemas, list) or not schemas:
            errors.append(f"{manifest_path}: tool_schemas must be a non-empty array")
            schemas = []
        for schema in schemas:
            if not isinstance(schema, dict) or set(schema) != {"action", "required", "optional"}:
                errors.append(f"{manifest_path}: every tool schema must contain action, required, and optional")
                continue
            if schema.get("action") not in (manifest.get("tools") or []):
                errors.append(f"{manifest_path}: tool schema action is not declared in tools: {schema.get('action')}")
            for field in ("required", "optional"):
                parameters = schema.get(field)
                if not isinstance(parameters, list) or any(
                    not isinstance(item, str) or not item.strip() for item in parameters
                ):
                    errors.append(f"{manifest_path}: tool schema {field} must be a string array")
                elif len(parameters) != len(set(parameters)):
                    errors.append(f"{manifest_path}: tool schema {field} must not contain duplicates")
                elif any(not PARAMETER_RE.fullmatch(item) for item in parameters):
                    errors.append(f"{manifest_path}: tool schema {field} contains an invalid parameter name")
            if isinstance(schema.get("required"), list) and isinstance(schema.get("optional"), list):
                overlap = set(schema["required"]) & set(schema["optional"])
                if overlap:
                    errors.append(
                        f"{manifest_path}: tool schema parameters cannot be both required and optional: "
                        f"{', '.join(sorted(overlap))}"
                    )

        entrypoint = str(manifest.get("entrypoint") or "")
        if entrypoint != "SKILL.md":
            errors.append(f"{manifest_path}: entrypoint must be SKILL.md")
        skill_path = skill_root / "SKILL.md"
        metadata = _frontmatter(skill_path, errors)
        if metadata.get("name") != skill_id:
            errors.append(f"{skill_path}: frontmatter name must equal {skill_id}")
        if metadata.get("description") != manifest.get("description"):
            errors.append(f"{skill_path}: frontmatter description must match manifest description")

        permissions = manifest.get("permissions")
        if not isinstance(permissions, dict) or set(permissions) != {"allow", "task_scoped", "confirm"}:
            errors.append(f"{manifest_path}: permissions must contain allow, task_scoped, and confirm")
            permissions = {}
        permission_sets = []
        for bucket in ("allow", "task_scoped", "confirm"):
            values = permissions.get(bucket)
            if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                errors.append(f"{manifest_path}: permissions.{bucket} must be a string array")
                values = []
            unknown_caps = set(values) - vocabulary_set
            if unknown_caps:
                errors.append(f"{manifest_path}: unknown capabilities: {', '.join(sorted(unknown_caps))}")
            permission_sets.append(set(values))
        if any(permission_sets[i] & permission_sets[j] for i in range(3) for j in range(i + 1, 3)):
            errors.append(f"{manifest_path}: permission buckets must be disjoint")

        budgets = manifest.get("budgets")
        if not isinstance(budgets, dict) or set(budgets) != set(BUDGET_LIMITS):
            errors.append(f"{manifest_path}: budgets must contain exactly {', '.join(BUDGET_LIMITS)}")
            budgets = {}
        for field, (minimum, maximum) in BUDGET_LIMITS.items():
            value = budgets.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
                errors.append(f"{manifest_path}: {field} must be an integer from {minimum} to {maximum}")

        completion = manifest.get("completion")
        if not isinstance(completion, dict) or set(completion) != {"required_evidence", "stop_when"}:
            errors.append(f"{manifest_path}: completion must contain required_evidence and stop_when")
        else:
            for field in ("required_evidence", "stop_when"):
                if not isinstance(completion[field], list) or not completion[field]:
                    errors.append(f"{manifest_path}: completion.{field} must be a non-empty array")

        try:
            skill_text = skill_path.read_text(encoding="utf-8")
        except OSError:
            skill_text = ""
        for relative in manifest.get("references") or []:
            reference_path = (skill_root / relative).resolve()
            try:
                reference_path.relative_to(skill_root)
            except ValueError:
                errors.append(f"{manifest_path}: reference escapes skill root: {relative}")
                continue
            if not relative.startswith("references/") or Path(relative).suffix.lower() != ".md":
                errors.append(f"{manifest_path}: references must be one-level Markdown files under references/: {relative}")
            if len(Path(relative).parts) != 2:
                errors.append(f"{manifest_path}: references must be one level deep: {relative}")
            if not reference_path.is_file():
                errors.append(f"{manifest_path}: missing reference: {relative}")
            if f"]({relative})" not in skill_text:
                errors.append(f"{skill_path}: must directly link declared reference {relative}")
    return sorted(set(errors))


def main(argv: List[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    root = Path(args[0]).resolve() if args else Path(__file__).resolve().parent
    errors = validate_catalog(root)
    if errors:
        print(json.dumps({"status": "error", "errors": errors}, indent=2))
        return 1
    index = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    print(json.dumps({"status": "ok", "schema_version": 1, "skills": index["skills"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
