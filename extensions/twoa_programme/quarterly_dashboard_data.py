"""Artifact loading and allocation helpers for quarterly dashboard."""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import Any

from extensions.twoa_programme.quarter_scope import (
    EC_SQUAD_NAME_TO_SLUG,
    EC_SQUAD_SPECS,
    education_cloud_squad_jqls,
)
from extensions.twoa_programme.pde_engine_releases import (
    carriage_cycle_label,
    carriage_delivery_kind,
    release_row_code,
)
from extensions.twoa_programme.quarterly_dashboard_constants import (
    ATL,
    JIRA_SERVER,
    LANE_ORDER,
    TIP_EC_SQUAD_SLICE,
    TIP_IN_PROGRESS_ROW,
    TIP_PROJECTED_ROW,
    TIP_RELEASE_EARNED,
    TIP_SPRINT_EARNED,
)
from extensions.twoa_programme.quarterly_dashboard_markup import _projected_release_display_name
from extensions.twoa_programme.quarterly_dashboard_links import (
    _browse_link,
    _filter_link,
    _fix_version_link,
    _fmt_num,
    _issues_in_link,
    _jql_link,
)
from extensions.twoa_programme.quarterly_dashboard_markup import (
    _metric_tip,
    _sanitize_atlassian_text,
    _section_l2_html,
    _td,
    _th,
    _unpointed_cell,
)
def load_artifacts(output_dir: Path) -> dict:
    """Merge quarter-status, deploy_burn, and squad_velocity JSON from output dir."""
    output_dir = Path(output_dir)
    status_path = output_dir / "quarter-status.json"
    if not status_path.is_file():
        raise FileNotFoundError(f"Missing {status_path}; run quarter_status.py --from-burn --write")

    status = json.loads(status_path.read_text(encoding="utf-8"))
    goal_path = output_dir / "quarter-goal.json"
    if goal_path.is_file():
        goal = json.loads(goal_path.read_text(encoding="utf-8"))
        if goal.get("plannedStoryPoints") is not None:
            status["plannedStoryPoints"] = goal["plannedStoryPoints"]
            status["goalSource"] = goal.get("source", "quarter-goal.json")
            status["goalInitiativeKey"] = goal.get("initiativeKey")
            earned = float(status.get("earnedStoryPoints") or 0.0)
            from dataclasses import replace

            from extensions.twoa_programme.quarterly_reporting import load_quarterly_reporting_config

            cfg = load_quarterly_reporting_config(
                Path(__file__).resolve().parents[2] / "config" / "quarterly-reporting.json"
            )
            cfg = replace(
                cfg,
                goal=replace(
                    cfg.goal,
                    planned_story_points=float(goal["plannedStoryPoints"]),
                ),
            )
            derived = cfg.tracking_snapshot(earned_story_points=earned)
            for key in (
                "idealEarnedStoryPoints",
                "burnVariance",
                "requiredDailyVelocity",
                "onTrack",
            ):
                if key in derived:
                    status[key] = derived[key]
    payload: dict = {"status": status}
    burn_path = output_dir / "deploy_burn.json"
    if burn_path.is_file():
        payload["burn"] = json.loads(burn_path.read_text(encoding="utf-8"))
    squad_path = output_dir / "squad_velocity.json"
    if squad_path.is_file():
        payload["squad"] = json.loads(squad_path.read_text(encoding="utf-8"))
    releases_path = output_dir / "engine-releases.json"
    if releases_path.is_file():
        payload["releases"] = json.loads(releases_path.read_text(encoding="utf-8"))
    plan_path = output_dir / "release-plan-metadata.json"
    if plan_path.is_file():
        payload["releasePlan"] = json.loads(plan_path.read_text(encoding="utf-8"))
    goal_path = output_dir / "quarter-goal.json"
    if goal_path.is_file():
        payload["goal"] = json.loads(goal_path.read_text(encoding="utf-8"))
    alloc_path = output_dir / "burn-allocation.json"
    if alloc_path.is_file():
        payload["burnAllocation"] = json.loads(alloc_path.read_text(encoding="utf-8"))
    epic_path = output_dir / "epic-timeline.json"
    if epic_path.is_file():
        payload["epicTimeline"] = json.loads(epic_path.read_text(encoding="utf-8"))
    milestone_path = output_dir / "delivery-milestones.json"
    if milestone_path.is_file():
        payload["deliveryMilestones"] = json.loads(milestone_path.read_text(encoding="utf-8"))
    return payload


def _parse_report_date(value: str | None) -> date:
    if not value:
        return date.today()
    return date.fromisoformat(str(value)[:10])


def _sprint_is_future(sprint: dict, as_of: date) -> bool:
    """True when the sprint window has not started yet (relative to report as-of)."""
    start_s = sprint.get("startDate")
    if not start_s:
        return False
    return date.fromisoformat(str(start_s)[:10]) > as_of


def _sprint_is_current(sprint: dict, as_of: date) -> bool:
    start_s = sprint.get("startDate")
    end_s = sprint.get("endDate")
    if not start_s or not end_s:
        return False
    start = date.fromisoformat(str(start_s)[:10])
    end = date.fromisoformat(str(end_s)[:10])
    return start <= as_of <= end


def _release_is_active(rel: dict, releases: list[dict], as_of: date) -> bool:
    if rel.get("projected"):
        return False
    from extensions.twoa_programme.burn_allocation_scope import active_release

    active = active_release(releases, as_of)
    if not active:
        return False
    return str(active.get("releaseDate"))[:10] == str(rel.get("releaseDate"))[:10]


def _allocation_metric_cells(
    row: dict,
    *,
    earned_keys: list[str],
    in_progress: bool,
) -> tuple[str, str]:
    if in_progress:
        scoped_sp = row.get("scopedStoryPoints")
        scoped_keys = [str(key) for key in (row.get("scopedIssueKeys") or []) if key]
        issue_count = row.get("scopedIssueCount")
        if issue_count is None:
            issue_count = len(scoped_keys) if scoped_keys else len(earned_keys)
        keys_for_link = scoped_keys or earned_keys
        sp_cell = _td(
            _fmt_num(scoped_sp if scoped_sp is not None else row.get("claimedStoryPoints")),
            num=True,
            pending=True,
            tip=TIP_IN_PROGRESS_ROW,
        )
        issue_inner = (
            _issues_in_link(keys_for_link, str(issue_count))
            if keys_for_link
            else str(issue_count)
        )
        issue_cell = _td(issue_inner, num=True, pending=True, tip=TIP_IN_PROGRESS_ROW)
        return sp_cell, issue_cell

    issue_count = len(earned_keys)
    issue_cell = (
        _issues_in_link(earned_keys, str(issue_count))
        if earned_keys
        else str(issue_count)
    )
    return (
        _td(_fmt_num(row.get("claimedStoryPoints")), num=True),
        _td(issue_cell, num=True),
    )


def _allocation_tables(
    allocation: dict,
    *,
    burn: dict | None = None,
    goal: dict | None = None,
    as_of: str | None = None,
) -> str:
    global_jql = ((burn or {}).get("scope") or {}).get("globalBurnJql") or ""
    as_of_date = _parse_report_date(as_of)
    sprint_rows = ""
    for sprint in allocation.get("sprints") or []:
        events = sprint.get("events") or []
        keys = [str(event["key"]) for event in events if event.get("key")]
        name = sprint.get("name", "")
        if keys:
            name_cell = _issues_in_link(keys, name)
        elif global_jql and sprint.get("startDate") and sprint.get("endDate"):
            name_cell = _jql_link(global_jql, name)
        else:
            name_cell = html.escape(name)
        projected = _sprint_is_future(sprint, as_of_date)
        in_progress = bool(sprint.get("inProgress")) or (
            not projected and _sprint_is_current(sprint, as_of_date)
        )
        row_class = ' class="row-projected"' if projected else ""
        row_tip = TIP_PROJECTED_ROW if projected else None
        sp_cell, issue_cell = _allocation_metric_cells(
            sprint,
            earned_keys=keys,
            in_progress=in_progress,
        )
        sprint_rows += (
            f"<tr{row_class}>"
            + _td(name_cell, tip=row_tip)
            + _td(html.escape(sprint.get("startDate", "")))
            + _td(html.escape(sprint.get("endDate", "")))
            + sp_cell
            + issue_cell
            + "</tr>"
        )
    release_rows = ""
    releases = allocation.get("inCycleReleases") or []
    for rel in releases:
        projected = bool(rel.get("projected"))
        fix_version = str(rel.get("name") or "")
        display_name = _projected_release_display_name(fix_version)
        events = rel.get("events") or []
        keys = [str(event["key"]) for event in events if event.get("key")]
        code_cell = _release_code_cell(rel)
        if projected:
            fix_cell = html.escape(display_name)
        elif fix_version and not fix_version.startswith("projected-"):
            fix_cell = _fix_version_link(fix_version, display_name)
        else:
            fix_cell = html.escape(display_name or str(rel.get("releaseDate", "")))
        in_progress = bool(rel.get("inProgress")) or (
            not projected and _release_is_active(rel, releases, as_of_date)
        )
        row_class = ' class="row-projected"' if projected else ""
        row_tip = TIP_PROJECTED_ROW if projected else None
        sp_cell, issue_cell = _allocation_metric_cells(
            rel,
            earned_keys=keys,
            in_progress=in_progress,
        )
        release_rows += (
            f"<tr{row_class}>"
            + _td(fix_cell, tip=row_tip)
            + f"<td>{code_cell}</td>"
            + sp_cell
            + issue_cell
            + "</tr>"
        )
    return (
        "<section class=\"report-card\">"
        + _section_l2_html("Story Points Earned against DOD by Sprint")
        + "<table><thead><tr>"
        + _th("Sprint")
        + _th("Start")
        + _th("End")
        + _th("Earned SP", tip=TIP_SPRINT_EARNED, num=True)
        + _th("Issues")
        + "</tr></thead><tbody>"
        + (sprint_rows or "<tr><td colspan=\"5\">Run allocate_burn.py --write</td></tr>")
        + "</tbody></table>"
        + "<p class=\"footnote\">Story points earned when an issue first met the lane definition of done "
        "(Deploy+ for Education Cloud and Integration; Done for Data Migration). "
        "Each row totals global quarter-scope burn whose credit date falls in that Release Plan sprint window "
        "(programme calendar from the release workbook, all lanes combined). "
        "Sprint names link to the issues credited in that window.</p>"
        + _section_l2_html("Story Points Earned against Releases")
        + "<table><thead><tr>"
        + _th("Release")
        + _th("Code")
        + _th("Earned SP", tip=TIP_RELEASE_EARNED, num=True)
        + _th("Issues")
        + "</tr></thead><tbody>"
        + (release_rows or "<tr><td colspan=\"4\">Run allocate_burn.py --write</td></tr>")
        + "</tbody></table>"
        "</section>"
    )


def _lane_planned_goals(goal: dict | None) -> dict[str, float]:
    """Per-lane planned SP from quarter-goal.json scope breakdown."""
    by_scope = (goal or {}).get("plannedStoryPointsByScope") or {}
    goals: dict[str, float] = {}
    for key in LANE_ORDER:
        val = (by_scope.get(key) or {}).get("plannedStoryPoints")
        if val is not None:
            goals[key] = float(val)
    return goals


def _total_scope_planned(goal: dict | None) -> float | None:
    """Sum of planned SP in global quarter scope (for lane chart total goal line)."""
    by_scope = (goal or {}).get("plannedStoryPointsByScope") or {}
    if row := by_scope.get("inGlobalQuarter"):
        val = row.get("plannedStoryPoints")
        if val is not None:
            return float(val)
    lane_goals = _lane_planned_goals(goal)
    if lane_goals:
        return sum(lane_goals.values())
    return None


def _education_cloud_squad_data(goal: dict | None, *, quarter_filter: str) -> dict[str, dict]:
    """Per-squad planned/unpointed from quarter-goal.json, with JQL fallback."""
    by_scope = (goal or {}).get("plannedStoryPointsByScope") or {}
    squad_data = dict(by_scope.get("educationCloudSquads") or {})
    for slug, spec in education_cloud_squad_jqls(quarter_filter=quarter_filter).items():
        squad_data.setdefault(
            slug,
            {
                "slug": slug,
                "label": spec["label"],
                "scopeJql": spec["scopeJql"],
                "burnJql": spec["burnJql"],
            },
        )
    return squad_data


def _earned_by_ec_squad(lane_burn: dict) -> dict[str, float]:
    """Deploy-earned SP in quarter, grouped by Delivery Squad on educationCloud events."""
    totals = {slug: 0.0 for slug, _, _ in EC_SQUAD_SPECS}
    for event in lane_burn.get("events") or []:
        for squad_name in event.get("deliverySquads") or []:
            slug = EC_SQUAD_NAME_TO_SLUG.get(squad_name)
            if slug:
                totals[slug] += float(event.get("story_points") or 0)
                break
    return totals


def _education_cloud_squad_slice_rows(
    burn: dict,
    goal: dict | None,
    *,
    quarter_filter: str,
) -> str:
    """Indented sub-rows under Education Cloud in the lane slice table."""
    lane_burn = (burn.get("lanes") or {}).get("educationCloud") or {}
    squad_data = _education_cloud_squad_data(goal, quarter_filter=quarter_filter)
    earned_by_squad = _earned_by_ec_squad(lane_burn)
    rows = ""
    for slug, _, _ in EC_SQUAD_SPECS:
        spec = squad_data.get(slug) or {}
        label = spec.get("label") or slug
        scope_jql = spec.get("scopeJql") or spec.get("burnJql") or ""
        burn_jql = spec.get("burnJql") or scope_jql
        planned = spec.get("plannedStoryPoints")
        earned = earned_by_squad.get(slug, 0.0)
        unpointed = spec.get("unpointedStoriesBugs")
        unpointed_jql = spec.get("unpointedStoriesBugsJql")
        unpointed_keys = spec.get("unpointedIssueKeys")
        if scope_jql:
            slice_inner = _jql_link(scope_jql, label)
        else:
            slice_inner = html.escape(label)
        slice_cell = _td(
            f'<abbr title="{html.escape(TIP_EC_SQUAD_SLICE, quote=True)}" class="metric-tip">'
            f"{slice_inner}</abbr>"
        )
        planned_cell = (
            _jql_link(scope_jql, _fmt_num(planned))
            if scope_jql and planned is not None
            else _fmt_num(planned)
        )
        earned_cell = (
            _jql_link(burn_jql, _fmt_num(earned))
            if burn_jql and earned
            else _fmt_num(earned if earned else 0.0)
        )
        unpointed_cell = _unpointed_cell(unpointed, unpointed_jql, issue_keys=unpointed_keys)
        rows += (
            '<tr class="slice-squad">'
            f"{slice_cell}"
            f'<td class="num">{planned_cell}</td>'
            f'<td class="num">{earned_cell}</td>'
            f'<td class="num">{unpointed_cell}</td>'
            "</tr>"
        )
    return rows


def _release_code_tooltip(rel: dict) -> str:
    rel_date = str(rel.get("releaseDate") or "")
    projected = bool(rel.get("projected"))
    cycle = carriage_cycle_label(rel.get("carriageType"), projected=projected)
    delivery = carriage_delivery_kind(rel.get("carriageType"), projected=projected)
    if delivery == "Go Live":
        return f"{rel_date} | {cycle}"
    return f"{rel_date} | {cycle} | {delivery}"


def _release_code_cell(rel: dict) -> str:
    code = rel.get("releaseCode") or release_row_code(rel)
    if bool(rel.get("projected")) and code.endswith("*"):
        code = code.rstrip("*").strip()
    tip = html.escape(_release_code_tooltip(rel), quote=True)
    return f'<abbr title="{tip}" class="release-code">{html.escape(code)}</abbr>'


