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
from extensions.twoa_programme.quarterly_dashboard_svg_core import (
    QUARTERLY_REPORT_MAX_SVG_WIDTH,
    QUARTERLY_REPORT_MIN_PLOT_WIDTH,
    _append_today_marker,
    _chart_today_in_quarter,
    _svg_x_axis_labels,
    _svg_x_bottom_margin,
    _today_legend_key_row,
)
from extensions.twoa_programme.sef_project_plan_reporting import (
    SefProjectPlanReportingConfig,
    load_phase_hub_keys,
    load_sef_project_plan_reporting_config,
)

START_DATE_FIELD = "customfield_10015"

CHAPTER_ROW_HEIGHT = 28
PHASE_ROW_HEIGHT = 32
STREAM_ROW_HEIGHT = 18
DETAIL_ROW_HEIGHT = 16
LABEL_WIDTH = 280
RIGHT_PAD = 24
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
BLOCK_BORDER_WIDTH = 0.75
PHASE_GAP = 20
CHART_WINDOW_PADDING_DAYS = 14

SEF_PROJECT_PLAN_EXTRA_CSS = """
.chart-wrap-sef-plan.chart-wrap-timeline {
  max-height: none;
  overflow-x: auto;
  overflow-y: visible;
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
    starts: list[date] = []
    ends: list[date] = []
    for row in _iter_timeline_rows(phases):
        start_raw = row.get("startDate")
        end_raw = row.get("endDate")
        if start_raw:
            starts.append(date.fromisoformat(str(start_raw)[:10]))
        if end_raw:
            ends.append(date.fromisoformat(str(end_raw)[:10]))
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


def fetch_sef_project_plan_timeline(
    adapter: "AtlassianAdapter",
    config: SefProjectPlanReportingConfig,
) -> dict[str, Any]:
    fallback_start = date.fromisoformat(config.chart_window_start)
    fallback_end = date.fromisoformat(config.chart_window_end)
    start_field = START_DATE_FIELD
    fields = ["summary", "status", "issuetype", "created", "duedate", start_field]
    hub_keys = load_phase_hub_keys(config)
    phases: list[dict[str, Any]] = []

    for hub_key in hub_keys:
        hub = adapter.http.get_json(
            f"/rest/api/3/issue/{hub_key}",
            params={"fields": ",".join(fields)},
        )
        hub_row = _issue_timeline_row(
            hub,
            fallback_start=fallback_start,
            fallback_end=fallback_end,
        )
        chapters_raw = _fetch_children(
            adapter,
            parent_key=hub_key,
            issue_type=config.chapter_issue_type,
            fields=fields,
        )
        chapters: list[dict[str, Any]] = []
        for chapter_issue in chapters_raw:
            chapter_row = _issue_timeline_row(
                chapter_issue,
                fallback_start=fallback_start,
                fallback_end=fallback_end,
            )
            packages_raw = _fetch_children(
                adapter,
                parent_key=str(chapter_issue["key"]),
                issue_type=config.package_issue_type,
                fields=fields,
            )
            packages: list[dict[str, Any]] = []
            for package_issue in packages_raw:
                package_row = _issue_timeline_row(
                    package_issue,
                    fallback_start=fallback_start,
                    fallback_end=fallback_end,
                )
                details_raw = _fetch_children(
                    adapter,
                    parent_key=str(package_issue["key"]),
                    issue_type=config.detail_issue_type,
                    fields=fields,
                )
                package_row["details"] = [
                    _issue_timeline_row(
                        detail_issue,
                        fallback_start=fallback_start,
                        fallback_end=fallback_end,
                    )
                    for detail_issue in details_raw
                ]
                packages.append(package_row)
            chapter_row["packages"] = packages
            chapters.append(chapter_row)
        hub_row["chapters"] = chapters
        phases.append(hub_row)

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
        "phases": phases,
    }


def _truncate_label(text: str, max_chars: int = LABEL_MAX_CHARS) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max_chars - 1]}…"


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


def _bar_tooltip(row: dict[str, Any]) -> str:
    lines = [
        f"{row.get('key')}: {row.get('summary')}",
        f"Timeline: {row.get('startDate')} to {row.get('endDate')}",
    ]
    status = row.get("status")
    if status:
        lines.append(f"Status: {status}")
    return "\n".join(lines)


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
        for chapter_index, chapter in enumerate(phase.get("chapters") or []):
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
    plot_top = CALENDAR_TOP
    plot_bottom = plot_top + plot_h
    svg_height = plot_bottom + _svg_x_bottom_margin()
    plot_w = _plot_width(span_days, px_per_day=px_per_day)
    plot_left = LABEL_WIDTH
    plot_right = plot_left + plot_w
    width = plot_right + RIGHT_PAD

    def x_for(day: date) -> float:
        offset = max(0, min(span_days, (day - x_min).days))
        return plot_left + offset / span_days * plot_w

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{svg_height}" '
        f'viewBox="0 0 {width} {svg_height}" preserveAspectRatio="xMinYMin meet" '
        f'role="img" aria-label="SEF integrated project plan timeline">',
        f'<rect x="0" y="0" width="{width}" height="{svg_height}" fill="#ffffff"/>',
        "<defs>"
        f'<clipPath id="sef-plan-label-col">'
        f'<rect x="0" y="{plot_top}" width="{plot_left - 8}" height="{plot_h}"/>'
        f"</clipPath></defs>",
    ]

    parts.append(
        f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" '
        f'stroke="{ATL["line"]}" stroke-width="1"/>'
    )
    parts.append(
        f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" '
        f'stroke="{ATL["line"]}" stroke-width="1"/>'
    )
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
        if phase_key:
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

        for chapter_index, chapter in enumerate(phase.get("chapters") or []):
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
            label = summary

            parts.append(f'<g>{_svg_embedded_title(_bar_tooltip(chapter))}')
            parts.append(
                f'<rect x="{x1:.1f}" y="{bar_y:.1f}" width="{bar_w:.1f}" '
                f'height="{CHAPTER_BAR_HEIGHT:.1f}" rx="2" fill="{fill}" opacity="{BAR_OPACITY}"/>'
            )
            parts.append("</g>")

            browse_url = f"{JIRA_SERVER}/browse/{html.escape(key)}"
            _append_label_link(
                parts,
                text=label,
                x=LABEL_PAD_X,
                y_center=row_cy,
                url=browse_url,
                tooltip=_bar_tooltip(chapter),
            )

            sub_y = y0 + CHAPTER_ROW_HEIGHT
            for package in chapter.get("packages") or []:
                sub_cy = sub_y + STREAM_ROW_HEIGHT / 2
                p_start = date.fromisoformat(str(package.get("startDate"))[:10])
                p_end = date.fromisoformat(str(package.get("endDate"))[:10])
                px1 = x_for(p_start)
                px2 = x_for(p_end)
                p_bar_w = max(px2 - px1, 2.0)
                p_bar_y = sub_y + (STREAM_ROW_HEIGHT - STREAM_BAR_HEIGHT) / 2
                p_fill = epic_bar_fill(str(package.get("status") or ""))
                p_key = str(package.get("key") or "")
                p_summary = str(package.get("summary") or p_key)
                parts.append(f'<g>{_svg_embedded_title(_bar_tooltip(package))}')
                parts.append(
                    f'<rect x="{px1:.1f}" y="{p_bar_y:.1f}" width="{p_bar_w:.1f}" '
                    f'height="{STREAM_BAR_HEIGHT:.1f}" rx="1" fill="{p_fill}" '
                    f'opacity="{SUB_BAR_OPACITY}"/>'
                )
                parts.append("</g>")
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
                    d_fill = epic_bar_fill(str(detail.get("status") or ""))
                    d_key = str(detail.get("key") or "")
                    d_summary = str(detail.get("summary") or d_key)
                    parts.append(f'<g>{_svg_embedded_title(_bar_tooltip(detail))}')
                    parts.append(
                        f'<rect x="{dx1:.1f}" y="{d_bar_y:.1f}" width="{d_bar_w:.1f}" '
                        f'height="{DETAIL_BAR_HEIGHT:.1f}" rx="1" fill="{d_fill}" '
                        f'opacity="{DETAIL_BAR_OPACITY}"/>'
                    )
                    parts.append("</g>")
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


def sef_project_plan_key_html() -> str:
    open_fill = EPIC_STATUS_FILL["open"]
    done_fill = EPIC_STATUS_FILL["done"]
    active_fill = EPIC_STATUS_FILL["active"]
    return (
        '<div class="chart-key">'
        '<p class="chart-key-title"><strong>Key</strong></p>'
        '<div class="chart-key-row">'
        f'<span class="legend-swatch" style="background:{open_fill};opacity:{BAR_OPACITY}"></span> '
        "Phase bar (Block Level Two): programme phase envelope (e.g. PDE-4072 Phase 1 HCM and Payroll)"
        "</div>"
        '<div class="chart-key-row">'
        f'<span class="legend-swatch" style="background:{open_fill};opacity:{BAR_OPACITY}"></span> '
        "Chapter bar (Block Level One): schedule window for the phase chapter"
        "</div>"
        '<div class="chart-key-row">'
        f'<span class="legend-swatch" style="background:{open_fill};opacity:{SUB_BAR_OPACITY}"></span> '
        "Stream bar (Block Level Zero): work package within the chapter (same colour, lighter)"
        "</div>"
        '<div class="chart-key-row">'
        f'<span class="legend-swatch" style="background:{open_fill};opacity:{DETAIL_BAR_OPACITY}"></span> '
        "Detail bar (Block Level Minus One): optional sub-item under a stream (same colour, lightest)"
        "</div>"
        '<div class="chart-key-row">'
        "Bar colour reflects Jira status: "
        f'<span class="legend-swatch" style="background:{done_fill};opacity:{BAR_OPACITY}"></span> Done '
        f'<span class="legend-swatch" style="background:{open_fill};opacity:{BAR_OPACITY}"></span> To Do '
        f'<span class="legend-swatch" style="background:{active_fill};opacity:{BAR_OPACITY}"></span> In progress'
        "</div>"
        f'<div class="chart-key-row">{_today_legend_key_row()}</div>'
        "</div>"
    )


def build_sef_project_plan_report_html(
    payload: dict[str, Any],
    *,
    generated_on: str,
    page_title: str | None = None,
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

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(title)}</title>
  <style>{REPORT_CSS}{SEF_PROJECT_PLAN_EXTRA_CSS}</style>
</head>
<body>
  <main class="report">
    <header class="report-header">
      <h1>{html.escape(title)}</h1>
      <p class="report-meta">Generated {html.escape(generated_on)}</p>
    </header>
    <section class="chart-section">
      <h1>Project plan timeline</h1>
      <p class="footnote">{html.escape(footnote)}</p>
      <div class="chart-wrap chart-wrap-timeline chart-wrap-sef-plan">{chart}</div>
      {sef_project_plan_key_html()}
    </section>
  </main>
</body>
</html>
"""
