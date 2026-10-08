"""SEFK Testlet remaining-work burndown from Jira status history."""

from __future__ import annotations

import html
from datetime import date, datetime, timedelta
from math import ceil
from typing import Any
from urllib.parse import quote


def _day(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _resolution_events(
    histories: list[dict[str, Any]],
) -> list[tuple[date, bool, bool]]:
    events: list[tuple[date, bool, bool]] = []
    for history in histories:
        changed = _day(history.get("created"))
        if changed is None:
            continue
        for item in history.get("items") or []:
            if str(item.get("field") or "").lower() != "resolution":
                continue
            from_resolved = bool(item.get("from") or item.get("fromString"))
            to_resolved = bool(item.get("to") or item.get("toString"))
            events.append((changed, from_resolved, to_resolved))
    return sorted(events, key=lambda event: event[0])


def testlet_scope_jql(test_type: str, platform: str | None = None) -> str:
    escaped_test_type = test_type.replace("\\", "\\\\").replace('"', '\\"')
    if test_type in {"Unit", "System Integration"}:
        clauses = [
            "filter = smart-project-sefk",
            "filter = smart-sefk-current-engine",
            "filter = smart-types-tests",
            f'"Test Types" = "{escaped_test_type}"',
        ]
        if test_type == "System Integration":
            clauses.append(
                'status in ("To Do", "Awaiting Test Development", '
                '"In Test Development", "In Testing", "Passed", "Failed", "Rejected")'
            )
    else:
        clauses = [
            "project = SEFK",
            "issuetype = Testlet",
            f'cf[10145] = "{escaped_test_type}"',
        ]
    if platform:
        escaped_platform = platform.replace("\\", "\\\\").replace('"', '\\"')
        clauses.append(f'cf[10079] = "{escaped_platform}"')
    return " AND ".join(clauses) + " ORDER BY created ASC, key ASC"


def _best_fit_trend(
    daily: list[dict[str, Any]],
    *,
    from_date: date | None = None,
) -> tuple[date, float, float, date | None] | None:
    dated_points = [
        (parsed_day, float(row["remaining"]))
        for row in daily
        if (parsed_day := _day(row.get("date"))) is not None
        and (from_date is None or parsed_day >= from_date)
    ]
    if len(dated_points) < 2:
        return None
    start = dated_points[0][0]
    end = dated_points[-1][0]
    points = [((day - start).days, remaining) for day, remaining in dated_points]
    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    variance = sum((x - mean_x) ** 2 for x, _ in points)
    if variance == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / variance
    intercept = mean_y - slope * mean_x
    forecast_date = None
    if slope < 0:
        zero_day = -intercept / slope
        last_observed_day = (end - start).days
        if zero_day > last_observed_day:
            forecast_date = start + timedelta(days=ceil(zero_day))
    return start, slope, intercept, forecast_date


def _y_axis_ticks(total_count: int) -> tuple[int, ...]:
    y_max = max(1, total_count)
    return tuple(sorted({0, y_max // 2, y_max}))


def _actual_point_label(
    row: dict[str, Any],
    value: int,
    total_count: int,
    test_type: str,
) -> str:
    point_day = _day(row.get("date"))
    date_label = point_day.strftime("%d %b %Y").lstrip("0") if point_day else "Unknown date"
    noun = "Testlet" if value == 1 else "Testlets"
    return (
        f"{date_label}: {value} of {total_count} {test_type} {noun} remaining\n"
        f"Resolved: {int(row.get('resolutiondateMatches') or 0)}\n"
        f"Created: {int(row.get('created') or 0)}"
    )


def build_sefk_testlet_burndown_payload(
    issues: list[dict[str, Any]],
    changelogs_by_key: dict[str, list[dict[str, Any]]],
    *,
    ideal_start: date | str,
    ideal_end: date | str,
    as_of: date | str | None = None,
) -> dict[str, Any]:
    """Replay Jira resolution changes and attach the planned ideal-pace window."""
    end = _day(as_of) if as_of is not None else date.today()
    if end is None:
        raise ValueError("as_of must be a valid ISO date")
    ideal_start_day = _day(ideal_start)
    ideal_end_day = _day(ideal_end)
    if ideal_start_day is None or ideal_end_day is None or ideal_end_day <= ideal_start_day:
        raise ValueError("ideal_start and ideal_end must be valid dates with ideal_end after ideal_start")

    events: dict[date, int] = {}
    created_by_day: dict[date, int] = {}
    resolutiondate_by_day: dict[date, int] = {}
    issue_count = 0
    earliest: date | None = None
    completed_now = 0
    for issue in issues:
        fields = issue.get("fields") or {}
        created = _day(fields.get("created"))
        if created is None or created > end:
            continue
        issue_count += 1
        created_by_day[created] = created_by_day.get(created, 0) + 1
        histories = changelogs_by_key.get(str(issue.get("key") or ""), [])
        resolution_events = _resolution_events(histories)
        currently_resolved = bool(fields.get("resolution"))
        if currently_resolved:
            completed_now += 1
        resolution_day = _day(fields.get("resolutiondate"))
        if resolution_day is not None and resolution_day <= end:
            resolutiondate_by_day[resolution_day] = resolutiondate_by_day.get(resolution_day, 0) + 1

        initially_resolved = resolution_events[0][1] if resolution_events else currently_resolved
        if not initially_resolved:
            events[created] = events.get(created, 0) + 1
        earliest = min(earliest, created) if earliest else created

        remaining = not initially_resolved
        for changed, _from_resolved, to_resolved in resolution_events:
            if changed < created or changed > end:
                continue
            if remaining and to_resolved:
                events[changed] = events.get(changed, 0) - 1
                remaining = False
            elif not remaining and not to_resolved:
                events[changed] = events.get(changed, 0) + 1
                remaining = True

    if earliest is None:
        return {
            "asOf": end.isoformat(),
            "startDate": end.isoformat(),
            "totalTestlets": 0,
            "completedTestlets": 0,
            "remainingTestlets": 0,
            "idealStartDate": ideal_start_day.isoformat(),
            "idealEndDate": ideal_end_day.isoformat(),
            "idealStartRemaining": 0,
            "forecastDate": None,
            "daily": [],
        }

    daily: list[dict[str, Any]] = []
    remaining_count = 0
    current_day = earliest
    while current_day <= end:
        remaining_count += events.get(current_day, 0)
        daily.append(
            {
                "date": current_day.isoformat(),
                "remaining": remaining_count,
                "created": created_by_day.get(current_day, 0),
                "resolutiondateMatches": resolutiondate_by_day.get(current_day, 0),
            }
        )
        current_day = date.fromordinal(current_day.toordinal() + 1)

    trend = _best_fit_trend(daily, from_date=ideal_start_day)
    return {
        "asOf": end.isoformat(),
        "startDate": earliest.isoformat(),
        "totalTestlets": issue_count,
        "completedTestlets": completed_now,
        "remainingTestlets": remaining_count,
        "idealStartDate": ideal_start_day.isoformat(),
        "idealEndDate": ideal_end_day.isoformat(),
        "idealStartRemaining": issue_count,
        "forecastDate": trend[3].isoformat() if trend and trend[3] else None,
        "daily": daily,
    }


def _render_svg(payload: dict[str, Any], *, test_type: str = "Unit") -> str:
    daily = payload.get("daily") or []
    if not daily:
        return f'<p class="empty">No {html.escape(test_type)} Testlets found in SEFK.</p>'

    width, height = 1000, 380
    left, right, top, bottom = 64, 24, 42, 48
    plot_width, plot_height = width - left - right, height - top - bottom
    ideal_start_day = _day(payload.get("idealStartDate")) or _day(daily[0]["date"])
    ideal_end_day = _day(payload.get("idealEndDate")) or _day(daily[-1]["date"])
    assert ideal_start_day is not None and ideal_end_day is not None
    visible_daily = [
        row for row in daily
        if (_day(row.get("date")) or ideal_start_day) >= ideal_start_day
    ]
    values = [int(row["remaining"]) for row in visible_daily]
    actual_start_day = _day(visible_daily[0]["date"]) if visible_daily else ideal_start_day
    actual_end_day = _day(visible_daily[-1]["date"]) if visible_daily else ideal_start_day
    assert actual_start_day is not None and actual_end_day is not None
    trend = _best_fit_trend(visible_daily, from_date=ideal_start_day)
    forecast_day = trend[3] if trend else None
    chart_start = ideal_start_day
    chart_end = max(ideal_end_day, actual_end_day, forecast_day or actual_end_day)
    if forecast_day is not None:
        chart_end += timedelta(days=5)
    chart_span = max(1, (chart_end - chart_start).days)
    ideal_start_remaining = int(payload.get("idealStartRemaining", values[0]))
    total_count = int(payload.get("totalTestlets") or max(values, default=0))
    y_max = max(1, total_count)

    def point(day: date, value: float) -> tuple[float, float]:
        x = left + plot_width * (day - chart_start).days / chart_span
        y = top + plot_height * (1 - value / y_max)
        return x, y

    weekend_rects: list[str] = []
    weekend_day = chart_start
    while weekend_day < chart_end:
        if weekend_day.weekday() >= 5:
            weekend_end = min(weekend_day + timedelta(days=1), chart_end)
            weekend_x = point(weekend_day, 0)[0]
            weekend_width = point(weekend_end, 0)[0] - weekend_x
            weekend_rects.append(
                f'<rect x="{weekend_x:.1f}" y="{top}" width="{weekend_width:.1f}" '
                f'height="{plot_height}" class="weekend-band" />'
            )
        weekend_day += timedelta(days=1)
    weekend_bands = "".join(weekend_rects)

    actual_points = " ".join(
        f"{point(_day(row['date']) or chart_start, value)[0]:.1f},"
        f"{point(_day(row['date']) or chart_start, value)[1]:.1f}"
        for row, value in zip(visible_daily, values)
    )

    def _actual_point_markup(row: dict[str, Any], value: int) -> str:
        point_day = _day(row.get("date"))
        point_x, point_y = point(point_day or chart_start, value)
        tooltip = html.escape(
            _actual_point_label(row, value, total_count, test_type)
        )
        return (
            f'<circle cx="{point_x:.1f}" cy="{point_y:.1f}" r="4" '
            f'class="actual-point" tabindex="0" aria-label="{tooltip}">'
            f'<title>{tooltip}</title></circle>'
        )

    actual_markers = "".join(
        _actual_point_markup(row, value)
        for row, value in zip(visible_daily, values)
    )
    ideal_points = (
        f"{point(ideal_start_day, ideal_start_remaining)[0]:.1f},"
        f"{point(ideal_start_day, ideal_start_remaining)[1]:.1f} "
        f"{point(ideal_end_day, 0)[0]:.1f},{point(ideal_end_day, 0)[1]:.1f}"
    )
    trend_points = ""
    if trend is not None:
        trend_start, slope, intercept, _ = trend
        fitted_end = intercept + slope * (actual_end_day - trend_start).days
        trend_end_day = forecast_day or actual_end_day
        trend_end_value = 0 if forecast_day else fitted_end
        fitted_start = min(float(y_max), max(0.0, intercept))
        fitted_end = min(float(y_max), max(0.0, fitted_end))
        trend_points = (
            f'{point(trend_start, fitted_start)[0]:.1f},'
            f'{point(trend_start, fitted_start)[1]:.1f} '
            f'{point(actual_end_day, fitted_end)[0]:.1f},'
            f'{point(actual_end_day, fitted_end)[1]:.1f}'
        )
        if forecast_day is not None:
            trend_points += (
                f' {point(trend_end_day, trend_end_value)[0]:.1f},'
                f'{point(trend_end_day, trend_end_value)[1]:.1f}'
            )
    ticks = _y_axis_ticks(total_count)
    y_grid = "".join(
        f'<line x1="{left}" y1="{point(chart_start, tick)[1]:.1f}" x2="{width-right}" '
        f'y2="{point(chart_start, tick)[1]:.1f}" class="grid" />'
        f'<text x="{left-12}" y="{point(chart_start, tick)[1]+4:.1f}" text-anchor="end">{tick}</text>'
        for tick in ticks
    )
    x_ticks = [chart_start]
    next_tick = chart_start + timedelta(days=7)
    while next_tick < chart_end - timedelta(days=3):
        x_ticks.append(next_tick)
        next_tick += timedelta(days=7)
    if chart_end != chart_start:
        x_ticks.append(chart_end)
    x_axis = "".join(
        f'<line x1="{point(day, 0)[0]:.1f}" y1="{top}" '
        f'x2="{point(day, 0)[0]:.1f}" y2="{height-bottom}" class="week-grid" />'
        f'<line x1="{point(day, 0)[0]:.1f}" y1="{height-bottom}" '
        f'x2="{point(day, 0)[0]:.1f}" y2="{height-bottom+6}" class="week-tick" />'
        f'<text x="{point(day, 0)[0]:.1f}" y="{height-12}" '
        f'text-anchor="{"start" if day == chart_start else "end" if day == chart_end else "middle"}">'
        f'{day.day} {day.strftime("%b")}</text>'
        for day in x_ticks
    )
    start_label = html.escape(chart_start.isoformat())
    end_label = html.escape(chart_end.isoformat())
    ideal_start_label = html.escape(ideal_start_day.isoformat())
    ideal_end_label = html.escape(ideal_end_day.isoformat())
    forecast_label = html.escape(forecast_day.isoformat()) if forecast_day else ""
    forecast_marker = ""
    if forecast_day is not None:
        forecast_x = point(forecast_day, 0)[0]
        forecast_marker = (
            f'<line x1="{forecast_x:.1f}" y1="{top}" x2="{forecast_x:.1f}" '
            f'y2="{height-bottom}" class="forecast-marker" />'
            f'<text x="{forecast_x:.1f}" y="{top-7}" text-anchor="middle" '
            f'class="forecast-label">Forecast {forecast_label}</text>'
        )
    target_x = point(ideal_end_day, 0)[0]
    target_label = html.escape(f"Target {ideal_end_day.day} {ideal_end_day.strftime('%b')}")
    target_marker = (
        f'<line x1="{target_x:.1f}" y1="{top}" x2="{target_x:.1f}" '
        f'y2="{height-bottom}" class="target-marker" />'
        f'<text x="{target_x:.1f}" y="{top-20}" text-anchor="middle" '
        f'class="target-label">{target_label}</text>'
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(test_type)} Testlets remaining from {start_label} to {end_label}; '
        f'target completion {ideal_end_label}; ideal pace from {ideal_start_label} to {ideal_end_label}">'
        f'<g class="weekends">{weekend_bands}</g>'
        f'<g class="axis-labels">{y_grid}{x_axis}</g>'
        f'<polyline points="{ideal_points}" class="ideal" />'
        f'<polyline points="{trend_points}" class="trend" />'
        f'<polyline points="{actual_points}" class="actual" />'
        f'{actual_markers}'
        f'{forecast_marker}'
        f'{target_marker}'
        f'<text x="18" y="{top+plot_height/2}" transform="rotate(-90 18 {top+plot_height/2})" '
        f'text-anchor="middle">{html.escape(test_type)} Testlets remaining</text></svg>'
    )


def build_sefk_testlet_burndown_html(
    payload: dict[str, Any],
    *,
    generated_on: str | None = None,
    test_type: str = "Unit",
    bounds_issue_key: str = "SEFK-1274",
    platform: str | None = None,
) -> str:
    generated = html.escape(generated_on or datetime.now().strftime("%d %b %Y"))
    as_of = html.escape(str(payload.get("asOf") or ""))
    ideal_start = html.escape(str(payload.get("idealStartDate") or ""))
    ideal_end = html.escape(str(payload.get("idealEndDate") or ""))
    forecast_date = html.escape(str(payload.get("forecastDate") or "No forecast"))
    safe_test_type = html.escape(test_type)
    safe_bounds_issue_key = html.escape(bounds_issue_key)
    scope_jql = testlet_scope_jql(test_type, platform)
    scope_description = f"SEFK Testlets where Test Types = {safe_test_type}"
    if platform:
        safe_platform = html.escape(platform)
        scope_description += f" and Platform = {safe_platform}"
    jql = quote(scope_jql, safe="")
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SEFK | {safe_test_type} Testlet burndown</title>
  <style>
    :root {{ color-scheme: light; --ink: #172b4d; --muted: #5e6c84; --grid: #dfe1e6; --blue: #0052cc; --green: #00875a; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: var(--ink); font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f5f7; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 28px 24px 48px; }}
    nav, .muted {{ color: var(--muted); font-size: 13px; }}
    nav a, a {{ color: var(--blue); text-decoration: none; }}
    nav a:hover, a:hover {{ text-decoration: underline; }}
    h1 {{ margin: 20px 0 4px; font-size: 26px; }}
    .subhead {{ margin: 0 0 24px; color: var(--muted); }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-block: 1px solid var(--grid); background: white; }}
    .metric {{ padding: 18px 20px; border-right: 1px solid var(--grid); }}
    .metric:last-child {{ border: 0; }}
    .metric strong {{ display: block; font-size: 28px; line-height: 1.15; font-variant-numeric: tabular-nums; }}
    .weekend-band {{ fill: #e8ebef; }}
    .week-tick {{ stroke: var(--muted); stroke-width: 1; }}
    .actual {{ fill: none; stroke: var(--blue); stroke-width: 3; stroke-linejoin: round; stroke-linecap: round; }}
    .actual-point {{ fill: var(--blue); stroke: #fff; stroke-width: 1.5; cursor: help; }}
    .actual-point:hover, .actual-point:focus {{ stroke: var(--ink); stroke-width: 2; }}
    .ideal {{ fill: none; stroke: var(--green); stroke-width: 2; stroke-dasharray: 7 6; }}
    .trend {{ fill: none; stroke: #de350b; stroke-width: 2.5; stroke-dasharray: 3 5; stroke-linejoin: round; }}
    .forecast-marker {{ stroke: #de350b; stroke-width: 1.5; stroke-dasharray: 2 4; }}
    .forecast-label {{ fill: #de350b; font-weight: 600; }}
    .target-marker {{ stroke: var(--green); stroke-width: 1.5; stroke-dasharray: 4 4; }}
    .target-label {{ fill: var(--green); font-weight: 600; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 22px; padding-top: 12px; color: var(--muted); font-size: 13px; }}
    .swatch {{ display: inline-block; width: 18px; margin-right: 6px; border-top: 3px solid var(--blue); vertical-align: middle; }}
    .swatch.ideal {{ border-color: var(--green); border-top-style: dashed; }}
    .swatch.trend {{ border-color: #de350b; border-top-style: dashed; }}
    .foot {{ margin-top: 18px; color: var(--muted); font-size: 13px; }}
    .empty {{ padding: 30px; text-align: center; color: var(--muted); }}
    @media (max-width: 600px) {{ main {{ padding: 20px 14px 32px; }} .metrics {{ grid-template-columns: 1fr; }} .metric {{ padding: 12px 16px; border-right: 0; border-bottom: 1px solid var(--grid); }} .metric strong {{ font-size: 23px; }} figure {{ padding: 12px 8px 8px; }} }}
  </style>
</head>
<body>
  <main>
        <nav aria-label="Breadcrumb"><a href="../index.html">TWoA reporting hub</a> / <a href="index.html">SEFK</a> / {safe_test_type} Testlet burndown</nav>
        <h1>SEFK {safe_test_type} Testlet burndown</h1>
        <p class="subhead">Remaining {safe_test_type} Testlets over time, reconstructed from creation dates and Jira resolution history.</p>
        <section class="metrics" aria-label="Current {safe_test_type} Testlet counts">
            <div class="metric"><strong>{int(payload.get("remainingTestlets") or 0)}</strong><span>Remaining as of {as_of}</span></div>
            <div class="metric"><strong>{int(payload.get("completedTestlets") or 0)}</strong><span>Currently resolved in Jira</span></div>
            <div class="metric"><strong>{int(payload.get("totalTestlets") or 0)}</strong><span>{safe_test_type} Testlets in scope</span></div>
            <div class="metric"><strong>{forecast_date}</strong><span>Best-fit completion estimate</span></div>
    </section>
    <figure>
    {_render_svg(payload, test_type=test_type)}
            <figcaption class="legend"><span><i class="swatch"></i>Actual remaining</span><span><i class="swatch ideal"></i>Ideal pace ({ideal_start} to {ideal_end})</span><span><i class="swatch trend"></i>Best-fit trend</span><span>Target completion: {ideal_end}</span></figcaption>
    </figure>
        <p class="foot">Scope: <a href="https://twoa.atlassian.net/issues/?jql={jql}" target="_blank" rel="noopener">{scope_description}</a>. Created {safe_test_type} Testlets add to remaining work; setting a Jira resolution burns one down, and clearing it on reopen adds one back. Ideal pace starts at the initial scope on {safe_bounds_issue_key}'s Start date and reaches zero on its Due date. Generated {generated}.</p>
  </main>
</body>
</html>
'''