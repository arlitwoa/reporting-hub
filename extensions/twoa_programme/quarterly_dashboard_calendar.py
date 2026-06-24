"""Release calendar, sprint bands, and chart legend for quarterly dashboard."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from extensions.twoa_programme.pde_engine_releases import (
    carriage_type_code,
    is_placeholder_engine_version,
    release_code_label,
)
from extensions.twoa_programme.quarterly_dashboard_constants import ATL, JIRA_SERVER, SPRINT_FILL, SPRINT_NUM_RE
from extensions.twoa_programme.quarterly_dashboard_links import (
    _browse_link,
    _fmt_num,
    _jql_link,
    _lane_label_link,
    _lane_scope_jql,
)
from extensions.twoa_programme.quarterly_dashboard_markup import (
    _chart_key_box,
    _chart_key_wrap,
    _goal_pace_tip,
    _legend_tip_row,
    _sanitize_atlassian_text,
    _section_l2_html,
)

def sprint_bands_from_release_plan(plan: dict) -> list[dict[str, Any]]:
    """Sprint shading bands from Release Plan row 3 (headers) + row 2 (dates)."""
    bands: list[dict[str, Any]] = []
    for index, sprint in enumerate(plan.get("sprints") or []):
        name = str(sprint.get("name") or "")
        match = SPRINT_NUM_RE.search(name)
        bands.append(
            {
                "label": name,
                "sprintNumber": sprint.get("sprintNumber") or (int(match.group(1)) if match else None),
                "start": date.fromisoformat(sprint["startDate"]),
                "end": date.fromisoformat(sprint["endDate"]),
                "fill": SPRINT_FILL[index % 2],
            }
        )
    return bands


def releases_from_release_plan(plan: dict) -> list[dict[str, Any]]:
    """All engine release markers for the chart (IC + OOC + projected)."""
    releases: list[dict[str, Any]] = []
    for row in plan.get("inCycleReleases") or []:
        name = str(row.get("name") or "")
        if name and is_placeholder_engine_version(name):
            continue
        if not name:
            name = f"prd-{row['releaseDate']}"
        releases.append(
            {
                "name": name,
                "releaseDate": row["releaseDate"],
                "carriageType": row.get("carriageType"),
                "projected": bool(row.get("projected")),
            }
        )
    return releases


def collect_sprint_bands(
    squad_data: dict | None,
    quarter_start: date,
    quarter_end: date,
) -> list[dict[str, Any]]:
    """Merge squad sprint windows by sprint number; clip to quarter; alternate fills."""
    if not squad_data:
        return []
    merged: dict[int, dict[str, Any]] = {}
    for squad in (squad_data.get("squads") or {}).values():
        for sprint in squad.get("sprints") or []:
            name = sprint.get("name") or ""
            match = SPRINT_NUM_RE.search(name)
            key = int(match.group(1)) if match else len(merged) + 1000
            start_s = sprint.get("sprintStartNz")
            end_s = sprint.get("sprintEndNz")
            if not start_s or not end_s:
                continue
            start = date.fromisoformat(start_s)
            end = date.fromisoformat(end_s)
            if end < quarter_start or start > quarter_end:
                continue
            clip_start = max(start, quarter_start)
            clip_end = min(end, quarter_end)
            bucket = merged.setdefault(
                key,
                {
                    "label": f"Sprint {key}",
                    "sprintNumber": key,
                    "start": clip_start,
                    "end": clip_end,
                },
            )
            bucket["start"] = min(bucket["start"], clip_start)
            bucket["end"] = max(bucket["end"], clip_end)
    bands = sorted(merged.values(), key=lambda row: row["start"])
    for index, band in enumerate(bands):
        band["fill"] = SPRINT_FILL[index % 2]
    return bands


def _parse_release_date(value: str) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def normalize_engine_releases(
    raw: list[dict],
    quarter_start: date,
    quarter_end: date,
) -> list[dict[str, str]]:
    """Engine fixVersions with releaseDate in the delivery quarter."""
    releases: list[dict[str, str]] = []
    for row in raw:
        name = str(row.get("name") or "")
        if is_placeholder_engine_version(name):
            continue
        if name.startswith("projected-"):
            name = str(row.get("releaseDate") or name)
        elif not name.endswith("-engine") and not row.get("releaseDate"):
            continue
        rd = _parse_release_date(str(row.get("releaseDate") or ""))
        if rd is None or rd < quarter_start or rd > quarter_end:
            continue
        releases.append({"name": name, "releaseDate": rd.isoformat()})
    releases.sort(key=lambda r: r["releaseDate"])
    return releases


def fetch_engine_releases(adapter: Any, quarter_start: date, quarter_end: date) -> list[dict[str, str]]:
    """Load EPCE engine fixVersion release dates from Jira (paginated /version endpoint)."""
    versions: list[dict] = []
    start_at = 0
    while True:
        page = adapter.http.get_json(
            "/rest/api/3/project/EPCE/version",
            params={"startAt": start_at, "maxResults": 50},
        )
        versions.extend(page.get("values") or [])
        if page.get("isLast", True) or not page.get("values"):
            break
        start_at += len(page.get("values") or [])
    return normalize_engine_releases(versions, quarter_start, quarter_end)


def short_release_label(name: str, rel: dict[str, Any] | None = None) -> str:
    if rel is not None:
        return release_code_label(
            str(rel.get("releaseDate") or ""),
            rel.get("carriageType"),
            projected=bool(rel.get("projected")),
        )
    stem = name.replace("-engine", "")
    if len(stem) == 8 and stem.isdigit():
        return release_code_label(f"20{stem[:2]}-{stem[2:4]}-{stem[4:6]}", None)
    if len(stem) >= 10 and stem[4] == "-":
        return release_code_label(stem[:10], None)
    return name


def _sprint_band_label(band: dict[str, Any]) -> str | None:
    """Compact sprint marker for chart bands (e.g. S22)."""
    num = band.get("sprintNumber")
    if num is not None:
        return f"S{num}"
    match = SPRINT_NUM_RE.search(str(band.get("label") or ""))
    return f"S{match.group(1)}" if match else None


def _week_start_dates(start: date, end: date) -> list[date]:
    """Mondays on or after start through end (ISO week start)."""
    cursor = start
    while cursor.weekday() != 0:
        cursor += timedelta(days=1)
    weeks: list[date] = []
    while cursor <= end:
        weeks.append(cursor)
        cursor += timedelta(days=7)
    return weeks


def _release_line_stroke(rel: dict[str, Any]) -> str:
    """Black for in-cycle releases; light orange for out-of-cycle and other."""
    code = carriage_type_code(rel.get("carriageType"), projected=bool(rel.get("projected")))
    if code in ("IC", "ID"):
        return ATL["release_in_cycle"]
    return ATL["release_out_cycle"]


def _layout_release_labels(
    releases: list[dict[str, Any]],
    *,
    x_for,
    x_min: date,
    x_max: date,
) -> list[tuple[float, str, dict[str, Any]]]:
    """Release codes above the plot, sorted left to right."""
    visible: list[tuple[float, str, dict[str, Any]]] = []
    for rel in releases:
        rd = date.fromisoformat(rel["releaseDate"])
        if rd < x_min or rd > x_max:
            continue
        visible.append(
            (x_for(rd), short_release_label(str(rel.get("name", "")), rel), rel)
        )
    visible.sort(key=lambda item: item[0])
    return visible


def _y_tick_step(y_max: float) -> float:
    """Pick a readable tick interval for cumulative SP (finer granularity)."""
    if y_max <= 20:
        return 2.0
    if y_max <= 60:
        return 5.0
    if y_max <= 150:
        return 10.0
    if y_max <= 400:
        return 25.0
    if y_max <= 800:
        return 50.0
    return 100.0


def _y_ticks(y_max: float) -> list[float]:
    step = _y_tick_step(y_max)
    ticks: list[float] = []
    value = 0.0
    while value <= y_max + step * 0.01:
        ticks.append(round(value, 1))
        value += step
    if not ticks or ticks[-1] < y_max:
        ticks.append(round(value, 1))
    return ticks


def _chart_legend_html() -> str:
    rows = [
        _legend_tip_row(
            (
                '<span class="legend-swatch sprint-a"></span>'
                '<span class="legend-swatch sprint-b"></span> Sprint bands (S# label)'
            ),
            "Alternating sprint shading from Release Plan; S# label when band is wide enough",
        ),
        _legend_tip_row(
            '<span class="legend-swatch release-in"></span> In-cycle engine release',
            "Vertical dashed line on engine release date (in-cycle carriage); hover for release name",
        ),
        _legend_tip_row(
            '<span class="legend-swatch release-out"></span> Out-of-cycle / other release',
            "Vertical dashed line on out-of-cycle or other engine release date; hover for release name",
        ),
        _legend_tip_row(
            f'<span class="legend-swatch earned"></span> Earned SP (cumulative)',
            "Cumulative deploy/done-earned story points credited in the delivery quarter",
        ),
        _legend_tip_row(
            f'<span class="legend-swatch goal"></span> Goal (linear to target date)',
            "Linear pace to initiative Goal SP by goal target date; flat after target if quarter continues",
        ),
    ]
    from extensions.twoa_programme.quarterly_dashboard_svg_core import (
        _milestone_legend_key_row,
        _today_legend_key_row,
    )

    rows.append(_milestone_legend_key_row())
    rows.append(_today_legend_key_row())
    return _chart_key_box("Key", rows)

