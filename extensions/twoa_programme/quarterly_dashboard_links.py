"""Jira links and numeric formatting for quarterly dashboard."""

from __future__ import annotations

import html
from urllib.parse import quote

from extensions.twoa_programme.quarterly_dashboard_constants import JIRA_SERVER
from extensions.twoa_programme.quarterly_dashboard_constants import _sanitize_atlassian_text

def _fmt_num(value: float | int | None, *, digits: int = 1) -> str:
    if value is None:
        return "&mdash;"
    return f"{float(value):.{digits}f}"


def _jira_search_url(jql: str) -> str:
    return f"{JIRA_SERVER}/issues/?jql={quote(jql, safe='')}"


def _jql_link(jql: str, label: str) -> str:
    return (
        f'<a href="{_jira_search_url(jql)}" target="_blank" rel="noopener">'
        f"{html.escape(label)}</a>"
    )


def _filter_link(filter_name: str, label: str | None = None) -> str:
    return _jql_link(f"filter = {filter_name}", label or filter_name)


def _browse_link(key: str, label: str | None = None) -> str:
    text = label or key
    return (
        f'<a href="{JIRA_SERVER}/browse/{html.escape(key)}" '
        f'target="_blank" rel="noopener">{html.escape(text)}</a>'
    )


def _fix_version_link(fix_version: str, label: str | None = None) -> str:
    text = label or fix_version
    jql = f'project = EPCE AND fixVersion = "{fix_version}"'
    return _jql_link(jql, text)


def _issues_in_link(keys: list[str], label: str) -> str:
    if not keys:
        return html.escape(label)
    jql = f"issue in ({', '.join(keys)})"
    return _jql_link(jql, label)


def _lane_scope_jql(burn: dict, goal: dict | None, lane_key: str) -> str | None:
    lane = (burn.get("lanes") or {}).get(lane_key) or {}
    if jql := lane.get("scopeJql"):
        return str(jql)
    planned = (burn.get("scope") or {}).get("plannedScopeJql") or {}
    if jql := planned.get(lane_key):
        return str(jql)
    by_scope = (goal or {}).get("plannedStoryPointsByScope") or {}
    if row := by_scope.get(lane_key):
        if jql := row.get("jql"):
            return str(jql)
    scope = burn.get("scope") or {}
    if lane_key == "unassigned" and scope.get("unassignedScopeJql"):
        return str(scope["unassignedScopeJql"])
    return None


def _lane_label_link(burn: dict, goal: dict | None, lane_key: str, label: str) -> str:
    jql = _lane_scope_jql(burn, goal, lane_key)
    if jql:
        return _jql_link(jql, _sanitize_atlassian_text(label))
    return html.escape(_sanitize_atlassian_text(label))


def _issue_link(key: str) -> str:
    return _browse_link(key)


