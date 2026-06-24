"""Unified Jira binding resolution for TWoA programme extensions."""

from __future__ import annotations

import os
from pathlib import Path

from artifact.jira_binding import JiraBinding

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_BINDING = _REPO_ROOT / "config" / "jira-binding.json"


class JiraBindingLoadError(RuntimeError):
    """Raised when jira-binding.json cannot be loaded or parsed."""


def _profiles_dir() -> Path | None:
    configured = os.environ.get("ARTIFACT_PROFILES_DIR", "").strip()
    if not configured:
        return None
    return Path(configured)


def resolve_binding_path(path: Path | None = None) -> Path | None:
    """
    Return the first existing jira-binding.json using documented resolution order:

    1. Explicit path argument
    2. ARTIFACT_PROFILES_DIR/jira-binding.json
    3. Repository config/jira-binding.json
    """
    if path is not None:
        return path if path.is_file() else None
    profiles = _profiles_dir()
    if profiles is not None:
        candidate = profiles / "jira-binding.json"
        if candidate.is_file():
            return candidate
    if _DEFAULT_BINDING.is_file():
        return _DEFAULT_BINDING
    return None


def load_jira_binding(path: Path | None = None) -> JiraBinding:
    """Load Jira binding; raise JiraBindingLoadError when missing or invalid."""
    resolved = resolve_binding_path(path)
    if resolved is None:
        raise JiraBindingLoadError(
            "jira-binding.json not found. Set ARTIFACT_PROFILES_DIR or add config/jira-binding.json."
        )
    try:
        return JiraBinding.from_file(resolved)
    except Exception as exc:
        raise JiraBindingLoadError(f"Failed to parse {resolved}: {exc}") from exc


def try_load_jira_binding(path: Path | None = None) -> JiraBinding | None:
    """
    Load binding when a file exists; return None when no file is configured.

    Parse failures still raise JiraBindingLoadError so CI and strict runs fail loud.
    """
    resolved = resolve_binding_path(path)
    if resolved is None:
        return None
    try:
        return JiraBinding.from_file(resolved)
    except Exception as exc:
        raise JiraBindingLoadError(f"Failed to parse {resolved}: {exc}") from exc
