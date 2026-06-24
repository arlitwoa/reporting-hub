"""Lane burn and scope coverage SVG/HTML for quarterly dashboard."""

from __future__ import annotations

import html
from datetime import date
from typing import Any

from extensions.twoa_programme.quarterly_dashboard_constants import (
    ATL,
    CHART_AXIS_FONT,
    LANE_DEFAULT_LABELS,
    LANE_ORDER,
    LANE_PLOT_HEIGHT,
    LANE_STACK_FILL,
    LANE_STACK_OPACITY,
    SVG_FONT,
    TIP_BREAKDOWN_SUM,
    TIP_CHART_LANE_GOAL,
    TIP_CHART_SCOPE_GOAL,
    TIP_EC_SQUAD_SLICE,
    TIP_EARNED_SLICE,
    TIP_GLOBAL_EARNED,
    TIP_GOAL_SP,
    TIP_PLANNED_QUARTER,
    TIP_PLANNED_SLICE,
    TIP_UNASSIGNED_SLICE,
    TIP_UNPOINTED,
    TIP_UNPOINTED_SLICE,
    Y_AXIS_LEFT,
)
from extensions.twoa_programme.quarterly_dashboard_data import (
    _education_cloud_squad_data,
    _education_cloud_squad_slice_rows,
    _earned_by_ec_squad,
    _lane_planned_goals,
    _total_scope_planned,
)
from extensions.twoa_programme.quarterly_dashboard_markup import (
    _projected_release_display_name,
    _unpointed_metrics,
)
from extensions.twoa_programme.quarterly_dashboard_links import (
    _browse_link,
    _filter_link,
    _fmt_num,
    _jql_link,
    _lane_label_link,
    _lane_scope_jql,
)
from extensions.twoa_programme.quarterly_dashboard_markup import (
    _goal_pace_tip,
    _meta_card,
    _section_l2_html,
    _section_l2_link,
    _svg_embedded_title,
    _td,
    _th,
    _unpointed_cell,
)
from extensions.twoa_programme.quarterly_dashboard_calendar import _y_ticks
from extensions.twoa_programme.quarterly_dashboard_svg_core import (
    QUARTERLY_REPORT_DEFAULT_RIGHT_PAD,
    _aligned_lane_cumulative,
    _linear_goal_polyline_points,
    _lane_chart_key_html,
    report_plot_width,
    _resolve_chart_calendar,
    _svg_chart_vertical_markers,
    _svg_sprint_calendar_underlay,
    _svg_x_axis_labels,
    _svg_x_bottom_margin,
    _visible_chart_milestones,
)
def _lane_burn_stacked_svg(
    burn: dict,
    *,
    quarter_start: str,
    quarter_end: str,
    goal_target: str | None = None,
    as_of: str | None = None,
    goal: dict | None = None,
    sprint_bands: list[dict[str, Any]] | None = None,
    releases: list[dict[str, Any]] | None = None,
    milestones: list[dict[str, Any]] | None = None,
    width: int | None = None,
    px_per_day: float = 11.0,
) -> str:
    from extensions.twoa_programme.quarterly_reporting import (
        extend_daily_burn_to_as_of,
        resolve_chart_as_of,
    )

    global_daily = burn.get("combinedDaily") or []
    chart_as_of = resolve_chart_as_of(as_of, quarter_end=quarter_end).isoformat()
    global_daily = extend_daily_burn_to_as_of(global_daily, chart_as_of, quarter_end=quarter_end)
    lanes = burn.get("lanes") or {}
    if not global_daily:
        return '<p class="footnote">No lane burn series yet. Run deploy_burn.py --write.</p>'

    dates, lane_series = _aligned_lane_cumulative(lanes, global_daily)
    if not dates:
        return '<p class="footnote">No lane burn series yet. Run deploy_burn.py --write.</p>'

    plot_top = 56
    release_label_anchor = plot_top - 6
    plot_bottom = plot_top + LANE_PLOT_HEIGHT
    svg_height = plot_bottom + _svg_x_bottom_margin()

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
    plot_h = LANE_PLOT_HEIGHT
    total_scope_planned = _total_scope_planned(goal)

    def x_for(day: date) -> float:
        offset = max(0, min(span_days, (day - x_min).days))
        return plot_left + offset / span_days * plot_w

    global_values = [float(row["cumulative_story_points"]) for row in global_daily]
    tick_top = max(
        global_values[-1] if global_values else 0.0,
        total_scope_planned or 0.0,
        1.0,
    )
    y_max = tick_top * 1.08

    def y_pos(v: float) -> float:
        return plot_bottom - (plot_bottom - plot_top) * v / y_max

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{svg_height}" '
        f'viewBox="0 0 {width} {svg_height}" preserveAspectRatio="xMinYMin meet" '
        f'role="img" aria-label="Cumulative deploy-earned story points by lane">',
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
            f'font-weight="600">{html.escape(label)}</text>'
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
        f'font-weight="600">Story points</text>'
    )

    if total_scope_planned is not None and total_scope_planned > 0:
        total_pts = _linear_goal_polyline_points(
            x_min=x_min,
            x_max=x_max,
            goal_target=goal_target_day,
            planned=total_scope_planned,
            x_for=x_for,
            y_pos=y_pos,
        )
        parts.append(
            f'<g>{_svg_embedded_title(TIP_CHART_SCOPE_GOAL.format(target=goal_target_day.isoformat()))}'
            f'<polyline fill="none" stroke="{ATL["neutral"]}" stroke-width="2" '
            f'stroke-dasharray="6 4" points="{" ".join(total_pts)}"/>'
            f"</g>"
        )

    n = len(dates)
    for lane_key in LANE_ORDER:
        if lane_key not in lane_series:
            continue
        lane_vals = lane_series[lane_key]
        lower = [0.0] * n
        for below in LANE_ORDER:
            if below == lane_key:
                break
            if below in lane_series:
                lower = [lower[i] + lane_series[below][i] for i in range(n)]
        top = [lower[i] + lane_vals[i] for i in range(n)]
        if max(top) <= 0:
            continue
        top_pts = " ".join(f"{x_for(dates[i]):.1f},{y_pos(top[i]):.1f}" for i in range(n))
        bot_pts = " ".join(
            f"{x_for(dates[i]):.1f},{y_pos(lower[i]):.1f}" for i in range(n - 1, -1, -1)
        )
        fill = LANE_STACK_FILL[lane_key]
        parts.append(
            f'<polygon points="{top_pts} {bot_pts}" fill="{fill}" opacity="{LANE_STACK_OPACITY}" '
            f'stroke="{fill}" stroke-width="0.5"/>'
        )

    global_pts = " ".join(
        f"{x_for(dates[i]):.1f},{y_pos(global_values[i]):.1f}" for i in range(len(global_values))
    )
    parts.append(
        f'<polyline fill="none" stroke="{ATL["blue"]}" stroke-width="2.5" points="{global_pts}"/>'
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


def _scope_coverage_section(
    status: dict,
    burn: dict,
    goal: dict | None,
    *,
    sprint_bands: list[dict[str, Any]] | None = None,
    releases: list[dict[str, Any]] | None = None,
    milestones: list[dict[str, Any]] | None = None,
) -> str:
    """Scope coverage: stacked lane burn chart, planned vs earned table, reconciliation cards."""
    coverage = status.get("scopeCoverage") or {}
    by_scope = (goal or {}).get("plannedStoryPointsByScope") or {}
    scope_meta = burn.get("scope") or {}
    quarter_filter = coverage.get("quarterFilter") or scope_meta.get("quarterFilter", "smart-current-quarter")
    global_earned = coverage.get("globalEarnedStoryPoints", status.get("earnedStoryPoints"))
    lane_sum = coverage.get("laneBreakdownSum")
    goal_total = status.get("plannedStoryPoints")
    in_quarter_planned = (by_scope.get("inGlobalQuarter") or {}).get("plannedStoryPoints")

    lane_order = tuple((key, LANE_DEFAULT_LABELS[key]) for key in LANE_ORDER)
    unpointed_total, unpointed_jql, unpointed_issue_keys, unpointed_by_lane = _unpointed_metrics(goal)
    rows = ""
    for key, default_label in lane_order:
        lane_burn = (burn.get("lanes") or {}).get(key) or {}
        label = default_label
        earned = lane_burn.get("totalStoryPointsEarned")
        if earned is None and key == "unassigned":
            earned = coverage.get("unassignedEarnedStoryPoints")
        planned_slice = (by_scope.get(key) or {}).get("plannedStoryPoints")
        scope_jql = _lane_scope_jql(burn, goal, key) or ""
        planned_jql = (by_scope.get(key) or {}).get("jql") or scope_jql
        slice_inner = _lane_label_link(burn, goal, key, label)
        if key == "unassigned":
            slice_cell = _td(
                f'<abbr title="{html.escape(TIP_UNASSIGNED_SLICE, quote=True)}" class="metric-tip">'
                f"{slice_inner}</abbr>"
            )
        else:
            slice_cell = _td(slice_inner)
        planned_cell = (
            _jql_link(str(planned_jql), _fmt_num(planned_slice))
            if planned_jql and planned_slice is not None
            else _fmt_num(planned_slice)
        )
        earned_cell = (
            _jql_link(scope_jql, _fmt_num(earned))
            if scope_jql and earned is not None
            else _fmt_num(earned)
        )
        lane_unpointed = (unpointed_by_lane.get(key) or {}).get("count")
        lane_unpointed_jql = (unpointed_by_lane.get(key) or {}).get("jql")
        lane_unpointed_keys = (unpointed_by_lane.get(key) or {}).get("issueKeys")
        unpointed_cell = _unpointed_cell(
            lane_unpointed,
            lane_unpointed_jql,
            issue_keys=lane_unpointed_keys,
        )
        has_activity = (
            (planned_slice is not None and float(planned_slice) > 0)
            or (earned is not None and float(earned) > 0)
        )
        row_class = "" if has_activity or key != "unassigned" else ' class="slice-inactive"'
        rows += (
            f"<tr{row_class}>"
            f"{slice_cell}"
            + _td(planned_cell, num=True)
            + _td(earned_cell, num=True)
            + _td(unpointed_cell, num=True)
            + "</tr>"
        )
        if key == "educationCloud":
            rows += _education_cloud_squad_slice_rows(
                burn,
                goal,
                quarter_filter=quarter_filter,
            )

    goal_initiative = (goal or {}).get("initiativeKey") or status.get("goalInitiativeKey") or "EPCE-3897"
    global_burn_jql = scope_meta.get("globalBurnJql") or f"filter = {quarter_filter}"
    global_scope_jql = scope_meta.get("globalScopeJql") or global_burn_jql
    goal_dd = (
        _browse_link(goal_initiative, _fmt_num(goal_total))
        if goal_total is not None
        else _fmt_num(goal_total)
    )
    planned_dd = (
        _jql_link(global_scope_jql, _fmt_num(in_quarter_planned))
        if in_quarter_planned is not None
        else _fmt_num(in_quarter_planned)
    )
    earned_dd = (
        _jql_link(global_burn_jql, _fmt_num(global_earned))
        if global_earned is not None
        else _fmt_num(global_earned)
    )

    lane_chart = _lane_burn_stacked_svg(
        burn,
        quarter_start=status.get("quarterStart", ""),
        quarter_end=status.get("quarterEnd", ""),
        goal_target=status.get("goalTargetDate"),
        as_of=status.get("asOf"),
        goal=goal,
        sprint_bands=sprint_bands,
        releases=releases,
        milestones=milestones,
    )

    section_title = (
        _section_l2_link(global_scope_jql, "Story Points Achieved by Lane")
        if global_scope_jql
        else _section_l2_html("Story Points Achieved by Lane")
    )

    return (
        "<section class=\"report-card\">"
        + section_title
        + f'<div class="chart-wrap">{lane_chart}</div>'
        + _lane_chart_key_html()
        + "<table><thead><tr>"
        + _th("Slice")
        + _th("Planned SP", tip=TIP_PLANNED_SLICE, num=True)
        + _th("Earned SP", tip=TIP_EARNED_SLICE, num=True)
        + _th("Unpointed", tip=TIP_UNPOINTED_SLICE, num=True)
        + "</tr></thead><tbody>"
        + rows
        + "</tbody></table>"
        + "<dl class=\"report-meta-grid\">"
        + _meta_card("Goal SP (initiative)", goal_dd, tip=TIP_GOAL_SP)
        + _meta_card("Planned in quarter scope", planned_dd, tip=TIP_PLANNED_QUARTER)
        + _meta_card("Global earned SP", earned_dd, tip=TIP_GLOBAL_EARNED)
        + _meta_card("Breakdown sum", _fmt_num(lane_sum), tip=TIP_BREAKDOWN_SUM)
        + _meta_card(
            "Unpointed Story/Bug",
            _unpointed_cell(unpointed_total, unpointed_jql, issue_keys=unpointed_issue_keys),
            tip=TIP_UNPOINTED,
        )
        + "</dl>"
        + "</section>"
    )


