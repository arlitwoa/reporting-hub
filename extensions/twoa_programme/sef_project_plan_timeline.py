"""SEF integrated project plan Block Gantt (PDE L2/L1/L0/L-1 hierarchy)."""

from __future__ import annotations

import html
import json
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from artifact.atlassian import AtlassianAdapter

from extensions.twoa_programme.epic_timeline import (
    EPIC_CHART_PX_PER_DAY,
    EPIC_STATUS_FILL,
    epic_bar_fill,
)
from extensions.twoa_programme.jira_search import search_all
from extensions.twoa_programme.quarterly_dashboard_constants import ATL, JIRA_SERVER, SVG_FONT
from extensions.twoa_programme.quarterly_dashboard_markup import REPORT_CSS, _svg_embedded_title
from extensions.twoa_programme.github_pages_nav import BREADCRUMB_CSS
from extensions.twoa_programme.quarterly_dashboard_svg_core import (
    QUARTERLY_REPORT_MAX_SVG_WIDTH,
    QUARTERLY_REPORT_MIN_PLOT_WIDTH,
    _append_today_marker,
    _chart_today_in_quarter,
    _svg_x_axis_labels,
    _svg_x_bottom_margin,
)
from extensions.twoa_programme.field_maps import field_aliases
from extensions.twoa_programme.milestone_scope_chart import (
    DTRAIN_PHASE_FILL,
    append_scope_composition_overlay,
    lane_bar_segments,
    timeline_bar_segment_order,
)
from extensions.twoa_programme.sef_block_scope import build_block_scope_rollups
from extensions.twoa_programme.sef_project_plan_reporting import (
    SefProjectPlanReportingConfig,
    discover_phase_hub_issues,
    load_sef_project_plan_reporting_config,
)

START_DATE_FIELD = "customfield_10015"

CHAPTER_ROW_HEIGHT = 28
PHASE_ROW_HEIGHT = 32
STREAM_ROW_HEIGHT = 18
DETAIL_ROW_HEIGHT = 16
LABEL_WIDTH = 280
RIGHT_PAD = 24
MILESTONE_RIGHT_LABEL_PAD = 180
CALENDAR_TOP = 40
BLOCK_GAP = 12
BLOCK_PAD_Y = 8
LABEL_PAD_X = 8
LABEL_MAX_CHARS = 42
SUB_LABEL_INDENT = 20
DETAIL_LABEL_INDENT = 36
CHAPTER_BAR_HEIGHT = CHAPTER_ROW_HEIGHT - 6
PHASE_BAR_HEIGHT = PHASE_ROW_HEIGHT - 8
STREAM_BAR_HEIGHT = STREAM_ROW_HEIGHT - 4
DETAIL_BAR_HEIGHT = DETAIL_ROW_HEIGHT - 4
BAR_OPACITY = 0.85
SUB_BAR_OPACITY = 0.55
DETAIL_BAR_OPACITY = 0.35
SCOPE_OVERLAY_OPACITY = 0.92
SUB_SCOPE_OVERLAY_OPACITY = 0.72
DETAIL_SCOPE_OVERLAY_OPACITY = 0.62
BLOCK_BORDER_WIDTH = 0.75
PHASE_GAP = 20
CHART_WINDOW_PADDING_DAYS = 0
MILESTONE_TRIANGLE_FILL = "#de350b"
DEPENDENCY_STROKE = MILESTONE_TRIANGLE_FILL
DEPENDENCY_STROKE_WIDTH = 1.1
DEPENDENCY_MIN_HORIZONTAL_RUN = 32.0
SWIMLANE_FILLS = ["#e8f4fd", "#e8f8ee"]  # alternating light blue / light green

# Map detail bar summary keywords to D-Train phase colours.
# Test Plan = Design, Test Preparation = Develop, Test Execution = Deliver, Test Summary Report = Drive
DETAIL_KEYWORD_FILLS: list[tuple[str, str]] = [
    ("test summary report", "#00875a"),  # Drive
    ("test memo", "#00875a"),             # Drive
    ("config workbooks", "#00875a"),      # Drive
    ("interface specs", "#00875a"),       # Drive
    ("report specs", "#00875a"),          # Drive
    ("test execution", "#5f6438"),        # Deliver
    ("test preparation", "#7f582d"),      # Develop
    ("test plan", "#9f4c22"),             # Design
]

TEST_CYCLE_BAR_FILL = "#1868db"  # Light blue for Test Cycle swimlane bars

# Package-level bars with specific keyword overrides.
PACKAGE_KEYWORD_FILLS: list[tuple[str, str]] = [
    ("data migration", "#0747a6"),       # Dark blue
    ("integration build", "#0747a6"),    # Dark blue
]


def _package_keyword_fill(summary: str) -> str | None:
    """Return a colour override for a known package type, or None to use default."""
    lower = summary.strip().lower()
    for keyword, color in PACKAGE_KEYWORD_FILLS:
        if keyword in lower:
            return color
    return None


def _detail_keyword_fill(summary: str) -> str | None:
    """Return a D-Train phase fill for a known detail type, or None to use default."""
    lower = summary.strip().lower()
    for keyword, color in DETAIL_KEYWORD_FILLS:
        if keyword in lower:
            return color
    return None

SEF_PROJECT_PLAN_EXTRA_CSS = """
.report-shell {
    max-width: none;
    width: min(100vw - 8px, 2200px);
    padding: 16px 4px 24px;
}
.chart-wrap-sef-plan.chart-wrap-timeline {
    max-height: none;
    min-height: 0;
    overflow-x: hidden;
    overflow-y: hidden;
}
.chart-wrap-sef-plan svg {
  display: block;
  width: 100%;
  height: auto;
  min-width: 0;
  max-width: 100%;
}
.chart-wrap-sef-plan svg a text {
  text-decoration: none;
}
.chart-wrap-sef-plan svg a:hover text {
  text-decoration: underline;
}
.sef-phase-divider {
  fill: #f4f5f7;
}
"""


def default_sef_project_plan_timeline_path(repo_root: Path | None = None) -> Path:
    config = load_sef_project_plan_reporting_config(repo_root=repo_root)
    return config.timeline_path(repo_root)


def load_sef_project_plan_timeline_payload(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_timeline_rows(phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for phase in phases:
        rows.append(phase)
        for chapter in phase.get("chapters") or []:
            rows.append(chapter)
            for package in chapter.get("packages") or []:
                rows.append(package)
                for detail in package.get("details") or []:
                    rows.append(detail)
    return rows


def resolve_chart_window_for_phases(
    phases: list[dict[str, Any]],
    *,
    fallback_start: str = "2026-06-01",
    fallback_end: str = "2027-12-03",
    padding_days: int = CHART_WINDOW_PADDING_DAYS,
) -> tuple[date, date]:
    """Span the x-axis from earliest start through latest end across all plan rows."""
    all_starts: list[date] = []
    all_ends: list[date] = []
    actionable_starts: list[date] = []
    actionable_ends: list[date] = []

    for phase in phases:
        for chapter in phase.get("chapters") or []:
            for package in chapter.get("packages") or []:
                p_start = package.get("startDate")
                p_end = package.get("endDate")
                if p_start:
                    actionable_starts.append(date.fromisoformat(str(p_start)[:10]))
                if p_end:
                    actionable_ends.append(date.fromisoformat(str(p_end)[:10]))
                for detail in package.get("details") or []:
                    d_start = detail.get("startDate")
                    d_end = detail.get("endDate")
                    if d_start:
                        actionable_starts.append(date.fromisoformat(str(d_start)[:10]))
                    if d_end:
                        actionable_ends.append(date.fromisoformat(str(d_end)[:10]))

    for row in _iter_timeline_rows(phases):
        start_raw = row.get("startDate")
        end_raw = row.get("endDate")
        if start_raw:
            all_starts.append(date.fromisoformat(str(start_raw)[:10]))
        if end_raw:
            all_ends.append(date.fromisoformat(str(end_raw)[:10]))

    starts = actionable_starts or all_starts
    ends = actionable_ends or all_ends
    if not starts or not ends:
        return date.fromisoformat(fallback_start), date.fromisoformat(fallback_end)
    pad = timedelta(days=padding_days)
    return min(starts) - pad, max(ends) + pad


def _payload_chart_window(payload: dict[str, Any]) -> tuple[date, date]:
    phases = payload.get("phases") or []
    if phases:
        return resolve_chart_window_for_phases(phases)
    return (
        date.fromisoformat(str(payload.get("chartWindowStart") or "2026-06-01")[:10]),
        date.fromisoformat(str(payload.get("chartWindowEnd") or "2027-12-03")[:10]),
    )


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _resolve_window(
    *,
    start_raw: str | None,
    created: str | None,
    due_raw: str | None,
    fallback_start: date,
    fallback_end: date,
) -> tuple[date, date]:
    start = _parse_day(start_raw) or _parse_day(created) or fallback_start
    end = _parse_day(due_raw) or start
    if end < start:
        end = start
    return start, end


def _issue_timeline_row(
    issue: dict[str, Any],
    *,
    fallback_start: date,
    fallback_end: date,
) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    start_raw = fields.get(START_DATE_FIELD)
    if isinstance(start_raw, str):
        start_s = start_raw[:10]
    else:
        start_s = None
    due_raw = fields.get("duedate")
    due_s = str(due_raw)[:10] if due_raw else None
    created = str(fields.get("created") or "")[:10]
    start, end = _resolve_window(
        start_raw=start_s,
        created=created,
        due_raw=due_s,
        fallback_start=fallback_start,
        fallback_end=fallback_end,
    )
    status = str((fields.get("status") or {}).get("name") or "")
    summary = str(fields.get("summary") or "").strip()
    key = str(issue.get("key") or "")
    row: dict[str, Any] = {
        "key": key,
        "summary": summary,
        "status": status,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
    }
    if due_s:
        row["dueDate"] = due_s
    return row


def _fetch_children(
    adapter: "AtlassianAdapter",
    *,
    parent_key: str,
    issue_type: str,
    fields: list[str],
) -> list[dict[str, Any]]:
    jql = f'parent = {parent_key} AND issuetype = "{issue_type}" ORDER BY rank ASC, key ASC'
    return search_all(adapter, jql, fields)


def _resolve_scope_filter_jql(
    adapter: "AtlassianAdapter",
    config: "SefProjectPlanReportingConfig",
) -> str | None:
    """Return JQL for scope filter if configured, else None."""
    if config.scope_filter_id:
        from extensions.twoa_programme.delivery_milestones import fetch_jira_saved_filter
        payload = fetch_jira_saved_filter(adapter, config.scope_filter_id)
        jql = str(payload.get("jql") or "").strip()
        return jql or f"filter = {config.scope_filter_id}"
    if config.scope_filter_name:
        return f"filter = {config.scope_filter_name}"
    return None


def _build_hierarchy_from_flat(
    issues: list[dict[str, Any]],
    config: "SefProjectPlanReportingConfig",
    *,
    fallback_start: "date",
    fallback_end: "date",
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Build phase→chapter→package→detail hierarchy from a flat issue list.

    Returns (phases, hub_keys, warnings).
    """
    block_types = {
        config.chapter_issue_type,   # Block Level One
        config.package_issue_type,   # Block Level Zero
        config.detail_issue_type,    # Block Level Minus One
    }
    hub_type = "Block Level Two"
    by_key: dict[str, dict[str, Any]] = {}
    for issue in issues:
        key = str(issue.get("key") or "")
        if not key:
            continue
        itype = ((issue.get("fields") or {}).get("issuetype") or {}).get("name") or ""
        if itype not in {hub_type, *block_types}:
            continue  # skip milestone levels etc.
        by_key[key] = issue

    # Build parent→children mapping
    children_of: dict[str, list[str]] = {}
    for key, issue in by_key.items():
        parent_key = ((issue.get("fields") or {}).get("parent") or {}).get("key") or ""
        children_of.setdefault(parent_key, []).append(key)

    # Hub issues are Block Level Two (parent not in our set)
    hub_keys_found = [
        key for key, issue in by_key.items()
        if ((issue.get("fields") or {}).get("issuetype") or {}).get("name") == hub_type
    ]
    hub_keys_found.sort()
    warnings: list[str] = []

    def make_detail(key: str) -> dict[str, Any]:
        return _issue_timeline_row(by_key[key], fallback_start=fallback_start, fallback_end=fallback_end)

    def make_package(key: str) -> dict[str, Any]:
        row = _issue_timeline_row(by_key[key], fallback_start=fallback_start, fallback_end=fallback_end)
        detail_keys = sorted(children_of.get(key, []))
        row["details"] = [
            make_detail(dk)
            for dk in detail_keys
            if dk in by_key and ((by_key[dk].get("fields") or {}).get("issuetype") or {}).get("name") == config.detail_issue_type
        ]
        return row

    def make_chapter(key: str) -> dict[str, Any]:
        row = _issue_timeline_row(by_key[key], fallback_start=fallback_start, fallback_end=fallback_end)
        pkg_keys = sorted(children_of.get(key, []))
        row["packages"] = [
            make_package(pk)
            for pk in pkg_keys
            if pk in by_key and ((by_key[pk].get("fields") or {}).get("issuetype") or {}).get("name") == config.package_issue_type
        ]
        return row

    phases: list[dict[str, Any]] = []
    for hub_key in hub_keys_found:
        hub_row = _issue_timeline_row(by_key[hub_key], fallback_start=fallback_start, fallback_end=fallback_end)
        chapter_keys = sorted(children_of.get(hub_key, []))
        hub_row["chapters"] = [
            make_chapter(ck)
            for ck in chapter_keys
            if ck in by_key and ((by_key[ck].get("fields") or {}).get("issuetype") or {}).get("name") == config.chapter_issue_type
        ]
        phases.append(hub_row)

    if not phases:
        warnings.append("Scope filter returned no Block Level Two (phase hub) issues.")
    return phases, hub_keys_found, warnings


def fetch_sef_project_plan_timeline(
    adapter: "AtlassianAdapter",
    config: SefProjectPlanReportingConfig,
) -> dict[str, Any]:
    fallback_start = date.fromisoformat(config.chart_window_start)
    fallback_end = date.fromisoformat(config.chart_window_end)
    start_field = START_DATE_FIELD
    fields = ["summary", "status", "issuetype", "created", "duedate", start_field]
    scope_fields = [*fields, "issuelinks"]
    story_points_field = field_aliases()["Story Points"]

    scope_filter_jql = _resolve_scope_filter_jql(adapter, config)
    if scope_filter_jql:
        # Single flat fetch from Jira filter — hierarchy built from parent fields.
        filter_fields = [*scope_fields, "parent"]
        all_issues = search_all(adapter, scope_filter_jql, filter_fields)
        phases, hub_keys, warnings = _build_hierarchy_from_flat(
            all_issues,
            config,
            fallback_start=fallback_start,
            fallback_end=fallback_end,
        )
        # Build block_issues dict for scope rollup
        block_issues: dict[str, dict[str, Any]] = {
            str(issue.get("key") or ""): issue
            for issue in all_issues
            if issue.get("key")
        }
    else:
        hub_issues, warnings = discover_phase_hub_issues(adapter, config, fields=fields)
        hub_keys = [str(issue.get("key") or "") for issue in hub_issues if issue.get("key")]
        phases = []
        block_issues = {}

        for hub in hub_issues:
            hub_key = str(hub.get("key") or "")
            if not hub_key:
                continue
            hub_row = _issue_timeline_row(
                hub,
                fallback_start=fallback_start,
                fallback_end=fallback_end,
            )
            chapters_raw = _fetch_children(
                adapter,
                parent_key=hub_key,
                issue_type=config.chapter_issue_type,
                fields=scope_fields,
            )
            chapters: list[dict[str, Any]] = []
            for chapter_issue in chapters_raw:
                chapter_key = str(chapter_issue["key"])
                block_issues[chapter_key] = chapter_issue
                chapter_row = _issue_timeline_row(
                    chapter_issue,
                    fallback_start=fallback_start,
                    fallback_end=fallback_end,
                )
                packages_raw = _fetch_children(
                    adapter,
                    parent_key=chapter_key,
                    issue_type=config.package_issue_type,
                    fields=scope_fields,
                )
                packages: list[dict[str, Any]] = []
                for package_issue in packages_raw:
                    package_key = str(package_issue["key"])
                    block_issues[package_key] = package_issue
                    package_row = _issue_timeline_row(
                        package_issue,
                        fallback_start=fallback_start,
                        fallback_end=fallback_end,
                    )
                    details_raw = _fetch_children(
                        adapter,
                        parent_key=package_key,
                        issue_type=config.detail_issue_type,
                        fields=scope_fields,
                    )
                    detail_rows: list[dict[str, Any]] = []
                    for detail_issue in details_raw:
                        detail_key = str(detail_issue["key"])
                        block_issues[detail_key] = detail_issue
                        detail_rows.append(
                            _issue_timeline_row(
                                detail_issue,
                                fallback_start=fallback_start,
                                fallback_end=fallback_end,
                            )
                        )
                    package_row["details"] = detail_rows
                    packages.append(package_row)
                chapter_row["packages"] = packages
                chapters.append(chapter_row)
            hub_row["chapters"] = chapters
            phases.append(hub_row)

    scope_rollups = build_block_scope_rollups(
        adapter,
        block_issues=block_issues,
        story_points_field=story_points_field,
    )
    for phase in phases:
        for chapter in phase.get("chapters") or []:
            chapter_key = str(chapter.get("key") or "")
            if chapter_key in scope_rollups:
                chapter["scopeRollup"] = scope_rollups[chapter_key]
            for package in chapter.get("packages") or []:
                package_key = str(package.get("key") or "")
                if package_key in scope_rollups:
                    package["scopeRollup"] = scope_rollups[package_key]
                for detail in package.get("details") or []:
                    detail_key = str(detail.get("key") or "")
                    if detail_key in scope_rollups:
                        detail["scopeRollup"] = scope_rollups[detail_key]

    window_start, window_end = resolve_chart_window_for_phases(
        phases,
        fallback_start=config.chart_window_start,
        fallback_end=config.chart_window_end,
    )

    return {
        "projectKey": config.project_key,
        "chartWindowStart": window_start.isoformat(),
        "chartWindowEnd": window_end.isoformat(),
        "phaseHubKeys": hub_keys,
        "warnings": warnings,
        "phases": phases,
    }


def _truncate_label(text: str, max_chars: int = LABEL_MAX_CHARS) -> str:
    cleaned = str(text or "").strip()
    return cleaned


def _label_column_width(phases: list[dict[str, Any]]) -> float:
    labels: list[str] = []
    for phase in phases:
        labels.append(str(phase.get("summary") or phase.get("key") or ""))
        for chapter in phase.get("chapters") or []:
            labels.append(str(chapter.get("summary") or chapter.get("key") or ""))
            for package in chapter.get("packages") or []:
                labels.append(str(package.get("summary") or package.get("key") or ""))
                for detail in package.get("details") or []:
                    labels.append(str(detail.get("summary") or detail.get("key") or ""))
    longest = max((len(item.strip()) for item in labels if str(item).strip()), default=0)
    # Approximate pixel width for UI font and leave padding so the longest heading is fully visible.
    dynamic = 24 + (longest * 6.4)
    return max(float(LABEL_WIDTH), dynamic)


def _append_label_link(
    parts: list[str],
    *,
    text: str,
    x: float,
    y_center: float,
    url: str,
    tooltip: str,
    font_size: int = 10,
    font_weight: str = "600",
    fill: str | None = None,
    indent: float = LABEL_PAD_X,
) -> None:
    text_fill = fill or ATL["ink"]
    parts.append(f'<g clip-path="url(#sef-plan-label-col)">{_svg_embedded_title(tooltip)}')
    parts.append(f'<a href="{url}" target="_blank" rel="noopener">')
    parts.append(
        f'<text x="{x:.1f}" y="{y_center:.1f}" text-anchor="start" dominant-baseline="middle" '
        f'font-family="{SVG_FONT}" font-size="{font_size}" fill="{text_fill}" '
        f'font-weight="{font_weight}">{html.escape(_truncate_label(text))}</text>'
    )
    parts.append("</a></g>")


def _append_label_text(
    parts: list[str],
    *,
    text: str,
    x: float,
    y_center: float,
    tooltip: str,
    font_size: int = 10,
    font_weight: str = "600",
    fill: str | None = None,
) -> None:
    text_fill = fill or ATL["ink"]
    parts.append(f'<g clip-path="url(#sef-plan-label-col)">{_svg_embedded_title(tooltip)}')
    parts.append(
        f'<text x="{x:.1f}" y="{y_center:.1f}" text-anchor="start" dominant-baseline="middle" '
        f'font-family="{SVG_FONT}" font-size="{font_size}" fill="{text_fill}" '
        f'font-weight="{font_weight}">{html.escape(_truncate_label(text))}</text>'
    )
    parts.append("</g>")


def _bar_tooltip(row: dict[str, Any]) -> str:
    lines = [
        f"{row.get('key')}: {row.get('summary')}",
        f"Timeline: {row.get('startDate')} to {row.get('endDate')}",
    ]
    status = row.get("status")
    if status:
        lines.append(f"Status: {status}")
    scope = row.get("scopeRollup")
    if scope:
        issue_count = int(scope.get("issueCount") or float(scope.get("totalWeight") or 0))
        lines.append(f"Scope: {issue_count} issues (Scope links)")
    return "\n".join(lines)


def _is_milestone_row(row: dict[str, Any]) -> bool:
    if bool(row.get("isMeetingGate")):
        return True
    issue_type = str(row.get("issueType") or "").strip().lower()
    if "milestone" in issue_type:
        return True
    summary = str(row.get("summary") or "").upper()
    return "MILESTONE" in summary


def _milestone_icon_url(row: dict[str, Any]) -> str:
    """Return an absolute Jira icon URL for Meeting Gate milestones, if available."""
    if not bool(row.get("isMeetingGate")):
        return ""
    raw = str(row.get("issueTypeIconUrl") or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("/"):
        return f"{JIRA_SERVER}{raw}"
    return f"{JIRA_SERVER}/{raw}"


def _append_timeline_bar(
    parts: list[str],
    *,
    row: dict[str, Any],
    x1: float,
    bar_y: float,
    bar_w: float,
    bar_h: float,
    fill: str,
    opacity: float,
    rx: int = 2,
    scope_overlay_opacity: float = SCOPE_OVERLAY_OPACITY,
) -> None:
    parts.append(f'<g>{_svg_embedded_title(_bar_tooltip(row))}')
    if _is_milestone_row(row):
        cx = x1
        icon_url = _milestone_icon_url(row)
        if icon_url:
            size = max(10.0, min(16.0, bar_h + 4.0))
            y = bar_y + max((bar_h - size) / 2.0, 0.0)
            parts.append(
                f'<image href="{html.escape(icon_url)}" x="{cx - size / 2.0:.1f}" y="{y:.1f}" '
                f'width="{size:.1f}" height="{size:.1f}" preserveAspectRatio="xMidYMid meet"/>'
            )
        else:
            tri_h = max(8.0, min(14.0, bar_h + 4.0))
            tri_w = tri_h
            top = bar_y + max((bar_h - tri_h) / 2.0, 0.0)
            points = (
                f"{cx:.1f},{top:.1f} "
                f"{cx - tri_w / 2.0:.1f},{top + tri_h:.1f} "
                f"{cx + tri_w / 2.0:.1f},{top + tri_h:.1f}"
            )
            parts.append(
                f'<polygon points="{points}" fill="{MILESTONE_TRIANGLE_FILL}" opacity="0.95"/>'
            )
        parts.append("</g>")
        return
    parts.append(
        f'<rect x="{x1:.1f}" y="{bar_y:.1f}" width="{bar_w:.1f}" '
        f'height="{bar_h:.1f}" rx="{rx}" fill="{fill}" opacity="{opacity}"/>'
    )
    scope = row.get("scopeRollup")
    if scope:
        segments = lane_bar_segments(scope, segment_order=timeline_bar_segment_order())
        if segments:
            append_scope_composition_overlay(
                parts,
                rollup=scope,
                segments=segments,
                x0=x1,
                y0=bar_y,
                bar_w=bar_w,
                bar_h=bar_h,
                overlay_opacity=scope_overlay_opacity,
                link_class="block-scope-segment",
            )
    parts.append("</g>")


def _iter_milestone_dependency_edges(phases: list[dict[str, Any]]) -> list[tuple[str, str]]:
    rows_by_key: dict[str, dict[str, Any]] = {}
    edges: list[tuple[str, str]] = []

    for row in _iter_timeline_rows(phases):
        key = str(row.get("key") or "").strip()
        if key:
            rows_by_key[key] = row

    for row in rows_by_key.values():
        blocked_key = str(row.get("key") or "").strip()
        if not blocked_key:
            continue
        for blocker in row.get("blockedByKeys") or []:
            blocker_key = str(blocker or "").strip()
            if blocker_key and blocker_key != blocked_key:
                blocker_row = rows_by_key.get(blocker_key)
                blocked_row = rows_by_key.get(blocked_key)
                if _is_milestone_row(blocked_row or {}) or _is_milestone_row(blocker_row or {}):
                    edges.append((blocker_key, blocked_key))

    return list(dict.fromkeys(edges))


def _append_dependency_connectors(
    parts: list[str],
    *,
    edges: list[tuple[str, str]],
    row_positions: dict[str, tuple[float, float, float]],
) -> None:
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    for blocker_key, blocked_key in edges:
        blocker = row_positions.get(blocker_key)
        blocked = row_positions.get(blocked_key)
        if not blocker or not blocked:
            continue
        blocker_start, blocker_y, blocker_end = blocker
        blocked_start, blocked_y, _blocked_end = blocked

        blocker_is_milestone = abs(blocker_end - blocker_start) < 0.1
        sx = blocker_start if blocker_is_milestone else blocker_end
        ex = blocked_start
        sy = blocker_y
        ey = blocked_y

        dx = ex - sx
        dy = ey - sy
        direction = 1.0 if dx >= 0 else -1.0
        abs_dx = max(6.0, abs(dx))
        # Horizontal runway before/after the curve: fixed minimum travel for visual clarity.
        lead_mag = _clamp(abs_dx * 0.28, DEPENDENCY_MIN_HORIZONTAL_RUN, 64.0)
        lead = lead_mag * direction
        run_start_x = sx + lead
        run_end_x = ex - lead

        # Match sketch intent: horizontal exit -> one easing curve -> straight diagonal -> horizontal entry.
        span = abs(run_end_x - run_start_x)
        tension = _clamp((span * 0.24) + 8.0, 10.0, 30.0)

        join_t = 0.30
        join_x = run_start_x + ((run_end_x - run_start_x) * join_t)
        join_y = sy + (dy * join_t)

        # Make the curve land with a tangent aligned to the straight middle segment.
        seg_dx = run_end_x - join_x
        seg_dy = ey - join_y
        c1x = run_start_x + (direction * tension)
        c1y = sy
        c2x = join_x - (seg_dx * 0.35)
        c2y = join_y - (seg_dy * 0.35)

        path_d = (
            f"M {sx:.1f} {sy:.1f} "
            f"L {run_start_x:.1f} {sy:.1f} "
            f"C {c1x:.1f} {c1y:.1f}, {c2x:.1f} {c2y:.1f}, {join_x:.1f} {join_y:.1f} "
            f"L {run_end_x:.1f} {ey:.1f} "
            f"L {ex:.1f} {ey:.1f}"
        )
        tooltip = f"Dependency: {blocker_key} blocks {blocked_key}"
        parts.append(f'<g>{_svg_embedded_title(tooltip)}')
        parts.append(
            f'<path d="{path_d}" '
            f'stroke="{DEPENDENCY_STROKE}" stroke-width="{DEPENDENCY_STROKE_WIDTH}" '
            f'stroke-linecap="round" stroke-linejoin="round" '
            f'fill="none" marker-end="url(#dep-arrow)"/>'
        )
        parts.append("</g>")


def _package_block_height(package: dict[str, Any]) -> int:
    details = package.get("details") or []
    return STREAM_ROW_HEIGHT + len(details) * DETAIL_ROW_HEIGHT


def _chapter_block_height(chapter: dict[str, Any]) -> int:
    packages = chapter.get("packages") or []
    content = CHAPTER_ROW_HEIGHT + sum(_package_block_height(package) for package in packages)
    return content + 2 * BLOCK_PAD_Y


def _plot_height(phases: list[dict[str, Any]]) -> int:
    if not phases:
        return PHASE_ROW_HEIGHT
    total = 0
    for index, phase in enumerate(phases):
        if index > 0:
            total += PHASE_GAP
        total += PHASE_ROW_HEIGHT
        chapters = phase.get("chapters") or []
        for chapter_index, chapter in enumerate(chapters):
            if chapter_index > 0:
                total += BLOCK_GAP
            total += _chapter_block_height(chapter)
    return total


def _plot_width(span_days: int, *, px_per_day: float = EPIC_CHART_PX_PER_DAY) -> float:
    raw = span_days * px_per_day
    return max(float(QUARTERLY_REPORT_MIN_PLOT_WIDTH), min(float(QUARTERLY_REPORT_MAX_SVG_WIDTH), raw))


def sef_project_plan_timeline_svg(
    payload: dict[str, Any],
    *,
    px_per_day: float = EPIC_CHART_PX_PER_DAY,
) -> str:
    phases = payload.get("phases") or []
    if not phases:
        return '<p class="footnote">No plan blocks. Run fetch_sef_project_plan_timeline.py --write.</p>'

    x_min, x_max = _payload_chart_window(payload)
    span_days = max(1, (x_max - x_min).days)
    plot_h = _plot_height(phases)
    MILESTONE_LABEL_ZONE = 80   # px above plot for stacked milestone labels
    plot_top = CALENDAR_TOP + MILESTONE_LABEL_ZONE
    plot_bottom = plot_top + plot_h
    svg_height = plot_bottom + _svg_x_bottom_margin()
    plot_w = _plot_width(span_days, px_per_day=px_per_day)
    plot_left = _label_column_width(phases)
    plot_right = plot_left + plot_w
    width = plot_right + RIGHT_PAD + MILESTONE_RIGHT_LABEL_PAD

    def x_for(day: date) -> float:
        offset = max(0, min(span_days, (day - x_min).days))
        return plot_left + offset / span_days * plot_w

    def _row_end_x(row: dict[str, Any], x1: float, bar_w: float) -> float:
        return x1 if _is_milestone_row(row) else (x1 + bar_w)

    row_positions: dict[str, tuple[float, float, float]] = {}
    milestone_markers: list[tuple[float, str, date, bool]] = []  # (x, label, day, is_gate)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{svg_height}" '
        f'viewBox="0 0 {width} {svg_height}" preserveAspectRatio="xMinYMin meet" '
        f'role="img" aria-label="SEF integrated project plan timeline">',
        f'<rect x="0" y="0" width="{width}" height="{svg_height}" fill="#ffffff"/>',
        "<defs>"
        f'<clipPath id="sef-plan-label-col">'
        f'<rect x="0" y="{plot_top}" width="{plot_left - 8}" height="{plot_h}"/>'
        f"</clipPath>"
        f'<marker id="dep-arrow" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto" markerUnits="userSpaceOnUse">'
        f'<path d="M 0 0 L 8 4 L 0 8 z" fill="{DEPENDENCY_STROKE}"/>'
        f"</marker></defs>",
    ]

    parts.append(
        f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" '
        f'stroke="{ATL["line"]}" stroke-width="1"/>'
    )
    parts.append(
        f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" '
        f'stroke="{ATL["line"]}" stroke-width="1"/>'
    )

    # Dashed vertical lines at each month start.
    _month = date(x_min.year, x_min.month, 1)
    while _month <= x_max:
        if _month >= x_min:
            _mx = x_for(_month)
            parts.append(
                f'<line x1="{_mx:.1f}" y1="{plot_top}" x2="{_mx:.1f}" y2="{plot_bottom}" '
                f'stroke="#555555" stroke-width="0.6" stroke-dasharray="4 3" opacity="0.5"/>'
            )
        if _month.month == 12:
            _month = date(_month.year + 1, 1, 1)
        else:
            _month = date(_month.year, _month.month + 1, 1)

    _svg_x_axis_labels(
        parts,
        x_min=x_min,
        x_max=x_max,
        plot_bottom=plot_bottom,
        plot_left=plot_left,
        plot_right=plot_right,
        x_for=x_for,
    )

    y_cursor = plot_top
    for phase_index, phase in enumerate(phases):
        if phase_index > 0:
            y_cursor += PHASE_GAP
            parts.append(
                f'<rect class="sef-phase-divider" x="0" y="{y_cursor - PHASE_GAP / 2:.1f}" '
                f'width="{plot_right:.1f}" height="{PHASE_GAP:.1f}" />'
            )

        phase_label = str(phase.get("summary") or phase.get("key") or "")
        phase_key = str(phase.get("key") or "")
        phase_start = date.fromisoformat(str(phase.get("startDate"))[:10])
        phase_end = date.fromisoformat(str(phase.get("endDate"))[:10])

        if phase_key:
            phase_start = date.fromisoformat(str(phase.get("startDate"))[:10])
            phase_end = date.fromisoformat(str(phase.get("endDate"))[:10])
            phase_x1 = x_for(phase_start)
            phase_x2 = x_for(phase_end)
            phase_bar_w = max(phase_x2 - phase_x1, 2.0)
            phase_row_cy = y_cursor + PHASE_ROW_HEIGHT / 2
            phase_bar_y = y_cursor + (PHASE_ROW_HEIGHT - PHASE_BAR_HEIGHT) / 2
            phase_fill = epic_bar_fill(str(phase.get("status") or ""))

            parts.append(f'<g>{_svg_embedded_title(_bar_tooltip(phase))}')
            parts.append(
                f'<rect x="{phase_x1:.1f}" y="{phase_bar_y:.1f}" width="{phase_bar_w:.1f}" '
                f'height="{PHASE_BAR_HEIGHT:.1f}" rx="2" fill="{phase_fill}" opacity="{BAR_OPACITY}"/>'
            )
            parts.append("</g>")
            row_positions[phase_key] = (phase_x1, phase_row_cy, _row_end_x(phase, phase_x1, phase_bar_w))
            _append_label_link(
                parts,
                text=phase_label,
                x=LABEL_PAD_X,
                y_center=phase_row_cy,
                url=f"{JIRA_SERVER}/browse/{html.escape(phase_key)}",
                tooltip=_bar_tooltip(phase),
                font_size=11,
                font_weight="700",
            )
            y_cursor += PHASE_ROW_HEIGHT

        chapters = phase.get("chapters") or []
        for chapter_index, chapter in enumerate(chapters):
            if chapter_index > 0:
                y_cursor += BLOCK_GAP
            block_h = _chapter_block_height(chapter)
            block_y = y_cursor
            y0 = block_y + BLOCK_PAD_Y
            row_cy = y0 + CHAPTER_ROW_HEIGHT / 2

            parts.append(
                f'<rect x="0" y="{block_y:.1f}" width="{plot_right:.1f}" height="{block_h:.1f}" '
                f'fill="none" stroke="{ATL["ink"]}" stroke-width="{BLOCK_BORDER_WIDTH}"/>'
            )

            start_day = date.fromisoformat(str(chapter.get("startDate"))[:10])
            end_day = date.fromisoformat(str(chapter.get("endDate"))[:10])
            x1 = x_for(start_day)
            x2 = x_for(end_day)
            bar_w = max(x2 - x1, 2.0)
            bar_y = y0 + (CHAPTER_ROW_HEIGHT - CHAPTER_BAR_HEIGHT) / 2
            fill = epic_bar_fill(str(chapter.get("status") or ""))
            key = str(chapter.get("key") or "")
            summary = str(chapter.get("summary") or key)

            same_window_as_phase = (
                str(chapter.get("startDate") or "")[:10] == phase_start.isoformat()
                and str(chapter.get("endDate") or "")[:10] == phase_end.isoformat()
            )
            draw_chapter_bar = bool(key) and not (len(chapters) == 1 and same_window_as_phase)
            if draw_chapter_bar:
                _append_timeline_bar(
                    parts,
                    row=chapter,
                    x1=x1,
                    bar_y=bar_y,
                    bar_w=bar_w,
                    bar_h=CHAPTER_BAR_HEIGHT,
                    fill=fill,
                    opacity=BAR_OPACITY,
                    scope_overlay_opacity=SCOPE_OVERLAY_OPACITY,
                )
            if key:
                row_positions[key] = (x1, row_cy, _row_end_x(chapter, x1, bar_w))
                _append_label_link(
                    parts,
                    text=summary,
                    x=LABEL_PAD_X,
                    y_center=row_cy,
                    url=f"{JIRA_SERVER}/browse/{html.escape(key)}",
                    tooltip=_bar_tooltip(chapter),
                )
            else:
                _append_label_text(
                    parts,
                    text=summary,
                    x=LABEL_PAD_X,
                    y_center=row_cy,
                    tooltip=_bar_tooltip(chapter),
                )

            sub_y = y0 + CHAPTER_ROW_HEIGHT
            for pkg_index, package in enumerate(chapter.get("packages") or []):
                # Alternating swimlane background for this package + its details.
                pkg_lane_h = STREAM_ROW_HEIGHT + len(package.get("details") or []) * DETAIL_ROW_HEIGHT
                lane_fill = SWIMLANE_FILLS[pkg_index % len(SWIMLANE_FILLS)]
                parts.append(
                    f'<rect x="0" y="{sub_y:.1f}" width="{plot_right:.1f}" '
                    f'height="{pkg_lane_h:.1f}" fill="{lane_fill}" opacity="0.55"/>'
                )

                sub_cy = sub_y + STREAM_ROW_HEIGHT / 2
                p_start = date.fromisoformat(str(package.get("startDate"))[:10])
                p_end = date.fromisoformat(str(package.get("endDate"))[:10])
                px1 = x_for(p_start)
                px2 = x_for(p_end)
                p_bar_w = max(px2 - px1, 2.0)
                p_bar_y = sub_y + (STREAM_ROW_HEIGHT - STREAM_BAR_HEIGHT) / 2
                p_key = str(package.get("key") or "")
                p_summary = str(package.get("summary") or p_key)
                p_issue_type = str((package.get("issueType") or "")).strip()
                _pkg_kw_fill = _package_keyword_fill(p_summary)
                if _pkg_kw_fill:
                    p_fill = _pkg_kw_fill
                    p_opacity = 0.85
                elif p_issue_type == "Test Cycle":
                    p_fill = TEST_CYCLE_BAR_FILL
                    p_opacity = 0.65
                else:
                    p_fill = epic_bar_fill(str(package.get("status") or ""))
                    p_opacity = SUB_BAR_OPACITY
                _append_timeline_bar(
                    parts,
                    row=package,
                    x1=px1,
                    bar_y=p_bar_y,
                    bar_w=p_bar_w,
                    bar_h=STREAM_BAR_HEIGHT,
                    fill=p_fill,
                    opacity=p_opacity,
                    rx=1,
                    scope_overlay_opacity=SUB_SCOPE_OVERLAY_OPACITY,
                )
                if p_key:
                    row_positions[p_key] = (px1, sub_cy, _row_end_x(package, px1, p_bar_w))
                if _is_milestone_row(package):
                    milestone_markers.append((px1, p_summary, p_start, bool(package.get("isMeetingGate"))))
                _append_label_link(
                    parts,
                    text=p_summary,
                    x=SUB_LABEL_INDENT,
                    y_center=sub_cy,
                    url=f"{JIRA_SERVER}/browse/{html.escape(p_key)}",
                    tooltip=_bar_tooltip(package),
                    font_size=9,
                    font_weight="400",
                    fill=ATL["text_subtle"],
                )
                sub_y += STREAM_ROW_HEIGHT

                for detail in package.get("details") or []:
                    detail_cy = sub_y + DETAIL_ROW_HEIGHT / 2
                    d_start = date.fromisoformat(str(detail.get("startDate"))[:10])
                    d_end = date.fromisoformat(str(detail.get("endDate"))[:10])
                    dx1 = x_for(d_start)
                    dx2 = x_for(d_end)
                    d_bar_w = max(dx2 - dx1, 2.0)
                    d_bar_y = sub_y + (DETAIL_ROW_HEIGHT - DETAIL_BAR_HEIGHT) / 2
                    d_key = str(detail.get("key") or "")
                    d_summary = str(detail.get("summary") or d_key)
                    _kw_fill = _detail_keyword_fill(d_summary)
                    d_fill = _kw_fill or epic_bar_fill(str(detail.get("status") or ""))
                    d_opacity = 0.72 if _kw_fill else DETAIL_BAR_OPACITY
                    _append_timeline_bar(
                        parts,
                        row=detail,
                        x1=dx1,
                        bar_y=d_bar_y,
                        bar_w=d_bar_w,
                        bar_h=DETAIL_BAR_HEIGHT,
                        fill=d_fill,
                        opacity=d_opacity,
                        rx=1,
                        scope_overlay_opacity=DETAIL_SCOPE_OVERLAY_OPACITY,
                    )
                    if d_key:
                        row_positions[d_key] = (dx1, detail_cy, _row_end_x(detail, dx1, d_bar_w))
                    if _is_milestone_row(detail):
                        milestone_markers.append((dx1, d_summary, d_start, bool(detail.get("isMeetingGate"))))
                    _append_label_link(
                        parts,
                        text=d_summary,
                        x=DETAIL_LABEL_INDENT,
                        y_center=detail_cy,
                        url=f"{JIRA_SERVER}/browse/{html.escape(d_key)}",
                        tooltip=_bar_tooltip(detail),
                        font_size=8,
                        font_weight="400",
                        fill=ATL["text_subtle"],
                    )
                    sub_y += DETAIL_ROW_HEIGHT

            y_cursor += block_h

    # Milestone vertical gridlines and stacked labels.
    if milestone_markers:
        LABEL_FONT = 8
        LABEL_LINE_H = 11
        LABEL_ZONE_TOP = CALENDAR_TOP + 4
        LABEL_BUCKET_PX = 32  # minimum px gap before stacking to next row

        # Sort by x so we can assign stacking rows left-to-right.
        sorted_markers = sorted(dict.fromkeys(  # dedupe same x+label+day+kind
            (round(x, 1), lbl, day, is_gate) for x, lbl, day, is_gate in milestone_markers
        ))
        # Assign each marker a row index (0 = topmost) to avoid label overlap.
        row_for: list[int] = []
        row_max_x: list[float] = []  # rightmost x used per row so far
        for mx, mlabel, mday, _is_gate in sorted_markers:
            assigned = False
            short_label = mlabel.split("|")[-1].strip() if "|" in mlabel else mlabel
            short_label = short_label[:30]
            label_text = f"{short_label} ({mday:%d/%m})"
            for r_idx, rmax in enumerate(row_max_x):
                if mx - rmax >= LABEL_BUCKET_PX:
                    row_for.append(r_idx)
                    row_max_x[r_idx] = mx + len(label_text) * 5
                    assigned = True
                    break
            if not assigned:
                row_for.append(len(row_max_x))
                row_max_x.append(mx + len(label_text) * 5)

        for i, (mx, mlabel, mday, is_gate) in enumerate(sorted_markers):
            label_y = LABEL_ZONE_TOP + row_for[i] * LABEL_LINE_H
            line_stroke = "#000000" if is_gate else "#ff6b6b"
            line_opacity = "0.65" if is_gate else "0.7"
            label_fill = "#000000" if is_gate else "#cc2200"
            label_weight = "600" if is_gate else "500"
            # Vertical dashed light-red line.
            parts.append(
                f'<line x1="{mx:.1f}" y1="{plot_top}" x2="{mx:.1f}" y2="{plot_bottom}" '
                f'stroke="{line_stroke}" stroke-width="0.8" stroke-dasharray="4 3" opacity="{line_opacity}"/>'
            )
            # Small tick from label down to plot top.
            parts.append(
                f'<line x1="{mx:.1f}" y1="{label_y + LABEL_LINE_H:.1f}" '
                f'x2="{mx:.1f}" y2="{plot_top}" '
                f'stroke="{line_stroke}" stroke-width="0.6" opacity="0.4"/>'
            )
            # Label text — clip to plot area so it doesn't overflow left.
            short = mlabel.split("|")[-1].strip() if "|" in mlabel else mlabel
            short = short[:30]
            label_text = f"{short} ({mday:%d/%m})"
            parts.append(
                f'<text x="{mx + 2:.1f}" y="{label_y + LABEL_FONT:.1f}" '
                f'font-family="{SVG_FONT}" font-size="{LABEL_FONT}" '
                f'fill="{label_fill}" font-weight="{label_weight}">'
                f'{html.escape(label_text)}</text>'
            )

    today = _chart_today_in_quarter(x_min, x_max)
    if today is not None:
        _append_today_marker(
            parts,
            today=today,
            x_for=x_for,
            plot_top=plot_top,
            plot_bottom=plot_bottom,
        )

    parts.append("</svg>")
    return "".join(parts)


def build_sef_project_plan_report_html(
    payload: dict[str, Any],
    *,
    generated_on: str,
    page_title: str | None = None,
    breadcrumb_nav: str = "",
) -> str:
    title = page_title or str(payload.get("pageTitle") or "SEF | Integrated Project Plan")
    chapter_count = sum(len(phase.get("chapters") or []) for phase in payload.get("phases") or [])
    package_count = sum(
        len(chapter.get("packages") or [])
        for phase in payload.get("phases") or []
        for chapter in phase.get("chapters") or []
    )
    detail_count = sum(
        len(package.get("details") or [])
        for phase in payload.get("phases") or []
        for chapter in phase.get("chapters") or []
        for package in chapter.get("packages") or []
    )
    footnote_parts = [
        f"{chapter_count} schedule chapters",
        f"{package_count} stream packages",
    ]
    if detail_count:
        footnote_parts.append(f"{detail_count} detail items")
    window_start, window_end = _payload_chart_window(payload)
    footnote = (
        f"{', '.join(footnote_parts)} from PDE Block work items "
        f"({window_start.isoformat()} to {window_end.isoformat()}). "
        "Each bar runs from start date through due date."
    )
    chart = sef_project_plan_timeline_svg(payload)
    nav_block = f"\n    {breadcrumb_nav}" if breadcrumb_nav else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(title)}</title>
  <style>{REPORT_CSS}{BREADCRUMB_CSS}{SEF_PROJECT_PLAN_EXTRA_CSS}</style>
</head>
<body>
  <main class="report-shell">{nav_block}
    <header class="report-header">
      <h1>{html.escape(title)}</h1>
      <p class="report-subtitle">Generated {html.escape(generated_on)}</p>
    </header>
    <section class="chart-section">
      <div class="chart-wrap chart-wrap-timeline chart-wrap-sef-plan">{chart}</div>
    </section>
  </main>
</body>
</html>
"""
