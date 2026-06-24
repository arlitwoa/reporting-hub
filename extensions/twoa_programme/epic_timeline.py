"""Epic timeline chart for quarterly dashboard (same calendar scale as deploy burn)."""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from datetime import date
from typing import Any

from artifact.delivery_health.sprint_engine import engine_date_from_fix_version

from extensions.twoa_programme.pde_engine_releases import is_placeholder_engine_version
from extensions.twoa_programme.quarter_scope import (
    EC_SQUAD_NAME_TO_SLUG,
    EC_SQUAD_SPECS,
    classify_exclusive_lane,
)

ENGINE_FV_RE = re.compile(r"\d{8}-engine", re.IGNORECASE)

EPIC_ROW_HEIGHT = 20
EPIC_SWIMLANE_HEADER = 22
EPIC_EC_SQUAD_HEADER = 18
EPIC_LABEL_WIDTH = 220
EPIC_CHART_PX_PER_DAY = 11.0
EPIC_BAR_OPACITY = 0.85

# Same slice order as Story Points Achieved by Lane table.
LANE_DISPLAY_ORDER = ("educationCloud", "integration", "dataMigration", "unassigned")
# Tie-break when child SP totals match (L3 → L2 → L1 → unassigned).
LANE_TIEBREAK_ORDER = ("dataMigration", "integration", "educationCloud", "unassigned")

EPIC_STATUS_FILL = {
    "done": "#00875a",
    "active": "#0052cc",
    "open": "#6b778c",
}

EPIC_CHILD_ISSUE_TYPES = frozenset({"Story", "Bug"})

EPIC_BAR_OPACITY_SCOPE = 0.35
EPIC_BAR_OPACITY_EARNED = 0.92
EPIC_BAR_OPACITY_NO_SP = 0.85

EPIC_TIMELINE_EXTRA_CSS = """
.chart-wrap-epic-timeline {
  max-height: none;
  overflow-x: hidden;
  overflow-y: visible;
}
.report-shell .chart-wrap-epic-timeline svg {
  display: block;
  width: 100%;
  height: auto;
  min-width: 0;
  max-width: 100%;
}
.chart-wrap-epic-timeline svg a {
  cursor: pointer;
}
.chart-wrap-epic-timeline svg a text {
  text-decoration: underline;
}
.chart-wrap-epic-timeline svg a.milestone-scope-segment {
  cursor: pointer;
}
.chart-key-epic-scope .chart-key-phase-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin: 8px 0 4px;
}
.chart-key-epic-scope .chart-key-phase-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}
"""


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _engine_fix_versions(names: list[str]) -> list[str]:
    out: list[str] = []
    for name in names:
        n = (name or "").strip()
        if not n or is_placeholder_engine_version(n):
            continue
        if ENGINE_FV_RE.search(n):
            out.append(n)
    return out


def build_release_date_lookup(
    releases: list[dict[str, Any]] | None,
    release_plan: dict[str, Any] | None = None,
) -> dict[str, date]:
    """Map fixVersion name to release date from allocation or release plan."""
    lookup: dict[str, date] = {}
    for source in (
        (release_plan or {}).get("inCycleReleases") or [],
        releases or [],
    ):
        for row in source:
            name = str(row.get("name") or "").strip()
            day = _parse_day(str(row.get("releaseDate") or ""))
            if name and day and name not in lookup:
                lookup[name] = day
    return lookup


def _dominant_fix_version(epic_versions: list[str], child_versions: list[str]) -> str | None:
    candidates = _engine_fix_versions(epic_versions)
    if candidates:
        return sorted(candidates)[-1]
    counts: dict[str, int] = {}
    for name in _engine_fix_versions(child_versions):
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: (item[1], item[0]))[0]


def resolve_epic_window(
    *,
    created: str | None,
    epic_fix_versions: list[str],
    child_fix_versions: list[str],
    release_lookup: dict[str, date],
    quarter_start: date,
    quarter_end: date,
) -> tuple[date, date, str | None]:
    """Bar from quarter start or created (later) through target engine release or quarter end."""
    created_day = _parse_day(created)
    start = quarter_start
    if created_day and created_day > start:
        start = created_day
    if start > quarter_end:
        start = quarter_end

    fix_version = _dominant_fix_version(epic_fix_versions, child_fix_versions)
    end = quarter_end
    if fix_version:
        end = release_lookup.get(fix_version) or engine_date_from_fix_version(fix_version) or quarter_end
    if end < start:
        end = start
    if end > quarter_end:
        end = quarter_end
    return start, end, fix_version


def classify_epic_lane(
    epic_issue: dict,
    child_issues: list[dict],
    *,
    delivery_squad_field: str,
    change_types_field: str,
    platform_field: str,
    story_points_field: str,
    skip_issue: Callable[[dict], bool] | None = None,
) -> str:
    """Assign epic to exclusive lane by quarter-scoped child weight (SP, else count of 1)."""
    totals: dict[str, float] = {lane: 0.0 for lane in LANE_DISPLAY_ORDER}
    for issue in child_issues:
        if skip_issue and skip_issue(issue):
            continue
        lane = classify_exclusive_lane(
            issue,
            delivery_squad_field=delivery_squad_field,
            change_types_field=change_types_field,
            platform_field=platform_field,
        )
        fields = issue.get("fields") or {}
        sp_raw = fields.get(story_points_field)
        weight = float(sp_raw) if sp_raw is not None and float(sp_raw) > 0 else 1.0
        totals[lane] += weight

    if sum(totals.values()) <= 0:
        return classify_exclusive_lane(
            epic_issue,
            delivery_squad_field=delivery_squad_field,
            change_types_field=change_types_field,
            platform_field=platform_field,
        )

    best = max(totals.values())
    for lane in LANE_TIEBREAK_ORDER:
        if totals[lane] == best:
            return lane
    return "unassigned"


def _field_values(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                out.append(str(item.get("value") or item.get("name") or ""))
            else:
                out.append(str(item))
        return [value for value in out if value]
    if isinstance(raw, dict):
        value = str(raw.get("value") or raw.get("name") or "")
        return [value] if value else []
    return [str(raw)]


def _issue_ec_squad_slug(issue: dict, delivery_squad_field: str) -> str | None:
    fields = issue.get("fields") or {}
    for name in _field_values(fields.get(delivery_squad_field)):
        slug = EC_SQUAD_NAME_TO_SLUG.get(name)
        if slug:
            return slug
    return None


def classify_epic_ec_squad(
    epic_issue: dict,
    child_issues: list[dict],
    *,
    delivery_squad_field: str,
    change_types_field: str,
    platform_field: str,
    story_points_field: str,
    skip_issue: Callable[[dict], bool] | None = None,
) -> str:
    """Education Cloud squad slug from quarter-scoped EC children (same squads as slice sub-rows)."""
    totals: dict[str, float] = {slug: 0.0 for slug, _, _ in EC_SQUAD_SPECS}
    for issue in child_issues:
        if skip_issue and skip_issue(issue):
            continue
        if classify_exclusive_lane(
            issue,
            delivery_squad_field=delivery_squad_field,
            change_types_field=change_types_field,
            platform_field=platform_field,
        ) != "educationCloud":
            continue
        slug = _issue_ec_squad_slug(issue, delivery_squad_field)
        if not slug:
            continue
        fields = issue.get("fields") or {}
        sp_raw = fields.get(story_points_field)
        weight = float(sp_raw) if sp_raw is not None and float(sp_raw) > 0 else 1.0
        totals[slug] += weight

    if sum(totals.values()) <= 0:
        return _issue_ec_squad_slug(epic_issue, delivery_squad_field) or "unassigned"

    best = max(totals.values())
    for slug, _, _ in EC_SQUAD_SPECS:
        if totals[slug] == best:
            return slug
    return "unassigned"


def group_ec_epics_by_squad(epics: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        slug: [] for slug, _, _ in EC_SQUAD_SPECS
    }
    grouped["unassigned"] = []
    for epic in epics:
        squad = str(epic.get("ecSquad") or "unassigned")
        if squad not in grouped:
            squad = "unassigned"
        grouped[squad].append(epic)
    for squad in grouped:
        grouped[squad].sort(
            key=lambda row: (str(row.get("endDate") or ""), str(row.get("key") or ""))
        )
    return grouped


def group_epics_by_lane(epics: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANE_DISPLAY_ORDER}
    for epic in epics:
        lane = str(epic.get("lane") or "unassigned")
        if lane not in grouped:
            lane = "unassigned"
        grouped[lane].append(epic)
    for lane in grouped:
        grouped[lane].sort(key=lambda row: (str(row.get("endDate") or ""), str(row.get("key") or "")))
    return grouped


def build_epic_timeline_rows(
    grouped: dict[str, list[dict[str, Any]]],
    *,
    lane_labels: dict[str, str],
) -> list[dict[str, Any]]:
    """Flat row list shared by layout height and SVG rendering (keeps labels aligned with bars)."""
    rows: list[dict[str, Any]] = []
    for lane_key in LANE_DISPLAY_ORDER:
        lane_epics = grouped.get(lane_key) or []
        if not lane_epics:
            continue
        rows.append(
            {
                "kind": "lane",
                "lane_key": lane_key,
                "label": lane_labels.get(lane_key, lane_key),
            }
        )
        if lane_key == "educationCloud":
            by_squad = group_ec_epics_by_squad(lane_epics)
            for slug, _squad_name, squad_label in EC_SQUAD_SPECS:
                squad_epics = by_squad.get(slug) or []
                if not squad_epics:
                    continue
                rows.append({"kind": "squad", "lane_key": lane_key, "label": squad_label})
                for epic in squad_epics:
                    rows.append(
                        {
                            "kind": "epic",
                            "lane_key": lane_key,
                            "squad_label": squad_label,
                            "epic": epic,
                        }
                    )
            orphans = by_squad.get("unassigned") or []
            if orphans:
                rows.append({"kind": "squad", "lane_key": lane_key, "label": "No squad"})
                for epic in orphans:
                    rows.append(
                        {
                            "kind": "epic",
                            "lane_key": lane_key,
                            "squad_label": "No squad",
                            "epic": epic,
                        }
                    )
        else:
            for epic in lane_epics:
                rows.append({"kind": "epic", "lane_key": lane_key, "epic": epic})
    return rows


def epic_timeline_plot_height(
    rows: list[dict[str, Any]],
    *,
    epic_row_height: float = EPIC_ROW_HEIGHT,
    swimlane_header: float = EPIC_SWIMLANE_HEADER,
    squad_header: float = EPIC_EC_SQUAD_HEADER,
) -> int:
    """Plot area height (excluding top release band and x-axis)."""
    height_by_kind = {
        "lane": swimlane_header,
        "squad": squad_header,
        "epic": epic_row_height,
    }
    return int(sum(height_by_kind[str(row["kind"])] for row in rows))


def resolve_epic_timeline_heights(
    rows: list[dict[str, Any]],
    *,
    plot_top: int = 56,
    bottom_margin: int,
    max_svg_height: int,
) -> dict[str, float]:
    """Scale row heights so the full SVG fits max_svg_height without vertical scroll."""
    natural_plot_h = epic_timeline_plot_height(rows)
    max_plot_h = max(max_svg_height - plot_top - bottom_margin, 1)
    scale = min(1.0, max_plot_h / natural_plot_h) if natural_plot_h else 1.0
    return {
        "scale": scale,
        "epic_row": EPIC_ROW_HEIGHT * scale,
        "swimlane": EPIC_SWIMLANE_HEADER * scale,
        "squad": EPIC_EC_SQUAD_HEADER * scale,
        "plot_h": natural_plot_h * scale,
    }


def epic_bar_fill(status: str | None) -> str:
    name = (status or "").strip().lower()
    if name in {"done", "closed", "resolved", "complete", "completed"}:
        return EPIC_STATUS_FILL["done"]
    if name in {"to do", "open", "backlog", "not started", "new"}:
        return EPIC_STATUS_FILL["open"]
    return EPIC_STATUS_FILL["active"]


def _child_is_credited(
    fields: dict,
    *,
    deploy_statuses: set[str],
    done_statuses: set[str],
) -> bool:
    status = str((fields.get("status") or {}).get("name") or "")
    return status in deploy_statuses or status in done_statuses


def summarize_epic_children(
    child_issues: list[dict],
    *,
    story_points_field: str,
    deploy_statuses: set[str],
    done_statuses: set[str],
    change_types_field: str = "",
    delivery_squad_field: str = "",
    skip_issue: Callable[[dict], bool] | None = None,
) -> dict[str, int | float]:
    """Story/Bug children only: count, SP total, deploy/done-earned SP, unpointed count."""
    child_count = 0
    story_points = 0.0
    earned = 0.0
    unpointed = 0
    for issue in child_issues:
        fields = issue.get("fields") or {}
        itype = str((fields.get("issuetype") or {}).get("name") or "")
        if itype not in EPIC_CHILD_ISSUE_TYPES:
            continue
        if skip_issue and skip_issue(issue):
            continue
        child_count += 1
        sp_raw = fields.get(story_points_field)
        if sp_raw is None:
            unpointed += 1
            continue
        sp = float(sp_raw)
        if sp <= 0:
            unpointed += 1
            continue
        story_points += sp
        if _child_is_credited(
            fields,
            deploy_statuses=deploy_statuses,
            done_statuses=done_statuses,
        ):
            earned += sp
    return {
        "childCount": child_count,
        "storyPoints": round(story_points, 2),
        "earnedStoryPoints": round(earned, 2),
        "unpointedCount": unpointed,
    }


def epic_sp_progress_ratio(epic: dict[str, Any]) -> float:
    total = float(epic.get("storyPoints") or 0)
    if total <= 0:
        return 0.0
    earned = float(epic.get("earnedStoryPoints") or 0)
    return min(1.0, max(0.0, earned / total))


def epic_timeline_tooltip(epic: dict[str, Any]) -> str:
    key = str(epic.get("key") or "")
    summary = str(epic.get("summary") or "")
    status = str(epic.get("status") or "")
    lines = [
        f"{key} | {summary}",
        f"Status: {status}",
        f"Children (Story/Bug): {int(epic.get('childCount') or 0)}",
        f"Story Points: {float(epic.get('storyPoints') or 0):g}",
        f"Earned SP: {float(epic.get('earnedStoryPoints') or 0):g}",
        f"Unpointed children: {int(epic.get('unpointedCount') or 0)}",
    ]
    scope = epic.get("scopeRollup") or {}
    if scope and float(scope.get("totalWeight") or 0) > 0:
        lines.append(
            f"Scope weight: {float(scope.get('totalWeight') or 0):g} "
            f"({float(scope.get('storyPoints') or 0):g} SP + "
            f"{int(scope.get('unpointedCount') or 0)} unpointed)"
        )
        from extensions.twoa_programme.milestone_scope_chart import lane_bar_segments

        for segment in lane_bar_segments(scope):
            pct = segment["fraction"] * 100
            lines.append(f"  {segment['key']}: {segment['weight']:g} ({pct:.0f}%)")
    fix_version = str(epic.get("fixVersion") or "")
    if fix_version:
        lines.append(f"Target release: {fix_version}")
    start_s = str(epic.get("startDate") or "")[:10]
    end_s = str(epic.get("endDate") or "")[:10]
    if start_s and end_s:
        lines.append(f"Timeline: {start_s} to {end_s}")
    return " | ".join(lines)



def _legend_tip_row_epic(content: str, tip: str) -> str:
    return (
        f'<abbr title="{html.escape(tip, quote=True)}" class="metric-tip">{content}</abbr>'
    )


def epic_timeline_key_html() -> str:
    from extensions.twoa_programme.milestone_scope_chart import (
        DTRAIN_PHASE_FILL,
        _UNPOINTED_SEGMENT,
        _UNKNOWN_PHASE,
        chart_dtrain_phases,
    )
    from extensions.twoa_programme.quarterly_dashboard_svg_core import (
        _milestone_legend_key_row,
        _today_legend_key_row,
    )

    phase_items = [
        (
            f'<span class="chart-key-phase-item">'
            f'<span class="legend-swatch" style="background:{DTRAIN_PHASE_FILL[phase]}"></span>'
            f"{html.escape(phase)}</span>"
        )
        for phase in chart_dtrain_phases()
    ]
    phase_items.extend(
        [
            (
                f'<span class="chart-key-phase-item">'
                f'<span class="legend-swatch" style="background:{DTRAIN_PHASE_FILL[_UNKNOWN_PHASE]}"></span>'
                f"Unknown</span>"
            ),
            (
                f'<span class="chart-key-phase-item">'
                f'<span class="legend-swatch" style="background:{DTRAIN_PHASE_FILL[_UNPOINTED_SEGMENT]}"></span>'
                f"Unpointed (1 each)</span>"
            ),
        ]
    )
    scope_key = (
        '<div class="chart-key chart-key-epic-scope">'
        '<p class="chart-key-title"><strong>Key — bar scope (D-Train)</strong></p>'
        f'<div class="chart-key-phase-strip">{"".join(phase_items)}</div>'
        '<p class="chart-key-note">Bar segments = Story/Bug scope by D-Train phase (Story Points) '
        "plus unpointed count. Click a segment to open scoped issues in Jira.</p>"
        "</div>"
    )
    rows = [
        _legend_tip_row_epic(
            (
                '<span class="legend-swatch sprint-a"></span>'
                '<span class="legend-swatch sprint-b"></span> Sprint bands (S# label)'
            ),
            "Alternating sprint shading from Release Plan; S# label when band is wide enough",
        ),
        _legend_tip_row_epic(
            '<span class="legend-swatch release-in"></span> In-cycle engine release',
            "Vertical dashed line on engine release date (in-cycle carriage); hover for release name",
        ),
        _legend_tip_row_epic(
            '<span class="legend-swatch release-out"></span> Out-of-cycle / other release',
            "Vertical dashed line on out-of-cycle or other engine release date; hover for release name",
        ),
    ]
    rows.append(_milestone_legend_key_row())
    rows.append(_today_legend_key_row())
    body = "".join(
        f'<div class="chart-key-row">{row if row.startswith("<") else html.escape(row)}</div>'
        for row in rows
    )
    calendar_key = (
        '<div class="chart-key">'
        '<p class="chart-key-title"><strong>Key — quarter calendar</strong></p>'
        f"{body}"
        "</div>"
    )
    return (
        '<div class="chart-key-wrap">'
        f"{scope_key}"
        f"{calendar_key}"
        "</div>"
    )


def _legend_tip_row_epic(content: str, tip: str) -> str:
    return (
        f'<abbr title="{html.escape(tip, quote=True)}" class="metric-tip">{content}</abbr>'
    )
