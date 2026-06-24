"""Jira-sourced delivery milestones for quarterly dashboard (EPCE-6872)."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from artifact.atlassian import AtlassianAdapter

from extensions.twoa_programme.epic_timeline import summarize_epic_children
from extensions.twoa_programme.jira_search import search_all
from extensions.twoa_programme.quarter_scope import (
    issue_excluded_from_analysis,
    milestone_linked_epic_scope_jql,
)
from extensions.twoa_programme.quarterly_reporting import NZ_TZ

MILESTONE_LINK_TYPE = "Milestone"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACT_NAME = "delivery-milestones.json"


def default_delivery_milestones_path(repo_root: Path | None = None) -> Path:
    from extensions.twoa_programme.quarterly_reporting import load_quarterly_reporting_config

    root = repo_root or _REPO_ROOT
    config = load_quarterly_reporting_config(root / "config" / "quarterly-reporting.json")
    return config.output_root(root) / _ARTIFACT_NAME


def adf_text(node: Any) -> str:
    """Flatten Jira ADF to plain text with paragraph and list structure preserved."""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        node_type = node.get("type")
        if node_type == "text":
            return node.get("text", "")
        if node_type == "hardBreak":
            return "\n"
        if node_type == "paragraph":
            inner = "".join(adf_text(c) for c in node.get("content") or [])
            return f"{inner}\n" if inner else ""
        if node_type == "listItem":
            inner = "".join(adf_text(c) for c in node.get("content") or [])
            return inner.strip()
        if node_type == "bulletList":
            items = [
                f"• {adf_text(item).strip()}"
                for item in (node.get("content") or [])
                if adf_text(item).strip()
            ]
            return "\n".join(items) + ("\n" if items else "")
        if node_type == "orderedList":
            items = [
                f"{index}. {adf_text(item).strip()}"
                for index, item in enumerate(node.get("content") or [], start=1)
                if adf_text(item).strip()
            ]
            return "\n".join(items) + ("\n" if items else "")
        if node_type in {"heading", "blockquote", "panel"}:
            inner = "".join(adf_text(c) for c in node.get("content") or [])
            return f"{inner.strip()}\n" if inner.strip() else ""
        if node_type == "rule":
            return "\n"
        return "".join(adf_text(c) for c in node.get("content") or [])
    if isinstance(node, list):
        return "".join(adf_text(c) for c in node)
    return ""


def normalize_milestone_description(text: str) -> str:
    """Collapse excess blank lines; keep bullets and paragraph breaks."""
    lines = [line.rstrip() for line in text.strip().splitlines()]
    cleaned: list[str] = []
    for line in lines:
        if not line and cleaned and not cleaned[-1]:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def milestone_work_item_notes(
    fields: dict[str, Any],
    *,
    notes_field: str,
) -> str:
    """Plain text from a milestone work item Notes custom field (ADF or string)."""
    raw = fields.get(notes_field)
    if not raw:
        return ""
    if isinstance(raw, dict):
        text = adf_text(raw)
    else:
        text = str(raw)
    return normalize_milestone_description(text)


def _parse_jira_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value)
    if raw.endswith("+0000"):
        raw = raw[:-5] + "+00:00"
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


_NOTES_CHANGELOG_FIELDS = frozenset({"Notes"})


def _notes_changelog_item_matches(item: dict[str, Any], *, notes_field_id: str) -> bool:
    field = str(item.get("field") or "")
    field_id = str(item.get("fieldId") or "")
    return field in _NOTES_CHANGELOG_FIELDS or field_id == notes_field_id


def notes_field_last_updated(
    histories: list[dict[str, Any]],
    *,
    notes_field_id: str,
) -> datetime | None:
    """Most recent Jira changelog timestamp when the Notes field changed."""
    latest: datetime | None = None
    for history in histories:
        created = _parse_jira_dt(history.get("created"))
        if created is None:
            continue
        for item in history.get("items") or []:
            if not _notes_changelog_item_matches(item, notes_field_id=notes_field_id):
                continue
            if latest is None or created > latest:
                latest = created
    return latest


def format_milestone_notes_updated_label(updated_at: datetime | str | None) -> str:
    """Human-readable Notes update date for report headings (NZ calendar date)."""
    if updated_at is None:
        return ""
    if isinstance(updated_at, str):
        parsed = _parse_jira_dt(updated_at)
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except ValueError:
                return ""
        updated_at = parsed
    day = updated_at.astimezone(NZ_TZ).date()
    return f"updated {day.strftime('%d %b %Y')}"


def milestone_notes_heading(*, notes_updated_at: datetime | str | None = None) -> str:
    """Plain-text Notes section heading, optionally with last-updated date."""
    suffix = format_milestone_notes_updated_label(notes_updated_at)
    return f"Notes · {suffix}" if suffix else "Notes"


def milestone_tooltip_sections(ms: dict[str, Any]) -> dict[str, Any]:
    """Structured tooltip content for a milestone chart row."""
    description = normalize_milestone_description(str(ms.get("description") or ""))
    rollup = ms.get("scopeRollup") or {}
    scope_epics = ms.get("scopeEpics") or []

    scope_lines: list[str] = []
    child_count = rollup.get("childCount")
    if child_count is not None:
        scope_lines.append(f"{int(child_count)} Story/Bug in quarter scope")
    story_points = rollup.get("storyPoints")
    if story_points is not None:
        scope_lines.append(f"{float(story_points):g} SP planned")
    earned = rollup.get("earnedStoryPoints")
    if earned is not None and float(earned) > 0:
        scope_lines.append(f"{float(earned):g} SP earned (Deploy+/Done)")
    unpointed = rollup.get("unpointedCount")
    if unpointed:
        scope_lines.append(f"{int(unpointed)} unpointed")

    epic_lines = [
        f"{epic.get('key')}: {epic.get('summary') or ''}".strip(": ")
        for epic in scope_epics
        if epic.get("key")
    ]

    return {
        "description": description,
        "scopeLines": scope_lines,
        "epicLines": epic_lines,
    }


def milestone_tooltip_plain(
    ms: dict[str, Any],
    *,
    pinned: bool = False,
) -> str:
    """Multi-line plain text for SVG <title> tooltips."""
    sections = milestone_tooltip_sections(ms)
    lines: list[str] = []
    label = str(ms.get("label") or ms.get("summary") or "").strip()
    day = str(ms.get("date") or ms.get("dueDate") or "")[:10]
    if label:
        header = f"{label} | {day}" if day else label
        key = str(ms.get("key") or "").strip()
        if key:
            header = f"{header} ({key})"
        lines.append(header)
    if sections["description"]:
        if lines:
            lines.append("")
        lines.append(sections["description"])
    if sections["scopeLines"]:
        if lines:
            lines.append("")
        lines.append("Scope")
        lines.extend(f"  {row}" for row in sections["scopeLines"])
    if sections["epicLines"]:
        if lines:
            lines.append("")
        lines.append("Linked epics")
        lines.extend(f"  {row}" for row in sections["epicLines"])
    if pinned:
        if lines:
            lines.append("")
        lines.append("Target date is just after quarter end; marker pinned to quarter end")
    return "\n".join(lines)


def milestone_linked_issues(issue: dict, *, link_type: str = MILESTONE_LINK_TYPE) -> list[dict]:
    rows: list[dict] = []
    for link in (issue.get("fields") or {}).get("issuelinks") or []:
        if (link.get("type") or {}).get("name") != link_type:
            continue
        target = link.get("outwardIssue") or link.get("inwardIssue") or {}
        if target.get("key"):
            rows.append(target)
    return rows


def fetch_jira_saved_filter(adapter: AtlassianAdapter, filter_id: str | int) -> dict[str, Any]:
    """Load a Jira saved filter by numeric id (e.g. 15858)."""
    return adapter.http.get_json(f"/rest/api/3/filter/{filter_id}")


def parse_milestone_report_window(jql: str) -> tuple[date | None, date | None]:
    """Best-effort chart window from a milestone report saved filter JQL."""
    dates = re.findall(r"'(\d{4}-\d{2}-\d{2})'", jql or "")
    if not dates:
        return None, None
    start = date.fromisoformat(dates[0])
    end = date.fromisoformat(dates[1]) if len(dates) > 1 else None
    if end is not None and re.search(r"duedate\s*<\s*'", jql, re.IGNORECASE):
        end = end - timedelta(days=1)
    return start, end


def resolve_milestone_in_scope_filter(
    adapter: AtlassianAdapter,
    *,
    filter_id: str | None = None,
    filter_name: str | None = None,
) -> tuple[str | None, str | None, tuple[date | None, date | None]]:
    """Return (filter name for JQL, raw filter JQL, parsed report window)."""
    if filter_id:
        payload = fetch_jira_saved_filter(adapter, filter_id)
        name = str(payload.get("name") or filter_name or "").strip() or None
        jql = str(payload.get("jql") or "")
        return name, jql, parse_milestone_report_window(jql)
    name = str(filter_name or "").strip() or None
    return name, None, (None, None)


def milestone_hub_children_jql(
    hub_key: str,
    *,
    project_key: str = "PDE",
    in_scope_filter: str | None = None,
) -> str:
    """Hub milestone rows; optional saved filter (e.g. smart-milestone-report / 15858)."""
    jql = f"project = {project_key} AND parent = {hub_key}"
    if in_scope_filter and in_scope_filter.strip():
        jql = f"{jql} AND filter = {in_scope_filter.strip()}"
    return f"{jql} ORDER BY duedate ASC, key ASC"


def find_milestone_hub_key(initiative: dict, *, link_type: str = MILESTONE_LINK_TYPE) -> str | None:
    for link in (initiative.get("fields") or {}).get("issuelinks") or []:
        if (link.get("type") or {}).get("name") != link_type:
            continue
        target = link.get("outwardIssue") or link.get("inwardIssue") or {}
        key = target.get("key")
        if key:
            return str(key)
    return None


def _rollup_scope_metrics(
    adapter: AtlassianAdapter,
    epic_keys: list[str],
    *,
    quarter_filter: str,
    story_points_field: str,
    change_types_field: str,
    delivery_squad_field: str,
    deploy_statuses: set[str],
    done_statuses: set[str],
    skip_issue,
) -> dict[str, Any]:
    if not epic_keys:
        return {
            "childCount": 0,
            "storyPoints": 0.0,
            "earnedStoryPoints": 0.0,
            "unpointedCount": 0,
            "scopeIssueKeys": [],
        }

    keys_csv = ", ".join(epic_keys)
    child_jql = milestone_linked_epic_scope_jql(parent_keys_csv=keys_csv)
    child_fields = [
        "parent",
        "issuetype",
        "status",
        story_points_field,
        change_types_field,
        delivery_squad_field,
    ]
    children = search_all(adapter, child_jql, child_fields)
    metrics = summarize_epic_children(
        children,
        story_points_field=story_points_field,
        change_types_field=change_types_field,
        delivery_squad_field=delivery_squad_field,
        deploy_statuses=deploy_statuses,
        done_statuses=done_statuses,
        skip_issue=skip_issue,
    )
    scope_keys = sorted(
        {
            str(issue.get("key"))
            for issue in children
            if issue.get("key")
            and not skip_issue(issue)
        }
    )
    return {
        **metrics,
        "scopeIssueKeys": scope_keys,
    }


def fetch_delivery_milestones(
    adapter: AtlassianAdapter,
    *,
    initiative_key: str,
    quarter_filter: str,
    in_scope_filter: str | None = None,
    milestone_report_project: str = "PDE",
    delivery_squad_field: str,
    change_types_field: str,
    platform_field: str,
    story_points_field: str,
    deploy_statuses: set[str],
    done_statuses: set[str],
    skip_issue_types: frozenset[str],
) -> dict[str, Any]:
    initiative = adapter.http.get_json(
        f"/rest/api/3/issue/{initiative_key}",
        params={"fields": "summary,issuelinks"},
    )
    hub_key = find_milestone_hub_key(initiative)
    if not hub_key:
        raise ValueError(
            f"No {MILESTONE_LINK_TYPE!r} link on initiative {initiative_key}; "
            "expected a Milestone Level One hub work item."
        )

    hub = adapter.http.get_json(
        f"/rest/api/3/issue/{hub_key}",
        params={"fields": "summary,issuetype"},
    )
    hub_fields = hub.get("fields") or {}

    def skip_issue(issue: dict) -> bool:
        itype = ((issue.get("fields") or {}).get("issuetype") or {}).get("name") or ""
        return itype in skip_issue_types or issue_excluded_from_analysis(issue)

    del platform_field  # reserved for future lane-aware milestone scope

    children = search_all(
        adapter,
        milestone_hub_children_jql(
            hub_key,
            project_key=milestone_report_project,
            in_scope_filter=in_scope_filter,
        ),
        ["summary", "description", "duedate", "status", "issuetype", "issuelinks"],
    )

    milestones: list[dict[str, Any]] = []
    for issue in children:
        key = issue["key"]
        fields = issue.get("fields") or {}
        linked = milestone_linked_issues(issue)
        epic_keys = [str(row["key"]) for row in linked if row.get("key")]
        scope_epics = [
            {
                "key": str(row["key"]),
                "summary": ((row.get("fields") or {}).get("summary") or ""),
                "issueType": ((row.get("fields") or {}).get("issuetype") or {}).get("name") or "",
            }
            for row in linked
        ]
        rollup = _rollup_scope_metrics(
            adapter,
            epic_keys,
            quarter_filter=quarter_filter,
            story_points_field=story_points_field,
            change_types_field=change_types_field,
            delivery_squad_field=delivery_squad_field,
            deploy_statuses=deploy_statuses,
            done_statuses=done_statuses,
            skip_issue=skip_issue,
        )
        due = fields.get("duedate")
        desc = fields.get("description")
        milestones.append(
            {
                "key": key,
                "label": str(fields.get("summary") or "").strip(),
                "summary": str(fields.get("summary") or "").strip(),
                "description": adf_text(desc).strip() if desc else "",
                "dueDate": str(due)[:10] if due else None,
                "status": (fields.get("status") or {}).get("name") or "",
                "issueType": (fields.get("issuetype") or {}).get("name") or "",
                "scopeEpics": scope_epics,
                "scopeRollup": {
                    "childCount": rollup["childCount"],
                    "storyPoints": rollup["storyPoints"],
                    "earnedStoryPoints": rollup["earnedStoryPoints"],
                    "unpointedCount": rollup["unpointedCount"],
                },
                "scopeIssueKeys": rollup["scopeIssueKeys"],
            }
        )

    milestones.sort(
        key=lambda row: (
            row.get("dueDate") or "9999-12-31",
            row.get("key") or "",
        )
    )

    return {
        "initiativeKey": initiative_key,
        "hubKey": hub_key,
        "hubSummary": hub_fields.get("summary") or "",
        "hubIssueType": (hub_fields.get("issuetype") or {}).get("name") or "",
        "inScopeFilter": in_scope_filter,
        "milestoneReportProject": milestone_report_project,
        "milestoneCount": len(milestones),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "milestones": milestones,
    }


def chart_milestone_rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Chart markers: label + date, sorted by due date."""
    if not payload:
        return []
    rows: list[dict[str, Any]] = []
    for item in payload.get("milestones") or []:
        label = str(item.get("label") or item.get("summary") or "").strip()
        day = str(item.get("dueDate") or "")[:10]
        if label and day:
            row: dict[str, Any] = {"label": label, "date": day}
            if item.get("key"):
                row["key"] = item["key"]
            if item.get("description"):
                row["description"] = item["description"]
            if item.get("scopeRollup"):
                row["scopeRollup"] = item["scopeRollup"]
            if item.get("scopeEpics"):
                row["scopeEpics"] = item["scopeEpics"]
            rows.append(row)
    return sorted(rows, key=lambda row: (row["date"], row.get("key", "")))


def load_delivery_milestones_payload(path: Path | None = None) -> dict[str, Any] | None:
    artifact = path or default_delivery_milestones_path()
    if not artifact.is_file():
        return None
    return json.loads(artifact.read_text(encoding="utf-8"))
