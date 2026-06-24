"""Milestone scope story-point timeline from Jira Story Points changelog replay."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from artifact.jira_binding import JiraBinding

from extensions.twoa_programme.milestone_scope_chart import (
    _UNKNOWN_PHASE,
    chart_dtrain_phases,
    resolve_issue_dtrain_phase,
)
from extensions.twoa_programme.quarter_scope import EXCLUDED_ANALYSIS_STATUSES
from extensions.twoa_programme.quarterly_reporting import (
    aggregate_daily_burn,
    credit_date_nz,
    extend_daily_burn_to_as_of,
)

_STORY_POINTS_FIELDS = frozenset({"Story Points", "Story points"})
_REJECTED_STATUSES = EXCLUDED_ANALYSIS_STATUSES


def phase_stack_order() -> tuple[str, ...]:
    return (*chart_dtrain_phases(), _UNKNOWN_PHASE)


def parse_jira_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value)
    if raw.endswith("+0000"):
        raw = raw[:-5] + "+00:00"
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def story_points_from_fields(fields: dict[str, Any], *, sp_field: str = "customfield_10026") -> float:
    raw = fields.get(sp_field)
    if raw is None:
        return 0.0
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.0


def _parse_sp_value(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return 0.0
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _sp_change_events(histories: list[dict[str, Any]]) -> list[tuple[datetime, float]]:
    events: list[tuple[datetime, float]] = []
    for history in sorted(histories, key=lambda row: row.get("created", "")):
        created = parse_jira_dt(history.get("created"))
        if created is None:
            continue
        for item in history.get("items") or []:
            if (item.get("field") or "") not in _STORY_POINTS_FIELDS:
                continue
            sp = _parse_sp_value(item.get("toString"))
            if sp is None:
                continue
            events.append((created, sp))
    return events


def _first_status_transition(histories: list[dict[str, Any]], target_statuses: set[str]) -> datetime | None:
    earliest: datetime | None = None
    for history in sorted(histories, key=lambda row: row.get("created", "")):
        created = parse_jira_dt(history.get("created"))
        if created is None:
            continue
        for item in history.get("items") or []:
            if (item.get("field") or "") != "status":
                continue
            if (item.get("toString") or "") in target_statuses:
                if earliest is None or created < earliest:
                    earliest = created
    return earliest


def _collect_issue_changes(
    histories: list[dict[str, Any]],
) -> list[tuple[datetime, str, float | str]]:
    changes: list[tuple[datetime, str, float | str]] = []
    for history in sorted(histories, key=lambda row: row.get("created", "")):
        created = parse_jira_dt(history.get("created"))
        if created is None:
            continue
        for item in history.get("items") or []:
            field = item.get("field") or ""
            if field in _STORY_POINTS_FIELDS:
                sp = _parse_sp_value(item.get("toString"))
                if sp is not None:
                    changes.append((created, "sp", sp))
            elif field == "status":
                changes.append((created, "status", item.get("toString") or ""))
    changes.sort(key=lambda row: row[0])
    return changes


def _status_at(
    histories: list[dict[str, Any]],
    *,
    before_day: date,
    fallback_status: str,
) -> str:
    status = fallback_status
    for history in sorted(histories, key=lambda row: row.get("created", "")):
        created = parse_jira_dt(history.get("created"))
        if created is None or credit_date_nz(created) >= before_day:
            break
        for item in history.get("items") or []:
            if (item.get("field") or "") == "status":
                status = item.get("toString") or status
    return status


def _sp_at_day_start(
    histories: list[dict[str, Any]],
    *,
    before_day: date,
    fallback_fields: dict[str, Any],
    sp_field: str,
) -> float:
    sp = 0.0
    saw_sp = False
    for history in sorted(histories, key=lambda row: row.get("created", "")):
        created = parse_jira_dt(history.get("created"))
        if created is None or credit_date_nz(created) >= before_day:
            break
        for item in history.get("items") or []:
            if (item.get("field") or "") not in _STORY_POINTS_FIELDS:
                continue
            parsed = _parse_sp_value(item.get("toString"))
            if parsed is not None:
                sp = parsed
                saw_sp = True
    if not saw_sp:
        sp = story_points_from_fields(fallback_fields, sp_field=sp_field)
    return sp


def issue_scope_phase_delta_events(
    issue: dict[str, Any],
    histories: list[dict[str, Any]],
    *,
    binding: JiraBinding,
    quarter_start: date,
    quarter_end: date,
    sp_field: str = "customfield_10026",
) -> list[dict[str, Any]]:
    """Return scope delta events split by D-Train phase (status at change time)."""
    fields = issue.get("fields") or {}
    fallback_status = str((fields.get("status") or {}).get("name") or "")
    created_dt = parse_jira_dt(fields.get("created"))
    rejected_dt = _first_status_transition(histories, _REJECTED_STATUSES)

    window_start = quarter_start
    if created_dt is not None:
        window_start = max(window_start, credit_date_nz(created_dt))
    window_end = quarter_end
    if rejected_dt is not None:
        window_end = min(window_end, credit_date_nz(rejected_dt))
    if window_start > window_end:
        return []

    changes = _collect_issue_changes(histories)
    sp = _sp_at_day_start(
        histories,
        before_day=window_start,
        fallback_fields=fields,
        sp_field=sp_field,
    )
    status = _status_at(histories, before_day=window_start, fallback_status=fallback_status)
    current_phase = resolve_issue_dtrain_phase(status, binding)

    by_day_phase: dict[tuple[str, str], float] = defaultdict(float)
    if sp > 0:
        by_day_phase[(window_start.isoformat(), current_phase)] += sp

    for change_dt, kind, value in changes:
        change_day = credit_date_nz(change_dt)
        if change_day < window_start or change_day > window_end:
            continue
        day_key = change_day.isoformat()
        if kind == "sp":
            new_sp = float(value)
            delta = new_sp - sp
            if delta != 0:
                by_day_phase[(day_key, current_phase)] += delta
            sp = new_sp
        else:
            new_phase = resolve_issue_dtrain_phase(str(value), binding)
            if new_phase != current_phase and sp > 0:
                by_day_phase[(day_key, current_phase)] -= sp
                by_day_phase[(day_key, new_phase)] += sp
            current_phase = new_phase

    if rejected_dt is not None:
        reject_day = credit_date_nz(rejected_dt)
        if window_start <= reject_day <= window_end and sp > 0:
            by_day_phase[(reject_day.isoformat(), current_phase)] -= sp

    return [
        {"date": day, "phase": phase, "delta": delta}
        for (day, phase), delta in sorted(by_day_phase.items())
        if delta != 0
    ]


def _aligned_phase_cumulative(
    phases: dict[str, Any],
    global_daily: list[dict[str, Any]],
    *,
    phase_order: tuple[str, ...],
) -> tuple[list[date], dict[str, list[float]]]:
    if not global_daily:
        return [], {}
    dates = [date.fromisoformat(str(row["date"])[:10]) for row in global_daily]
    series: dict[str, list[float]] = {}
    for phase_key in phase_order:
        phase_row = phases.get(phase_key) or {}
        by_date = {
            date.fromisoformat(str(row["date"])[:10]): float(row["cumulative_story_points"])
            for row in phase_row.get("daily") or []
        }
        values: list[float] = []
        last = 0.0
        for day in dates:
            if day in by_date:
                last = by_date[day]
            values.append(last)
        series[phase_key] = values
    return dates, series


def build_milestone_scope_phase_daily(
    issues: list[dict[str, Any]],
    changelogs_by_key: dict[str, list[dict[str, Any]]],
    *,
    binding: JiraBinding,
    quarter_start: date | str,
    quarter_end: date | str,
    sp_field: str = "customfield_10026",
    as_of: date | str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], float]:
    """Build per-phase scope daily series and combined scope total."""
    start = date.fromisoformat(str(quarter_start)[:10])
    end = date.fromisoformat(str(quarter_end)[:10])
    phase_order = phase_stack_order()
    phase_events: dict[str, list[dict[str, Any]]] = {phase: [] for phase in phase_order}
    combined_events: list[dict[str, Any]] = []

    for issue in issues:
        key = str(issue.get("key") or "")
        if not key:
            continue
        histories = changelogs_by_key.get(key) or []
        for event in issue_scope_phase_delta_events(
            issue,
            histories,
            binding=binding,
            quarter_start=start,
            quarter_end=end,
            sp_field=sp_field,
        ):
            phase = str(event.get("phase") or _UNKNOWN_PHASE)
            if phase not in phase_events:
                phase = _UNKNOWN_PHASE
            row = {"credit_date": event["date"], "story_points": event["delta"]}
            phase_events[phase].append(row)
            combined_events.append(row)

    phases_payload: dict[str, Any] = {}
    for phase_key in phase_order:
        daily, total = aggregate_daily_burn(phase_events[phase_key])
        phases_payload[phase_key] = {
            "totalStoryPoints": total,
            "daily": daily,
        }

    scope_daily, scope_total = aggregate_daily_burn(combined_events)
    if as_of is not None:
        scope_daily = extend_daily_burn_to_as_of(scope_daily, as_of, quarter_end=end)
        for phase_key in phase_order:
            phases_payload[phase_key]["daily"] = extend_daily_burn_to_as_of(
                phases_payload[phase_key]["daily"] or [],
                as_of,
                quarter_end=end,
            )
    return phases_payload, scope_daily, scope_total


def proportional_scope_phases_daily(
    scope_daily: list[dict[str, Any]],
    phase_amounts: dict[str, float],
    *,
    phase_order: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Split total scope daily into phase bands using current composition shares."""
    order = phase_order or phase_stack_order()
    positive = {phase: float(phase_amounts.get(phase) or 0) for phase in order}
    total = sum(positive.values())
    if total <= 0 or not scope_daily:
        return {}
    shares = {phase: amount / total for phase, amount in positive.items() if amount > 0}
    phases_payload: dict[str, Any] = {}
    for phase, share in shares.items():
        daily = [
            {
                "date": row["date"],
                "cumulative_story_points": round(float(row["cumulative_story_points"]) * share, 4),
            }
            for row in scope_daily
        ]
        phases_payload[phase] = {
            "totalStoryPoints": round(total * share, 2),
            "daily": daily,
        }
    return phases_payload


def issue_scope_delta_events(
    issue: dict[str, Any],
    histories: list[dict[str, Any]],
    *,
    quarter_start: date,
    quarter_end: date,
    sp_field: str = "customfield_10026",
) -> list[dict[str, Any]]:
    """Return scope delta events (date + delta story points) for one in-scope issue."""
    fields = issue.get("fields") or {}
    created_dt = parse_jira_dt(fields.get("created"))
    rejected_dt = _first_status_transition(histories, _REJECTED_STATUSES)

    window_start = quarter_start
    if created_dt is not None:
        window_start = max(window_start, credit_date_nz(created_dt))
    window_end = quarter_end
    if rejected_dt is not None:
        window_end = min(window_end, credit_date_nz(rejected_dt))
    if window_start > window_end:
        return []

    sp_changes = _sp_change_events(histories)
    sp_at_start = 0.0
    for change_dt, sp in sp_changes:
        if credit_date_nz(change_dt) < window_start:
            sp_at_start = sp
    if not sp_changes:
        sp_at_start = story_points_from_fields(fields, sp_field=sp_field)

    by_day: dict[str, float] = {}
    if sp_at_start > 0:
        by_day[window_start.isoformat()] = by_day.get(window_start.isoformat(), 0.0) + sp_at_start

    last_sp = sp_at_start
    for change_dt, sp in sp_changes:
        change_day = credit_date_nz(change_dt)
        if change_day < window_start:
            continue
        if change_day > window_end:
            break
        delta = sp - last_sp
        if delta != 0:
            day_key = change_day.isoformat()
            by_day[day_key] = by_day.get(day_key, 0.0) + delta
        last_sp = sp

    if rejected_dt is not None:
        reject_day = credit_date_nz(rejected_dt)
        if window_start <= reject_day <= window_end and last_sp > 0:
            day_key = reject_day.isoformat()
            by_day[day_key] = by_day.get(day_key, 0.0) - last_sp

    return [{"date": day, "delta": delta} for day, delta in sorted(by_day.items()) if delta != 0]


def build_milestone_scope_daily(
    issues: list[dict[str, Any]],
    changelogs_by_key: dict[str, list[dict[str, Any]]],
    *,
    quarter_start: date | str,
    quarter_end: date | str,
    sp_field: str = "customfield_10026",
    as_of: date | str | None = None,
) -> tuple[list[dict[str, Any]], float]:
    """Sum scope SP deltas across milestone issues into a daily cumulative series."""
    start = date.fromisoformat(str(quarter_start)[:10])
    end = date.fromisoformat(str(quarter_end)[:10])
    delta_events: list[dict[str, Any]] = []
    for issue in issues:
        key = str(issue.get("key") or "")
        if not key:
            continue
        histories = changelogs_by_key.get(key) or []
        delta_events.extend(
            issue_scope_delta_events(
                issue,
                histories,
                quarter_start=start,
                quarter_end=end,
                sp_field=sp_field,
            )
        )

    scope_events = [
        {"credit_date": event["date"], "story_points": event["delta"]}
        for event in delta_events
    ]
    daily, total = aggregate_daily_burn(scope_events)
    if as_of is not None:
        daily = extend_daily_burn_to_as_of(daily, as_of, quarter_end=end)
    return daily, total


def flat_scope_daily(
    story_points: float,
    *,
    quarter_start: date | str,
    quarter_end: date | str,
    as_of: date | str | None = None,
) -> list[dict[str, Any]]:
    """Fallback scope line when changelog history is unavailable."""
    if story_points <= 0:
        return []
    start = date.fromisoformat(str(quarter_start)[:10])
    end = date.fromisoformat(str(quarter_end)[:10])
    target = end
    if as_of is not None:
        target = min(end, date.fromisoformat(str(as_of)[:10]))
    return [
        {"date": start.isoformat(), "cumulative_story_points": story_points},
        {"date": target.isoformat(), "cumulative_story_points": story_points},
    ]


def flat_unpointed_daily(
    unpointed_count: int,
    *,
    quarter_start: date | str,
    quarter_end: date | str,
    as_of: date | str | None = None,
) -> list[dict[str, Any]]:
    """Fallback unpointed count line when changelog history is unavailable."""
    if unpointed_count <= 0:
        return []
    start = date.fromisoformat(str(quarter_start)[:10])
    end = date.fromisoformat(str(quarter_end)[:10])
    target = end
    if as_of is not None:
        target = min(end, date.fromisoformat(str(as_of)[:10]))
    weight = float(unpointed_count)
    return [
        {"date": start.isoformat(), "cumulative_story_points": weight},
        {"date": target.isoformat(), "cumulative_story_points": weight},
    ]


def aligned_daily_cumulative(
    daily: list[dict[str, Any]],
    dates: list[date],
) -> list[float]:
    """Step-hold daily cumulative values onto chart dates."""
    if not dates:
        return []
    by_date = {
        date.fromisoformat(str(row["date"])[:10]): float(row["cumulative_story_points"])
        for row in daily
    }
    values: list[float] = []
    last = 0.0
    for day in dates:
        if day in by_date:
            last = by_date[day]
        values.append(last)
    return values
