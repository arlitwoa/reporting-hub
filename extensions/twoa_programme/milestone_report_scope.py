"""Resolve milestone report in-scope filter and chart window from config."""

from __future__ import annotations

from datetime import date
from typing import Any

from artifact.atlassian import AtlassianAdapter

from extensions.twoa_programme.delivery_milestones import resolve_milestone_in_scope_filter
from extensions.twoa_programme.quarterly_reporting import DeliveryMilestones, QuarterPeriod


def report_window_dates(payload: dict[str, Any]) -> tuple[date | None, date | None]:
    """Report chart window from timeline artifact (filter-driven or legacy quarter fields)."""
    start_raw = payload.get("reportWindowStart") or payload.get("quarterStart")
    end_raw = payload.get("reportWindowEnd") or payload.get("quarterEnd")
    start = date.fromisoformat(str(start_raw)[:10]) if start_raw else None
    end = date.fromisoformat(str(end_raw)[:10]) if end_raw else None
    return start, end


def milestone_report_page_title(payload: dict[str, Any]) -> str:
    start, end = report_window_dates(payload)
    if start and end:
        return (
            f"Milestone Report | {start.strftime('%d %b %Y')} to {end.strftime('%d %b %Y')}"
        )
    return "Milestone Report"


def milestone_report_timeline_footnote(payload: dict[str, Any], *, detail: str) -> str:
    count = int(payload.get("milestoneCount") or 0)
    start, end = report_window_dates(payload)
    if start and end:
        window = f"{start.isoformat()} to {end.isoformat()}"
        return f"{count} milestones in scope for this report ({window}). {detail}"
    return f"{count} milestones in scope for this report. {detail}"


def resolve_milestone_report_scope(
    adapter: AtlassianAdapter,
    delivery_milestones: DeliveryMilestones,
    quarter: QuarterPeriod,
) -> tuple[str | None, str | None, date, date]:
    """Return filter name, filter JQL, and report window start/end dates."""
    filter_name, filter_jql, (window_start, window_end) = resolve_milestone_in_scope_filter(
        adapter,
        filter_id=delivery_milestones.in_scope_filter_id,
        filter_name=delivery_milestones.in_scope_filter,
    )
    report_start = window_start or quarter.start_date
    report_end = window_end or quarter.end_date
    return filter_name, filter_jql, report_start, report_end
