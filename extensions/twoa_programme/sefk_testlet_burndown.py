"""SEFK Testlet remaining-work burndown from Jira status history."""

from __future__ import annotations

import html
from datetime import date, datetime, timedelta
from math import ceil
from typing import Any
from urllib.parse import quote

from extensions.twoa_programme.quarterly_reporting import NZ_TZ

# Jira changelog dates are read in the reporting account's timezone (NZ), so "today" must be
# NZ too. CI runners use UTC, where date.today() lags NZ by up to 13 hours and drops
# same-day transitions.


def _day(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


_TERMINAL_STATUS_NAMES = frozenset({"passed", "rejected", "deferred"})


def _status_name_and_category(value: Any) -> tuple[str, str]:
    if isinstance(value, dict):
        name = str(value.get("name") or "").strip()
        category = str((value.get("statusCategory") or {}).get("key") or "").strip()
        return name, category
    return str(value or "").strip(), ""


def _is_rejected_status(value: Any) -> bool:
    name, _category = _status_name_and_category(value)
    return name.casefold() == "rejected"


def _is_terminal_status(value: Any) -> bool:
    """Passed, Rejected, Deferred, or any other Jira Done-category status except Failed."""
    name, category = _status_name_and_category(value)
    folded = name.casefold()
    if folded in _TERMINAL_STATUS_NAMES:
        return True
    return category.casefold() == "done" and folded != "failed"


def _is_execution_status(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"passed", "failed"}


FLAGGED_FIELD = "customfield_10021"


def _is_flagged(value: Any) -> bool:
    if isinstance(value, list):
        return any(_is_flagged(item) for item in value)
    if isinstance(value, dict):
        value = value.get("value") or value.get("name")
    return "impediment" in str(value or "").casefold()


def _flagged_events(
    histories: list[dict[str, Any]],
    *,
    current_flagged: bool,
) -> tuple[bool, list[tuple[date, bool]]]:
    """Return the initial Flagged=Impediment state and dated state changes."""
    changes: list[tuple[date, bool, bool]] = []
    for history in sorted(histories, key=lambda history: str(history.get("created") or "")):
        changed = _day(history.get("created"))
        for item in history.get("items") or []:
            field = str(item.get("field") or "").casefold()
            field_id = str(item.get("fieldId") or "")
            if field != "flagged" and field_id != FLAGGED_FIELD:
                continue
            from_flagged = _is_flagged(item.get("fromString") or item.get("from"))
            to_flagged = _is_flagged(item.get("toString") or item.get("to"))
            if changed is not None:
                changes.append((changed, from_flagged, to_flagged))
    initially_flagged = changes[0][1] if changes else current_flagged
    return initially_flagged, [(changed, to_flagged) for changed, _from, to_flagged in changes]


def _resolved_state_events(
    histories: list[dict[str, Any]],
    *,
    current_resolution: bool,
    current_status: str,
) -> tuple[bool, list[tuple[date, bool, bool, int, int, int, int, int, int, int]], bool]:
    ordered_histories = sorted(histories, key=lambda history: str(history.get("created") or ""))
    first_resolution_change = None
    first_status_change = None
    for history in ordered_histories:
        for item in history.get("items") or []:
            field = str(item.get("field") or item.get("fieldId") or "").casefold()
            if field == "resolution" and first_resolution_change is None:
                first_resolution_change = item
            elif field == "status" and first_status_change is None:
                first_status_change = item

    resolution_is_set = (
        bool(first_resolution_change.get("from") or first_resolution_change.get("fromString"))
        if first_resolution_change is not None
        else current_resolution
    )
    status_is_terminal = (
        _is_terminal_status(first_status_change.get("fromString") or first_status_change.get("from"))
        if first_status_change is not None
        else _is_terminal_status(current_status)
    )
    status_name = (
        str(first_status_change.get("fromString") or first_status_change.get("from") or "")
        if first_status_change is not None
        else current_status
    )
    has_status_state = first_status_change is not None or bool(current_status)
    initially_resolved = status_is_terminal if has_status_state else resolution_is_set
    events: list[tuple[date, bool, bool, int, int, int, int, int, int, int]] = []
    for history in ordered_histories:
        changed = _day(history.get("created"))
        if changed is None:
            continue
        was_resolved = status_is_terminal if has_status_state else resolution_is_set
        resolved_count = 0
        terminal_count = 0
        rejected_count = 0
        deferred_count = 0
        executed_count = 0
        passed_count = 0
        failed_count = 0
        for item in history.get("items") or []:
            field = str(item.get("field") or item.get("fieldId") or "").casefold()
            if field == "resolution":
                to_resolution = bool(item.get("to") or item.get("toString"))
                if not resolution_is_set and to_resolution:
                    resolved_count += 1
                resolution_is_set = to_resolution
            elif field == "status":
                to_status = str(item.get("toString") or item.get("to") or "")
                is_terminal_status = _is_terminal_status(to_status)
                if not status_is_terminal and is_terminal_status:
                    terminal_count += 1
                if _is_rejected_status(to_status) and not _is_rejected_status(status_name):
                    rejected_count += 1
                if to_status.strip().casefold() == "deferred" and status_name.strip().casefold() != "deferred":
                    deferred_count += 1
                if _is_execution_status(to_status) and to_status.casefold() != status_name.casefold():
                    executed_count += 1
                    if to_status.casefold() == "passed":
                        passed_count += 1
                    elif to_status.casefold() == "failed":
                        failed_count += 1
                status_is_terminal = is_terminal_status
                status_name = to_status
        is_resolved = status_is_terminal if has_status_state else resolution_is_set
        if was_resolved != is_resolved or resolved_count or terminal_count or rejected_count or deferred_count or executed_count:
            events.append((changed, was_resolved, is_resolved, resolved_count, terminal_count, rejected_count, deferred_count, executed_count, passed_count, failed_count))
    return initially_resolved, events, first_resolution_change is not None


def testlet_scope_jql(
    test_type: str,
    platform: str | None = None,
    *,
    include_all_engine_versions: bool = False,
) -> str:
    escaped_test_type = test_type.replace("\\", "\\\\").replace('"', '\\"')
    if test_type in {"Unit", "System Integration"}:
        clauses = [
            "filter = smart-project-sefk",
            "filter = smart-types-tests",
            f'"Test Types" = "{escaped_test_type}"',
        ]
        if test_type != "System Integration" or not include_all_engine_versions:
            clauses.insert(1, "filter = smart-sefk-current-engine")
        if test_type == "System Integration":
            clauses.append(
                'status in ("To Do", "Awaiting Test Development", '
                '"In Test Development", "In Testing", "Passed", "Failed", "Rejected", "Deferred")'
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


def resolved_testlets_for_day_jql(
    test_type: str,
    day: date,
    platform: str | None = None,
    *,
    include_all_engine_versions: bool = False,
) -> str:
    scope = testlet_scope_jql(
        test_type,
        platform,
        include_all_engine_versions=include_all_engine_versions,
    ).rsplit(" ORDER BY ", 1)[0]
    day_window = f'("{day.isoformat()} 00:00", "{day.isoformat()} 23:59")'
    return (
        f'{scope} AND (status CHANGED TO "Passed" DURING {day_window} '
        f'OR status CHANGED TO "Rejected" DURING {day_window} '
        f'OR status CHANGED TO "Deferred" DURING {day_window}) '
        "ORDER BY key ASC"
    )


def _y_axis_ticks(total_count: int) -> tuple[int, ...]:
    y_max = max(1, total_count)
    return tuple(sorted({0, y_max // 2, y_max}))


def _run_rate_metrics(payload: dict[str, Any]) -> tuple[float, float, float | None]:
    as_of = _day(payload.get("asOf"))
    start = _day(payload.get("idealStartDate"))
    due = _day(payload.get("idealEndDate"))
    if as_of is None or start is None:
        return 0.0, 0.0, None

    executed = sum(
        int(row.get("executed") or 0)
        for row in payload.get("daily") or []
        if (day := _day(row.get("date"))) is not None and start <= day <= as_of
    )
    elapsed_days = (as_of - start).days + 1
    run_rate = executed / elapsed_days if elapsed_days > 0 else 0.0
    passed = sum(
        int(row.get("passed") or 0)
        for row in payload.get("daily") or []
        if (day := _day(row.get("date"))) is not None and start <= day <= as_of
    )
    successful_rate = passed / elapsed_days if elapsed_days > 0 else 0.0

    remaining = max(0, int(payload.get("remainingTestlets") or 0))
    if remaining == 0:
        required_rate = 0.0
    elif due is None or as_of > due:
        required_rate = None
    else:
        days_remaining = max(1, (due - as_of).days)
        required_rate = remaining / days_remaining
    return run_rate, successful_rate, required_rate


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
        f"Terminal outcomes: {int(row.get('terminal') or 0)}\n"
        f"Passed: {int(row.get('passed') or 0)}\n"
        f"Rejected: {int(row.get('rejected') or 0)}\n"
        f"Deferred: {int(row.get('deferred') or 0)}\n"
        f"Execution attempts: {int(row.get('executed') or 0)}\n"
        f"Failed: {int(row.get('failed') or 0)}\n"
        f"Blocked: {int(row.get('blocked') or 0)}\n"
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
    """Replay Jira resolution and Rejected-status changes with the ideal-pace window."""
    end = _day(as_of) if as_of is not None else datetime.now(NZ_TZ).date()
    if end is None:
        raise ValueError("as_of must be a valid ISO date")
    ideal_start_day = _day(ideal_start)
    ideal_end_day = _day(ideal_end)
    if ideal_start_day is None or ideal_end_day is None or ideal_end_day <= ideal_start_day:
        raise ValueError("ideal_start and ideal_end must be valid dates with ideal_end after ideal_start")

    events: dict[date, int] = {}
    created_by_day: dict[date, int] = {}
    resolutiondate_by_day: dict[date, int] = {}
    completed_by_day: dict[date, int] = {}
    terminal_by_day: dict[date, int] = {}
    rejected_by_day: dict[date, int] = {}
    deferred_by_day: dict[date, int] = {}
    executed_by_day: dict[date, int] = {}
    passed_by_day: dict[date, int] = {}
    failed_by_day: dict[date, int] = {}
    blocked_delta_by_day: dict[date, int] = {}
    issue_count = 0
    earliest: date | None = None
    completed_now = 0
    rejected_now = 0
    deferred_now = 0
    passed_now = 0
    failed_now = 0
    blocked_now = 0
    for issue in issues:
        fields = issue.get("fields") or {}
        created = _day(fields.get("created"))
        if created is None or created > end:
            continue
        issue_count += 1
        created_by_day[created] = created_by_day.get(created, 0) + 1
        histories = changelogs_by_key.get(str(issue.get("key") or ""), [])
        current_resolution = bool(fields.get("resolution"))
        current_status_field = fields.get("status")
        current_status, _current_category = _status_name_and_category(current_status_field)
        status_key = current_status.casefold()
        currently_terminal = _is_terminal_status(current_status_field or current_status)
        if status_key == "passed":
            passed_now += 1
            completed_now += 1
        elif status_key == "rejected":
            rejected_now += 1
            completed_now += 1
        elif currently_terminal:
            deferred_now += 1
            completed_now += 1
        elif not current_status and current_resolution:
            completed_now += 1
        elif status_key == "failed":
            failed_now += 1
        current_flagged = _is_flagged(fields.get(FLAGGED_FIELD))
        if current_flagged:
            blocked_now += 1
        flagged, flagged_changes = _flagged_events(histories, current_flagged=current_flagged)
        if flagged:
            blocked_delta_by_day[created] = blocked_delta_by_day.get(created, 0) + 1
        for changed, to_flagged in flagged_changes:
            if changed > end or to_flagged == flagged:
                continue
            changed = max(changed, created)
            blocked_delta_by_day[changed] = blocked_delta_by_day.get(changed, 0) + (1 if to_flagged else -1)
            flagged = to_flagged
        resolution_day = _day(fields.get("resolutiondate"))
        if resolution_day is not None and resolution_day <= end:
            resolutiondate_by_day[resolution_day] = resolutiondate_by_day.get(resolution_day, 0) + 1
        initially_resolved, resolved_events, has_resolution_history = _resolved_state_events(
            histories,
            current_resolution=current_resolution,
            current_status=current_status_field or current_status,
        )
        if resolution_day is not None and resolution_day <= end:
            if current_resolution and not has_resolution_history:
                completed_by_day[resolution_day] = completed_by_day.get(resolution_day, 0) + 1

        if not initially_resolved:
            events[created] = events.get(created, 0) + 1
        earliest = min(earliest, created) if earliest else created

        remaining = not initially_resolved
        for changed, _from_resolved, to_resolved, resolved_count, terminal_count, rejected_count, deferred_count, executed_count, passed_count, failed_count in resolved_events:
            if changed < created or changed > end:
                continue
            if resolved_count:
                completed_by_day[changed] = completed_by_day.get(changed, 0) + resolved_count
            if terminal_count:
                terminal_by_day[changed] = terminal_by_day.get(changed, 0) + terminal_count
            if rejected_count:
                rejected_by_day[changed] = rejected_by_day.get(changed, 0) + rejected_count
            if deferred_count:
                deferred_by_day[changed] = deferred_by_day.get(changed, 0) + deferred_count
            if executed_count:
                executed_by_day[changed] = executed_by_day.get(changed, 0) + executed_count
            if passed_count:
                passed_by_day[changed] = passed_by_day.get(changed, 0) + passed_count
            if failed_count:
                failed_by_day[changed] = failed_by_day.get(changed, 0) + failed_count
            if remaining and to_resolved:
                events[changed] = events.get(changed, 0) - 1
                remaining = False
            elif not remaining and not to_resolved:
                events[changed] = events.get(changed, 0) + 1
                remaining = True
        if remaining and currently_terminal:
            events[end] = events.get(end, 0) - 1
            remaining = False
            terminal_by_day[end] = terminal_by_day.get(end, 0) + 1
            if status_key == "passed":
                passed_by_day[end] = passed_by_day.get(end, 0) + 1
            elif status_key == "rejected":
                rejected_by_day[end] = rejected_by_day.get(end, 0) + 1
            else:
                deferred_by_day[end] = deferred_by_day.get(end, 0) + 1

    if earliest is None:
        return {
            "asOf": end.isoformat(),
            "startDate": end.isoformat(),
            "totalTestlets": 0,
            "completedTestlets": 0,
            "rejectedTestlets": 0,
            "deferredTestlets": 0,
            "passedTestlets": 0,
            "failedTestlets": 0,
            "blockedTestlets": 0,
            "remainingTestlets": 0,
            "idealStartDate": ideal_start_day.isoformat(),
            "idealEndDate": ideal_end_day.isoformat(),
            "idealStartRemaining": 0,
            "forecastDate": None,
            "daily": [],
        }

    daily: list[dict[str, Any]] = []
    remaining_count = 0
    blocked_count = 0
    current_day = earliest
    while current_day <= end:
        remaining_count += events.get(current_day, 0)
        blocked_count += blocked_delta_by_day.get(current_day, 0)
        daily.append(
            {
                "date": current_day.isoformat(),
                "remaining": remaining_count,
                "created": created_by_day.get(current_day, 0),
                "resolutiondateMatches": resolutiondate_by_day.get(current_day, 0),
                "completed": completed_by_day.get(current_day, 0),
                "terminal": terminal_by_day.get(current_day, 0),
                "rejected": rejected_by_day.get(current_day, 0),
                "deferred": deferred_by_day.get(current_day, 0),
                "executed": executed_by_day.get(current_day, 0),
                "passed": passed_by_day.get(current_day, 0),
                "failed": failed_by_day.get(current_day, 0),
                "blocked": blocked_count,
            }
        )
        current_day = date.fromordinal(current_day.toordinal() + 1)

    elapsed_days = max(1, (end - ideal_start_day).days + 1)
    successful_completions = sum(
        row["passed"]
        for row in daily
        if ideal_start_day <= (_day(row["date"]) or end) <= end
    )
    successful_rate = successful_completions / elapsed_days
    forecast_day = (
        end + timedelta(days=ceil(remaining_count / successful_rate))
        if remaining_count and successful_rate > 0
        else end if remaining_count == 0 else None
    )
    return {
        "asOf": end.isoformat(),
        "startDate": earliest.isoformat(),
        "totalTestlets": issue_count,
        "completedTestlets": completed_now,
        "rejectedTestlets": rejected_now,
        "deferredTestlets": deferred_now,
        "passedTestlets": passed_now,
        "failedTestlets": failed_now,
        "blockedTestlets": blocked_now,
        "remainingTestlets": remaining_count,
        "idealStartDate": ideal_start_day.isoformat(),
        "idealEndDate": ideal_end_day.isoformat(),
        "idealStartRemaining": issue_count,
        "forecastDate": forecast_day.isoformat() if forecast_day else None,
        "daily": daily,
    }


# Days past the target/last data point the x-axis may extend to show the forecast.
_FORECAST_AXIS_MARGIN_DAYS = 14
# Upper bound on x-axis date labels before the tick spacing is widened.
_MAX_X_TICKS = 10


def _render_svg(
    payload: dict[str, Any],
    *,
    test_type: str = "Unit",
    platform: str | None = None,
    include_all_engine_versions: bool = False,
) -> str:
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
    forecast_day = _day(payload.get("forecastDate"))
    chart_start = ideal_start_day
    horizon = max(ideal_end_day, actual_end_day)
    # A forecast far beyond the target date (e.g. very low pass rate) must not stretch the
    # axis and squash the real data, so the axis is capped and the forecast runs off the edge.
    axis_cap = horizon + timedelta(days=_FORECAST_AXIS_MARGIN_DAYS)
    forecast_off_chart = forecast_day is not None and forecast_day > axis_cap
    if forecast_day is None:
        chart_end = horizon
    else:
        chart_end = min(max(horizon, forecast_day) + timedelta(days=5), axis_cap)
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
    forecast_points = ""
    forecast_start_day = _day(visible_daily[-1].get("date")) if visible_daily else None
    if forecast_day is not None and forecast_start_day is not None and forecast_day > forecast_start_day:
        forecast_start_value = int(visible_daily[-1]["remaining"])
        forecast_end_day, forecast_end_value = forecast_day, 0.0
        if forecast_off_chart:
            # Clip the straight forecast line where it leaves the capped axis.
            fraction = (chart_end - forecast_start_day).days / (forecast_day - forecast_start_day).days
            forecast_end_day = chart_end
            forecast_end_value = forecast_start_value * (1 - fraction)
        forecast_points = (
            f'{point(forecast_start_day, forecast_start_value)[0]:.1f},'
            f'{point(forecast_start_day, forecast_start_value)[1]:.1f} '
            f'{point(forecast_end_day, forecast_end_value)[0]:.1f},'
            f'{point(forecast_end_day, forecast_end_value)[1]:.1f}'
        )
    forecast_line = f'<polyline points="{forecast_points}" class="forecast-trend" />' if forecast_points else ""

    def _actual_point_markup(row: dict[str, Any], value: int) -> str:
        point_day = _day(row.get("date"))
        point_x, point_y = point(point_day or chart_start, value)
        tooltip = html.escape(
            _actual_point_label(row, value, total_count, test_type)
        )
        point_day = point_day or chart_start
        resolved_jql = quote(
            resolved_testlets_for_day_jql(
                test_type,
                point_day,
                platform,
                include_all_engine_versions=include_all_engine_versions,
            ),
            safe="",
        )
        href = html.escape(
            f"https://twoa.atlassian.net/issues/?jql={resolved_jql}",
            quote=True,
        )
        link_label = html.escape(f"Open terminal {test_type} Testlets for {point_day.isoformat()} in Jira")
        return (
            f'<a href="{href}" target="_blank" rel="noopener" tabindex="0" '
            f'class="actual-point-link" aria-label="{link_label}">'
            f'<circle cx="{point_x:.1f}" cy="{point_y:.1f}" r="4" '
            f'class="actual-point" aria-hidden="true">'
            f'<title>{tooltip}\nClick to view terminal Testlets in Jira</title></circle></a>'
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
    ticks = _y_axis_ticks(total_count)
    y_grid = "".join(
        f'<line x1="{left}" y1="{point(chart_start, tick)[1]:.1f}" x2="{width-right}" '
        f'y2="{point(chart_start, tick)[1]:.1f}" class="grid" />'
        f'<text x="{left-12}" y="{point(chart_start, tick)[1]+4:.1f}" text-anchor="end">{tick}</text>'
        for tick in ticks
    )
    x_ticks = [chart_start]
    # Weekly ticks, widened to a multiple of weeks so long spans keep readable labels.
    tick_step = timedelta(days=7 * max(1, ceil(chart_span / 7 / _MAX_X_TICKS)))
    next_tick = chart_start + tick_step
    while next_tick < chart_end - timedelta(days=3):
        x_ticks.append(next_tick)
        next_tick += tick_step
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
        if forecast_off_chart:
            forecast_x = point(chart_end, 0)[0]
            forecast_text = f"Forecast {forecast_label} (off chart)"
            forecast_anchor = "end"
        else:
            forecast_x = point(forecast_day, 0)[0]
            forecast_text = f"Forecast {forecast_label}"
            forecast_anchor = "middle"
        forecast_marker = (
            f'<line x1="{forecast_x:.1f}" y1="{top}" x2="{forecast_x:.1f}" '
            f'y2="{height-bottom}" class="forecast-marker" />'
            f'<text x="{forecast_x:.1f}" y="{top-7}" text-anchor="{forecast_anchor}" '
            f'class="forecast-label">{forecast_text}</text>'
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
        f'<polyline points="{actual_points}" class="actual" />'
        f'{forecast_line}'
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
    include_all_engine_versions: bool = False,
) -> str:
    generated = html.escape(generated_on or datetime.now().strftime("%d %b %Y"))
    as_of = html.escape(str(payload.get("asOf") or ""))
    ideal_start = html.escape(str(payload.get("idealStartDate") or ""))
    ideal_end = html.escape(str(payload.get("idealEndDate") or ""))
    safe_test_type = html.escape(test_type)
    platform_title = {
        "azure-integration-services": "Workday <> AIS <> TWoA",
        "workday": "Workday <> GPC <> Datapay",
    }.get(platform, test_type)
    report_title = f"{test_type} | {platform_title} | Testlet Burndown"
    safe_report_title = html.escape(report_title)
    safe_bounds_issue_key = html.escape(bounds_issue_key)
    run_rate, successful_rate, required_run_rate = _run_rate_metrics(payload)
    run_rate_text = f"{run_rate:.1f}"
    successful_rate_text = f"{successful_rate:.1f}"
    if required_run_rate is None:
        required_run_rate_text = "Past due"
    else:
        required_run_rate_text = f"{required_run_rate:.1f}"
    scope_jql = testlet_scope_jql(
        test_type,
        platform,
        include_all_engine_versions=include_all_engine_versions,
    )
    scope_description = f"SEFK Testlets where Test Types = {safe_test_type}"
    if platform:
        safe_platform = html.escape(platform)
        scope_description += f" and Platform = {safe_platform}"
    if test_type == "System Integration" and include_all_engine_versions:
        scope_description += " (all SEFK engine versions)"
    jql = quote(scope_jql, safe="")
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SEFK | {safe_report_title}</title>
  <style>
    :root {{ color-scheme: light; --ink: #172b4d; --muted: #5e6c84; --grid: #dfe1e6; --series-actual: #3bbf91; --series-ideal: #6041a8; --series-forecast: #f5ae0b; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: var(--ink); font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f5f7; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 28px 24px 48px; }}
    nav, .muted {{ color: var(--muted); font-size: 13px; }}
    nav a, a {{ color: var(--blue); text-decoration: none; }}
    nav a:hover, a:hover {{ text-decoration: underline; }}
    h1 {{ margin: 20px 0 4px; font-size: 26px; }}
    .subhead {{ margin: 0 0 24px; color: var(--muted); }}
    .metrics {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; }}
    .metric {{ --metric-accent: var(--series-ideal); min-width: 0; min-height: 104px; padding: 15px 16px; border: 1px solid var(--grid); border-top: 3px solid var(--metric-accent); border-radius: 4px; background: #fff; box-shadow: 0 1px 2px rgba(23, 43, 77, .06); }}
    .metric:nth-child(1) {{ --metric-accent: var(--series-forecast); }}
    .metric:nth-child(2), .metric:nth-child(3), .metric:nth-child(10) {{ --metric-accent: var(--series-actual); }}
    .metric:nth-child(4), .metric:nth-child(5) {{ --metric-accent: #718096; }}
    .metric:nth-child(6) {{ --metric-accent: #bd5148; }}
    .metric:nth-child(7) {{ --metric-accent: #d97008; }}
    .metric:nth-child(8) {{ --metric-accent: #53729a; }}
    .metric:nth-child(9) {{ --metric-accent: #37828a; }}
    .metric:nth-child(11) {{ --metric-accent: var(--series-ideal); }}
    .metric strong {{ display: block; font-size: 27px; line-height: 1.05; font-variant-numeric: tabular-nums; }}
    .metric span {{ display: block; margin-top: 7px; color: var(--muted); font-size: 13px; line-height: 1.35; overflow-wrap: anywhere; }}
    .weekend-band {{ fill: #e8ebef; }}
    .week-tick {{ stroke: var(--muted); stroke-width: 1; }}
    .actual {{ fill: none; stroke: var(--series-actual); stroke-width: 3; stroke-linejoin: round; stroke-linecap: round; }}
    .forecast-trend {{ fill: none; stroke: var(--series-forecast); stroke-width: 2.5; stroke-dasharray: 3 5; stroke-linejoin: round; }}
    .actual-point {{ fill: var(--series-actual); stroke: #fff; stroke-width: 1.5; cursor: help; }}
    .actual-point:hover, .actual-point:focus {{ stroke: var(--ink); stroke-width: 2; }}
    .actual-point-link {{ cursor: pointer; }}
    .ideal {{ fill: none; stroke: var(--series-ideal); stroke-width: 2; stroke-dasharray: 7 6; }}
    .forecast-marker {{ stroke: var(--series-forecast); stroke-width: 1.5; stroke-dasharray: 2 4; }}
    .forecast-label {{ fill: #9b6900; font-weight: 600; }}
    .target-marker {{ stroke: var(--series-ideal); stroke-width: 1.5; stroke-dasharray: 4 4; }}
    .target-label {{ fill: var(--series-ideal); font-weight: 600; }}
    .chart-layout {{ display: grid; grid-template-columns: minmax(0, 1fr) 176px; gap: 16px; align-items: center; }}
    .chart-layout svg {{ display: block; width: 100%; height: auto; min-width: 0; overflow: visible; }}
    .legend {{ margin: 0; padding: 8px 0; color: var(--muted); font-size: 13px; }}
    .legend-list {{ display: grid; gap: 12px; margin: 0; padding: 0; list-style: none; }}
    .legend-item {{ display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 8px; align-items: center; }}
    .swatch {{ display: block; width: 18px; border-top: 3px solid var(--series-actual); }}
    .swatch.actual {{ position: relative; }}
    .swatch.actual::after {{ position: absolute; top: -5px; left: 6px; width: 7px; height: 7px; border: 1px solid #fff; border-radius: 50%; background: var(--series-actual); content: ""; }}
    .swatch.ideal {{ border-top: 2px dashed var(--series-ideal); }}
    .swatch.forecast {{ width: 0; height: 16px; margin-left: 8px; border-top: 0; border-left: 2px dashed var(--series-forecast); }}
    .swatch.target {{ width: 0; height: 16px; margin-left: 8px; border-top: 0; border-left: 2px dashed var(--series-ideal); }}
    .foot {{ margin-top: 18px; color: var(--muted); font-size: 13px; }}
    .empty {{ padding: 30px; text-align: center; color: var(--muted); }}
    @media (max-width: 1000px) {{ .metrics {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
    @media (max-width: 700px) {{ main {{ padding: 20px 14px 32px; }} .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }} .metric {{ min-height: 92px; padding: 12px; }} .metric strong {{ font-size: 23px; }} figure {{ padding: 12px 8px 8px; }} .chart-layout {{ grid-template-columns: minmax(0, 1fr); gap: 8px; }} .legend-list {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }} }}
  </style>
</head>
<body>
  <main>
        <nav aria-label="Breadcrumb"><a href="../index.html">TWoA reporting hub</a> / <a href="index.html">SEFK</a> / {safe_report_title}</nav>
        <h1>{safe_report_title}</h1>
        <p class="subhead">Remaining {safe_test_type} Testlets over time, reconstructed from creation dates and Jira resolution and status history.</p>
        <section class="metrics" aria-label="Current {safe_test_type} Testlet counts">
            <div class="metric"><strong>{int(payload.get("remainingTestlets") or 0)}</strong><span>Remaining as of {as_of}</span></div>
            <div class="metric"><strong>{int(payload.get("completedTestlets") or 0)}</strong><span>Terminal outcomes</span></div>
            <div class="metric"><strong>{int(payload.get("passedTestlets") or 0)}</strong><span>Passed</span></div>
            <div class="metric"><strong>{int(payload.get("rejectedTestlets") or 0)}</strong><span>Rejected / removed</span></div>
            <div class="metric"><strong>{int(payload.get("deferredTestlets") or 0)}</strong><span>Deferred / removed</span></div>
            <div class="metric"><strong>{int(payload.get("failedTestlets") or 0)}</strong><span>Failed (within Remaining)</span></div>
            <div class="metric"><strong>{int(payload.get("blockedTestlets") or 0)}</strong><span>Blocked (flagged Impediment)</span></div>
            <div class="metric"><strong>{int(payload.get("totalTestlets") or 0)}</strong><span>{safe_test_type} Testlets in scope</span></div>
            <div class="metric"><strong>{run_rate_text}</strong><span>Execution attempts/day</span></div>
            <div class="metric"><strong>{successful_rate_text}</strong><span>Successful completions/day</span></div>
            <div class="metric"><strong>{required_run_rate_text}</strong><span>Required completion rate (tests/day)</span></div>
    </section>
    <figure>
            <div class="chart-layout">
                {_render_svg(
                    payload,
                    test_type=test_type,
                    platform=platform,
                    include_all_engine_versions=include_all_engine_versions,
                )}
                <figcaption class="legend" aria-label="Chart legend">
                    <ul class="legend-list">
                        <li class="legend-item"><i class="swatch actual"></i><span>Actual remaining</span></li>
                        <li class="legend-item"><i class="swatch ideal"></i><span>Ideal pace</span></li>
                        <li class="legend-item"><i class="swatch forecast"></i><span>Forecast</span></li>
                        <li class="legend-item"><i class="swatch target"></i><span>Target completion</span></li>
                    </ul>
                </figcaption>
            </div>
    </figure>
        <p class="foot">Scope: <a href="https://twoa.atlassian.net/issues/?jql={jql}" target="_blank" rel="noopener">{scope_description}</a>. Terminal outcomes are Passed, Rejected, or Deferred. Rejected and Deferred are out of active scope; Failed remains in Remaining. Blocked counts Testlets flagged as an Impediment. Execution attempts include Passed and Failed transitions; forecast completion and required pace use Passed transitions only. Ideal pace starts at the initial scope on {safe_bounds_issue_key}'s Start date and reaches zero on its Due date. Generated {generated}.</p>
  </main>
</body>
</html>
'''