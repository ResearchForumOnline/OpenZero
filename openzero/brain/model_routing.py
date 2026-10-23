"""Explicit local/cloud model selection shared by panel and standalone CLI.

A model's family name or a slash in an Ollama alias is not permission to send
the prompt to a cloud service. Unknown model names stay on the local route.
"""
from typing import Mapping

CLOUD_MODEL_NAMES = frozenset({
    "groq/compound", "groq/compound-large", "openai/gpt-oss-120b",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "llama-3.3-70b-versatile", "qwen/qwen3-32b",
})


def select_model_route(mode: str, model: str) -> str:
    mode = str(mode or "local").strip().lower()
    if mode == "cloud":
        return "cloud"
    if mode == "hybrid" and str(model or "").strip().lower() in CLOUD_MODEL_NAMES:
        return "cloud"
    return "local"


def cloud_model_for(model: str) -> str:
    normalized = str(model or "").strip().lower()
    return normalized if normalized in CLOUD_MODEL_NAMES else "groq/compound-large"


def automatic_repair_allowed(config: Mapping[str, str]) -> bool:
    value = str(config.get("OLLAMA_AUTO_REPAIR_ENABLED", "true")).strip().lower()
    return value in {"1", "true", "yes", "on", "enabled"}
