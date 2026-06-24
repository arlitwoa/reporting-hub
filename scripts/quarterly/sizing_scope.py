"""Scope sizing analyses to Story, Spike, and Bug children only."""
from __future__ import annotations

from typing import Any

SCOPE_TYPES = frozenset({"Story", "Spike", "Bug"})
EXCLUDED_STATUSES = frozenset({"Rejected"})
SCOPE_NOTE = (
    "<strong>Scope:</strong> Story, Spike, and Bug issue types only "
    "(excludes Task, Test, Sub-task, Buglet, etc.; Rejected status omitted)."
)


def scope_type_jql() -> str:
    return "issuetype in (Story, Spike, Bug)"


def scope_child_jql(parent_key: str, extra: str = "") -> str:
    base = f'parent = {parent_key} AND {scope_type_jql()}'
    if extra:
        return f"{base} AND {extra}"
    return base


def scope_initiative_jql(initiative_key: str, extra: str = "") -> str:
    base = f"parent in childIssuesOf({initiative_key}) AND {scope_type_jql()}"
    if extra:
        return f"{base} AND {extra}"
    return base


def _metrics(children: list[dict[str, Any]]) -> dict[str, Any]:
    child_count = len(children)
    missing = sum(1 for c in children if c.get("story_points") is None)
    total_sp = sum(float(c["story_points"]) for c in children if c.get("story_points") is not None)
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for c in children:
        st = c.get("status") or "Unknown"
        ty = c.get("type") or "Unknown"
        by_status[st] = by_status.get(st, 0) + 1
        by_type[ty] = by_type.get(ty, 0) + 1
    return {
        "child_count": child_count,
        "total_in_jira": child_count,
        "missing_story_points": missing,
        "total_story_points": total_sp,
        "by_status": by_status,
        "by_type": by_type,
        "children": children,
    }


def rescope_epic(epic: dict[str, Any]) -> dict[str, Any]:
    children = [
        c
        for c in (epic.get("children") or [])
        if c.get("type") in SCOPE_TYPES and (c.get("status") or "") not in EXCLUDED_STATUSES
    ]
    out = dict(epic)
    out.update(_metrics(children))
    return out


def apply_scope(data: dict[str, Any]) -> dict[str, Any]:
    epics = [rescope_epic(e) for e in data.get("epics") or []]
    total_children = sum(int(e.get("child_count") or 0) for e in epics)
    missing_sp = sum(int(e.get("missing_story_points") or 0) for e in epics)
    total_sp = sum(float(e.get("total_story_points") or 0) for e in epics)
    return {
        **data,
        "scope_issue_types": sorted(SCOPE_TYPES),
        "epics": epics,
        "total_epics": len(epics),
        "total_children": total_children,
        "total_in_jira": total_children,
        "missing_story_points": missing_sp,
        "total_story_points": total_sp,
    }
