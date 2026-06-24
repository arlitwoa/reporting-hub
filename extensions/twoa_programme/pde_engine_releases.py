"""PDE Engine fixVersion calendar for quarterly reporting (real + projected releases)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from artifact.delivery_health.sprint_engine import engine_date_from_fix_version

CARRIAGE_TYPE_FIELD = "customfield_10120"
RELEASE_CADENCE_DAYS = 14
IN_CYCLE_CARRIAGE = "In Cycle"
OUT_OF_CYCLE_CARRIAGE = "Out Of Cycle"

# Carriage Type → two-letter release suffix (MMdd + suffix, e.g. 0416IC, 0422OC).
CARRIAGE_TYPE_CODES: dict[str, str] = {
    "In Cycle Code": "IC",
    "Out Of Cycle Code": "OC",
    "In Cycle Data": "ID",
    "Out Of Cycle Data": "OD",
    "In Cycle": "IC",
    "Out Of Cycle": "OC",
    "Go Live": "GL",
}


def carriage_type_code(carriage_type: str | None, *, projected: bool = False) -> str:
    """Map PDE Carriage Type to release suffix (IC/OC/ID/OD/…)."""
    if projected:
        return "IC"
    if not carriage_type:
        return "IC"
    key = carriage_type.strip()
    if key in CARRIAGE_TYPE_CODES:
        return CARRIAGE_TYPE_CODES[key]
    lower = key.lower()
    is_data = "data" in lower
    is_out = "out" in lower
    if is_data and is_out:
        return "OD"
    if is_data:
        return "ID"
    if is_out:
        return "OC"
    return "IC"


def carriage_cycle_label(carriage_type: str | None, *, projected: bool = False) -> str:
    """First carriage level: in-cycle vs out-of-cycle timing (or Go Live)."""
    if projected:
        return "Projected in-cycle"
    if not carriage_type:
        return "In Cycle"
    key = carriage_type.strip()
    if key == "Go Live":
        return "Go Live"
    lower = key.lower()
    if "out" in lower and "cycle" in lower:
        return "Out Of Cycle"
    if "in" in lower and "cycle" in lower:
        return "In Cycle"
    return key


def carriage_delivery_kind(carriage_type: str | None, *, projected: bool = False) -> str:
    """Second carriage level: Code vs Data (IC/OC/ID/OD suffix meaning)."""
    if projected:
        return "Code"
    if not carriage_type:
        return "Code"
    key = carriage_type.strip()
    if key == "Go Live":
        return "Go Live"
    if "data" in key.lower():
        return "Data"
    return "Code"


def release_date_mmdd(release_date: str) -> str:
    """Month-day stamp for release labels (e.g. 2026-04-16 → 0416)."""
    if release_date and len(release_date) >= 10:
        return f"{release_date[5:7]}{release_date[8:10]}"
    return "????"


def is_placeholder_engine_version(name: str) -> bool:
    """True for template fixVersions such as yyyymmdd-engine-none (also yyymmdd prefix)."""
    low = (name or "").strip().lower()
    return low.startswith("yyyymmdd") or low.startswith("yyymmdd")


def release_code_label(
    release_date: str,
    carriage_type: str | None = None,
    *,
    projected: bool = False,
) -> str:
    """Compact chart label: MMdd + suffix (IC in-cycle code, OC out-of-cycle code, ID/OD data, …)."""
    mmdd = release_date_mmdd(release_date)
    code = carriage_type_code(carriage_type, projected=projected)
    suffix = "*" if projected else ""
    return f"{mmdd}{code}{suffix}"


def release_row_code(row: dict[str, Any]) -> str:
    return release_code_label(
        str(row.get("releaseDate") or ""),
        row.get("carriageType"),
        projected=bool(row.get("projected")),
    )


def is_in_cycle_release(row: dict[str, Any]) -> bool:
    """True when this release defines an earned-SP window (in-cycle cadence, not OOC hotfix)."""
    if row.get("projected"):
        return True
    return row.get("carriageType") == IN_CYCLE_CARRIAGE


def _carriage_value(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return str(raw.get("value") or raw.get("name") or "") or None
    return str(raw) or None


def _search_engines(
    http: Any,
    jql: str,
    *,
    fields: list[str],
    page_size: int = 50,
) -> list[dict]:
    issues: list[dict] = []
    next_token: str | None = None
    while True:
        payload: dict[str, Any] = {
            "jql": jql,
            "maxResults": page_size,
            "fields": fields,
        }
        if next_token:
            payload["nextPageToken"] = next_token
        response = http.post_json("/rest/api/3/search/jql", payload)
        batch = response.get("issues") or []
        issues.extend(batch)
        if response.get("isLast", True) or not batch:
            break
        next_token = response.get("nextPageToken")
        if not next_token:
            break
    return issues


def fetch_pde_engine_releases(
    adapter: Any,
    *,
    engine_project_key: str = "PDE",
    engine_issue_type: str = "Engine",
    engine_in_cycle_filter: str = "smart-engine-in-cycle",
    carriage_type_field: str = CARRIAGE_TYPE_FIELD,
) -> tuple[list[dict[str, Any]], str | None]:
    """Load real PDE Engine releases and the current in-cycle fixVersion name."""
    fields = ["fixVersions", carriage_type_field, "status"]
    jql = (
        f"project = {engine_project_key} "
        f"AND issuetype = {engine_issue_type} "
        f"AND fixVersion is not EMPTY "
        f"ORDER BY fixVersion ASC"
    )
    issues = _search_engines(adapter.http, jql, fields=fields)

    by_name: dict[str, dict[str, Any]] = {}
    for issue in issues:
        carriage = _carriage_value(issue.get("fields", {}).get(carriage_type_field))
        status = (issue.get("fields", {}).get("status") or {}).get("name")
        for version in issue.get("fields", {}).get("fixVersions") or []:
            name = str(version.get("name") or "").strip()
            if not name or is_placeholder_engine_version(name):
                continue
            release_day = engine_date_from_fix_version(name)
            if release_day is None:
                continue
            by_name[name] = {
                "name": name,
                "releaseDate": release_day.isoformat(),
                "carriageType": carriage,
                "engineKey": issue.get("key"),
                "engineStatus": status,
                "projected": False,
            }

    in_cycle_name: str | None = None
    in_cycle_jql = (
        f"project = {engine_project_key} "
        f"AND issuetype = {engine_issue_type} "
        f"AND filter = {engine_in_cycle_filter} "
        f"ORDER BY updated DESC"
    )
    in_cycle = _search_engines(adapter.http, in_cycle_jql, fields=["fixVersions"], page_size=5)
    for issue in in_cycle:
        for version in issue.get("fields", {}).get("fixVersions") or []:
            name = str(version.get("name") or "").strip()
            if name and not is_placeholder_engine_version(name):
                in_cycle_name = name
                break
        if in_cycle_name:
            break

    real = sorted(by_name.values(), key=lambda row: row["releaseDate"])
    return real, in_cycle_name


def extend_engine_releases(
    real_releases: list[dict[str, Any]],
    *,
    in_cycle_name: str | None,
    quarter_start: date,
    quarter_end: date,
    cadence_days: int = RELEASE_CADENCE_DAYS,
) -> list[dict[str, Any]]:
    """Merge PDE real releases with biweekly forward projection from last in-cycle engine."""
    known_names = {row["name"] for row in real_releases if row.get("name")}
    known_dates = {date.fromisoformat(row["releaseDate"]) for row in real_releases if row.get("releaseDate")}

    in_quarter = [
        row
        for row in real_releases
        if quarter_start <= date.fromisoformat(row["releaseDate"]) <= quarter_end
    ]
    calendar: dict[str, dict[str, Any]] = {row["name"]: dict(row) for row in in_quarter}

    anchor_date: date | None = None
    if in_cycle_name and in_cycle_name in known_names:
        anchor_date = date.fromisoformat(next(row["releaseDate"] for row in real_releases if row["name"] == in_cycle_name))
    elif in_cycle_name:
        anchor_date = engine_date_from_fix_version(in_cycle_name)
    elif real_releases:
        anchor_date = date.fromisoformat(real_releases[-1]["releaseDate"])

    if anchor_date is not None:
        cursor = anchor_date
        while cursor <= quarter_end:
            cursor += timedelta(days=cadence_days)
            if cursor > quarter_end or cursor in known_dates:
                continue
            placeholder_name = f"projected-{cursor.isoformat()}-engine"
            calendar[placeholder_name] = {
                "name": placeholder_name,
                "releaseDate": cursor.isoformat(),
                "carriageType": None,
                "projected": True,
            }
            known_dates.add(cursor)

    return sorted(calendar.values(), key=lambda row: row["releaseDate"])


def build_quarter_engine_calendar(
    adapter: Any,
    *,
    quarter_start: date,
    quarter_end: date,
    engine_project_key: str = "PDE",
    engine_issue_type: str = "Engine",
    engine_in_cycle_filter: str = "smart-engine-in-cycle",
    carriage_type_field: str = CARRIAGE_TYPE_FIELD,
    cadence_days: int = RELEASE_CADENCE_DAYS,
) -> dict[str, Any]:
    """Fetch PDE engines and return quarter-scoped release calendar metadata."""
    real, in_cycle_name = fetch_pde_engine_releases(
        adapter,
        engine_project_key=engine_project_key,
        engine_issue_type=engine_issue_type,
        engine_in_cycle_filter=engine_in_cycle_filter,
        carriage_type_field=carriage_type_field,
    )
    in_cycle = extended = extend_engine_releases(
        real,
        in_cycle_name=in_cycle_name,
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        cadence_days=cadence_days,
    )
    return {
        "source": "pde-engines",
        "engineProjectKey": engine_project_key,
        "engineInCycleFilter": engine_in_cycle_filter,
        "inCycleFixVersion": in_cycle_name,
        "releaseCadenceDays": cadence_days,
        "realReleaseCount": len([row for row in in_cycle if not row.get("projected")]),
        "projectedReleaseCount": len([row for row in in_cycle if row.get("projected")]),
        "realReleases": real,
        "inCycleReleases": in_cycle,
    }
