"""Fail-closed compatibility shim for the retired legacy shell executor.

OpenZero's governed operator runtime lives in :mod:`brain.autonomous_runtime`
and requires a fresh, exact-action approval for raw shell execution.  Older
releases exposed helpers from this module that executed arbitrary strings and
attempted privilege escalation.  Those helpers are intentionally retained only
as non-executing stubs so an old import cannot silently restore that behavior.
"""

from __future__ import annotations


LEGACY_EXECUTION_DISABLED = (
    "Legacy direct command execution is disabled. Use the governed OpenZero "
    "operator runtime, which applies policy and exact-action confirmation."
)


def execute_bash(command: str):
    """Refuse legacy shell execution while preserving the old return shape."""

    del command
    return f"[BLOCKED] {LEGACY_EXECUTION_DISABLED}", 126


def execute_persistent(session_name: str, command: str):
    """Refuse legacy background execution while preserving compatibility."""

    del session_name, command
    return f"[BLOCKED] {LEGACY_EXECUTION_DISABLED}", 126
