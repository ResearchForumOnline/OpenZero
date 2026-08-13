"""Retired compatibility surface for OpenZero's legacy XML command loop.

This module deliberately performs no model call, command parsing, or process
execution.  Current autonomous work must enter through the governed runtime in
``brain.autonomous_runtime`` so policy, bounded budgets, durable checkpoints,
and exact-action confirmation cannot be bypassed by an old import.
"""

from __future__ import annotations

from .shell_core import LEGACY_EXECUTION_DISABLED


def call_llm(prompt: str) -> str:
    """Return a fail-closed response instead of invoking the retired loop."""

    del prompt
    return f"[BLOCKED] {LEGACY_EXECUTION_DISABLED}"


def process_agent_logic(user_input: str, history: str = "") -> str:
    """Refuse the retired model-output-to-command execution path."""

    del user_input, history
    return f"[BLOCKED] {LEGACY_EXECUTION_DISABLED}"
