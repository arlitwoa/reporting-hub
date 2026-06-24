"""Jira changelog burn helpers for quarterly deploy / Done credit (EPCE-6745)."""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from artifact.atlassian import AtlassianAdapter

from extensions.twoa_programme.jira_search import search_all
from extensions.twoa_programme.quarter_scope import (
    EC_SQUAD_NAME_TO_SLUG,
    EC_SQUAD_SPECS,
    LANE_KEYS,
    classify_exclusive_lane,
    education_cloud_squad_jqls,
    issue_excluded_from_analysis,
)
from extensions.twoa_programme.quarterly_reporting import (
    NZ_TZ,
    QuarterPeriod,
    aggregate_daily_burn,
    credit_date_nz,
    filter_events_in_quarter,
)

from scripts.quarterly.common import BINDING_PATH, SKIP_ISSUE_TYPES


def _issue_type_name(issue: dict) -> str:
    return ((issue.get("fields") or {}).get("issuetype") or {}).get("name") or ""


def _skip_analysis_issue(issue: dict, *, itype: str | None = None) -> bool:
    if itype is None:
        itype = _issue_type_name(issue)
    return itype in SKIP_ISSUE_TYPES or issue_excluded_from_analysis(issue)


CREDIT_MODE_DEPLOY_OR_DONE = "deploy_or_done"


def load_deploy_statuses() -> set[str]:
    binding = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
    status_map = binding.get("statusMap") or {}
    deploy = {name for name, phase in status_map.items() if phase == "Deploy"}
    deploy.add("PRD")
    return deploy


def load_done_statuses(*, velocity_credit_status: str = "Done") -> set[str]:
    """Terminal Drive-mapped statuses used when an issue never hits the deploy gate."""
    binding = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
    status_map = binding.get("statusMap") or {}
    done = {name for name, phase in status_map.items() if phase == "Drive"}
    if velocity_credit_status:
        done.add(velocity_credit_status)
    return done


def resolve_deploy_or_done_credit(
    *,
    deploy_at: datetime | None,
    deploy_status: str | None,
    done_at: datetime | None,
    done_status: str | None,
) -> tuple[datetime | None, str | None, str | None]:
    if deploy_at is not None:
        return deploy_at, deploy_status, "deploy"
    if done_at is not None:
        return done_at, done_status, "done"
    return None, None, None


def is_earned_status(
    status: str,
    deploy_statuses: set[str],
    done_statuses: set[str],
) -> bool:
    return status in deploy_statuses or status in done_statuses


def credit_ledger_from_status_transitions(
    transitions: list[tuple[datetime, str, str]],
    *,
    deploy_statuses: set[str],
    done_statuses: set[str],
) -> list[dict[str, Any]]:
    """Replay status changes; +1 credit on enter earned, -1 revoke on leave."""
    ledger: list[dict[str, Any]] = []
    currently_earned = False
    for created, _from_status, to_status in transitions:
        entering = is_earned_status(to_status, deploy_statuses, done_statuses)
        if entering and not currently_earned:
            mode = "deploy" if to_status in deploy_statuses else "done"
            ledger.append(
                {
                    "credit_at": created.isoformat(),
                    "delta": 1,
                    "status_at_credit": to_status,
                    "credit_mode": mode,
                }
            )
            currently_earned = True
        elif not entering and currently_earned:
            ledger.append(
                {
                    "credit_at": created.isoformat(),
                    "delta": -1,
                    "status_at_credit": to_status,
                    "credit_mode": "revoke",
                }
            )
            currently_earned = False
    return ledger


def ledger_currently_credited(ledger: list[dict[str, Any]]) -> bool:
    state = False
    for row in ledger:
        state = int(row.get("delta") or 0) > 0
    return state


def _fetch_status_transitions(
    adapter: AtlassianAdapter,
    issue_key: str,
) -> list[tuple[datetime, str, str]]:
    transitions: list[tuple[datetime, str, str]] = []
    start = 0
    while True:
        page = get_json_retry(
            adapter,
            f"/rest/api/3/issue/{issue_key}/changelog",
            params={"startAt": start, "maxResults": 100},
        )
        for record in page.get("values") or []:
            created = parse_jira_dt(record["created"])
            for item in record.get("items") or []:
                if item.get("field") != "status":
                    continue
                transitions.append(
                    (
                        created,
                        str(item.get("fromString") or ""),
                        str(item.get("toString") or ""),
                    )
                )
        if page.get("isLast", True):
            break
        start += len(page.get("values") or [])
    transitions.sort(key=lambda row: row[0])
    return transitions


def fetch_deploy_or_done_credit_ledger(
    adapter: AtlassianAdapter,
    issue_key: str,
    deploy_statuses: set[str],
    done_statuses: set[str],
) -> list[dict[str, Any]]:
    transitions = _fetch_status_transitions(adapter, issue_key)
    return credit_ledger_from_status_transitions(
        transitions,
        deploy_statuses=deploy_statuses,
        done_statuses=done_statuses,
    )


def _pack_ledger_cache(ledger: list[dict[str, Any]]) -> str:
    return json.dumps(ledger)


def _unpack_ledger_cache(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _resolve_credit_ledger(
    adapter: AtlassianAdapter,
    issue_key: str,
    deploy_statuses: set[str],
    done_statuses: set[str],
    *,
    cache: dict[str, str],
    cache_key: str,
    throttle_seconds: float = 0.0,
) -> list[dict[str, Any]]:
    if cache_key in cache:
        return _unpack_ledger_cache(cache[cache_key])
    if throttle_seconds:
        time.sleep(throttle_seconds)
    ledger = fetch_deploy_or_done_credit_ledger(
        adapter,
        issue_key,
        deploy_statuses,
        done_statuses,
    )
    cache[cache_key] = _pack_ledger_cache(ledger)
    return ledger


def _burn_events_from_ledger(
    ledger: list[dict[str, Any]],
    *,
    issue: dict[str, Any],
    sp_val: float,
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    key = str(issue.get("key") or "")
    fields = issue.get("fields") or {}
    itype = _issue_type_name(issue)
    status = str((fields.get("status") or {}).get("name") or "")
    events: list[dict[str, Any]] = []
    for row in ledger:
        delta = int(row.get("delta") or 0)
        if delta == 0:
            continue
        credit_at = parse_jira_dt(str(row["credit_at"]))
        credit_day = credit_date_nz(credit_at)
        events.append(
            {
                "key": key,
                "type": itype,
                "summary": fields.get("summary"),
                "story_points": sp_val * delta,
                "credit_at": credit_at.isoformat(),
                "credit_date": credit_day.isoformat(),
                "status_at_credit": row.get("status_at_credit"),
                "status_now": status,
                "statusCategory": _status_category_key(fields),
                "fixVersions": _fix_version_names(fields),
                "credit_mode": row.get("credit_mode") or ("revoke" if delta < 0 else "deploy_or_done"),
                **(extra or {}),
            }
        )
    return events


def parse_jira_dt(value: str) -> datetime:
    if value.endswith("+0000"):
        value = value[:-5] + "+00:00"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def get_json_retry(
    adapter: AtlassianAdapter,
    path: str,
    *,
    params: dict | None = None,
    attempts: int = 5,
):
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return adapter.http.get_json(path, params=params)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def first_status_transition(
    adapter: AtlassianAdapter,
    issue_key: str,
    target_statuses: set[str],
) -> tuple[datetime | None, str | None]:
    start = 0
    earliest: datetime | None = None
    earliest_status: str | None = None
    while True:
        page = get_json_retry(
            adapter,
            f"/rest/api/3/issue/{issue_key}/changelog",
            params={"startAt": start, "maxResults": 100},
        )
        for record in page.get("values") or []:
            created = parse_jira_dt(record["created"])
            for item in record.get("items") or []:
                if item.get("field") != "status":
                    continue
                to_status = item.get("toString") or ""
                if to_status in target_statuses:
                    if earliest is None or created < earliest:
                        earliest = created
                        earliest_status = to_status
        if page.get("isLast", True):
            break
        start += len(page.get("values") or [])
    return earliest, earliest_status


def first_deploy_or_done_transition(
    adapter: AtlassianAdapter,
    issue_key: str,
    deploy_statuses: set[str],
    done_statuses: set[str],
) -> tuple[datetime | None, str | None, str | None]:
    """Most recent credit timestamp when the issue is currently in an earned status."""
    ledger = fetch_deploy_or_done_credit_ledger(
        adapter,
        issue_key,
        deploy_statuses,
        done_statuses,
    )
    if not ledger_currently_credited(ledger):
        return None, None, None
    for row in reversed(ledger):
        if int(row.get("delta") or 0) > 0:
            return (
                parse_jira_dt(str(row["credit_at"])),
                str(row.get("status_at_credit") or "") or None,
                str(row.get("credit_mode") or "") or None,
            )
    return None, None, None


def _chunked_keys(keys: list[str], size: int = 50) -> list[list[str]]:
    return [keys[index : index + size] for index in range(0, len(keys), size)]


def align_milestone_credit_events(
    events: list[dict[str, Any]],
    *,
    window_start: date,
    window_end: date,
) -> list[dict[str, Any]]:
    """Keep credits within the milestone window; clamp pre-start Done/deploy to start date."""
    aligned: list[dict[str, Any]] = []
    for event in events:
        raw = event.get("credit_at")
        if not raw:
            continue
        credit_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        credit_day = credit_date_nz(credit_at)
        if credit_day > window_end:
            continue
        if credit_day < window_start:
            credit_at = datetime.combine(window_start, datetime.min.time(), tzinfo=NZ_TZ)
            credit_day = window_start
        aligned.append(
            {
                **event,
                "credit_at": credit_at.isoformat(),
                "credit_date": credit_day.isoformat(),
            }
        )
    aligned.sort(key=lambda row: row["credit_at"])
    return aligned


def earned_events_for_scope_keys(
    adapter: AtlassianAdapter,
    scope_keys: set[str] | list[str],
    *,
    sp_field: str,
    deploy_statuses: set[str],
    done_statuses: set[str],
    cache_path: Path,
    seed_events_by_key: dict[str, dict[str, Any]] | None = None,
    throttle_seconds: float = 0.15,
    quarter: QuarterPeriod | None = None,
    window_start: date | None = None,
    window_end: date | None = None,
) -> list[dict[str, Any]]:
    """Resolve deploy/done credit for milestone scope keys (ignores global burn JQL)."""
    seed = seed_events_by_key or {}
    ordered_keys = sorted({str(key) for key in scope_keys if key})
    if not ordered_keys:
        return []

    cache = _load_cache(cache_path)
    cache_dirty = False
    issues_by_key: dict[str, dict[str, Any]] = {}
    keys_to_fetch: list[str] = []
    for key in ordered_keys:
        keys_to_fetch.append(key)

    fields = ["summary", "issuetype", "status", "fixVersions", sp_field]
    for chunk in _chunked_keys(keys_to_fetch):
        jql = f"key in ({', '.join(chunk)})"
        for issue in search_all(adapter, jql, fields):
            issue_key = str(issue.get("key") or "")
            if issue_key:
                issues_by_key[issue_key] = issue

    events: list[dict[str, Any]] = []
    for key in ordered_keys:
        issue = issues_by_key.get(key)
        if not issue:
            seed_event = seed.get(key)
            if not seed_event:
                continue
            issue = {
                "key": key,
                "fields": {
                    "summary": seed_event.get("summary"),
                    "issuetype": {"name": seed_event.get("type") or "Story"},
                    "status": {"name": seed_event.get("status_now") or ""},
                    sp_field: seed_event.get("story_points"),
                    "fixVersions": [],
                },
            }
        fields_row = issue.get("fields") or {}
        itype = _issue_type_name(issue)
        if _skip_analysis_issue(issue, itype=itype):
            continue
        sp_raw = fields_row.get(sp_field)
        if sp_raw is None:
            continue
        sp_val = float(sp_raw)
        if sp_val <= 0:
            continue

        cache_key = f"credit:v3:milestone:{key}"
        ledger = _resolve_credit_ledger(
            adapter,
            key,
            deploy_statuses,
            done_statuses,
            cache=cache,
            cache_key=cache_key,
            throttle_seconds=throttle_seconds,
        )
        cache_dirty = True
        issue_events = _burn_events_from_ledger(
            ledger,
            issue=issue,
            sp_val=sp_val,
            extra={"creditSource": "milestone_scope"},
        )
        if not issue_events:
            continue
        events.extend(issue_events)

    if cache_dirty:
        _save_cache(cache_path, cache)

    events.sort(key=lambda row: row["credit_at"])
    if window_start is not None and window_end is not None:
        return align_milestone_credit_events(
            events,
            window_start=window_start,
            window_end=window_end,
        )
    if quarter is not None:
        return filter_events_in_quarter(events, quarter)
    return events


def _fix_version_names(fields: dict[str, Any]) -> list[str]:
    return [
        str(version.get("name"))
        for version in (fields.get("fixVersions") or [])
        if isinstance(version, dict) and version.get("name")
    ]


def _status_category_key(fields: dict[str, Any]) -> str | None:
    status = fields.get("status") or {}
    if not isinstance(status, dict):
        return None
    category = status.get("statusCategory") or {}
    if not isinstance(category, dict):
        return None
    key = category.get("key")
    return str(key) if key else None


def _field_values(fields: dict[str, Any], field_id: str) -> list[str]:
    raw = fields.get(field_id)
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


def sum_story_points_in_scope(
    adapter: AtlassianAdapter,
    jql: str,
    sp_field: str,
) -> dict[str, float | int]:
    """Sum Story Points for all issues matching scope JQL."""
    issues = search_all(adapter, jql, ["issuetype", sp_field, "status"])
    total = 0.0
    counted = 0
    missing = 0
    scanned = 0
    for issue in issues:
        itype = _issue_type_name(issue)
        if _skip_analysis_issue(issue, itype=itype):
            continue
        scanned += 1
        sp = (issue.get("fields") or {}).get(sp_field)
        if sp is None:
            missing += 1
            continue
        total += float(sp)
        counted += 1
    return {
        "plannedStoryPoints": round(total, 2),
        "issuesWithStoryPoints": counted,
        "issuesMissingStoryPoints": missing,
        "issuesScanned": scanned,
    }


def sum_story_points_by_exclusive_lane(
    adapter: AtlassianAdapter,
    global_scope_jql: str,
    sp_field: str,
    *,
    delivery_squad_field: str,
    change_types_field: str,
    platform_field: str,
    lane_jqls: dict[str, str],
) -> dict[str, dict]:
    """Partition global scope in Python (Jira exclusive JQL under-counts with NOT/OR)."""
    fields = [
        "issuetype",
        "status",
        sp_field,
        delivery_squad_field,
        change_types_field,
        platform_field,
        "issuelinks",
    ]
    issues = search_all(adapter, global_scope_jql, fields)
    breakdown: dict[str, dict] = {
        key: {
            "jql": lane_jqls[key],
            "plannedStoryPoints": 0.0,
            "issuesWithStoryPoints": 0,
            "issuesMissingStoryPoints": 0,
            "issuesScanned": 0,
            "partitionMethod": "python_exclusive",
        }
        for key in LANE_KEYS
    }
    for issue in issues:
        itype = _issue_type_name(issue)
        if _skip_analysis_issue(issue, itype=itype):
            continue
        lane = classify_exclusive_lane(
            issue,
            delivery_squad_field=delivery_squad_field,
            change_types_field=change_types_field,
            platform_field=platform_field,
        )
        row = breakdown[lane]
        row["issuesScanned"] += 1
        sp = (issue.get("fields") or {}).get(sp_field)
        if sp is None:
            row["issuesMissingStoryPoints"] += 1
            continue
        row["issuesWithStoryPoints"] += 1
        row["plannedStoryPoints"] = round(row["plannedStoryPoints"] + float(sp), 2)
    return breakdown


BURN_ISSUE_TYPES = frozenset({"Story", "Bug"})


def unpointed_stories_bugs_jql(base_jql: str, *, story_points_field: str = "Story Points") -> str:
    return f'{base_jql} AND "{story_points_field}" is EMPTY'


def count_unpointed_stories_bugs_by_lane(
    adapter: AtlassianAdapter,
    global_burn_jql: str,
    sp_field: str,
    *,
    delivery_squad_field: str,
    change_types_field: str,
    platform_field: str,
    lane_jqls: dict[str, str],
    story_points_jql_name: str = "Story Points",
) -> dict:
    """Count Story/Bug issues in quarter scope with no story points, partitioned by lane."""
    fields = [
        "issuetype",
        "status",
        sp_field,
        delivery_squad_field,
        change_types_field,
        platform_field,
        "issuelinks",
    ]
    issues = search_all(adapter, global_burn_jql, fields)
    by_lane: dict[str, dict] = {
        key: {
            "count": 0,
            "jql": unpointed_stories_bugs_jql(lane_jqls[key], story_points_field=story_points_jql_name),
            "issueKeys": [],
        }
        for key in LANE_KEYS
    }
    total = 0
    issue_keys: list[str] = []
    for issue in issues:
        itype = _issue_type_name(issue)
        if itype not in BURN_ISSUE_TYPES or _skip_analysis_issue(issue, itype=itype):
            continue
        if (issue.get("fields") or {}).get(sp_field) is not None:
            continue
        lane = classify_exclusive_lane(
            issue,
            delivery_squad_field=delivery_squad_field,
            change_types_field=change_types_field,
            platform_field=platform_field,
        )
        key = str(issue.get("key") or "")
        by_lane[lane]["count"] += 1
        if key:
            by_lane[lane]["issueKeys"].append(key)
            issue_keys.append(key)
        total += 1
    return {
        "total": total,
        "jql": unpointed_stories_bugs_jql(global_burn_jql, story_points_field=story_points_jql_name),
        "issueKeys": issue_keys,
        "byLane": by_lane,
    }


def count_unpointed_stories_bugs_for_jql(
    adapter: AtlassianAdapter,
    jql: str,
    sp_field: str,
    *,
    story_points_jql_name: str = "Story Points",
) -> dict[str, int | str]:
    """Count Story/Bug issues in scope with no story points."""
    issues = search_all(adapter, jql, ["issuetype", sp_field, "status"])
    count = 0
    for issue in issues:
        itype = _issue_type_name(issue)
        if itype not in BURN_ISSUE_TYPES or _skip_analysis_issue(issue, itype=itype):
            continue
        if (issue.get("fields") or {}).get(sp_field) is not None:
            continue
        count += 1
    return {
        "count": count,
        "jql": unpointed_stories_bugs_jql(jql, story_points_field=story_points_jql_name),
    }


def _primary_ec_squad_slug(squad_names: list[str]) -> str | None:
    """First Education Cloud squad on the issue (matches earned-event attribution)."""
    for name in squad_names:
        slug = EC_SQUAD_NAME_TO_SLUG.get(name)
        if slug:
            return slug
    return None


def education_cloud_squad_scope_breakdown(
    adapter: AtlassianAdapter,
    sp_field: str,
    *,
    quarter_filter: str,
    global_scope_jql: str,
    global_burn_jql: str,
    delivery_squad_field: str,
    change_types_field: str,
    platform_field: str,
    story_points_jql_name: str = "Story Points",
) -> dict[str, dict]:
    """Planned SP and unpointed Story/Bug per EC squad (Python partition, same as lane totals)."""
    squad_specs = education_cloud_squad_jqls(quarter_filter=quarter_filter)
    breakdown: dict[str, dict] = {
        slug: {
            "slug": slug,
            "label": spec["label"],
            "squadName": spec["squadName"],
            "scopeJql": spec["scopeJql"],
            "burnJql": spec["burnJql"],
            "plannedStoryPoints": 0.0,
            "issuesWithStoryPoints": 0,
            "issuesMissingStoryPoints": 0,
            "unpointedStoriesBugs": 0,
            "unpointedStoriesBugsJql": unpointed_stories_bugs_jql(
                spec["burnJql"],
                story_points_field=story_points_jql_name,
            ),
            "unpointedIssueKeys": [],
            "partitionMethod": "python_ec_squad",
        }
        for slug, spec in squad_specs.items()
    }
    fields = [
        "issuetype",
        "status",
        sp_field,
        delivery_squad_field,
        change_types_field,
        platform_field,
        "issuelinks",
    ]
    issues = search_all(adapter, global_scope_jql, fields)
    for issue in issues:
        itype = _issue_type_name(issue)
        if _skip_analysis_issue(issue, itype=itype):
            continue
        lane = classify_exclusive_lane(
            issue,
            delivery_squad_field=delivery_squad_field,
            change_types_field=change_types_field,
            platform_field=platform_field,
        )
        if lane != "educationCloud":
            continue
        squad_names = _field_values(issue.get("fields") or {}, delivery_squad_field)
        slug = _primary_ec_squad_slug(squad_names)
        if not slug or slug not in breakdown:
            continue
        row = breakdown[slug]
        sp = (issue.get("fields") or {}).get(sp_field)
        if sp is None:
            row["issuesMissingStoryPoints"] += 1
            if itype in BURN_ISSUE_TYPES:
                row["unpointedStoriesBugs"] += 1
                issue_key = str(issue.get("key") or "")
                if issue_key:
                    row["unpointedIssueKeys"].append(issue_key)
            continue
        row["issuesWithStoryPoints"] += 1
        row["plannedStoryPoints"] = round(row["plannedStoryPoints"] + float(sp), 2)
    return breakdown


def _load_cache(cache_path: Path) -> dict[str, str | None]:
    if not cache_path.exists():
        return {}
    return json.loads(cache_path.read_text(encoding="utf-8"))


def _save_cache(cache_path: Path, cache: dict[str, str | None]) -> None:
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _pack_credit_cache(
    credit_at: datetime | None,
    status_at_credit: str | None,
    credit_mode: str | None = None,
) -> str | None:
    if credit_at is None:
        return None
    return "|".join(
        [
            credit_at.isoformat(),
            status_at_credit or "",
            credit_mode or "",
        ]
    )


def _unpack_credit_cache(raw: str | None) -> tuple[datetime | None, str | None, str | None]:
    if not raw:
        return None, None, None
    if "|" not in raw:
        return parse_jira_dt(raw), None, None
    parts = raw.split("|")
    at_s = parts[0]
    status = parts[1] if len(parts) > 1 else ""
    mode = parts[2] if len(parts) > 2 else None
    return parse_jira_dt(at_s), status or None, mode or None


def burn_lane(
    adapter: AtlassianAdapter,
    *,
    lane_key: str,
    label: str,
    scope_jql: str,
    quarter: QuarterPeriod,
    sp_field: str,
    deploy_statuses: set[str],
    done_statuses: set[str],
    cache_path: Path,
    limit: int | None = None,
    throttle_seconds: float = 0.15,
    extra_fields: list[str] | None = None,
) -> dict:
    """Scan lane scope and return deploy- or Done-earned SP within the quarter."""
    fields = ["summary", "issuetype", "status", "fixVersions", sp_field, *(extra_fields or [])]
    issues = search_all(adapter, scope_jql, fields)
    cache = _load_cache(cache_path)

    candidates: list[tuple[dict, float, dict]] = []
    for iss in issues:
        f = iss.get("fields") or {}
        itype = (f.get("issuetype") or {}).get("name") or ""
        if _skip_analysis_issue(iss, itype=itype):
            continue
        sp = f.get(sp_field)
        if sp is None or float(sp) <= 0:
            continue
        candidates.append((iss, float(sp), f))
        if limit is not None and len(candidates) >= limit:
            break

    earned_events: list[dict] = []
    not_credited: list[dict] = []

    for idx, (iss, sp_val, f) in enumerate(candidates, 1):
        if idx % 25 == 0:
            print(f"{lane_key}: changelog {idx}/{len(candidates)}...", flush=True)
        status = (f.get("status") or {}).get("name") or ""
        key = iss["key"]
        cache_key = f"credit:v3:{lane_key}:{key}"
        ledger = _resolve_credit_ledger(
            adapter,
            key,
            deploy_statuses,
            done_statuses,
            cache=cache,
            cache_key=cache_key,
            throttle_seconds=throttle_seconds,
        )
        _save_cache(cache_path, cache)

        itype = (f.get("issuetype") or {}).get("name") or ""
        issue_events = _burn_events_from_ledger(ledger, issue=iss, sp_val=sp_val)
        net_sp = sum(float(event.get("story_points") or 0) for event in issue_events)
        if net_sp <= 0 and not ledger_currently_credited(ledger):
            not_credited.append(
                {
                    "key": key,
                    "type": itype,
                    "status": status,
                    "story_points": sp_val,
                    "summary": f.get("summary"),
                }
            )
            continue

        earned_events.extend(issue_events)

    earned_events.sort(key=lambda e: e["credit_at"])
    in_quarter = filter_events_in_quarter(earned_events, quarter)
    daily, total = aggregate_daily_burn(in_quarter)
    return {
        "lane": lane_key,
        "label": label,
        "scopeJql": scope_jql,
        "creditMode": CREDIT_MODE_DEPLOY_OR_DONE,
        "deployStatuses": sorted(deploy_statuses),
        "doneStatuses": sorted(done_statuses),
        "issuesScanned": len(issues),
        "candidatesWithStoryPoints": len(candidates),
        "earnedEventCount": len(in_quarter),
        "totalStoryPointsEarned": total,
        "events": in_quarter,
        "daily": daily,
        "notYetCreditedCount": len(not_credited),
        "notYetCreditedSample": not_credited[:20],
    }


def burn_global_with_lane_split(
    adapter: AtlassianAdapter,
    *,
    global_scope_jql: str,
    quarter: QuarterPeriod,
    sp_field: str,
    lane_specs: dict[str, dict],
    cache_path: Path,
    delivery_squad_field: str,
    change_types_field: str,
    platform_field: str,
    limit: int | None = None,
    throttle_seconds: float = 0.15,
    deploy_statuses: set[str],
    done_statuses: set[str],
    selected_lanes: tuple[str, ...] | None = None,
) -> tuple[dict, dict[str, dict]]:
    """Scan global scope once; split earned SP into exclusive lanes in Python."""
    fields = [
        "summary",
        "issuetype",
        "status",
        "fixVersions",
        sp_field,
        delivery_squad_field,
        change_types_field,
        platform_field,
        "issuelinks",
    ]
    issues = search_all(adapter, global_scope_jql, fields)
    cache = _load_cache(cache_path)
    lanes = selected_lanes or tuple(lane_specs.keys())

    lane_state: dict[str, dict] = {
        lane_key: {
            "lane": lane_key,
            "label": lane_specs[lane_key]["label"],
            "scopeJql": lane_specs[lane_key]["scope_jql"],
            "creditMode": CREDIT_MODE_DEPLOY_OR_DONE,
            "deployStatuses": sorted(deploy_statuses),
            "doneStatuses": sorted(done_statuses),
            "issuesScanned": 0,
            "candidatesWithStoryPoints": 0,
            "earnedEventCount": 0,
            "totalStoryPointsEarned": 0.0,
            "events": [],
            "daily": [],
            "notYetCreditedCount": 0,
            "notYetCreditedSample": [],
            "partitionMethod": "python_exclusive",
        }
        for lane_key in lanes
    }
    global_events: list[dict] = []
    global_not_credited: list[dict] = []
    global_candidates = 0
    global_scanned = 0

    for iss in issues:
        f = iss.get("fields") or {}
        itype = (f.get("issuetype") or {}).get("name") or ""
        if _skip_analysis_issue(iss, itype=itype):
            continue
        global_scanned += 1
        sp = f.get(sp_field)
        if sp is None or float(sp) <= 0:
            continue
        global_candidates += 1
        if limit is not None and global_candidates > limit:
            break

        lane_key = classify_exclusive_lane(
            iss,
            delivery_squad_field=delivery_squad_field,
            change_types_field=change_types_field,
            platform_field=platform_field,
        )
        if lane_key in lane_state:
            lane_state[lane_key]["issuesScanned"] += 1
            lane_state[lane_key]["candidatesWithStoryPoints"] += 1

        status = (f.get("status") or {}).get("name") or ""
        key = iss["key"]
        cache_key = f"credit:v3:global:{key}"
        ledger = _resolve_credit_ledger(
            adapter,
            key,
            deploy_statuses,
            done_statuses,
            cache=cache,
            cache_key=cache_key,
            throttle_seconds=throttle_seconds,
        )
        _save_cache(cache_path, cache)

        issue_events = _burn_events_from_ledger(ledger, issue=iss, sp_val=float(sp))
        net_sp = sum(float(event.get("story_points") or 0) for event in issue_events)
        if net_sp <= 0 and not ledger_currently_credited(ledger):
            row = {
                "key": key,
                "type": itype,
                "status": status,
                "story_points": float(sp),
                "summary": f.get("summary"),
            }
            global_not_credited.append(row)
            if lane_key in lane_state:
                lane_state[lane_key]["notYetCreditedCount"] += 1
                sample = lane_state[lane_key]["notYetCreditedSample"]
                if len(sample) < 20:
                    sample.append(row)
            continue

        squads = _field_values(f, delivery_squad_field)
        for event in issue_events:
            event["lane"] = lane_key
            event["deliverySquads"] = squads
        global_events.extend(issue_events)
        if lane_key in lane_state:
            lane_state[lane_key]["events"].extend(issue_events)

    global_events.sort(key=lambda e: e["credit_at"])
    in_quarter = filter_events_in_quarter(global_events, quarter)
    global_daily, global_total = aggregate_daily_burn(in_quarter)

    global_result = {
        "lane": "global",
        "label": "Global quarter scope",
        "scopeJql": global_scope_jql,
        "creditMode": CREDIT_MODE_DEPLOY_OR_DONE,
        "deployStatuses": sorted(deploy_statuses),
        "doneStatuses": sorted(done_statuses),
        "issuesScanned": global_scanned,
        "candidatesWithStoryPoints": min(global_candidates, limit or global_candidates),
        "earnedEventCount": len(in_quarter),
        "totalStoryPointsEarned": global_total,
        "events": in_quarter,
        "daily": global_daily,
        "notYetCreditedCount": len(global_not_credited),
        "notYetCreditedSample": global_not_credited[:20],
        "partitionMethod": "python_exclusive",
    }

    lane_results: dict[str, dict] = {}
    for lane_key, row in lane_state.items():
        events = sorted(row["events"], key=lambda e: e["credit_at"])
        lane_in_quarter = filter_events_in_quarter(events, quarter)
        daily, total = aggregate_daily_burn(lane_in_quarter)
        row["events"] = lane_in_quarter
        row["daily"] = daily
        row["earnedEventCount"] = len(lane_in_quarter)
        row["totalStoryPointsEarned"] = total
        lane_results[lane_key] = row

    return global_result, lane_results
