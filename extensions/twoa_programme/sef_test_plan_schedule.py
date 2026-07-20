"""Fetch SEF Test Plan Block schedules from PDE and render Confluence sections."""

from __future__ import annotations

from datetime import date
from typing import Any

from artifact.confluence_blocks import h2, h3, jira_issue_link, p, p_html, page_link, table_wide_html, url_link

from extensions.twoa_programme.field_maps import field_aliases
from extensions.twoa_programme.jira_search import search_all
from extensions.twoa_programme.sef_block_scope import build_block_scope_rollups
from extensions.twoa_programme.sef_test_plan_manifest import (
    INTEGRATED_PROJECT_PLAN_TITLE,
    SEF_JIRA_PLAN_URL,
    TestPlanConfig,
    list_published_test_plans,
    load_project_plan_manifest,
)

JIRA_BASE = "https://twoa.atlassian.net"
START_DATE_FIELD = "customfield_10015"
ISSUE_FIELDS = [
    "summary",
    "status",
    "issuetype",
    "created",
    "duedate",
    START_DATE_FIELD,
    "parent",
    "issuelinks",
]


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _issue_bounds(fields: dict[str, Any]) -> tuple[date | None, date | None]:
    start_raw = fields.get(START_DATE_FIELD)
    start = _parse_day(str(start_raw)[:10] if start_raw else None)
    if start is None:
        start = _parse_day(str(fields.get("created") or "")[:10])
    due = _parse_day(str(fields.get("duedate") or "")[:10]) or start
    if start and due and due < start:
        due = start
    return start, due


def _dependency_keys(fields: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (blocked_by_keys, blocks_keys) from Jira issue links."""
    blocked_by: list[str] = []
    blocks: list[str] = []
    for link in fields.get("issuelinks") or []:
        if not isinstance(link, dict):
            continue
        link_type = link.get("type") or {}
        name = str(link_type.get("name") or "").lower()
        inward = str(link_type.get("inward") or "").lower()
        outward = str(link_type.get("outward") or "").lower()
        in_key = str(((link.get("inwardIssue") or {}).get("key") or "")).strip()
        out_key = str(((link.get("outwardIssue") or {}).get("key") or "")).strip()

        is_block_type = "block" in name or "block" in inward or "block" in outward
        if not is_block_type:
            continue

        if in_key:
            blocked_by.append(in_key)
        if out_key:
            blocks.append(out_key)

    return list(dict.fromkeys(blocked_by)), list(dict.fromkeys(blocks))


def fetch_test_plan_issues(
    adapter: Any,
    plan: TestPlanConfig,
) -> dict[str, dict[str, Any]]:
    keys = plan.all_block_keys()
    if not keys:
        return {}
    jql = f"key in ({', '.join(keys)}) ORDER BY rank ASC, key ASC"
    issues = search_all(adapter, jql, ISSUE_FIELDS)
    return {str(issue["key"]): issue for issue in issues}


def _schedule_row(issue: dict[str, Any]) -> list[str]:
    fields = issue.get("fields") or {}
    start, due = _issue_bounds(fields)
    status = str((fields.get("status") or {}).get("name") or "")
    summary = str(fields.get("summary") or "").strip()
    key = str(issue.get("key") or "")
    start_s = start.isoformat() if start else "Pending"
    due_s = due.isoformat() if due else "Pending"
    return [summary, start_s, due_s, status, jira_issue_link(JIRA_BASE, key)]


def _rows_for_keys(
    issues_by_key: dict[str, dict[str, Any]],
    key_map: dict[str, str],
) -> list[list[str]]:
    rows: list[list[str]] = []
    for label, key in key_map.items():
        issue = issues_by_key.get(key)
        if not issue:
            rows.append([label, "Pending", "Pending", "Not found", jira_issue_link(JIRA_BASE, key)])
            continue
        rows.append(_schedule_row(issue))
    return rows


def next_open_block_label(
    issues_by_key: dict[str, dict[str, Any]],
    plan: TestPlanConfig,
) -> str:
    today = date.today()
    candidates: list[tuple[date, str]] = []
    done_names = {"done", "closed", "passed", "resolved", "not required"}
    for key in plan.all_block_keys():
        issue = issues_by_key.get(key)
        if not issue:
            continue
        fields = issue.get("fields") or {}
        status = str((fields.get("status") or {}).get("name") or "").lower()
        if status in done_names:
            continue
        start, due = _issue_bounds(fields)
        anchor = start or due or today
        summary = str(fields.get("summary") or key)
        candidates.append((anchor, summary))
    if not candidates:
        return "All blocks complete or not yet scheduled"
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def build_test_plan_block_schedule_section(
    plan: TestPlanConfig,
    *,
    issues_by_key: dict[str, dict[str, Any]] | None = None,
    integrated_plan_link: str | None = None,
) -> str:
    """Dynamic Block schedule section for a Test Plan Confluence page."""
    integrated = integrated_plan_link or page_link("DTRAIN", INTEGRATED_PROJECT_PLAN_TITLE)
    hub = plan.reporting_hub.site_url() if plan.reporting_hub else ""
    jira_plan = url_link(plan.jira_plan_url, "SEF integrated Block Plan in Jira Plans")

    intro = p(
        "Schedule rows below are PDE Block work items in the integrated project plan. "
        "Dates and status refresh from Jira on publish. Edit the Block Plan in Jira Plans; "
        "the Reporting Hub snapshot and this table read the same issues."
    )

    if issues_by_key:
        main_rows = _rows_for_keys(issues_by_key, plan.details)
        nip_rows = _rows_for_keys(issues_by_key, plan.nip_details) if plan.nip_details else []
    else:
        main_rows = [[label, "Pending", "Pending", "Awaiting publish", jira_issue_link(JIRA_BASE, key)] for label, key in plan.details.items()]
        nip_rows = (
            [[label, "Pending", "Pending", "Awaiting publish", jira_issue_link(JIRA_BASE, key)] for label, key in plan.nip_details.items()]
            if plan.nip_details
            else []
        )

    schedule = (
        h2("Block Schedule")
        + intro
        + h3("Schedule Blocks")
        + table_wide_html(["Block", "Start", "Due", "Status", "Jira"], main_rows)
    )
    if nip_rows:
        schedule += (
            h3("P1 NIP Detail")
            + p("Non-integrated parallel preparation and execution blocks under the Payroll Stream package.")
            + table_wide_html(["Block", "Start", "Due", "Status", "Jira"], nip_rows)
        )

    live_bits = []
    if hub:
        live_bits.append(f"Sub-plan Gantt: {url_link(hub, hub)}.")
    live_bits.append(f"Integrated Block Plan: {jira_plan}.")
    live_bits.append(f"Programme context: {integrated}.")
    schedule += h3("Live Views") + p_html(" ".join(live_bits))
    return schedule


def build_test_plans_catalog_section(
    manifest: dict[str, Any] | None = None,
    *,
    adapter: Any | None = None,
) -> str:
    """Index of governed Test Plans for SEF | Test Strategy."""
    payload = manifest or load_project_plan_manifest()
    plans = list_published_test_plans(payload)
    if not plans:
        return ""

    issues_by_plan: dict[str, dict[str, dict[str, Any]]] = {}
    if adapter is not None:
        for plan in plans:
            issues_by_plan[plan.slug] = fetch_test_plan_issues(adapter, plan)

    rows: list[list[str]] = []
    for plan in plans:
        conf = (
            page_link("DTRAIN", plan.title)
            if not plan.confluence_url
            else url_link(plan.confluence_url, plan.title)
        )
        hub_cell = (
            url_link(plan.reporting_hub.site_url(), "Sub-plan Gantt")
            if plan.reporting_hub
            else "Pending"
        )
        block_count = str(len(plan.all_block_keys()))
        if adapter is not None:
            next_item = next_open_block_label(issues_by_plan.get(plan.slug, {}), plan)
        else:
            next_item = "Refreshed on publish"
        rows.append([plan.title, conf, hub_cell, block_count, next_item])

    return (
        h2("Test Plans and Block Schedules")
        + p(
            "Executable test plans under this strategy. Each annex links PDE Block schedule rows "
            "in the integrated project plan. Narrative and evidence rules stay on the Test Plan page; "
            "dates and status are read from Jira on publish."
        )
        + table_wide_html(
            ["Test Plan", "Confluence", "Sub-plan Gantt", "Block rows", "Next open block"],
            rows,
        )
        + p_html(
            f"Integrated programme schedule: {page_link('DTRAIN', INTEGRATED_PROJECT_PLAN_TITLE)}. "
            f"Native Block Plan view: {url_link(SEF_JIRA_PLAN_URL, 'Jira Plans')}."
        )
    )


def fetch_test_plan_timeline_payload(
    adapter: Any,
    plan: TestPlanConfig,
) -> dict[str, Any]:
    """Build a phases payload for the SEF project plan Gantt renderer (reporting hub)."""
    keys = plan.all_block_keys()
    stream_keys = plan.stream_parent_keys()
    filter_id = plan.jira_filter_id()
    if filter_id:
        jql = f"filter = {filter_id} ORDER BY rank ASC, key ASC"
        issues = search_all(adapter, jql, ISSUE_FIELDS)
        keys = [str(issue.get("key") or "") for issue in issues if issue.get("key")]
    else:
        all_keys = list(dict.fromkeys(stream_keys + keys))
        if not all_keys:
            return {"phases": [], "pageTitle": plan.title}
        jql = f"key in ({', '.join(all_keys)}) ORDER BY rank ASC, key ASC"
        issues = search_all(adapter, jql, ISSUE_FIELDS)
    issues_by_key = {str(issue["key"]): issue for issue in issues}

    # Meeting work items with Meeting Type = Gate should behave like milestones.
    meeting_gate_keys: set[str] = set()
    meeting_keys = [
        str(issue.get("key") or "")
        for issue in issues
        if str((((issue.get("fields") or {}).get("issuetype") or {}).get("name") or "").strip().lower()) == "meeting"
    ]
    meeting_keys = [k for k in meeting_keys if k]
    if meeting_keys:
        try:
            gate_meetings = search_all(
                adapter,
                f'key in ({", ".join(meeting_keys)}) AND "Meeting Type" = Gate',
                ["key"],
            )
            meeting_gate_keys = {
                str(issue.get("key") or "") for issue in gate_meetings if issue.get("key")
            }
        except Exception:
            # If Meeting Type is unavailable in this Jira project context, continue without gating.
            meeting_gate_keys = set()

    parent_keys: list[str] = []
    for issue in issues:
        parent = ((issue.get("fields") or {}).get("parent") or {}).get("key")
        if parent:
            parent_keys.append(str(parent))
    parent_key_set = set(parent_keys)
    # In filter mode Jira can return both parent and child block levels; only render leaf keys as details.
    detail_keys = [key for key in keys if key and key not in parent_key_set]
    if filter_id:
        missing_parent_keys = [key for key in dict.fromkeys(parent_keys) if key not in issues_by_key]
        if missing_parent_keys:
            parent_jql = f"key in ({', '.join(missing_parent_keys)})"
            parent_issues = search_all(adapter, parent_jql, ISSUE_FIELDS)
            for issue in parent_issues:
                key = str(issue.get("key") or "")
                if key:
                    issues_by_key[key] = issue
        stream_keys = list(dict.fromkeys(stream_keys + parent_keys))

    rollup_keys = list(dict.fromkeys(stream_keys + detail_keys))
    story_points_field = field_aliases()["Story Points"]
    scope_rollups = build_block_scope_rollups(
        adapter,
        block_issues={key: issues_by_key[key] for key in rollup_keys if key in issues_by_key},
        story_points_field=story_points_field,
    )

    fallback_start = date(2026, 6, 1)
    fallback_end = date(2027, 12, 3)

    def timeline_row(issue: dict[str, Any]) -> dict[str, Any]:
        fields_data = issue.get("fields") or {}
        start, end = _issue_bounds(fields_data)
        start = start or fallback_start
        end = end or fallback_end
        issue_type_obj = fields_data.get("issuetype") or {}
        issue_type = str((issue_type_obj.get("name") or "")).strip()
        key = str(issue.get("key") or "")
        blocked_by_keys, blocks_keys = _dependency_keys(fields_data)
        return {
            "key": key,
            "summary": str(fields_data.get("summary") or "").strip(),
            "issueType": issue_type,
            "issueTypeIconUrl": str(issue_type_obj.get("iconUrl") or "").strip(),
            "isMeetingGate": key in meeting_gate_keys,
            "status": str((fields_data.get("status") or {}).get("name") or ""),
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "blockedByKeys": blocked_by_keys,
            "blocksKeys": blocks_keys,
            **(
                {"scopeRollup": scope_rollups[str(issue.get("key") or "")]}
                if str(issue.get("key") or "") in scope_rollups
                else {}
            ),
        }

    def row_sort_key(row: dict[str, Any]) -> tuple[date, date, str]:
        start = _parse_day(str(row.get("startDate") or "")) or fallback_start
        end = _parse_day(str(row.get("endDate") or "")) or start
        label = str(row.get("summary") or row.get("key") or "")
        return (start, end, label)

    packages: list[dict[str, Any]] = []
    parent_for_key: dict[str, str] = {}
    for key in detail_keys:
        issue = issues_by_key.get(key)
        if not issue:
            continue
        parent = ((issue.get("fields") or {}).get("parent") or {}).get("key")
        if parent:
            parent_for_key[key] = str(parent)

    grouped: dict[str, list[str]] = {parent: [] for parent in stream_keys}
    grouped.setdefault("unassigned", [])
    for key in detail_keys:
        parent = parent_for_key.get(key)
        if parent and parent in grouped:
            grouped[parent].append(key)
        elif parent:
            grouped.setdefault(parent, []).append(key)
        else:
            grouped["unassigned"].append(key)

    def _is_container_type(issue: dict[str, Any]) -> bool:
        itype = str(((issue.get("fields") or {}).get("issuetype") or {}).get("name") or "").strip().lower()
        return itype in {"test strategy", "block level two"}

    for parent_key in stream_keys + [k for k in grouped if k not in stream_keys and k != "unassigned"]:
        child_keys = grouped.get(parent_key) or []
        if not child_keys and parent_key not in issues_by_key:
            continue
        package_issue = issues_by_key.get(parent_key)

        # Container types (e.g. Test Strategy) are suppressed as bars;
        # their children are promoted to sibling package rows.
        if package_issue and _is_container_type(package_issue) and child_keys:
            for child_key in child_keys:
                if child_key not in issues_by_key:
                    continue
                child_row = timeline_row(issues_by_key[child_key])
                child_row["details"] = []
                packages.append(child_row)
            continue

        if package_issue:
            package_row = timeline_row(package_issue)
        else:
            package_row = {
                "key": parent_key,
                "summary": parent_key,
                "status": "",
                "startDate": fallback_start.isoformat(),
                "endDate": fallback_end.isoformat(),
            }
        package_row["details"] = [timeline_row(issues_by_key[key]) for key in child_keys if key in issues_by_key]
        package_row["details"].sort(key=row_sort_key)

        packages.append(package_row)

    unassigned = grouped.get("unassigned") or []
    if unassigned:
        packages.append(
            {
                "key": "",
                "summary": "Other schedule blocks",
                "status": "",
                "startDate": fallback_start.isoformat(),
                "endDate": fallback_end.isoformat(),
                "details": [timeline_row(issues_by_key[key]) for key in unassigned if key in issues_by_key],
            }
        )

    # Sort all packages by start date once all rows are assembled.
    packages.sort(key=row_sort_key)

    chapter = {
        "key": "",
        "summary": "",
        "status": "",
        "startDate": fallback_start.isoformat(),
        "endDate": fallback_end.isoformat(),
        "packages": packages,
    }
    phase = {
        "key": "",
        "summary": "Test plan Block schedule",
        "status": "",
        "startDate": fallback_start.isoformat(),
        "endDate": fallback_end.isoformat(),
        "chapters": [chapter],
    }
    return {
        "pageTitle": f"{plan.title} | Block Schedule",
        "phases": [phase],
    }
