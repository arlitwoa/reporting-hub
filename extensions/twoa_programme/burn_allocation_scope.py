"""Scoped Story/Bug counts for in-progress sprint and active release rows."""

from __future__ import annotations

from datetime import date
from typing import Any

from artifact.atlassian import AtlassianAdapter

from extensions.twoa_programme.jira_search import search_all


def sprint_contains(as_of: date, sprint: dict) -> bool:
    start = date.fromisoformat(str(sprint["startDate"])[:10])
    end = date.fromisoformat(str(sprint["endDate"])[:10])
    return start <= as_of <= end


def active_release(releases: list[dict], as_of: date) -> dict | None:
    """Next real (non-projected) in-cycle release on or after as-of."""
    real = [row for row in releases if not row.get("projected")]
    for row in sorted(real, key=lambda item: str(item.get("releaseDate") or "")):
        if date.fromisoformat(str(row["releaseDate"])[:10]) >= as_of:
            return row
    return None


def scope_metrics_from_jira(
    adapter: AtlassianAdapter,
    jql: str,
    *,
    story_points_field: str,
) -> dict[str, Any]:
    issues = search_all(adapter, jql, fields=["key", story_points_field])
    keys: list[str] = []
    total = 0.0
    for issue in issues:
        key = str(issue.get("key") or "")
        if not key:
            continue
        keys.append(key)
        raw_sp = (issue.get("fields") or {}).get(story_points_field)
        if raw_sp is not None:
            total += float(raw_sp)
    return {
        "scopedStoryPoints": round(total, 2),
        "scopedIssueCount": len(keys),
        "scopedIssueKeys": keys,
    }


def enrich_in_progress_scope(
    allocation: dict[str, Any],
    *,
    adapter: AtlassianAdapter,
    global_scope_jql: str,
    global_burn_jql: str,
    story_points_field: str,
    as_of: date,
) -> None:
    """Attach scoped SP/issue counts to the calendar-current sprint and active release."""
    for sprint in allocation.get("sprints") or []:
        if not sprint_contains(as_of, sprint):
            continue
        jql = f"({global_scope_jql}) AND sprint in openSprints()"
        sprint.update(
            inProgress=True,
            **scope_metrics_from_jira(
                adapter,
                jql,
                story_points_field=story_points_field,
            ),
        )

    rel = active_release(allocation.get("inCycleReleases") or [], as_of)
    if not rel:
        return
    fix_version = str(rel.get("name") or "")
    if not fix_version or fix_version.startswith("projected-"):
        return
    jql = f'({global_burn_jql}) AND fixVersion = "{fix_version}"'
    rel.update(
        inProgress=True,
        **scope_metrics_from_jira(
            adapter,
            jql,
            story_points_field=story_points_field,
        ),
    )
