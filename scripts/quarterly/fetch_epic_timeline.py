#!/usr/bin/env python3
"""Fetch epic timeline rows for quarterly dashboard (target engine release on quarter calendar)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from artifact.atlassian import AtlassianAdapter  # noqa: E402

from extensions.twoa_programme.epic_timeline import (  # noqa: E402
    build_release_date_lookup,
    classify_epic_ec_squad,
    classify_epic_lane,
    resolve_epic_window,
    summarize_epic_children,
)
from extensions.twoa_programme.jira_binding_loader import load_jira_binding  # noqa: E402
from extensions.twoa_programme.milestone_scope_chart import rollup_milestone_epic_phases  # noqa: E402
from extensions.twoa_programme.quarter_scope import (  # noqa: E402
    global_scope_jql,
    issue_excluded_from_analysis,
)
from extensions.twoa_programme.quarterly_reporting import load_quarterly_reporting_config  # noqa: E402
from scripts.quarterly.common import CONFIG_PATH, SKIP_ISSUE_TYPES, out_path  # noqa: E402
from scripts.quarterly.jira_burn import load_deploy_statuses, load_done_statuses  # noqa: E402

EPIC_FIELDS = [
    "summary",
    "status",
    "created",
    "fixVersions",
    "issuetype",
    "issuelinks",
]


def _issue_type_name(issue: dict) -> str:
    return ((issue.get("fields") or {}).get("issuetype") or {}).get("name") or ""


def _skip_analysis_issue(issue: dict) -> bool:
    itype = _issue_type_name(issue)
    return itype in SKIP_ISSUE_TYPES or issue_excluded_from_analysis(issue)


def _search_all(adapter: AtlassianAdapter, jql: str, fields: list[str]) -> list[dict]:
    issues: list[dict] = []
    token: str | None = None
    while True:
        body: dict = {"jql": jql, "maxResults": 100, "fields": fields}
        if token:
            body["nextPageToken"] = token
        data = adapter.http.post_json("/rest/api/3/search/jql", body=body)
        batch = data.get("issues") or []
        issues.extend(batch)
        if data.get("isLast", True) or not batch:
            break
        token = data.get("nextPageToken")
        if not token:
            break
    return issues


def _fix_version_names(fields: dict) -> list[str]:
    return [str(v.get("name")) for v in (fields.get("fixVersions") or []) if v.get("name")]


def fetch_epic_timeline(
    adapter: AtlassianAdapter,
    *,
    initiative_key: str,
    quarter_start: date,
    quarter_end: date,
    release_lookup: dict[str, date],
    quarter_filter: str,
    delivery_squad_field: str,
    change_types_field: str,
    platform_field: str,
    story_points_field: str,
    deploy_statuses: set[str],
    done_statuses: set[str],
) -> dict:
    epic_jql = f"project = EPCE AND issuetype = Epic AND parent = {initiative_key} ORDER BY key ASC"
    epics = _search_all(adapter, epic_jql, EPIC_FIELDS + [delivery_squad_field, change_types_field, platform_field])
    epic_keys = [e["key"] for e in epics]
    child_fix: dict[str, list[str]] = defaultdict(list)
    children_by_epic: dict[str, list[dict]] = defaultdict(list)

    if epic_keys:
        keys_csv = ", ".join(epic_keys)
        child_jql = f"{global_scope_jql(quarter_filter=quarter_filter)} AND parent in ({keys_csv})"
        child_fields = [
            "fixVersions",
            "parent",
            "issuetype",
            "status",
            story_points_field,
            delivery_squad_field,
            change_types_field,
            platform_field,
            "issuelinks",
        ]
        for issue in _search_all(adapter, child_jql, child_fields):
            parent = (issue.get("fields") or {}).get("parent") or {}
            parent_key = parent.get("key")
            if not parent_key:
                continue
            child_fix[parent_key].extend(_fix_version_names(issue.get("fields") or {}))
            children_by_epic[parent_key].append(issue)

    rows: list[dict] = []
    for issue in epics:
        key = issue["key"]
        fields = issue.get("fields") or {}
        status = (fields.get("status") or {}).get("name") or ""
        created = (fields.get("created") or "")[:10]
        epic_fvs = _fix_version_names(fields)
        start, end, fix_version = resolve_epic_window(
            created=created,
            epic_fix_versions=epic_fvs,
            child_fix_versions=child_fix.get(key, []),
            release_lookup=release_lookup,
            quarter_start=quarter_start,
            quarter_end=quarter_end,
        )
        lane = classify_epic_lane(
            issue,
            children_by_epic.get(key, []),
            delivery_squad_field=delivery_squad_field,
            change_types_field=change_types_field,
            platform_field=platform_field,
            story_points_field=story_points_field,
            skip_issue=_skip_analysis_issue,
        )
        ec_squad = None
        if lane == "educationCloud":
            ec_squad = classify_epic_ec_squad(
                issue,
                children_by_epic.get(key, []),
                delivery_squad_field=delivery_squad_field,
                change_types_field=change_types_field,
                platform_field=platform_field,
                story_points_field=story_points_field,
                skip_issue=_skip_analysis_issue,
            )
        row = {
            "key": key,
            "summary": fields.get("summary") or "",
            "status": status,
            "created": created,
            "lane": lane,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "fixVersion": fix_version,
            "releaseDate": end.isoformat() if fix_version else None,
        }
        if ec_squad:
            row["ecSquad"] = ec_squad
        child_metrics = summarize_epic_children(
            children_by_epic.get(key, []),
            story_points_field=story_points_field,
            change_types_field=change_types_field,
            delivery_squad_field=delivery_squad_field,
            deploy_statuses=deploy_statuses,
            done_statuses=done_statuses,
            skip_issue=_skip_analysis_issue,
        )
        row.update(child_metrics)
        rows.append(row)

    jira_binding = load_jira_binding()
    if jira_binding is not None and epic_keys:
        all_children: list[dict] = []
        for child_list in children_by_epic.values():
            all_children.extend(child_list)
        epic_rollups = rollup_milestone_epic_phases(
            all_children,
            epic_keys=epic_keys,
            delivery_squad_field=delivery_squad_field,
            change_types_field=change_types_field,
            platform_field=platform_field,
            story_points_field=story_points_field,
            binding=jira_binding,
            skip_issue=_skip_analysis_issue,
        )
        for row in rows:
            rollup = epic_rollups.get(str(row["key"]) or "", {})
            if float(rollup.get("totalWeight") or 0) > 0:
                row["scopeRollup"] = rollup

    return {
        "initiativeKey": initiative_key,
        "quarterStart": quarter_start.isoformat(),
        "quarterEnd": quarter_end.isoformat(),
        "lanePartition": "python_exclusive (same as Story Points Achieved by Lane)",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "epicCount": len(rows),
        "epics": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch epic timeline for quarterly dashboard.")
    parser.add_argument("--write", action="store_true", help="Write epic-timeline.json.")
    args = parser.parse_args(argv)

    config = load_quarterly_reporting_config(CONFIG_PATH)
    initiative = config.quarter.initiative_key
    quarter_start = config.quarter.start_date
    quarter_end = config.quarter.end_date

    output_dir = config.output_root(_REPO_ROOT)
    releases: list = []
    release_plan: dict = {}
    releases_path = output_dir / "engine-releases.json"
    plan_path = output_dir / "release-plan-metadata.json"
    alloc_path = output_dir / "burn-allocation.json"
    if releases_path.is_file():
        releases = json.loads(releases_path.read_text(encoding="utf-8"))
    if plan_path.is_file():
        release_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    elif alloc_path.is_file():
        allocation = json.loads(alloc_path.read_text(encoding="utf-8"))
        release_plan = {"inCycleReleases": allocation.get("inCycleReleases") or []}

    release_lookup = build_release_date_lookup(releases, release_plan)
    deploy_statuses = load_deploy_statuses()
    done_statuses = load_done_statuses(
        velocity_credit_status=config.data_migration.velocity_credit_status,
    )

    adapter = AtlassianAdapter.from_profile("atlassian", os.environ["ARTIFACT_PROFILES_DIR"])
    aliases = adapter._resolve_field_aliases()
    delivery_squad_field = aliases.get("Delivery Squad") or "customfield_11102"
    change_types_field = aliases.get("Change Types") or "customfield_10079"
    platform_field = aliases.get("Platform") or "customfield_10120"
    story_points_field = aliases.get("Story Points") or "customfield_10026"

    payload = fetch_epic_timeline(
        adapter,
        initiative_key=initiative,
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        release_lookup=release_lookup,
        quarter_filter=config.scope.quarter_filter,
        delivery_squad_field=delivery_squad_field,
        change_types_field=change_types_field,
        platform_field=platform_field,
        story_points_field=story_points_field,
        deploy_statuses=deploy_statuses,
        done_statuses=done_statuses,
    )

    text = json.dumps(payload, indent=2)
    print(text)
    if args.write:
        path = out_path("epic-timeline.json")
        path.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
