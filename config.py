"""
Infrastructure configuration for Candidate-Market Fit Engine.

Handles: paths, endpoints, model settings, tuning.yaml loading.
All scoring parameters live in tuning.yaml — this file is plumbing only.
"""
from pathlib import Path
from typing import Any

import yaml


# --- Paths ---
APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
AGENTS_DIR = APP_DIR / "agents"
MATCHING_DIR = APP_DIR / "matching"
TUNING_FILE = APP_DIR / "tuning.yaml"

# Workspace root (Babson Claude Code/)
WORKSPACE_ROOT = APP_DIR.parent.parent.parent


# --- Ollama ---
OLLAMA_ENDPOINT = "http://localhost:11434"
OLLAMA_TIMEOUT = 180  # seconds; reasoning tasks can be slow


# --- Tuning config loader ---
_tuning_cache: dict[str, Any] | None = None


def load_tuning(reload: bool = False) -> dict[str, Any]:
    """Load tuning.yaml. Cached after first call unless reload=True."""
    global _tuning_cache
    if _tuning_cache is not None and not reload:
        return _tuning_cache
    with open(TUNING_FILE, "r", encoding="utf-8") as f:
        _tuning_cache = yaml.safe_load(f)
    return _tuning_cache


def get_tuning(section: str, key: str | None = None) -> Any:
    """Get a tuning parameter. Examples:
        get_tuning("skill_extraction", "onet_match_threshold") -> 0.70
        get_tuning("models") -> full models dict
    """
    cfg = load_tuning()
    section_data = cfg.get(section, {})
    if key is None:
        return section_data
    return section_data.get(key)


# --- Convenience accessors ---
def extraction_model() -> str:
    return get_tuning("models", "extraction_model")


def reasoning_model() -> str:
    return get_tuning("models", "reasoning_model")


def embedding_model() -> str:
    return get_tuning("models", "embedding_model")


def extraction_options(extra: dict | None = None) -> dict:
    """Standard Ollama options for extraction-tier calls (includes num_ctx)."""
    opts = {
        "temperature": get_tuning("models", "extraction_temperature") or 0.1,
        "num_ctx": get_tuning("models", "extraction_context_window") or 16384,
    }
    if extra:
        opts.update(extra)
    return opts


def reasoning_options(extra: dict | None = None) -> dict:
    """Standard Ollama options for reasoning-tier calls (includes num_ctx)."""
    opts = {
        "temperature": get_tuning("models", "reasoning_temperature") or 0.3,
        "num_ctx": get_tuning("models", "reasoning_context_window") or 16384,
    }
    if extra:
        opts.update(extra)
    return opts
