"""Extrapolate Release Plan sprint/PRD cadence and allocate deploy-earned SP."""

from __future__ import annotations

import re
from datetime import date, timedelta
from statistics import median
from typing import Any

from extensions.twoa_programme.pde_engine_releases import is_placeholder_engine_version, release_row_code

SPRINT_RE = re.compile(r"sprint\s*(\d+)", re.IGNORECASE)


def _parse_sprint_num(name: str) -> int | None:
    match = SPRINT_RE.search(name or "")
    return int(match.group(1)) if match else None


def _clip_window(start: date, end: date, quarter_start: date, quarter_end: date) -> tuple[date, date] | None:
    clip_start = max(start, quarter_start)
    clip_end = min(end, quarter_end)
    if clip_start > clip_end:
        return None
    return clip_start, clip_end


def extend_sprint_calendar(
    sprints: list[dict],
    *,
    quarter_start: date,
    quarter_end: date,
) -> list[dict]:
    """Backfill and forward-fill 14-day sprint blocks from workbook anchors."""
    if not sprints:
        return []
    parsed = []
    for row in sprints:
        num = _parse_sprint_num(row.get("name", ""))
        start = date.fromisoformat(row["startDate"])
        end = date.fromisoformat(row["endDate"])
        length = (end - start).days + 1
        parsed.append({"num": num, "name": row["name"], "start": start, "end": end, "length": length})
    parsed.sort(key=lambda item: item["start"])
    anchor = parsed[0]
    sprint_len = anchor["length"] if anchor["length"] > 0 else 14
    by_num = {item["num"]: item for item in parsed if item["num"] is not None}

    earliest = parsed[0]
    if earliest["num"] is not None:
        cursor_end = earliest["start"] - timedelta(days=1)
        num = earliest["num"] - 1
        while cursor_end >= quarter_start and num > 0:
            cursor_start = cursor_end - timedelta(days=sprint_len - 1)
            by_num[num] = {
                "num": num,
                "name": f"Sprint {num}",
                "start": cursor_start,
                "end": cursor_end,
                "length": sprint_len,
                "projected": True,
            }
            cursor_end = cursor_start - timedelta(days=1)
            num -= 1

    latest = parsed[-1]
    if latest["num"] is not None:
        cursor_start = latest["end"] + timedelta(days=1)
        num = latest["num"] + 1
        while cursor_start <= quarter_end:
            cursor_end = cursor_start + timedelta(days=sprint_len - 1)
            by_num[num] = {
                "num": num,
                "name": f"Sprint {num}",
                "start": cursor_start,
                "end": cursor_end,
                "length": sprint_len,
                "projected": True,
            }
            cursor_start = cursor_end + timedelta(days=1)
            num += 1

    for item in parsed:
        if item["num"] is not None:
            item.setdefault("projected", False)
            by_num[item["num"]] = item

    out: list[dict] = []
    for num in sorted(by_num):
        item = by_num[num]
        clipped = _clip_window(item["start"], item["end"], quarter_start, quarter_end)
        if not clipped:
            continue
        clip_start, clip_end = clipped
        out.append(
            {
                "name": item["name"],
                "sprintNumber": num,
                "startDate": clip_start.isoformat(),
                "endDate": clip_end.isoformat(),
                "projected": bool(item.get("projected")),
            }
        )
    return out


def extend_prd_releases(
    releases: list[dict],
    *,
    quarter_start: date,
    quarter_end: date,
) -> list[dict]:
    """Legacy PRD row extrapolation (workbook). Prefer PDE engine calendar when available."""
    known = sorted(
        {date.fromisoformat(row["releaseDate"]) for row in releases if row.get("releaseDate")},
    )
    if not known:
        return []
    gaps = [(known[i] - known[i - 1]).days for i in range(1, len(known))]
    step = int(median(gaps)) if gaps else 14
    step = max(step, 7)

    all_dates = set(known)
    cursor = known[0]
    while cursor > quarter_start:
        cursor -= timedelta(days=step)
        if cursor >= quarter_start:
            all_dates.add(cursor)
    cursor = known[-1]
    while cursor < quarter_end:
        cursor += timedelta(days=step)
        if cursor <= quarter_end:
            all_dates.add(cursor)

    projected_known = set(known)
    out: list[dict] = []
    for day in sorted(all_dates):
        out.append(
            {
                "releaseDate": day.isoformat(),
                "env": "PRD",
                "projected": day not in projected_known,
            }
        )
    return out


def _collect_burn_events(burn: dict) -> list[dict]:
    events: list[dict] = []
    for lane in (burn.get("lanes") or {}).values():
        for event in lane.get("events") or []:
            events.append({**event, "lane": lane.get("lane")})
    return events


def _release_name_set(releases: list[dict]) -> set[str]:
    return {
        str(row.get("name"))
        for row in releases
        if row.get("name") and not str(row.get("name")).startswith("projected-")
    }


def _matching_release_name(fix_versions: list[str], release_names: set[str]) -> str | None:
    for name in fix_versions:
        if name in release_names and not is_placeholder_engine_version(name):
            return name
    return None


def _event_is_done(event: dict) -> bool:
    return str(event.get("statusCategory") or "").lower() == "done"


def _release_windows(
    releases: list[dict],
    *,
    quarter_start: date,
) -> list[tuple[dict, date, date]]:
    ordered = sorted(releases, key=lambda row: str(row.get("releaseDate") or ""))
    windows: list[tuple[dict, date, date]] = []
    prev_day: date | None = None
    for rel in ordered:
        rel_day = date.fromisoformat(str(rel["releaseDate"]))
        window_start = (prev_day + timedelta(days=1)) if prev_day else quarter_start
        windows.append((rel, window_start, rel_day))
        prev_day = rel_day
    return windows


def _claim_event_snapshot(event: dict) -> dict:
    return {
        "key": event["key"],
        "story_points": float(event.get("story_points") or 0),
        "credit_date": event["credit_date"],
        "lane": event.get("lane"),
    }


def _allocate_release_claims(
    releases: list[dict],
    events: list[dict],
    *,
    quarter_start: date,
) -> dict[str, list[dict]]:
    release_names = _release_name_set(releases)
    by_release_name: dict[str, list[dict]] = {name: [] for name in release_names}
    assigned_keys: set[str] = set()

    for event in events:
        fix_versions = [str(name) for name in (event.get("fixVersions") or []) if name]
        release_name = _matching_release_name(fix_versions, release_names)
        if not release_name or not _event_is_done(event):
            continue
        key = str(event.get("key") or "")
        if not key or key in assigned_keys:
            continue
        assigned_keys.add(key)
        by_release_name.setdefault(release_name, []).append(_claim_event_snapshot(event))

    for rel, window_start, window_end in _release_windows(releases, quarter_start=quarter_start):
        release_name = str(rel.get("name") or "")
        if not release_name:
            continue
        for event in events:
            key = str(event.get("key") or "")
            if not key or key in assigned_keys:
                continue
            credit = date.fromisoformat(str(event["credit_date"])[:10])
            if window_start <= credit <= window_end:
                assigned_keys.add(key)
                by_release_name.setdefault(release_name, []).append(_claim_event_snapshot(event))

    return by_release_name


def allocate_burn_to_calendar(
    plan: dict,
    burn: dict | None,
    *,
    quarter_start: date,
    quarter_end: date,
) -> dict[str, Any]:
    """Claim deploy-earned SP per sprint window and per PRD release period."""
    if plan.get("extended"):
        sprints = plan.get("sprints") or []
        releases = plan.get("inCycleReleases") or []
    else:
        sprints = extend_sprint_calendar(
            plan.get("sprints") or [],
            quarter_start=quarter_start,
            quarter_end=quarter_end,
        )
        releases = extend_prd_releases(
            plan.get("inCycleReleases") or [],
            quarter_start=quarter_start,
            quarter_end=quarter_end,
        )
    events = _collect_burn_events(burn or {})

    sprint_rows: list[dict] = []
    for sprint in sprints:
        start = date.fromisoformat(sprint["startDate"])
        end = date.fromisoformat(sprint["endDate"])
        claimed: list[dict] = []
        total = 0.0
        for event in events:
            credit = date.fromisoformat(event["credit_date"])
            if start <= credit <= end:
                sp = float(event.get("story_points") or 0)
                total += sp
                claimed.append(
                    {
                        "key": event["key"],
                        "story_points": sp,
                        "credit_date": event["credit_date"],
                        "lane": event.get("lane"),
                    }
                )
        sprint_rows.append(
            {
                **sprint,
                "claimedStoryPoints": round(total, 2),
                "events": claimed,
                "projected": bool(sprint.get("projected")),
            }
        )

    allocation_releases = list(releases)
    release_claims = _allocate_release_claims(
        allocation_releases,
        events,
        quarter_start=quarter_start,
    )
    release_windows = {
        str(rel.get("name") or ""): (start, end)
        for rel, start, end in _release_windows(allocation_releases, quarter_start=quarter_start)
    }
    release_rows: list[dict] = []
    for rel in allocation_releases:
        release_name = str(rel.get("name") or "")
        claimed = release_claims.get(release_name, [])
        total = round(sum(row["story_points"] for row in claimed), 2)
        window_start, window_end = release_windows.get(release_name, (None, None))
        release_rows.append(
            {
                **rel,
                "releaseCode": release_row_code(rel),
                "windowStart": window_start.isoformat() if window_start else rel.get("releaseDate"),
                "windowEnd": window_end.isoformat() if window_end else rel.get("releaseDate"),
                "claimedStoryPoints": total,
                "events": claimed,
                "projected": bool(rel.get("projected")),
            }
        )

    return {
        "quarterStart": quarter_start.isoformat(),
        "quarterEnd": quarter_end.isoformat(),
        "sprintCadenceDays": (date.fromisoformat(sprints[1]["startDate"]) - date.fromisoformat(sprints[0]["startDate"])).days
        if len(sprints) > 1
        else 14,
        "releaseCadenceDays": int(
            median(
                [
                    (
                        date.fromisoformat(releases[i]["releaseDate"])
                        - date.fromisoformat(releases[i - 1]["releaseDate"])
                    ).days
                    for i in range(1, len(releases))
                ]
            )
        )
        if len(releases) > 1
        else 14,
        "sprints": sprint_rows,
        "inCycleReleases": release_rows,
        "totalClaimedStoryPoints": round(sum(row["claimedStoryPoints"] for row in sprint_rows), 2),
        "releaseMarkerCount": len(releases),
        "releaseAllocationCount": len(release_rows),
        "note": (
            "Sprint claim = credit_date within sprint. "
            "Release claim = deploy-earned SP on issues tagged with this engine fixVersion "
            "when status category is Done; otherwise credit_date in the PRD window "
            "(day after previous release through this release date)."
        ),
    }
