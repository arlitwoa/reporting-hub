"""Dashboard HTML and Confluence render entry points."""

from __future__ import annotations

import html

from artifact.confluence_blocks import (
    h2,
    jira_issue_link,
    p,
    p_html,
    page_link,
    table_wide,
    url_link,
)

from extensions.twoa_programme.epic_timeline import EPIC_TIMELINE_EXTRA_CSS, epic_timeline_key_html
from extensions.twoa_programme.quarterly_dashboard_constants import (
    ATL,
    JIRA_SERVER,
    TIP_DAYS_LEFT,
    TIP_EARNED_SP,
    TIP_ELAPSED,
    TIP_GOAL_DAYS_LEFT,
    TIP_GOAL_SP,
    TIP_IDEAL_LINEAR,
    TIP_REQ_DAILY,
    TIP_SQUAD_BASELINE,
    TIP_SQUAD_CREDIT,
    TIP_SQUAD_SPRINTS,
    TIP_UNPOINTED,
    TIP_VARIANCE,
)
from extensions.twoa_programme.quarterly_dashboard_svg_core import _resolve_chart_calendar
from extensions.twoa_programme.quarterly_dashboard_markup import _unpointed_metrics
from extensions.twoa_programme.quarterly_dashboard_links import (
    _browse_link,
    _fmt_num,
    _jql_link,
    _lane_label_link,
)
from extensions.twoa_programme.quarterly_dashboard_markup import (
    REPORT_CSS,
    _goal_pace_tip,
    _meta_card,
    _sanitize_atlassian_text,
    _section_l2_html,
    _section_l2_link,
    _status_goal_target,
    _th,
    _unpointed_cell,
)
from extensions.twoa_programme.quarterly_dashboard_tables import (
    _education_cloud_squad_table_rows,
    _track_pill,
)
from extensions.twoa_programme.quarterly_dashboard_calendar import _chart_legend_html
from extensions.twoa_programme.quarterly_dashboard_svg_core import (
    _load_delivery_milestones,
)
from extensions.twoa_programme.quarterly_dashboard_svg_epic import _burn_svg, _epic_timeline_svg
from extensions.twoa_programme.quarterly_dashboard_data import _allocation_tables
from extensions.twoa_programme.quarterly_dashboard_svg_lane import _scope_coverage_section


def build_confluence_template_body(
    *,
    quarter_label: str,
    quarter_slug: str,
    quarter_start: str,
    quarter_end: str,
    initiative_key: str,
    goal_target_date: str | None,
    github_pages_url: str,
    generated_on: str,
) -> str:
    """Scaffold storage HTML for the live Current Quarter page before first data publish."""
    goal_rows = (
        [["Goal target", goal_target_date]]
        if goal_target_date and goal_target_date != quarter_end
        else []
    )
    progress_rows = [
        ["Quarter", f"{quarter_label} ({quarter_slug})"],
        ["Initiative", initiative_key],
        ["Window", f"{quarter_start} to {quarter_end}"],
        *goal_rows,
        ["Status", "Awaiting first refresh"],
    ]
    lane_rows = [
        ["Lane 1, Education Cloud (Deploy+)", "Pending"],
        ["Lane 2, Integration (Deploy+)", "Pending"],
        ["Lane 3, Data Migration (Done only)", "Pending"],
    ]
    squad_rows = [
        ["Kakariki", "Pending"],
        ["Kikorangi", "Pending"],
        ["Waiporoporo", "Pending"],
    ]
    pdm = page_link("DTRAIN", "EPC Programme Delivery Model")
    return (
        p(
            "Current delivery quarter report for EPCE: three-lane programme progress "
            "with summary tables on Confluence and interactive charts on GitHub Pages."
        )
        + p_html(
            f"Story {jira_issue_link('https://twoa.atlassian.net', 'EPCE-6745')}. "
            f"Initiative {jira_issue_link('https://twoa.atlassian.net', initiative_key)}. "
            f"Three-lane model: {pdm}."
        )
        + h2("Quarter Progress")
        + table_wide(["Metric", "Value"], progress_rows)
        + h2("Deploy Burn by Lane")
        + table_wide(["Lane", "Earned SP"], lane_rows)
        + h2("Education Cloud Squad Velocity")
        + table_wide(["Squad", "Quarter deploy credit"], squad_rows)
        + h2("Live Dashboard")
        + p_html(
            f"Full interactive dashboard: {url_link(github_pages_url, github_pages_url)}. "
            "Confluence shows summary tables only; charts are not embedded here."
        )
    )


def build_confluence_body(payload: dict, *, generated_on: str) -> str:
    """Confluence storage HTML (tables and paragraphs, no embedded stylesheet)."""
    status = payload["status"]
    burn = payload.get("burn") or {}
    squad = payload.get("squad") or {}
    goal = payload.get("goal")
    initiative_key = (
        (goal or {}).get("initiativeKey")
        or status.get("goalInitiativeKey")
        or status.get("initiativeKey")
        or (payload.get("epicTimeline") or {}).get("initiativeKey")
        or "EPCE-3897"
    )
    quarter = status.get("quarter", "")

    lane_rows = ""
    for lane_key, lane in (burn.get("lanes") or {}).items():
        label = _sanitize_atlassian_text(lane.get("label", lane_key))
        lane_rows += (
            "<tr>"
            f"<td>{_lane_label_link(burn, goal, lane_key, label)}</td>"
            f'<td style="text-align:right">{_fmt_num(lane.get("totalStoryPointsEarned"))}</td>'
            f'<td style="text-align:right">{lane.get("earnedEventCount", 0)}</td>'
            "</tr>"
        )

    squad_rows = _education_cloud_squad_table_rows(squad)

    burn_by_lane = status.get("burnByLane") or {}
    if not lane_rows and burn_by_lane:
        for lane_key, total in burn_by_lane.items():
            lane_rows += (
                "<tr>"
                f"<td>{html.escape(lane_key)}</td>"
                f'<td style="text-align:right">{_fmt_num(total)}</td>'
                "<td>&mdash;</td></tr>"
            )

    return (
        "<p>"
        f"Initiative {_browse_link(initiative_key)}"
        f" | {html.escape(status.get('quarterStart', ''))} - {html.escape(status.get('quarterEnd', ''))}</p>"
        "<p><strong>Three-lane quarterly model:</strong> Education Cloud (Deploy+), "
        "Integration (Deploy+), Data Migration (Done only). "
        "Earned SP from changelog credit in the delivery quarter.</p>"
        + _section_l2_html("Quarter Progress")
        + "<table data-layout=\"wide\"><tbody>"
        f"<tr><td>Quarter</td><td>{html.escape(quarter)}</td></tr>"
        f"<tr><td>As of</td><td>{html.escape(str(status.get('asOf', '')))}</td></tr>"
        f"<tr><td>Elapsed</td><td>{_fmt_num((status.get('elapsedFraction') or 0) * 100, digits=1)}%</td></tr>"
        f"<tr><td>Days remaining</td><td>{status.get('daysRemaining', '')}</td></tr>"
        + (
            f"<tr><td>Goal target</td><td>{html.escape(str(status.get('goalTargetDate')))}</td></tr>"
            f"<tr><td>Days to goal target</td><td>{status.get('goalDaysRemaining', '')}</td></tr>"
            if status.get("goalTargetDate")
            and status.get("goalTargetDate") != status.get("quarterEnd")
            else ""
        )
        + f"<tr><td>Earned SP</td><td>{_jql_link((burn.get('scope') or {}).get('globalBurnJql', ''), _fmt_num(status.get('earnedStoryPoints'))) if (burn.get('scope') or {}).get('globalBurnJql') else _fmt_num(status.get('earnedStoryPoints'))}</td></tr>"
        f"<tr><td>Goal SP</td><td>{_browse_link((goal or {}).get('initiativeKey') or status.get('goalInitiativeKey', ''), _fmt_num(status.get('plannedStoryPoints'))) if (goal or {}).get('initiativeKey') or status.get('goalInitiativeKey') else _fmt_num(status.get('plannedStoryPoints'))}</td></tr>"
        f"<tr><td>Ideal earned (linear)</td><td>{_fmt_num(status.get('idealEarnedStoryPoints'))}</td></tr>"
        f"<tr><td>Variance</td><td>{_fmt_num(status.get('burnVariance'))}</td></tr>"
        f"<tr><td>Required daily velocity</td><td>{_fmt_num(status.get('requiredDailyVelocity'))}</td></tr>"
        "</tbody></table>"
        + _section_l2_html("Deploy Burn by Lane")
        + "<table data-layout=\"wide\"><thead><tr><th>Lane</th>"
        '<th style="text-align:right">Earned SP</th>'
        '<th style="text-align:right">Events</th></tr></thead><tbody>'
        + (lane_rows or "<tr><td colspan=\"3\">No deploy burn data for this quarter.</td></tr>")
        + "</tbody></table>"
        + _section_l2_html("Education Cloud Squad Velocity")
        + "<table data-layout=\"wide\"><thead><tr><th>Squad</th>"
        '<th style="text-align:right">Sprints</th>'
        '<th style="text-align:right">Quarter deploy credit</th>'
        '<th style="text-align:right">Baseline velocity</th></tr></thead><tbody>'
        + (squad_rows or "<tr><td colspan=\"4\">No squad velocity data for this quarter.</td></tr>")
        + "</tbody></table>"
    )


def build_dashboard_html(payload: dict, *, generated_on: str, page_title: str) -> str:
    status = payload["status"]
    burn = payload.get("burn") or {}
    squad = payload.get("squad") or {}
    goal = payload.get("goal")
    initiative_key = (
        (goal or {}).get("initiativeKey")
        or status.get("goalInitiativeKey")
        or status.get("initiativeKey")
        or (payload.get("epicTimeline") or {}).get("initiativeKey")
        or "EPCE-3897"
    )
    daily = burn.get("combinedDaily") or []
    planned = status.get("plannedStoryPoints")

    squad_table = _education_cloud_squad_table_rows(squad, include_board=True)

    allocation = payload.get("burnAllocation")
    sprint_bands, releases = _resolve_chart_calendar(payload, status, squad)
    quarter_start = status.get("quarterStart", "")
    quarter_end = status.get("quarterEnd", "")
    from extensions.twoa_programme.delivery_milestones import chart_milestone_rows

    milestones = chart_milestone_rows(payload.get("deliveryMilestones")) or _load_delivery_milestones()
    goal_target = _status_goal_target(status)
    chart = _burn_svg(
        daily,
        planned=planned,
        quarter_start=status.get("quarterStart", ""),
        quarter_end=status.get("quarterEnd", ""),
        goal_target=status.get("goalTargetDate"),
        as_of=status.get("asOf"),
        sprint_bands=sprint_bands,
        releases=releases,
        milestones=milestones,
    )
    epic_timeline = payload.get("epicTimeline") or {}
    epic_chart = _epic_timeline_svg(
        epic_timeline.get("epics") or [],
        quarter_start=status.get("quarterStart", ""),
        quarter_end=status.get("quarterEnd", ""),
        sprint_bands=sprint_bands,
        releases=releases,
        milestones=milestones,
    )

    global_burn_jql = (burn.get("scope") or {}).get("globalBurnJql") or ""
    goal_initiative = initiative_key
    unpointed_total, unpointed_jql, unpointed_issue_keys, _ = _unpointed_metrics(goal)

    earned_dd = (
        _jql_link(global_burn_jql, _fmt_num(status.get("earnedStoryPoints")))
        if global_burn_jql and status.get("earnedStoryPoints") is not None
        else _fmt_num(status.get("earnedStoryPoints"))
    )
    goal_dd = (
        _browse_link(goal_initiative, _fmt_num(status.get("plannedStoryPoints")))
        if goal_initiative and status.get("plannedStoryPoints") is not None
        else _fmt_num(status.get("plannedStoryPoints"))
    )
    meta = [
        ("Elapsed", f"{(status.get('elapsedFraction') or 0) * 100:.1f}%", TIP_ELAPSED),
        ("Days left", str(status.get("daysRemaining", "")), TIP_DAYS_LEFT),
    ]
    if status.get("goalTargetDate") and status.get("goalTargetDate") != status.get("quarterEnd"):
        meta.append(
            (
                "Goal days left",
                str(status.get("goalDaysRemaining", "")),
                _goal_pace_tip(TIP_GOAL_DAYS_LEFT, goal_target),
            )
        )
    meta.extend(
        [
            ("Earned SP", earned_dd, TIP_EARNED_SP),
            ("Goal SP", goal_dd, TIP_GOAL_SP),
            (
                "Ideal (linear)",
                _fmt_num(status.get("idealEarnedStoryPoints")),
                _goal_pace_tip(TIP_IDEAL_LINEAR, goal_target),
            ),
            (
                "Variance",
                _fmt_num(status.get("burnVariance")),
                _goal_pace_tip(TIP_VARIANCE, goal_target),
            ),
            (
                "Req. daily SP",
                _fmt_num(status.get("requiredDailyVelocity")),
                _goal_pace_tip(TIP_REQ_DAILY, goal_target),
            ),
            (
                "Unpointed Story/Bug",
                _unpointed_cell(unpointed_total, unpointed_jql, issue_keys=unpointed_issue_keys)
                if unpointed_total is not None
                else "&mdash;",
                TIP_UNPOINTED,
            ),
        ]
    )
    meta_html = "".join(_meta_card(label, value, tip=tip) for label, value, tip in meta)

    chart_section_title = (
        _section_l2_link(global_burn_jql, "Cumulative Deploy | Earned SP")
        if global_burn_jql
        else _section_l2_html("Cumulative Deploy | Earned SP")
    )
    epic_section_title = _section_l2_link(
        f'project = EPCE AND issuetype = Epic AND parent = {goal_initiative or "EPCE-3897"}',
        "Epic Timeline",
    )

    goal_target_note = ""
    if status.get("goalTargetDate") and status.get("goalTargetDate") != status.get("quarterEnd"):
        goal_target_note = f" | Goal target {html.escape(str(status.get('goalTargetDate')))}"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page_title)}</title>
  <style>{REPORT_CSS}{EPIC_TIMELINE_EXTRA_CSS}</style>
</head>
<body>
  <main class="report-shell">
    <header class="report-header">
      <h1>{html.escape(page_title)}</h1>
      <p class="report-subtitle">
        Initiative <a href="{JIRA_SERVER}/browse/{html.escape(initiative_key)}">{html.escape(initiative_key)}</a>
        | {html.escape(status.get("quarterStart", ""))} - {html.escape(status.get("quarterEnd", ""))}{goal_target_note}
        | {html.escape(generated_on)}
      </p>
      <p>{_track_pill(status.get("onTrack"), goal_target=goal_target)}</p>
      <dl class="report-meta-grid">{meta_html}</dl>
    </header>
    <section class="report-card">
      {chart_section_title}
      <div class="chart-wrap">{chart}</div>
      {_chart_legend_html()}
    </section>
    <section class="report-card">
      {epic_section_title}
      <div class="chart-wrap chart-wrap-timeline chart-wrap-epic-timeline">{epic_chart}</div>
      {epic_timeline_key_html()}
    </section>
    {_scope_coverage_section(status, burn, goal, sprint_bands=sprint_bands, releases=releases, milestones=milestones)}
    <section class="report-card">
      {_section_l2_html("Education Cloud | Squad Velocity")}
      <table>
        <thead><tr>{_th("Squad")}{_th("Board")}{_th("Sprints", tip=TIP_SQUAD_SPRINTS, num=True)}
        {_th("Quarter credit", tip=TIP_SQUAD_CREDIT, num=True)}{_th("Baseline", tip=TIP_SQUAD_BASELINE, num=True)}</tr></thead>
        <tbody>{squad_table or '<tr><td colspan="5">Run squad_velocity.py --write</td></tr>'}</tbody>
      </table>
    </section>
    {_allocation_tables(allocation, burn=burn, goal=goal, as_of=status.get("asOf")) if allocation else ""}
  </main>
</body>
</html>"""
