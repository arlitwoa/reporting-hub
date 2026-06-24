"""Milestone scope burn-up charts — scope by D-Train phase with deploy-earned line."""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import Any

from extensions.twoa_programme.delivery_milestones import format_milestone_notes_updated_label
from extensions.twoa_programme.jira_binding_loader import load_jira_binding
from extensions.twoa_programme.milestone_scope_chart import (
    DTRAIN_PHASE_FILL,
    resolve_issue_dtrain_phase,
)
from extensions.twoa_programme.milestone_scope_history import (
    _aligned_phase_cumulative,
    aligned_daily_cumulative,
    flat_scope_daily,
    flat_unpointed_daily,
    phase_stack_order,
    proportional_scope_phases_daily,
)
from extensions.twoa_programme.milestone_timeline import (
    MILESTONE_TIMELINE_EXTRA_CSS,
    _truncate_label,
    milestone_timeline_chart_bounds,
)
from extensions.twoa_programme.quarterly_dashboard_svg_core import report_plot_width
from extensions.twoa_programme.quarterly_dashboard_constants import (
    ATL,
    CHART_AXIS_FONT,
    SVG_FONT,
    Y_AXIS_LEFT,
)
from extensions.twoa_programme.quarterly_dashboard_links import _jql_link
from extensions.twoa_programme.quarterly_dashboard_markup import (
    REPORT_CSS,
    _svg_embedded_title,
    _unpointed_cell,
)
from extensions.twoa_programme.quarterly_dashboard_svg_core import (
    _append_milestone_markers,
    _linear_goal_polyline_points,
    _milestone_legend_swatch,
    _svg_chart_vertical_markers,
    _svg_sprint_calendar_underlay,
    _svg_x_axis_labels,
    _svg_x_bottom_margin,
    _visible_chart_milestones,
)
from extensions.twoa_programme.quarterly_reporting import (
    QuarterPeriod,
    aggregate_daily_burn,
    extend_daily_burn_to_as_of,
    resolve_chart_as_of,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BURN_ARTIFACT = "deploy_burn.json"

MILESTONE_BURN_PLOT_HEIGHT = 220
MILESTONE_BURN_PX_PER_DAY = 11.0
EARNED_LINE_HIT_HEIGHT = 14.0
MILESTONE_BURN_SECTION_GAP = 28
MILESTONE_BURN_LABEL_WIDTH = 300
MILESTONE_BURN_SVG_INSET_TOP = 14
MILESTONE_BURN_SVG_INSET_LEFT = 10
MILESTONE_BURN_SVG_INSET_RIGHT = 36
MILESTONE_BURN_SVG_INSET_BOTTOM = 10
MILESTONE_BURN_PLOT_TOP = 56
MILESTONE_BURN_Y_LABEL_X = 30
MILESTONE_BURN_SCOPE_STACK_OPACITY = 0.75
MILESTONE_BURN_UNPOINTED_STACK_OPACITY = 0.75

TIP_MILESTONE_BURN_GOAL = (
    "Linear pace to scoped story points by milestone target end date ({target})."
)
UNPOINTED_PHASE = "Unpointed"
TIP_MILESTONE_BURN_WEIGHT_CEILING = (
    "Total scope weight including unpointed in-scope issues (1 weight each)."
)


def burn_up_phase_stack_order() -> tuple[str, ...]:
    """Drive at chart bottom, Dream then Unknown at top — inverted from timeline bars."""
    order = phase_stack_order()
    if order and order[-1] == "Unknown":
        return (*reversed(order[:-1]), "Unknown")
    return tuple(reversed(order))

MILESTONE_BURN_EXTRA_CSS = """
main.report {
  max-width: 1280px;
  margin: 0 auto;
  padding: 28px 32px 48px;
}
.chart-section,
.milestone-burn-section {
  margin-top: 36px;
}
.chart-section h1,
.milestone-burn-section h1 {
  margin: 0 0 10px;
  font-size: 20px;
  font-weight: 600;
}
.chart-section > .footnote,
.milestone-burn-section > .footnote {
  margin: 0 0 18px;
}
.chart-section .chart-wrap {
  padding: 14px 20px 18px;
}
.milestone-burn-section {
  margin-top: 40px;
}
.milestone-burn-block {
  margin: 0 0 48px;
  padding: 0;
}
.milestone-burn-block h2 {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 600;
}
.milestone-burn-block h2 a {
  color: var(--link, #0052cc);
  text-decoration: none;
}
.milestone-burn-block h2 a:hover {
  text-decoration: underline;
}
.milestone-burn-block .footnote {
  margin: 0 0 18px;
  line-height: 1.55;
}
.milestone-burn-intro {
  display: grid;
  grid-template-columns: minmax(200px, 25%) minmax(0, 1fr);
  gap: 0;
  align-items: stretch;
  margin: 0;
}
.milestone-burn-intro--solo {
  grid-template-columns: minmax(220px, max-content);
}
.milestone-burn-intro .milestone-summary-card,
.milestone-burn-intro .milestone-notes-card {
  border-bottom: none;
}
.milestone-summary-card,
.milestone-notes-card {
  padding: 10px 12px;
  border: 1px solid var(--border, #dfe1e6);
  background: #fff;
  font-size: 12px;
  line-height: 1.45;
}
.milestone-summary-card {
  border-radius: 4px 0 0 0;
}
.milestone-notes-card {
  border-radius: 0 4px 0 0;
  border-left-width: 3px;
  border-left-color: var(--border-strong, #c1c7d0);
}
.milestone-stat-lead {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--text, #172b4d);
}
.milestone-stat-lead a {
  color: var(--link, #0052cc);
  text-decoration: none;
}
.milestone-stat-lead a:hover {
  text-decoration: underline;
}
.milestone-stat-details {
  margin: 0;
  display: grid;
  gap: 4px;
}
.milestone-stat-row {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 8px;
  align-items: baseline;
}
.milestone-stat-row dt {
  margin: 0;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--muted, #5e6c84);
}
.milestone-stat-row dd {
  margin: 0;
  font-size: 11px;
  color: var(--muted, #5e6c84);
}
.milestone-stat-row dd a {
  color: var(--link, #0052cc);
  text-decoration: none;
}
.milestone-stat-row dd a:hover {
  text-decoration: underline;
}
.milestone-stat-footnote {
  margin: 8px 0 0;
  font-size: 10px;
  line-height: 1.4;
  color: var(--muted, #5e6c84);
}
.milestone-notes-label {
  margin: 0 0 6px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--muted, #5e6c84);
}
.milestone-notes-updated {
  font-weight: 500;
  text-transform: none;
  letter-spacing: normal;
}
.milestone-notes-body {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text, #172b4d);
  white-space: pre-wrap;
}
@media (max-width: 900px) {
  .milestone-burn-intro {
    grid-template-columns: 1fr;
    gap: 0;
  }
  .milestone-summary-card {
    border-radius: 4px 4px 0 0;
  }
  .milestone-notes-card {
    border-radius: 0;
    border-left-width: 1px;
    border-top-width: 0;
  }
}
.milestone-burn-intro + .chart-wrap {
  border-top: none;
  border-radius: 0 0 8px 8px;
  margin-top: 0;
}
.milestone-burn-block .chart-wrap {
  padding: 10px 20px 18px;
  overflow-x: hidden;
}
.milestone-burn-block .chart-wrap svg {
  display: block;
  width: 100%;
  height: auto;
  min-width: 0;
  max-width: 100%;
}
.chart-key--dtrain .chart-key-phase-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin: 8px 0 4px;
}
.chart-key--dtrain .chart-key-phase-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted, #5e6c84);
}
"""


def _milestone_chart_marker(milestone: dict[str, Any]) -> dict[str, Any] | None:
    """Single-milestone due-date marker row for chart overlay."""
    day = str(milestone.get("dueDate") or "")[:10]
    if not day:
        return None
    label = str(milestone.get("summary") or milestone.get("label") or "").strip()
    row: dict[str, Any] = {"label": label or str(milestone.get("key") or ""), "date": day}
    if milestone.get("key"):
        row["key"] = milestone["key"]
    if milestone.get("scopeRollup"):
        row["scopeRollup"] = milestone["scopeRollup"]
    if milestone.get("scopeEpics"):
        row["scopeEpics"] = milestone["scopeEpics"]
    return row


def _milestone_scope_jql(milestone: dict[str, Any]) -> str | None:
    keys = [str(key) for key in milestone.get("scopeIssueKeys") or [] if key]
    if not keys:
        return None
    return f"key in ({', '.join(keys)}) AND status != Rejected"


def _milestone_credited_jql(milestone: dict[str, Any]) -> str | None:
    keys = [str(key) for key in milestone.get("creditedIssueKeys") or [] if key]
    if not keys:
        return None
    return f"key in ({', '.join(keys)})"


def _milestone_ideal_earned_at(
    *,
    planned: float,
    start: date,
    goal_target: date,
    as_of: date,
) -> float | None:
    if planned <= 0 or goal_target <= start:
        return None
    if as_of <= start:
        return 0.0
    if as_of >= goal_target:
        return planned
    elapsed = (as_of - start).days
    span = (goal_target - start).days or 1
    return planned * elapsed / span


def _milestone_stat_row(label: str, value_html: str) -> str:
    return (
        f'<div class="milestone-stat-row">'
        f"<dt>{html.escape(label)}</dt>"
        f"<dd>{value_html}</dd>"
        f"</div>"
    )


def _milestone_burn_meta_html(
    milestone: dict[str, Any],
    *,
    earned: float,
    scope: float,
    chart_as_of: date,
    quarter_start: date | str,
) -> str:
    scope_jql = _milestone_scope_jql(milestone)
    credited_jql = _milestone_credited_jql(milestone)
    earned_label = f"{earned:g}"
    scope_label = f"{scope:g}"
    if credited_jql:
        earned_part = _jql_link(credited_jql, earned_label)
    else:
        earned_part = html.escape(earned_label)
    if scope_jql:
        scope_part = _jql_link(scope_jql, scope_label)
    else:
        scope_part = html.escape(scope_label)
    credit_count = int(milestone.get("earnedEventCount") or 0)
    if credited_jql and credit_count:
        credit_part = _jql_link(credited_jql, str(credit_count))
    else:
        credit_part = html.escape(str(credit_count))
    lead = (
        f"Earned {earned_part} SP of {scope_part} scoped story points "
        f"({credit_part} credited issues)"
    )

    detail_rows: list[str] = []
    unpointed = _milestone_unpointed_count(milestone)
    if unpointed:
        total_weight = _milestone_total_weight(milestone, scoped_sp=scope)
        count_html = _unpointed_cell(unpointed, _milestone_unpointed_jql(milestone))
        detail_rows.append(
            _milestone_stat_row("Weight", f"{total_weight:g} total · {count_html} unpointed")
        )

    start = str(milestone.get("startDate") or "")[:10]
    due = str(milestone.get("dueDate") or "")[:10]
    if start and due:
        window = f"{html.escape(start)} → {html.escape(due)}"
    elif start:
        window = f"from {html.escape(start)}"
    elif due:
        window = f"due {html.escape(due)}"
    else:
        window = ""
    if window:
        detail_rows.append(_milestone_stat_row("Window", window))

    pace = _milestone_goal_pace_meta(
        milestone,
        earned=earned,
        scope=scope,
        chart_as_of=chart_as_of,
        quarter_start=quarter_start,
    )
    if pace:
        detail_rows.append(_milestone_stat_row("Pace", html.escape(pace)))

    footnote = ""
    if scope > 0 and not milestone.get("scopePhases"):
        footnote = (
            '<p class="milestone-stat-footnote">Scope phase mix uses today&apos;s composition '
            "(re-fetch timeline for status history).</p>"
        )

    details_html = (
        f'<dl class="milestone-stat-details">{"".join(detail_rows)}</dl>' if detail_rows else ""
    )
    return (
        '<div class="milestone-summary-card">'
        f'<p class="milestone-stat-lead">{lead}</p>'
        f"{details_html}"
        f"{footnote}"
        "</div>"
    )


def _milestone_notes_html(milestone: dict[str, Any]) -> str:
    notes = str(milestone.get("notes") or "").strip()
    if not notes:
        return ""
    updated_suffix = format_milestone_notes_updated_label(milestone.get("notesUpdatedAt"))
    if updated_suffix:
        label_html = (
            f'Notes <span class="milestone-notes-updated">· {html.escape(updated_suffix)}</span>'
        )
    else:
        label_html = "Notes"
    return (
        '<div class="milestone-notes-card">'
        f'<p class="milestone-notes-label">{label_html}</p>'
        f'<p class="milestone-notes-body">{html.escape(notes)}</p>'
        "</div>"
    )


def _milestone_intro_html(meta_card: str, notes_html: str) -> str:
    if notes_html:
        return (
            f'<div class="milestone-burn-intro">'
            f"{meta_card}"
            f"{notes_html}"
            f"</div>"
        )
    return f'<div class="milestone-burn-intro milestone-burn-intro--solo">{meta_card}</div>'


def _milestone_goal_pace_meta(
    milestone: dict[str, Any],
    *,
    earned: float,
    scope: float,
    chart_as_of: date,
    quarter_start: date | str,
) -> str | None:
    due_raw = str(milestone.get("dueDate") or "")[:10]
    if not due_raw or scope <= 0:
        return None
    goal_target = date.fromisoformat(due_raw)
    start = date.fromisoformat(str(milestone.get("startDate") or quarter_start)[:10])
    ideal = _milestone_ideal_earned_at(
        planned=scope,
        start=start,
        goal_target=goal_target,
        as_of=chart_as_of,
    )
    if ideal is None:
        return None
    ideal_label = f"{ideal:.0f}" if ideal >= 10 else f"{ideal:g}"
    delta = earned - ideal
    if abs(delta) < 1.0:
        return f"{earned:g} earned vs ~{ideal_label} on pace today"
    if delta < 0:
        behind = f"{abs(delta):.0f}" if abs(delta) >= 10 else f"{abs(delta):g}"
        return f"{earned:g} earned vs ~{ideal_label} on pace today ({behind} SP behind)"
    ahead = f"{delta:.0f}" if delta >= 10 else f"{delta:g}"
    return f"{earned:g} earned vs ~{ideal_label} on pace today ({ahead} SP ahead)"


def _y_ticks(max_value: float) -> list[float]:
    if max_value <= 0:
        return [0.0]
    step = 10.0
    if max_value <= 20:
        step = 5.0
    elif max_value <= 50:
        step = 10.0
    elif max_value <= 120:
        step = 20.0
    else:
        step = 50.0
    ticks: list[float] = []
    cursor = 0.0
    while cursor <= max_value * 1.02:
        ticks.append(cursor)
        cursor += step
    return ticks


def _resolve_scope_daily(
    milestone: dict[str, Any],
    *,
    quarter_start: date | str,
    quarter_end: date | str,
    chart_as_of: date | str | None = None,
) -> list[dict[str, Any]]:
    scope_daily = milestone.get("scopeDaily") or []
    if scope_daily:
        return extend_daily_burn_to_as_of(
            list(scope_daily),
            str(chart_as_of or quarter_end)[:10],
            quarter_end=quarter_end,
        )
    scope_rollup = milestone.get("scopeRollup") or {}
    story_points = float(scope_rollup.get("storyPoints") or 0)
    return flat_scope_daily(
        story_points,
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        as_of=chart_as_of,
    )


def _resolve_scope_phases(
    milestone: dict[str, Any],
    scope_daily: list[dict[str, Any]],
) -> dict[str, Any]:
    scope_phases = milestone.get("scopePhases") or {}
    if scope_phases:
        return scope_phases
    phase_amounts = (milestone.get("scopeRollup") or {}).get("phases") or {}
    if scope_daily and phase_amounts:
        return proportional_scope_phases_daily(
            scope_daily,
            phase_amounts,
            phase_order=phase_stack_order(),
        )
    return {}


def _milestone_unpointed_count(milestone: dict[str, Any]) -> int:
    return int((milestone.get("scopeRollup") or {}).get("unpointedCount") or 0)


def _milestone_total_weight(milestone: dict[str, Any], *, scoped_sp: float) -> float:
    rollup = milestone.get("scopeRollup") or {}
    total_weight = rollup.get("totalWeight")
    if total_weight is not None:
        return float(total_weight)
    return scoped_sp + _milestone_unpointed_count(milestone)


def _milestone_unpointed_jql(milestone: dict[str, Any]) -> str | None:
    keys = [str(key) for key in milestone.get("scopeIssueKeys") or [] if key]
    if not keys:
        return None
    from scripts.quarterly.jira_burn import unpointed_stories_bugs_jql

    base = (
        f"key in ({', '.join(keys)}) AND issuetype in (Story, Bug) AND status != Rejected"
    )
    return unpointed_stories_bugs_jql(base)


def _resolve_unpointed_daily(
    milestone: dict[str, Any],
    *,
    quarter_start: date | str,
    quarter_end: date | str,
    chart_as_of: date | str | None = None,
) -> list[dict[str, Any]]:
    unpointed_daily = milestone.get("scopeUnpointedDaily") or []
    if unpointed_daily:
        return extend_daily_burn_to_as_of(
            list(unpointed_daily),
            str(chart_as_of or quarter_end)[:10],
            quarter_end=quarter_end,
        )
    count = _milestone_unpointed_count(milestone)
    return flat_unpointed_daily(
        count,
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        as_of=chart_as_of,
    )


def _extend_scope_phases_to_as_of(
    scope_phases: dict[str, Any],
    scope_daily: list[dict[str, Any]],
) -> dict[str, Any]:
    if not scope_daily:
        return scope_phases
    as_of_date = str(scope_daily[-1]["date"])[:10]
    extended: dict[str, Any] = {}
    for phase_key, phase_row in scope_phases.items():
        daily = extend_daily_burn_to_as_of(
            list(phase_row.get("daily") or []),
            as_of_date,
            quarter_end=as_of_date,
        )
        extended[phase_key] = {**phase_row, "daily": daily}
    return extended


def _series_totals(
    phase_series: dict[str, list[float]],
    phase_order: tuple[str, ...],
    length: int,
) -> list[float]:
    totals: list[float] = []
    for index in range(length):
        totals.append(
            sum(float(phase_series.get(phase, [0.0] * length)[index]) for phase in phase_order)
        )
    return totals


def _phase_step_tooltip(
    *,
    layer_label: str,
    phase: str,
    story_points: float,
    day: date,
    total: float,
) -> str:
    label = f"{layer_label}: {phase}" if layer_label else phase
    if total > 0 and story_points > 0:
        share = story_points / total * 100.0
        return (
            f"{label} — {story_points:g} SP "
            f"({share:.0f}% of {total:g} SP) from {day.isoformat()}"
        )
    return f"{label} — {story_points:g} SP from {day.isoformat()}"


def _unpointed_step_tooltip(*, count: float, day: date, scoped_sp: float) -> str:
    issues = int(count)
    noun = "issue" if issues == 1 else "issues"
    total = scoped_sp + count
    return (
        f"Unpointed — {issues} {noun} (1 weight each) "
        f"({total:g} total weight) from {day.isoformat()}"
    )


def _append_unpointed_stack(
    parts: list[str],
    *,
    dates: list[date],
    sp_totals: list[float],
    unpointed_vals: list[float],
    x_for,
    y_pos,
    plot_right: float,
    default_day_width: float,
    opacity: float = MILESTONE_BURN_UNPOINTED_STACK_OPACITY,
) -> None:
    n = len(dates)
    if n == 0 or max(unpointed_vals) <= 0:
        return
    lower = sp_totals
    top = [lower[i] + unpointed_vals[i] for i in range(n)]
    top_pts = " ".join(f"{x_for(dates[i]):.1f},{y_pos(top[i]):.1f}" for i in range(n))
    bot_pts = " ".join(
        f"{x_for(dates[i]):.1f},{y_pos(lower[i]):.1f}" for i in range(n - 1, -1, -1)
    )
    fill = DTRAIN_PHASE_FILL.get(UNPOINTED_PHASE, "#c1c7d0")
    parts.append(
        f'<polygon points="{top_pts} {bot_pts}" fill="{fill}" opacity="{opacity}" stroke="none" '
        f'pointer-events="none"/>'
    )
    for index in range(n):
        if unpointed_vals[index] <= 0:
            continue
        y_top = y_pos(top[index])
        y_bottom = y_pos(lower[index])
        if y_bottom - y_top < 1.0:
            continue
        x_start, x_end = _segment_x_bounds(
            dates,
            index,
            x_for=x_for,
            plot_right=plot_right,
            default_day_width=default_day_width,
        )
        tip = _unpointed_step_tooltip(
            count=unpointed_vals[index],
            day=dates[index],
            scoped_sp=lower[index],
        )
        parts.append(
            f'<g>{_svg_embedded_title(tip)}'
            f'<rect x="{x_start:.1f}" y="{y_top:.1f}" width="{x_end - x_start:.1f}" '
            f'height="{y_bottom - y_top:.1f}" fill="transparent" pointer-events="all"/>'
            f"</g>"
        )


def _append_weight_ceiling_line(
    parts: list[str],
    *,
    total_weight: float,
    scoped_sp: float,
    y_pos,
    plot_left: float,
    plot_right: float,
) -> None:
    if total_weight <= scoped_sp:
        return
    y = y_pos(total_weight)
    parts.append(
        f'<g>{_svg_embedded_title(TIP_MILESTONE_BURN_WEIGHT_CEILING)}'
        f'<line x1="{plot_left:.1f}" y1="{y:.1f}" x2="{plot_right:.1f}" y2="{y:.1f}" '
        f'stroke="{ATL["neutral"]}" stroke-width="1" stroke-dasharray="3 3" opacity="0.55"/>'
        f"</g>"
    )


def _segment_x_bounds(
    dates: list[date],
    index: int,
    *,
    x_for,
    plot_right: float,
    default_day_width: float,
) -> tuple[float, float]:
    x_start = float(x_for(dates[index]))
    if index + 1 < len(dates):
        x_end = float(x_for(dates[index + 1]))
    else:
        x_end = min(plot_right, x_start + max(default_day_width, 4.0))
    if x_end <= x_start:
        x_end = x_start + 4.0
    return x_start, x_end


def _append_phase_stack(
    parts: list[str],
    *,
    dates: list[date],
    phase_series: dict[str, list[float]],
    phase_order: tuple[str, ...],
    x_for,
    y_pos,
    layer_label: str,
    plot_right: float,
    default_day_width: float,
    opacity: float | None = None,
    polygon_stroke: str | None = "none",
    polygon_stroke_width: float = 0.0,
) -> None:
    n = len(dates)
    if n == 0:
        return
    totals = _series_totals(phase_series, phase_order, n)

    for phase_key in phase_order:
        if phase_key not in phase_series:
            continue
        phase_vals = phase_series[phase_key]
        lower = [0.0] * n
        for below in phase_order:
            if below == phase_key:
                break
            if below in phase_series:
                lower = [lower[i] + phase_series[below][i] for i in range(n)]
        top = [lower[i] + phase_vals[i] for i in range(n)]
        if max(top) <= 0:
            continue
        top_pts = " ".join(f"{x_for(dates[i]):.1f},{y_pos(top[i]):.1f}" for i in range(n))
        bot_pts = " ".join(
            f"{x_for(dates[i]):.1f},{y_pos(lower[i]):.1f}" for i in range(n - 1, -1, -1)
        )
        fill = DTRAIN_PHASE_FILL.get(phase_key, ATL["neutral"])
        opacity_attr = f' opacity="{opacity}"' if opacity is not None else ""
        if polygon_stroke and polygon_stroke != "none":
            stroke_attrs = (
                f'stroke="{polygon_stroke}" stroke-width="{polygon_stroke_width:.1f}"'
            )
        else:
            stroke_attrs = 'stroke="none"'
        parts.append(
            f'<polygon points="{top_pts} {bot_pts}" fill="{fill}"{opacity_attr} '
            f'{stroke_attrs} pointer-events="none"/>'
        )

        for index in range(n):
            if phase_vals[index] <= 0:
                continue
            y_top = y_pos(top[index])
            y_bottom = y_pos(lower[index])
            if y_bottom - y_top < 1.0:
                continue
            x_start, x_end = _segment_x_bounds(
                dates,
                index,
                x_for=x_for,
                plot_right=plot_right,
                default_day_width=default_day_width,
            )
            tip = _phase_step_tooltip(
                layer_label=layer_label,
                phase=phase_key,
                story_points=phase_vals[index],
                day=dates[index],
                total=totals[index],
            )
            parts.append(
                f'<g>{_svg_embedded_title(tip)}'
                f'<rect x="{x_start:.1f}" y="{y_top:.1f}" width="{x_end - x_start:.1f}" '
                f'height="{y_bottom - y_top:.1f}" fill="transparent" pointer-events="all"/>'
                f"</g>"
            )


def _append_earned_line_with_tooltips(
    parts: list[str],
    *,
    combined_daily: list[dict[str, Any]],
    x_for,
    y_pos,
    plot_left: float,
    plot_right: float,
    default_day_width: float,
) -> None:
    if not combined_daily:
        return

    earned_pts = " ".join(
        f"{x_for(date.fromisoformat(str(row['date'])[:10])):.1f},"
        f"{y_pos(float(row['cumulative_story_points'])):.1f}"
        for row in combined_daily
    )
    last_cum = float(combined_daily[-1]["cumulative_story_points"])
    parts.append(
        f'<g>{_svg_embedded_title(f"Cumulative deploy-earned SP: {last_cum:g}")}'
        f'<polyline fill="none" stroke="transparent" stroke-width="12" '
        f'pointer-events="stroke" points="{earned_pts}"/>'
        f'<polyline fill="none" stroke="{ATL["blue"]}" stroke-width="2.5" '
        f'pointer-events="none" points="{earned_pts}"/>'
        f"</g>"
    )

    dates = [date.fromisoformat(str(row["date"])[:10]) for row in combined_daily]
    for index, row in enumerate(combined_daily):
        day = dates[index]
        cumulative = float(row["cumulative_story_points"])
        delta = float(row.get("earned_that_day") or 0)
        x_end = float(x_for(day))
        if index > 0:
            x_start = float(x_for(dates[index - 1]))
        else:
            x_start = max(plot_left, x_end - max(default_day_width, 4.0))
        if x_end <= x_start:
            x_end = x_start + 4.0
        tip = (
            f"Earned {cumulative:g} SP by {day.isoformat()}"
            if delta <= 0
            else f"Earned {cumulative:g} SP by {day.isoformat()} (+{delta:g} SP)"
        )
        y_line = y_pos(cumulative)
        hit_top = y_line - EARNED_LINE_HIT_HEIGHT / 2
        parts.append(
            f'<g>{_svg_embedded_title(tip)}'
            f'<rect x="{x_start:.1f}" y="{hit_top:.1f}" '
            f'width="{x_end - x_start:.1f}" height="{EARNED_LINE_HIT_HEIGHT:.1f}" '
            f'fill="transparent" pointer-events="all"/>'
            f"</g>"
        )


def build_milestone_burn_payload(
    timeline_payload: dict[str, Any],
    deploy_burn: dict[str, Any],
    *,
    binding=None,
    adapter: Any | None = None,
    quarter: QuarterPeriod | None = None,
    sp_field: str = "customfield_10026",
    deploy_statuses: set[str] | None = None,
    done_statuses: set[str] | None = None,
    credit_cache_path: Path | None = None,
) -> dict[str, Any]:
    """Attach earned-by-phase and scope series to each milestone."""
    jira_binding = binding or load_jira_binding()
    global_events = ((deploy_burn.get("global") or {}).get("events") or [])
    events_by_key = {str(event.get("key")): event for event in global_events if event.get("key")}
    phase_order = phase_stack_order()
    quarter_start = timeline_payload.get("quarterStart")
    quarter_end = timeline_payload.get("quarterEnd")
    use_milestone_scope_credit = (
        adapter is not None
        and quarter is not None
        and deploy_statuses is not None
        and done_statuses is not None
        and credit_cache_path is not None
    )
    if use_milestone_scope_credit:
        from scripts.quarterly.jira_burn import earned_events_for_scope_keys

    milestones: list[dict[str, Any]] = []
    for milestone in timeline_payload.get("milestones") or []:
        scope_keys = {str(key) for key in milestone.get("scopeIssueKeys") or []}
        if use_milestone_scope_credit:
            window_start = date.fromisoformat(
                str(milestone.get("startDate") or quarter_start)[:10]
            )
            window_end = date.fromisoformat(str(quarter_end)[:10])
            raw_events = earned_events_for_scope_keys(
                adapter,
                scope_keys,
                sp_field=sp_field,
                deploy_statuses=deploy_statuses,
                done_statuses=done_statuses,
                cache_path=credit_cache_path,
                seed_events_by_key=events_by_key,
                window_start=window_start,
                window_end=window_end,
            )
        else:
            raw_events = [
                events_by_key[key]
                for key in sorted(scope_keys)
                if key in events_by_key
            ]

        milestone_events: list[dict[str, Any]] = []
        for event in raw_events:
            phase = resolve_issue_dtrain_phase(
                str(event.get("status_at_credit") or event.get("status_now") or ""),
                jira_binding,
            )
            milestone_events.append({**event, "dtrainPhase": phase})

        phase_events: dict[str, list[dict[str, Any]]] = {phase: [] for phase in phase_order}
        for event in milestone_events:
            phase = str(event.get("dtrainPhase") or "Unknown")
            if phase not in phase_events:
                phase = "Unknown"
            phase_events[phase].append(event)

        earned_phases: dict[str, Any] = {}
        for phase_key in phase_order:
            daily, total = aggregate_daily_burn(phase_events[phase_key])
            earned_phases[phase_key] = {
                "totalStoryPointsEarned": total,
                "eventCount": len(phase_events[phase_key]),
                "daily": daily,
            }

        combined_daily, total_earned = aggregate_daily_burn(milestone_events)
        scope_rollup = milestone.get("scopeRollup") or {}
        total_scope_sp = float(
            milestone.get("totalScopeStoryPoints")
            or scope_rollup.get("storyPoints")
            or 0
        )
        credited_by_key: dict[str, float] = {}
        for event in milestone_events:
            event_key = str(event.get("key") or "")
            if not event_key:
                continue
            credited_by_key[event_key] = credited_by_key.get(event_key, 0.0) + float(
                event.get("story_points") or 0
            )
        credited_issue_keys = sorted(
            key for key, net_sp in credited_by_key.items() if net_sp > 0
        )
        milestones.append(
            {
                "key": milestone.get("key"),
                "summary": milestone.get("summary") or milestone.get("label"),
                "notes": milestone.get("notes") or "",
                "notesUpdatedAt": milestone.get("notesUpdatedAt"),
                "startDate": milestone.get("startDate"),
                "endDate": milestone.get("endDate"),
                "dueDate": milestone.get("dueDate"),
                "scopeRollup": scope_rollup,
                "scopeIssueKeys": sorted(scope_keys),
                "creditedIssueKeys": credited_issue_keys,
                "totalScopeStoryPoints": total_scope_sp,
                "totalScopeWeight": _milestone_total_weight(milestone, scoped_sp=total_scope_sp),
                "unpointedCount": _milestone_unpointed_count(milestone),
                "scopeDaily": milestone.get("scopeDaily") or [],
                "scopePhases": milestone.get("scopePhases") or {},
                "scopeUnpointedDaily": milestone.get("scopeUnpointedDaily") or [],
                "scopeIssueCount": len(scope_keys),
                "combinedDaily": combined_daily,
                "totalStoryPointsEarned": total_earned,
                "earnedEventCount": len(milestone_events),
                "earnedPhases": earned_phases,
                "phaseOrder": list(phase_order),
            }
        )

    return {
        "initiativeKey": timeline_payload.get("initiativeKey"),
        "quarterStart": quarter_start,
        "quarterEnd": quarter_end,
        "milestoneCount": len(milestones),
        "milestones": milestones,
    }


def load_deploy_burn_payload(output_dir: Path) -> dict[str, Any] | None:
    path = Path(output_dir) / _BURN_ARTIFACT
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def milestone_burn_phase_key_html() -> str:
    items = []
    for phase in burn_up_phase_stack_order():
        items.append(
            f'<span class="chart-key-phase-item">'
            f'<span class="legend-swatch" style="background:{DTRAIN_PHASE_FILL[phase]}"></span>'
            f"{html.escape(phase)}</span>"
        )
    return (
        '<div class="chart-key chart-key--dtrain">'
        '<p class="chart-key-title"><strong>D-Train phase colours</strong> '
        "(stacked bottom → top: Drive through Dream)</p>"
        f'<div class="chart-key-phase-strip">{"".join(items)}</div>'
        '<div class="chart-key-row">'
        '<span class="legend-swatch" style="background:#de350b"></span> '
        "Scope target (stacked composition by D-Train phase)"
        "</div>"
        '<div class="chart-key-row">'
        f'<span class="legend-swatch" style="background:{DTRAIN_PHASE_FILL.get(UNPOINTED_PHASE, "#c1c7d0")}"></span> '
        "Unpointed in-scope issues (1 weight each, grey band above scoped SP)"
        "</div>"
        '<div class="chart-key-row">'
        '<span class="legend-swatch" style="background:#0052cc"></span> '
        "Cumulative deploy-earned SP"
        "</div>"
        '<div class="chart-key-row">'
        '<span class="legend-swatch goal"></span> '
        "Goal (linear pace to scoped SP by target end date)"
        "</div>"
        '<div class="chart-key-row">'
        '<span class="legend-swatch" style="border-top:2px dashed #97a0af;background:transparent;height:0"></span> '
        "Total weight ceiling (scoped SP + unpointed)"
        "</div>"
        '<div class="chart-key-row">'
        f"{_milestone_legend_swatch()} Target end date"
        "</div>"
        "</div>"
    )


def milestone_burn_up_plot_width(
    span_days: int,
    *,
    px_per_day: float = MILESTONE_BURN_PX_PER_DAY,
) -> int:
    plot_left = Y_AXIS_LEFT + MILESTONE_BURN_SVG_INSET_LEFT
    return report_plot_width(
        span_days,
        px_per_day=px_per_day,
        plot_left=plot_left,
        plot_right_pad=MILESTONE_BURN_SVG_INSET_RIGHT,
    )


def milestone_burn_up_svg(
    milestone: dict[str, Any],
    *,
    sprint_bands: list[dict[str, Any]] | None = None,
    releases: list[dict[str, Any]] | None = None,
    quarter_start: date | str,
    quarter_end: date | str,
    chart_as_of: date | str | None = None,
    px_per_day: float = MILESTONE_BURN_PX_PER_DAY,
) -> str:
    combined_daily = milestone.get("combinedDaily") or []
    chart_as_of_day = resolve_chart_as_of(chart_as_of, quarter_end=str(quarter_end)[:10])
    scope_daily = _resolve_scope_daily(
        milestone,
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        chart_as_of=chart_as_of_day.isoformat(),
    )
    if combined_daily:
        combined_daily = extend_daily_burn_to_as_of(
            combined_daily,
            chart_as_of_day.isoformat(),
            quarter_end=str(quarter_end)[:10],
        )

    if not combined_daily and not scope_daily:
        return '<p class="footnote">No milestone scope or earned story points yet.</p>'

    phase_order = burn_up_phase_stack_order()
    scope_phases = _extend_scope_phases_to_as_of(
        _resolve_scope_phases(milestone, scope_daily),
        scope_daily,
    )
    unpointed_daily = _resolve_unpointed_daily(
        milestone,
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        chart_as_of=chart_as_of_day.isoformat(),
    )
    chart_dates = scope_daily or combined_daily
    scope_dates, scope_phase_series = _aligned_phase_cumulative(
        scope_phases,
        chart_dates,
        phase_order=phase_order,
    )
    unpointed_vals: list[float] = []
    if scope_dates:
        unpointed_vals = aligned_daily_cumulative(unpointed_daily, scope_dates)

    x_min_default = date.fromisoformat(str(quarter_start)[:10])
    x_max = date.fromisoformat(str(quarter_end)[:10])
    x_min, _ = milestone_timeline_chart_bounds(
        [milestone],
        quarter_start=x_min_default,
        quarter_end=x_max,
    )

    plot_top = MILESTONE_BURN_PLOT_TOP + MILESTONE_BURN_SVG_INSET_TOP
    release_label_anchor = plot_top - 10
    plot_bottom = plot_top + MILESTONE_BURN_PLOT_HEIGHT
    svg_height = (
        plot_bottom
        + _svg_x_bottom_margin()
        + MILESTONE_BURN_SVG_INSET_BOTTOM
    )
    span_days = (x_max - x_min).days or 1
    plot_left = Y_AXIS_LEFT + MILESTONE_BURN_SVG_INSET_LEFT
    plot_w = milestone_burn_up_plot_width(span_days, px_per_day=px_per_day)
    plot_right = plot_left + plot_w
    width = plot_right + MILESTONE_BURN_SVG_INSET_RIGHT
    plot_h = MILESTONE_BURN_PLOT_HEIGHT

    def x_for(day: date) -> float:
        offset = max(0, min(span_days, (day - x_min).days))
        return plot_left + offset / span_days * plot_w

    earned_values = [float(row["cumulative_story_points"]) for row in combined_daily]
    scope_values = [float(row["cumulative_story_points"]) for row in scope_daily]
    unpointed_count = _milestone_unpointed_count(milestone)
    scoped_sp_top = scope_values[-1] if scope_values else 0.0
    unpointed_top = unpointed_vals[-1] if unpointed_vals else float(unpointed_count)
    total_weight = _milestone_total_weight(milestone, scoped_sp=scoped_sp_top)
    tick_top = max(
        earned_values[-1] if earned_values else 0.0,
        scoped_sp_top + unpointed_top,
        total_weight if unpointed_count else scoped_sp_top,
        1.0,
    )
    y_max = tick_top * 1.08

    def y_pos(value: float) -> float:
        return plot_bottom - (plot_bottom - plot_top) * value / y_max

    default_day_width = plot_w / max(span_days, 1)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{svg_height}" '
        f'viewBox="0 0 {width} {svg_height}" preserveAspectRatio="xMinYMin meet" '
        f'role="img" aria-label="Milestone scope burn-up">',
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
        show_sprint_shading=True,
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
        f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" '
        f'stroke="{ATL["line"]}"/>'
    )
    parts.append(
        f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" '
        f'stroke="{ATL["line"]}"/>'
    )
    y_label_x = MILESTONE_BURN_Y_LABEL_X
    parts.append(
        f'<text x="{y_label_x}" y="{plot_top + plot_h / 2:.0f}" '
        f'transform="rotate(-90 {y_label_x} {plot_top + plot_h / 2:.0f})" text-anchor="middle" '
        f'font-family="{SVG_FONT}" font-size="{CHART_AXIS_FONT}" fill="{ATL["text_subtle"]}" '
        f'font-weight="600">'
        f'{"Story points (+ unpointed weight)" if unpointed_count else "Story points"}'
        f"</text>"
    )

    goal_target_day = None
    due_raw = str(milestone.get("dueDate") or "")[:10]
    if due_raw:
        goal_target_day = date.fromisoformat(due_raw)
    planned_scope = float(
        milestone.get("totalScopeStoryPoints")
        or (milestone.get("scopeRollup") or {}).get("storyPoints")
        or 0
    )
    if goal_target_day and planned_scope > 0:
        ideal_pts = _linear_goal_polyline_points(
            x_min=x_min,
            x_max=x_max,
            goal_target=goal_target_day,
            planned=planned_scope,
            x_for=x_for,
            y_pos=y_pos,
        )
        parts.append(
            f'<g>{_svg_embedded_title(TIP_MILESTONE_BURN_GOAL.format(target=goal_target_day.isoformat()))}'
            f'<polyline fill="none" stroke="{ATL["neutral"]}" stroke-width="2" '
            f'stroke-dasharray="6 4" points="{" ".join(ideal_pts)}"/>'
            f"</g>"
        )

    if scope_phases and scope_dates:
        sp_totals = _series_totals(scope_phase_series, phase_order, len(scope_dates))
        _append_phase_stack(
            parts,
            dates=scope_dates,
            phase_series=scope_phase_series,
            phase_order=phase_order,
            x_for=x_for,
            y_pos=y_pos,
            layer_label="",
            plot_right=plot_right,
            default_day_width=default_day_width,
            opacity=MILESTONE_BURN_SCOPE_STACK_OPACITY,
        )
        _append_unpointed_stack(
            parts,
            dates=scope_dates,
            sp_totals=sp_totals,
            unpointed_vals=unpointed_vals,
            x_for=x_for,
            y_pos=y_pos,
            plot_right=plot_right,
            default_day_width=default_day_width,
        )
        _append_weight_ceiling_line(
            parts,
            total_weight=total_weight,
            scoped_sp=scoped_sp_top,
            y_pos=y_pos,
            plot_left=plot_left,
            plot_right=plot_right,
        )

    _append_earned_line_with_tooltips(
        parts,
        combined_daily=combined_daily,
        x_for=x_for,
        y_pos=y_pos,
        plot_left=plot_left,
        plot_right=plot_right,
        default_day_width=default_day_width,
    )

    _svg_chart_vertical_markers(
        parts,
        releases=releases,
        milestones=None,
        plot_top=plot_top,
        plot_bottom=plot_bottom,
        x_for=x_for,
        x_min=x_min,
        x_max=x_max,
    )

    marker_row = _milestone_chart_marker(milestone)
    if marker_row:
        due_markers = _visible_chart_milestones(
            [marker_row],
            x_min=x_min,
            x_max=x_max,
            x_for=x_for,
        )
        _append_milestone_markers(
            parts,
            due_markers,
            plot_top=plot_top,
            plot_bottom=plot_bottom,
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


def build_milestone_burn_up_section_html(
    burn_payload: dict[str, Any],
    *,
    sprint_bands: list[dict[str, Any]] | None = None,
    releases: list[dict[str, Any]] | None = None,
    quarter_start: date | str,
    quarter_end: date | str,
    chart_as_of: date | str | None = None,
) -> str:
    from extensions.twoa_programme.quarterly_dashboard_constants import JIRA_SERVER

    blocks: list[str] = []
    chart_as_of_day = resolve_chart_as_of(chart_as_of, quarter_end=str(quarter_end)[:10])
    for milestone in burn_payload.get("milestones") or []:
        summary = str(milestone.get("summary") or "")
        key = str(milestone.get("key") or "")
        earned = float(milestone.get("totalStoryPointsEarned") or 0)
        scope = float(milestone.get("totalScopeStoryPoints") or 0)
        chart = milestone_burn_up_svg(
            milestone,
            sprint_bands=sprint_bands,
            releases=releases,
            quarter_start=quarter_start,
            quarter_end=quarter_end,
            chart_as_of=chart_as_of,
        )
        browse_url = f"{JIRA_SERVER}/browse/{html.escape(key)}"
        title = html.escape(_truncate_label(summary, 72))
        meta = _milestone_burn_meta_html(
            milestone,
            earned=earned,
            scope=scope,
            chart_as_of=chart_as_of_day,
            quarter_start=quarter_start,
        )
        notes_html = _milestone_notes_html(milestone)
        intro_html = _milestone_intro_html(meta, notes_html)
        blocks.append(
            f'<article class="milestone-burn-block">'
            f'<h2><a href="{browse_url}" target="_blank" rel="noopener">{title}</a></h2>'
            f"{intro_html}"
            f'<div class="chart-wrap chart-wrap-timeline">{chart}</div>'
            f"</article>"
        )

    if not blocks:
        return (
            '<section class="milestone-burn-section">'
            "<h1>Milestone scope burn-up</h1>"
            '<p class="footnote">No milestone burn data. Run fetch_milestone_timeline.py --write '
            "and deploy_burn.py --write.</p>"
            "</section>"
        )

    return (
        '<section class="milestone-burn-section">'
        "<h1>Milestone scope burn-up</h1>"
        '<p class="footnote">Scope target (stacked bands) shows in-scope story points by D-Train phase, '
        "stacked with Drive at the bottom and Dream at the top; unpointed in-scope issues appear as a grey "
        "band above scoped SP (1 weight each). Milestone scope is all Story/Bug/Spike under milestone-linked "
        "epics (not limited to the quarter scope filter). The blue line is cumulative deploy-earned SP "
        "for milestone scope issues (deploy gate first, else Done/Drive), not limited to quarter global burn "
        "JQL. The dashed goal line is linear pace to scoped SP by the milestone target end date (Jira due date). "
        "The faint dashed ceiling is total scope weight (scoped SP + unpointed). "
        "Scope steps when estimates change; phase mix follows status when timeline is re-fetched. "
        "Hover bands and the earned line for details.</p>"
        f'{"".join(blocks)}'
        f"{milestone_burn_phase_key_html()}"
        "</section>"
    )


def build_milestone_scope_report_html(
    timeline_payload: dict[str, Any],
    burn_payload: dict[str, Any],
    *,
    generated_on: str,
    page_title: str,
    sprint_bands: list[dict[str, Any]] | None = None,
    releases: list[dict[str, Any]] | None = None,
    quarter_start: date | str,
    quarter_end: date | str,
    chart_as_of: date | str | None = None,
) -> str:
    from extensions.twoa_programme.milestone_report_scope import milestone_report_timeline_footnote
    from extensions.twoa_programme.milestone_timeline import (
        milestone_timeline_key_html,
        milestone_timeline_svg,
    )

    timeline_chart = milestone_timeline_svg(
        timeline_payload,
        sprint_bands=sprint_bands,
        releases=releases,
        quarter_start=quarter_start,
        quarter_end=quarter_end,
    )
    timeline_footnote = milestone_report_timeline_footnote(
        timeline_payload,
        detail="Each bar runs from milestone start date through due date.",
    )
    burn_section = build_milestone_burn_up_section_html(
        burn_payload,
        sprint_bands=sprint_bands,
        releases=releases,
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        chart_as_of=chart_as_of,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(page_title)}</title>
  <style>{REPORT_CSS}{MILESTONE_TIMELINE_EXTRA_CSS}{MILESTONE_BURN_EXTRA_CSS}</style>
</head>
<body>
  <main class="report">
    <header class="report-header">
      <h1>{html.escape(page_title)}</h1>
      <p class="report-meta">Generated {html.escape(generated_on)}</p>
    </header>
    <section class="chart-section">
      <h1>Milestone timeline</h1>
      <p class="footnote">{html.escape(timeline_footnote)}</p>
      <div class="chart-wrap chart-wrap-timeline chart-wrap-milestone">{timeline_chart}</div>
      {milestone_timeline_key_html()}
    </section>
    {burn_section}
  </main>
</body>
</html>
"""
