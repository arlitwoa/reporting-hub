"""Cache for Artifact core's per-sprint deploy credit (the dominant cost of velocity baselines).

``deploy_credit_for_sprint`` runs a full sprint query with the changelog expanded. The
quarterly ``squad_velocity`` step and the Sprint Health reports both ask for the same closed
sprints (and ``squad_velocity`` asks twice: once for the quarter's sprints, once for the
baseline window), so the same heavy query runs many times per refresh.

This module wraps that function so that:

* within one process each sprint is computed at most once (in-memory memo), and
* sprints that closed a while ago are also persisted to disk and reused across runs, until the
  entry is older than ``max_age``.

The persisted credit is read from current Jira data (story points are the *current* values), so
entries expire after ``max_age`` rather than living forever. Sprints that closed recently are
never persisted, since late edits are most likely then. The key includes the sprint window and
the configured deploy/terminal statuses, so a config change is a cache miss.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

_KEY_PREFIX = "sprint-credit:v1:"
_WRAPPED_ATTR = "_sprint_credit_cache_wrapped"

DEFAULT_MAX_AGE = timedelta(hours=24)
DEFAULT_MIN_CLOSED_AGE = timedelta(days=7)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class SprintCreditCache:
    def __init__(
        self,
        path: Path | None,
        *,
        max_age: timedelta = DEFAULT_MAX_AGE,
        min_closed_age: timedelta = DEFAULT_MIN_CLOSED_AGE,
    ) -> None:
        self.path = path
        self.max_age = max_age
        self.min_closed_age = min_closed_age
        self._lock = threading.Lock()
        self._memo: dict[tuple[Any, str, str], float] = {}
        self._persisted: dict[str, dict[str, Any]] = self._load()
        self._dirty = False

    # -- persistence ------------------------------------------------------------------
    def _load(self) -> dict[str, dict[str, Any]]:
        if self.path is None or not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            k: v
            for k, v in raw.items()
            if str(k).startswith(_KEY_PREFIX) and isinstance(v, dict)
        }

    def save(self) -> None:
        with self._lock:
            if self.path is None or not self._dirty:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._persisted, separators=(",", ":")), encoding="utf-8")
            self._dirty = False

    # -- keys -------------------------------------------------------------------------
    @staticmethod
    def _config_signature(config: Any) -> str:
        scope_jql = getattr(config, "sprint_scope_jql", None)
        parts = [
            sorted(getattr(config, "deploy_statuses", []) or []),
            sorted(getattr(config, "terminal_statuses", []) or []),
            getattr(config, "story_points_field", ""),
            # Template with a placeholder sprint id, so a change to the scope JQL invalidates.
            scope_jql("{sprint}") if callable(scope_jql) else "",
        ]
        return hashlib.sha1(json.dumps(parts, default=str).encode("utf-8")).hexdigest()[:8]

    def _persist_key(self, sprint: dict, config: Any, now: datetime) -> str | None:
        """Disk-cache key, or None when this sprint must not be persisted."""
        if str(sprint.get("state") or "").lower() != "closed":
            return None
        closed_at = _parse_dt(sprint.get("completeDate")) or _parse_dt(sprint.get("endDate"))
        if closed_at is None or now - closed_at < self.min_closed_age:
            return None
        return (
            f"{_KEY_PREFIX}{sprint.get('id')}:{sprint.get('startDate')}:{sprint.get('endDate')}:"
            f"{self._config_signature(config)}"
        )

    # -- wrapping ---------------------------------------------------------------------
    def wrap(
        self,
        compute: Callable[[Any, dict], float],
        get_config: Callable[[], Any],
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> Callable[[Any, dict], float]:
        def cached(jira: Any, sprint: dict) -> float:
            config = get_config()
            memo_key = (
                sprint.get("id"),
                f"{sprint.get('startDate')}|{sprint.get('endDate')}",
                self._config_signature(config),
            )
            current = now()
            persist_key = self._persist_key(sprint, config, current)
            with self._lock:
                if memo_key in self._memo:
                    return self._memo[memo_key]
                if persist_key is not None:
                    entry = self._persisted.get(persist_key)
                    fetched_at = _parse_dt(entry.get("at")) if entry else None
                    if (
                        entry is not None
                        and fetched_at is not None
                        and current - fetched_at < self.max_age
                        and isinstance(entry.get("credit"), (int, float))
                    ):
                        credit = float(entry["credit"])
                        self._memo[memo_key] = credit
                        return credit
            credit = compute(jira, sprint)
            with self._lock:
                self._memo[memo_key] = credit
                if persist_key is not None:
                    # Replace older entries for the same sprint (e.g. after a config change).
                    stale = f"{_KEY_PREFIX}{sprint.get('id')}:"
                    for old in [k for k in self._persisted if k.startswith(stale)]:
                        del self._persisted[old]
                    self._persisted[persist_key] = {"credit": credit, "at": current.isoformat()}
                    self._dirty = True
            return credit

        setattr(cached, _WRAPPED_ATTR, True)
        return cached


def default_cache_path() -> Path:
    """Shared by every step in a refresh (under the gitignored, CI-cached ``output/``)."""
    return Path(__file__).resolve().parents[2] / "output" / "sprint-credit-cache.json"


def prefetch_sprint_credits(jira: Any, sprints: list[dict], *, workers: int | None = None) -> None:
    """Compute credit for each distinct sprint concurrently, warming the cache/memo.

    Requires :func:`install_sprint_credit_cache` to have run, so results are retained for
    the sequential code that follows.
    """
    from artifact.delivery_health import sprint_engine

    from extensions.twoa_programme.concurrency import map_concurrently

    engine = sys.modules[sprint_engine.baseline_velocity.__module__]
    unique: dict[Any, dict] = {}
    for sprint in sprints:
        unique.setdefault(sprint.get("id"), sprint)
    todo = list(unique.values())
    if not todo:
        return
    print(f"sprint credit: {len(todo)} distinct sprints", flush=True)
    map_concurrently(
        lambda sprint: engine.deploy_credit_for_sprint(jira, sprint),
        todo,
        lambda _sprint, _credit: None,
        workers=workers,
    )


def install_sprint_credit_cache(path: Path | None, **kwargs: Any) -> SprintCreditCache:
    """Wrap ``deploy_credit_for_sprint`` in Artifact core's sprint engine, in place.

    Patching the engine module (rather than only our call sites) is what makes
    ``baseline_velocity`` and the Sprint Health metrics benefit too, since they call it
    through the module namespace. Safe to call more than once; later calls reuse the first
    wrapper's cache.
    """
    from artifact.delivery_health import sprint_engine

    engine = sys.modules[sprint_engine.baseline_velocity.__module__]
    existing = engine.deploy_credit_for_sprint
    if getattr(existing, _WRAPPED_ATTR, False):
        return getattr(existing, "cache")

    cache = SprintCreditCache(path, **kwargs)
    wrapped = cache.wrap(existing, engine._cfg)
    wrapped.cache = cache  # type: ignore[attr-defined]
    engine.deploy_credit_for_sprint = wrapped
    return cache
