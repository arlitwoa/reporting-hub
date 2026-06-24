"""Epic timeline SVG for quarterly dashboard."""

from __future__ import annotations

import html
from datetime import date
from typing import Any

from extensions.twoa_programme.epic_timeline import (
    EPIC_BAR_OPACITY_EARNED,
    EPIC_BAR_OPACITY_NO_SP,
    EPIC_BAR_OPACITY_SCOPE,
    EPIC_CHART_PX_PER_DAY,
    EPIC_LABEL_WIDTH,
    EPIC_ROW_HEIGHT,
    EPIC_SWIMLANE_HEADER,
    EPIC_EC_SQUAD_HEADER,
    build_epic_timeline_rows,
    epic_bar_fill,
    epic_sp_progress_ratio,
    epic_timeline_plot_height,
    epic_timeline_tooltip,
    group_epics_by_lane,
    resolve_epic_timeline_heights,
)
from extensions.twoa_programme.quarterly_dashboard_calendar import _y_ticks
from extensions.twoa_programme.quarterly_dashboard_constants import (
    ATL,
    CHART_AXIS_FONT,
    JIRA_SERVER,
    LANE_DEFAULT_LABELS,
    LANE_STACK_FILL,
    PLOT_HEIGHT,
    SVG_FONT,
    TIP_CHART_GOAL_LINEAR,
    Y_AXIS_LEFT,
)
from extensions.twoa_programme.milestone_scope_chart import (
    append_scope_composition_overlay,
    lane_bar_segments,
)
from extensions.twoa_programme.quarterly_dashboard_links import _browse_link, _fmt_num
from extensions.twoa_programme.quarterly_dashboard_markup import _svg_embedded_title
from extensions.twoa_programme.quarterly_dashboard_svg_core import (
    QUARTERLY_REPORT_DEFAULT_RIGHT_PAD,
    QUARTERLY_REPORT_MAX_EPIC_TIMELINE_SVG_HEIGHT,
    _linear_goal_polyline_points,
    report_plot_width,
    _svg_chart_vertical_markers,
    _svg_sprint_calendar_underlay,
    _svg_x_axis_labels,
    _svg_x_bottom_margin,
)
def _append_epic_timeline_row(
    parts: list[str],
    *,
    epic: dict[str, Any],
    y0: float,
    plot_left: float,
    plot_right: float,
    quarter_start: str,
    quarter_end: str,
    x_for,
    lane_label: str,
    squad_label: str | None = None,
    epic_row_height: float = EPIC_ROW_HEIGHT,
) -> None:
    row_cy = y0 + epic_row_height / 2
    key = str(epic.get("key") or "")
    start_s = str(epic.get("startDate") or quarter_start)[:10]
    end_s = str(epic.get("endDate") or quarter_end)[:10]
    start_day = date.fromisoformat(start_s)
    end_day = date.fromisoformat(end_s)
    x1 = x_for(start_day)
    x2 = x_for(end_day)
    bar_w = max(x2 - x1, 2.0)
    bar_h = epic_row_height * (EPIC_ROW_HEIGHT - 6.0) / EPIC_ROW_HEIGHT
    bar_y = y0 + (epic_row_height - bar_h) / 2
    fill = epic_bar_fill(str(epic.get("status") or ""))
    tip = epic_timeline_tooltip(epic)
    if squad_label:
        tip += f" | {squad_label}"
    if lane_label:
        tip += f" | {lane_label}"
    scope = epic.get("scopeRollup") or {}
    segments = lane_bar_segments(scope) if scope else []
    total_sp = float(epic.get("storyPoints") or 0)
    parts.append(f'<g>{_svg_embedded_title(tip)}')
    if segments:
        parts.append(
            f'<rect x="{x1:.1f}" y="{bar_y:.1f}" width="{bar_w:.1f}" '
            f'height="{bar_h:.1f}" rx="2" fill="{fill}" opacity="{EPIC_BAR_OPACITY_SCOPE}"/>'
        )
        append_scope_composition_overlay(
            parts,
            rollup=scope,
            segments=segments,
            x0=x1,
            y0=bar_y,
            bar_w=bar_w,
            bar_h=bar_h,
            overlay_opacity=0.92,
        )
    elif total_sp > 0:
        parts.append(
            f'<rect x="{x1:.1f}" y="{bar_y:.1f}" width="{bar_w:.1f}" '
            f'height="{bar_h:.1f}" rx="2" fill="{fill}" opacity="{EPIC_BAR_OPACITY_SCOPE}"/>'
        )
        ratio = epic_sp_progress_ratio(epic)
        if ratio > 0:
            earned_w = max(bar_w * ratio, 1.0)
            parts.append(
                f'<rect x="{x1:.1f}" y="{bar_y:.1f}" width="{earned_w:.1f}" '
                f'height="{bar_h:.1f}" rx="2" fill="{fill}" opacity="{EPIC_BAR_OPACITY_EARNED}"/>'
            )
    else:
        parts.append(
            f'<rect x="{x1:.1f}" y="{bar_y:.1f}" width="{bar_w:.1f}" '
            f'height="{bar_h:.1f}" rx="2" fill="{fill}" opacity="{EPIC_BAR_OPACITY_NO_SP}"/>'
        )
    parts.append("</g>")
    browse_url = f"{JIRA_SERVER}/browse/{html.escape(key)}"
    parts.append(
        f'<g>{_svg_embedded_title(tip)}'
        f'<a href="{browse_url}" target="_blank" rel="noopener">'
        f'<text x="{plot_left - 8}" y="{row_cy:.1f}" text-anchor="end" '
        f'dominant-baseline="middle" font-family="{SVG_FONT}" font-size="10" '
        f'fill="{ATL["blue"]}" font-weight="600">{html.escape(key)}</text></a></g>'
    )


def _epic_timeline_layout_height(grouped: dict[str, list[dict[str, Any]]]) -> int:
    """Plot area height (excluding top release band and x-axis)."""
    rows = build_epic_timeline_rows(grouped, lane_labels=LANE_DEFAULT_LABELS)
    return epic_timeline_plot_height(rows)


def _epic_timeline_svg(
    epics: list[dict[str, Any]],
    *,
    quarter_start: str,
    quarter_end: str,
    sprint_bands: list[dict[str, Any]] | None = None,
    releases: list[dict[str, Any]] | None = None,
    milestones: list[dict[str, Any]] | None = None,
    px_per_day: float = EPIC_CHART_PX_PER_DAY,
) -> str:
    """Gantt-style epic rows grouped by lane swimlanes (same slices as scope table)."""
    if not epics:
        return '<p class="footnote">No epics in timeline. Run fetch_epic_timeline.py --write.</p>'

    grouped = group_epics_by_lane(epics)
    timeline_rows = build_epic_timeline_rows(grouped, lane_labels=LANE_DEFAULT_LABELS)
    plot_top = 56
    bottom_margin = _svg_x_bottom_margin()
    heights = resolve_epic_timeline_heights(
        timeline_rows,
        plot_top=plot_top,
        bottom_margin=bottom_margin,
        max_svg_height=QUARTERLY_REPORT_MAX_EPIC_TIMELINE_SVG_HEIGHT,
    )
    plot_h = heights["plot_h"]
    epic_row_height = heights["epic_row"]
    swimlane_header = heights["swimlane"]
    squad_header = heights["squad"]
    if plot_h == 0:
        return '<p class="footnote">No epics with lane assignment. Run fetch_epic_timeline.py --write.</p>'

    release_label_anchor = plot_top - 6
    plot_bottom = plot_top + plot_h
    svg_height = int(round(plot_bottom + bottom_margin))

    x_min = date.fromisoformat(quarter_start)
    x_max = date.fromisoformat(quarter_end)
    span_days = (x_max - x_min).days or 1
    plot_w = report_plot_width(
        span_days,
        px_per_day=px_per_day,
        plot_left=EPIC_LABEL_WIDTH,
        plot_right_pad=QUARTERLY_REPORT_DEFAULT_RIGHT_PAD,
    )
    plot_left = EPIC_LABEL_WIDTH
    plot_right = plot_left + plot_w
    width = plot_right + QUARTERLY_REPORT_DEFAULT_RIGHT_PAD

    def x_for(day: date) -> float:
        offset = max(0, min(span_days, (day - x_min).days))
        return plot_left + offset / span_days * plot_w

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{svg_height}" '
        f'viewBox="0 0 {width} {svg_height}" preserveAspectRatio="xMinYMin meet" '
        f'role="img" aria-label="Epic delivery timeline by lane">',
        f'<rect x="0" y="0" width="{width}" height="{svg_height}" fill="#ffffff"/>',
    ]

    _svg_sprint_calendar_underlay(
        parts,
        sprint_bands=sprint_bands,
        plot_top=plot_top,
        plot_bottom=plot_bottom,
        plot_h=plot_h,
        x_for=x_for,
        x_min=x_min,
        x_max=x_max,
    )

    parts.append(
        f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" '
        f'stroke="{ATL["line"]}" stroke-width="1"/>'
    )
    parts.append(
        f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" '
        f'stroke="{ATL["line"]}" stroke-width="1"/>'
    )

    y_cursor = plot_top
    row_index = 0

    def draw_lane_header(lane_key: str, label: str) -> None:
        nonlocal y_cursor
        lane_fill = LANE_STACK_FILL.get(lane_key, ATL["neutral"])
        header_y1 = y_cursor
        header_y2 = y_cursor + swimlane_header
        parts.append(
            f'<rect x="0" y="{header_y1:.1f}" width="{width}" height="{swimlane_header:.1f}" '
            f'fill="{lane_fill}" opacity="0.12"/>'
        )
        parts.append(
            f'<rect x="{plot_left}" y="{header_y1:.1f}" width="{plot_w}" height="{swimlane_header:.1f}" '
            f'fill="{lane_fill}" opacity="0.08"/>'
        )
        parts.append(
            f'<text x="12" y="{header_y1 + swimlane_header * 0.68:.1f}" font-family="{SVG_FONT}" font-size="11" '
            f'fill="{ATL["ink"]}" font-weight="700">{html.escape(label)}</text>'
        )
        parts.append(
            f'<line x1="0" y1="{header_y2:.1f}" x2="{width}" y2="{header_y2:.1f}" '
            f'stroke="{ATL["line"]}" stroke-width="1"/>'
        )
        y_cursor = header_y2

    def draw_ec_squad_header(label: str) -> None:
        nonlocal y_cursor
        lane_fill = LANE_STACK_FILL["educationCloud"]
        header_y1 = y_cursor
        header_y2 = y_cursor + squad_header
        parts.append(
            f'<rect x="0" y="{header_y1:.1f}" width="{width}" height="{squad_header:.1f}" '
            f'fill="{lane_fill}" opacity="0.06"/>'
        )
        parts.append(
            f'<text x="28" y="{header_y1 + squad_header * 0.72:.1f}" font-family="{SVG_FONT}" font-size="10" '
            f'fill="{ATL["text_subtle"]}" font-weight="600">{html.escape(label)}</text>'
        )
        parts.append(
            f'<line x1="{plot_left}" y1="{header_y2:.1f}" x2="{width}" y2="{header_y2:.1f}" '
            f'stroke="{ATL["grid"]}" stroke-width="1" opacity="0.8"/>'
        )
        y_cursor = header_y2

    row_height_by_kind = {
        "lane": swimlane_header,
        "squad": squad_header,
        "epic": epic_row_height,
    }

    for row in timeline_rows:
        kind = row["kind"]
        if kind == "lane":
            draw_lane_header(str(row["lane_key"]), str(row["label"]))
            continue
        if kind == "squad":
            draw_ec_squad_header(str(row["label"]))
            continue

        epic = row["epic"]
        lane_label = LANE_DEFAULT_LABELS.get(str(row["lane_key"]), str(row["lane_key"]))
        squad_label = row.get("squad_label")
        y0 = y_cursor
        _append_epic_timeline_row(
            parts,
            epic=epic,
            y0=y0,
            plot_left=plot_left,
            plot_right=plot_right,
            quarter_start=quarter_start,
            quarter_end=quarter_end,
            x_for=x_for,
            lane_label=lane_label,
            squad_label=str(squad_label) if squad_label else None,
            epic_row_height=epic_row_height,
        )
        if row_index > 0 and row_index % 2 == 0:
            parts.append(
                f'<line x1="{plot_left}" y1="{y0:.1f}" x2="{plot_right}" y2="{y0:.1f}" '
                f'stroke="{ATL["grid"]}" stroke-width="1" opacity="0.6"/>'
            )
        y_cursor += row_height_by_kind["epic"]
        row_index += 1

    _svg_chart_vertical_markers(
        parts,
        releases=releases,
        milestones=milestones,
        plot_top=plot_top,
        plot_bottom=plot_bottom,
        x_for=x_for,
        x_min=x_min,
        x_max=x_max,
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
    parts.append("</svg>")
    return "".join(parts)


def _burn_svg(
    daily: list[dict],
    *,
    planned: float | None,
    quarter_start: str,
    quarter_end: str,
    goal_target: str | None = None,
    as_of: str | None = None,
    sprint_bands: list[dict[str, Any]] | None = None,
    releases: list[dict[str, Any]] | None = None,
    milestones: list[dict[str, Any]] | None = None,
    width: int | None = None,
    height: int | None = None,
    px_per_day: float = 11.0,
) -> str:
    from extensions.twoa_programme.quarterly_reporting import (
        extend_daily_burn_to_as_of,
        resolve_chart_as_of,
    )

    chart_as_of = resolve_chart_as_of(as_of, quarter_end=quarter_end).isoformat()
    daily = extend_daily_burn_to_as_of(daily, chart_as_of, quarter_end=quarter_end)
    if not daily:
        return '<p class="footnote">No deploy-earned daily series yet. Run deploy_burn.py --write.</p>'

    plot_top = 56
    release_label_anchor = plot_top - 6
    plot_bottom = plot_top + PLOT_HEIGHT
    svg_height = height or (plot_bottom + _svg_x_bottom_margin())

    x_min = date.fromisoformat(quarter_start)
    x_max = date.fromisoformat(quarter_end)
    goal_target_day = date.fromisoformat(str(goal_target or quarter_end)[:10])
    span_days = (x_max - x_min).days or 1
    plot_left, plot_right_margin = Y_AXIS_LEFT, QUARTERLY_REPORT_DEFAULT_RIGHT_PAD
    plot_w = report_plot_width(
        span_days,
        px_per_day=px_per_day,
        plot_left=plot_left,
        plot_right_pad=plot_right_margin,
    )
    width = width or plot_left + plot_w + plot_right_margin
    plot_right = plot_left + plot_w
    plot_h = PLOT_HEIGHT

    def x_for(day: date) -> float:
        offset = max(0, min(span_days, (day - x_min).days))
        return plot_left + offset / span_days * plot_w

    dates = [date.fromisoformat(row["date"]) for row in daily]
    values = [float(row["cumulative_story_points"]) for row in daily]
    tick_top = max(values[-1], planned or 0.0, 1.0)
    y_max = tick_top * 1.08

    def y_pos(v: float) -> float:
        return plot_bottom - (plot_bottom - plot_top) * v / y_max

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{svg_height}" '
        f'viewBox="0 0 {width} {svg_height}" preserveAspectRatio="xMinYMin meet" '
        f'role="img" aria-label="Cumulative deploy-earned story points">',
        f'<rect x="0" y="0" width="{width}" height="{svg_height}" fill="#ffffff"/>',
    ]

    _svg_sprint_calendar_underlay(
        parts,
        sprint_bands=sprint_bands,
        plot_top=plot_top,
        plot_bottom=plot_bottom,
        plot_h=plot_h,
        x_for=x_for,
        x_min=x_min,
        x_max=x_max,
    )

    for tick in _y_ticks(tick_top):
        y = y_pos(tick)
        parts.append(
            f'<line x1="{plot_left}" y1="{y:.1f}" x2="{plot_right}" y2="{y:.1f}" '
            f'stroke="{ATL["grid"]}" stroke-width="1"/>'
        )
        label = f"{int(tick)}" if tick == int(tick) else f"{tick:.1f}"
        parts.append(
            f'<text x="{plot_left - 10}" y="{y + 5:.1f}" text-anchor="end" '
            f'font-family="{SVG_FONT}" font-size="{CHART_AXIS_FONT}" fill="{ATL["text_subtle"]}" '
            f'font-weight="600">'
            f'{html.escape(label)}</text>'
        )

    parts.append(
        f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" stroke="{ATL["line"]}"/>'
    )
    parts.append(
        f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" stroke="{ATL["line"]}"/>'
    )
    parts.append(
        f'<text x="22" y="{plot_top + plot_h / 2:.0f}" transform="rotate(-90 22 {plot_top + plot_h / 2:.0f})" '
        f'text-anchor="middle" font-family="{SVG_FONT}" font-size="{CHART_AXIS_FONT}" fill="{ATL["text_subtle"]}" '
        f'font-weight="600">'
        f"Story points</text>"
    )

    if planned is not None:
        ideal_pts = _linear_goal_polyline_points(
            x_min=x_min,
            x_max=x_max,
            goal_target=goal_target_day,
            planned=float(planned),
            x_for=x_for,
            y_pos=y_pos,
        )
        parts.append(
            f'<g>{_svg_embedded_title(TIP_CHART_GOAL_LINEAR.format(target=goal_target_day.isoformat()))}'
            f'<polyline fill="none" stroke="{ATL["neutral"]}" stroke-width="2" '
            f'stroke-dasharray="6 4" points="{" ".join(ideal_pts)}"/>'
            f"</g>"
        )

    points = " ".join(f"{x_for(d):.1f},{y_pos(v):.1f}" for d, v in zip(dates, values, strict=False))
    parts.append(
        f'<polyline fill="none" stroke="{ATL["blue"]}" stroke-width="2.5" points="{points}"/>'
    )

    _svg_chart_vertical_markers(
        parts,
        releases=releases,
        milestones=milestones,
        plot_top=plot_top,
        plot_bottom=plot_bottom,
        x_for=x_for,
        x_min=x_min,
        x_max=x_max,
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

    parts.append("</svg>")
    return "".join(parts)


