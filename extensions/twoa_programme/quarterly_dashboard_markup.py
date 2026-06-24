"""HTML/CSS helpers for quarterly dashboard."""

from __future__ import annotations

import html
import re
from datetime import date
from typing import Any

from extensions.twoa_programme.quarterly_dashboard_constants import (
    ATL,
    LANE_STACK_FILL,
    SVG_FONT,
    TIP_CHART_GOAL_LINEAR,
    TIP_CHART_LANE_GOAL,
    TIP_CHART_SCOPE_GOAL,
    TIP_EARNED_SP,
    TIP_GOAL_SP,
    TIP_IDEAL_LINEAR,
    TIP_REQ_DAILY,
    TIP_VARIANCE,
    _DASH_RE,
)
from extensions.twoa_programme.quarterly_dashboard_constants import _sanitize_atlassian_text
from extensions.twoa_programme.quarterly_dashboard_links import _jql_link, _issues_in_link

def _status_goal_target(status: dict) -> date:
    raw = status.get("goalTargetDate") or status.get("quarterEnd", "")
    return date.fromisoformat(str(raw)[:10])


def _goal_pace_tip(template: str, goal_target: date) -> str:
    return template.format(target=goal_target.isoformat())


def _section_l2_link(jql: str, title: str) -> str:
    return f'<p class="section-l2"><strong>{_jql_link(jql, _sanitize_atlassian_text(title))}</strong></p>'


def _section_l2_html(title: str) -> str:
    """TWoA section label: strong paragraph, not H2."""

    safe = html.escape(_sanitize_atlassian_text(title), quote=False)
    return f'<p class="section-l2"><strong>{safe}</strong></p>'


def _section_l1_html(title: str) -> str:
    safe = html.escape(_sanitize_atlassian_text(title), quote=False)
    return f'<p class="section-l1"><strong><u>{safe}</u></strong></p>'


def _legend_tip_row(content: str, tip: str) -> str:
    return (
        f'<abbr title="{html.escape(tip, quote=True)}" class="metric-tip">{content}</abbr>'
    )


def _sprint_band_tooltip(band: dict[str, Any]) -> str:
    name = str(band.get("label") or "").strip()
    start = band.get("start")
    end = band.get("end")
    start_s = start.isoformat() if isinstance(start, date) else str(start or "")
    end_s = end.isoformat() if isinstance(end, date) else str(end or "")
    if name and start_s and end_s:
        return f"{name}: {start_s} to {end_s}"
    if name:
        return name
    return f"{start_s} to {end_s}" if start_s and end_s else "Sprint window"


def _unpointed_cell(
    count: int | None,
    jql: str | None,
    *,
    issue_keys: list[str] | None = None,
) -> str:
    if count is None:
        return "&mdash;"
    if count > 0:
        if issue_keys:
            return _issues_in_link(issue_keys, str(count))
        if jql:
            return _jql_link(jql, str(count))
    return str(count)


def _chart_key_box(title: str, rows: list[str]) -> str:
    body = "".join(f'<div class="chart-key-row">{row}</div>' for row in rows)
    return (
        f'<div class="chart-{"milestones" if title == "Milestones" else "key"}">'
        f'<p class="chart-key-title"><strong>{html.escape(title)}</strong></p>'
        f"{body}"
        "</div>"
    )


def _chart_key_wrap(key_html: str, milestones_html: str) -> str:
    if milestones_html:
        return f'<div class="chart-key-wrap">{key_html}{milestones_html}</div>'
    return key_html


REPORT_CSS = f"""
:root {{
  color-scheme: light;
  --page-bg: #f4f5f7;
  --card-bg: #ffffff;
  --border: {ATL["line"]};
  --text: {ATL["ink"]};
  --muted: {ATL["text_subtle"]};
  --accent-bg: #deebff;
  --accent-text: {ATL["blue"]};
  --blue: {ATL["blue"]};
  --green: {ATL["green"]};
  --red: {ATL["red"]};
  --amber: {ATL["amber"]};
  --purple: {ATL["purple"]};
}}
body {{
  margin: 0;
  background: var(--page-bg);
  color: var(--text);
  font-family: {SVG_FONT};
}}
body::before {{
  content: "";
  display: block;
  height: 8px;
  background: linear-gradient(90deg, var(--blue), var(--purple), var(--green));
}}
.report-shell {{ max-width: 1280px; margin: 0 auto; padding: 28px 32px 40px; }}
.report-header, .report-card {{
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(9, 30, 66, 0.08);
  padding: 24px;
  margin-bottom: 24px;
}}
.report-header h1 {{
  margin: 0 0 8px;
  font-size: 26px;
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: var(--text);
}}
.report-subtitle {{
  margin: 0 0 16px;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.5;
}}
.report-subtitle a {{
  color: var(--blue);
  font-weight: 600;
  text-decoration: none;
}}
.report-subtitle a:hover {{ text-decoration: underline; }}
.section-l1 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.35; color: var(--text); }}
.section-l2 a {{ font-weight: 700; }}
p, li, td, th {{ font-size: 14px; line-height: 1.55; color: var(--text); }}
.report-meta-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin: 16px 0;
}}
.report-meta-card {{
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fafbfc;
  padding: 12px 14px;
}}
.report-meta-card dt {{
  margin: 0 0 4px;
  color: var(--muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}}
.report-meta-card dd {{ margin: 0; font-size: 20px; font-weight: 700; color: var(--text); }}
.health-pill {{
  display: inline-block;
  border-radius: 3px;
  color: #fff;
  font-weight: 700;
  font-size: 11px;
  padding: 4px 8px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}}
.health-pill.green {{ background: var(--green); }}
.health-pill.amber {{ background: var(--amber); }}
.health-pill.red {{ background: var(--red); }}
.health-pill.neutral {{ background: var(--neutral); }}
table {{
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}}
th, td {{ border-bottom: 1px solid var(--border); padding: 8px 10px; text-align: left; }}
tr:last-child td {{ border-bottom: none; }}
th {{ background: #fafbfc; color: var(--muted); font-size: 12px; font-weight: 700; }}
a {{ color: var(--blue); font-weight: 600; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
code {{ font-size: 12px; color: var(--text); background: #f4f5f7; padding: 1px 4px; border-radius: 3px; }}
.num {{ text-align: right; }}
tr.slice-inactive td {{
  color: #a5adba;
}}
tr.slice-inactive a {{
  color: #8993a4;
}}
tr.slice-squad td:first-child {{
  padding-left: 28px;
  color: var(--muted);
  font-size: 13px;
}}
tr.slice-squad td {{
  background: #fafbfc;
}}
tr.slice-squad a {{
  font-weight: 500;
}}
abbr.metric-tip,
abbr.release-code {{
  text-decoration: none;
  cursor: help;
}}
abbr.metric-tip .health-pill {{
  cursor: help;
}}
th abbr.metric-tip,
.report-meta-card dt abbr.metric-tip {{
  color: inherit;
  font-size: inherit;
  font-weight: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
}}
tr.row-projected td {{
  color: #a5adba;
}}
tr.row-projected a {{
  color: #8993a4;
}}
td.pending-metric {{
  color: #a5adba;
}}
td.pending-metric a {{
  color: #8993a4;
}}
.chart-wrap {{
  overflow-x: auto;
  overflow-y: hidden;
  max-width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  padding: 4px 0;
}}
.chart-wrap svg {{ display: block; min-width: 920px; }}
.report-shell .chart-wrap {{
  overflow-x: hidden;
}}
.report-shell .chart-wrap svg {{
  display: block;
  width: 100%;
  height: auto;
  min-width: 0;
  max-width: 100%;
}}
.chart-wrap-timeline {{
  overflow-y: auto;
  max-height: 720px;
}}
.chart-wrap-timeline svg a {{
  cursor: pointer;
}}
.chart-wrap-timeline svg a text {{
  text-decoration: underline;
}}
.chart-key {{
  margin: 12px 0 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #ffffff;
  padding: 12px 14px;
}}
.chart-key-wrap {{
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 12px 0 0;
  align-items: stretch;
}}
.chart-key-wrap > .chart-key,
.chart-key-wrap > .chart-milestones {{
  flex: 1 1 280px;
  margin: 0;
}}
.chart-milestones {{
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #ffffff;
  padding: 12px 14px;
}}
.chart-key-title {{
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}}
.chart-key-row {{
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}}
.legend-swatch {{
  display: inline-block;
  width: 16px;
  height: 12px;
  margin-right: 6px;
  vertical-align: middle;
  border-radius: 2px;
  flex-shrink: 0;
}}
.legend-swatch.sprint-a {{ background: {ATL["sprint_a"]}; border: 1px solid #85a9ff; }}
.legend-swatch.sprint-b {{ background: {ATL["sprint_b"]}; border: 1px solid #57d9a3; }}
.legend-swatch.release-in {{
  width: 24px;
  height: 14px;
  border-top: 3px dashed {ATL["release_in_cycle"]};
  background: transparent;
}}
.legend-swatch.release-out {{
  width: 24px;
  height: 14px;
  border-top: 3px dashed {ATL["release_out_cycle"]};
  background: transparent;
}}
.legend-swatch.milestone {{
  width: 14px;
  height: 14px;
  border: none;
  background: transparent;
  vertical-align: middle;
}}
.legend-swatch.today {{
  width: 14px;
  height: 14px;
  border: none;
  background: transparent;
  vertical-align: middle;
}}
.chart-key-row .chart-key-milestone-letter {{
  display: inline-block;
  padding-left: 22px;
}}
.chart-key-wrap abbr.metric-tip {{
  cursor: help;
  text-decoration: none;
}}
.chart-key-wrap abbr.metric-tip strong {{
  text-decoration: none;
}}
.chart-milestones .milestone-tip {{
  position: relative;
  cursor: help;
  display: inline-block;
  max-width: 100%;
}}
.milestone-tip-pop {{
  display: none;
  position: absolute;
  left: 0;
  top: calc(100% + 6px);
  z-index: 30;
  min-width: 280px;
  max-width: min(420px, 90vw);
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 8px 24px rgba(9, 30, 66, 0.18);
  color: var(--text);
  font-size: 12px;
  line-height: 1.45;
  text-align: left;
  white-space: normal;
}}
.milestone-tip:hover .milestone-tip-pop,
.milestone-tip:focus-within .milestone-tip-pop {{
  display: block;
}}
.milestone-tip-desc {{
  margin: 0 0 8px;
  color: var(--text);
}}
.milestone-tip-heading {{
  margin: 8px 0 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
}}
.milestone-tip-pop ul {{
  margin: 0 0 4px;
  padding-left: 18px;
}}
.milestone-tip-pop li {{
  margin: 2px 0;
}}
.milestone-tip-note {{
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 11px;
}}
.milestone-letter-link {{
  color: {ATL["red"]};
  font-weight: 700;
  text-decoration: none;
}}
.milestone-letter-link:hover {{
  text-decoration: underline;
}}
.chart-wrap svg a.chart-milestone-link {{
  cursor: pointer;
}}
.chart-wrap svg a.chart-milestone-link:hover line.chart-milestone-line {{
  stroke-width: 3.5;
  opacity: 1;
}}
.legend-swatch.earned {{
  width: 20px;
  height: 14px;
  border-top: 3px solid {ATL["blue"]};
  background: transparent;
}}
.legend-swatch.goal {{
  width: 20px;
  height: 14px;
  border-top: 3px dashed {ATL["neutral"]};
  background: transparent;
}}
.legend-swatch.lane-ec {{ background: {LANE_STACK_FILL["educationCloud"]}; }}
.legend-swatch.lane-int {{ background: {LANE_STACK_FILL["integration"]}; }}
.legend-swatch.lane-data {{ background: {LANE_STACK_FILL["dataMigration"]}; }}
.legend-swatch.lane-unassigned {{ background: {LANE_STACK_FILL["unassigned"]}; }}
.legend-swatch.global-line {{ border-top: 3px solid {ATL["blue"]}; width: 16px; height: 0; margin-bottom: 4px; background: transparent; }}
.footnote {{ color: var(--muted); font-size: 12px; margin-top: 12px; line-height: 1.5; }}
"""


def _unpointed_metrics(
    goal: dict | None,
) -> tuple[int | None, str | None, list[str] | None, dict[str, dict]]:
    """Global and per-lane unpointed Story/Bug counts from quarter-goal.json."""
    if not goal:
        return None, None, None, {}
    total = goal.get("unpointedStoriesBugs")
    jql = goal.get("unpointedStoriesBugsJql")
    issue_keys = goal.get("unpointedStoriesBugsIssueKeys")
    by_scope = goal.get("plannedStoryPointsByScope") or {}
    nested = by_scope.get("unpointedStoriesBugs") or {}
    by_lane = nested.get("byLane") or {}
    if total is None and nested.get("total") is not None:
        total = nested.get("total")
    if not jql and nested.get("jql"):
        jql = nested.get("jql")
    if not issue_keys and nested.get("issueKeys"):
        issue_keys = nested.get("issueKeys")
    return total, jql, issue_keys, by_lane


def _projected_release_display_name(name: str) -> str:
    if not name.startswith("projected-"):
        return name
    stem = name.removeprefix("projected-")
    if stem.endswith("-engine") and len(stem) > 7:
        date_part = stem[: -len("-engine")]
        parts = date_part.split("-")
        if len(parts) == 3:
            return f"{parts[0]}{parts[1]}{parts[2]}-engine"
    return stem


def _metric_tip(label: str, tooltip: str) -> str:
    return (
        f'<abbr title="{html.escape(tooltip, quote=True)}" class="metric-tip">'
        f"{html.escape(label)}</abbr>"
    )


def _svg_embedded_title(tooltip: str) -> str:
    return f"<title>{html.escape(tooltip)}</title>"


def _meta_card(label: str, value: str, *, tip: str | None = None) -> str:
    dt = _metric_tip(label, tip) if tip else html.escape(label)
    return f'<div class="report-meta-card"><dt>{dt}</dt><dd>{value}</dd></div>'


def _th(label: str, *, tip: str | None = None, num: bool = False) -> str:
    inner = _metric_tip(label, tip) if tip else html.escape(label)
    cls = ' class="num"' if num else ""
    return f"<th{cls}>{inner}</th>"


def _td(inner: str, *, tip: str | None = None, num: bool = False, pending: bool = False) -> str:
    attrs = ""
    if tip:
        attrs += f' title="{html.escape(tip, quote=True)}"'
    classes: list[str] = []
    if num:
        classes.append("num")
    if pending:
        classes.append("pending-metric")
    if classes:
        attrs += f' class="{" ".join(classes)}"'
    return f"<td{attrs}>{inner}</td>"

