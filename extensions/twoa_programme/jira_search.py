"""Shared Jira search helpers for TWoA programme extensions."""

from __future__ import annotations

from typing import Any

from artifact.atlassian import AtlassianAdapter


def search_all(adapter: AtlassianAdapter, jql: str, fields: list[str]) -> list[dict]:
    """Paginate Jira POST /rest/api/3/search/jql until all issues are collected."""
    issues: list[dict] = []
    token: str | None = None
    while True:
        body: dict[str, Any] = {"jql": jql, "maxResults": 100, "fields": fields}
        if token:
            body["nextPageToken"] = token
        data = adapter.http.post_json("/rest/api/3/search/jql", body=body)
        batch = data.get("issues") or []
        issues.extend(batch)
        if data.get("isLast", True) or not batch:
            break
        token = data.get("nextPageToken")
        if not token:
            break
    return issues
