#!/usr/bin/env python3
"""Fetch quarter planned SP from initiative sizing (EPCE-3897 goal = size-epics aggregate)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from artifact.atlassian import AtlassianAdapter  # noqa: E402

from extensions.twoa_programme.quarter_scope import planned_scope_jqls  # noqa: E402
from extensions.twoa_programme.quarterly_reporting import load_quarterly_reporting_config  # noqa: E402
from scripts.quarterly.common import CONFIG_PATH, out_path  # noqa: E402
from scripts.quarterly.jira_burn import (  # noqa: E402
    count_unpointed_stories_bugs_by_lane,
    education_cloud_squad_scope_breakdown,
    sum_story_points_by_exclusive_lane,
    sum_story_points_in_scope,
)
from scripts.quarterly.sizing_scope import SCOPE_NOTE, apply_scope  # noqa: E402


def fetch_initiative_goal(
    adapter: AtlassianAdapter,
    initiative_key: str,
    *,
    limit: int = 100,
    max_epics: int = 50,
) -> dict:
    """Size all epics under initiative; return scoped Story/Spike/Bug SP total."""
    raw = adapter.jira_size_epics(initiative_key, limit=limit, max_epics=max_epics)
    scoped = apply_scope(raw)
    return {
        "initiativeKey": initiative_key,
        "initiativeUrl": f"https://twoa.atlassian.net/browse/{initiative_key}",
        "source": "artifact size-epics + sizing_scope (Story, Spike, Bug; excludes Rejected)",
        "scopeNote": SCOPE_NOTE,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "totalStoryPoints": scoped["total_story_points"],
        "totalChildren": scoped["total_children"],
        "totalEpics": scoped["total_epics"],
        "missingStoryPoints": scoped["missing_story_points"],
        "jqlUsed": scoped.get("jql_used"),
        "sizing": scoped,
    }


def fetch_scope_breakdown(adapter: AtlassianAdapter, config, sp_field: str) -> dict:
    """Planned SP sums for exclusive global quarter slices (includes Spike)."""
    jqls = planned_scope_jqls(quarter_filter=config.scope.quarter_filter)
    aliases = adapter._resolve_field_aliases()
    delivery_squad_field = aliases.get("Delivery Squad") or "customfield_11102"
    change_types_field = aliases.get("Change Types") or "customfield_10079"
    platform_field = aliases.get("Platform") or "customfield_10120"
    breakdown = sum_story_points_by_exclusive_lane(
        adapter,
        config.scope.global_scope_jql,
        sp_field,
        delivery_squad_field=delivery_squad_field,
        change_types_field=change_types_field,
        platform_field=platform_field,
        lane_jqls=jqls,
    )
    breakdown["inGlobalQuarter"] = {
        "jql": config.scope.global_scope_jql,
        **sum_story_points_in_scope(adapter, config.scope.global_scope_jql, sp_field),
    }
    sp_jql_name = "Story Points"
    for alias, field_id in aliases.items():
        if field_id == sp_field:
            sp_jql_name = alias
            break
    breakdown["unpointedStoriesBugs"] = count_unpointed_stories_bugs_by_lane(
        adapter,
        config.scope.global_burn_jql,
        sp_field,
        delivery_squad_field=delivery_squad_field,
        change_types_field=change_types_field,
        platform_field=platform_field,
        lane_jqls=jqls,
        story_points_jql_name=sp_jql_name,
    )
    breakdown["educationCloudSquads"] = education_cloud_squad_scope_breakdown(
        adapter,
        sp_field,
        quarter_filter=config.scope.quarter_filter,
        global_scope_jql=config.scope.global_scope_jql,
        global_burn_jql=config.scope.global_burn_jql,
        delivery_squad_field=delivery_squad_field,
        change_types_field=change_types_field,
        platform_field=platform_field,
        story_points_jql_name=sp_jql_name,
    )
    return breakdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch quarter goal SP from initiative (same aggregate as Smartificer sizing)."
    )
    parser.add_argument("--limit", type=int, default=100, help="Max children per epic.")
    parser.add_argument("--max-epics", type=int, default=50, help="Max epics under initiative.")
    parser.add_argument(
        "--skip-scope-breakdown",
        action="store_true",
        help="Skip per-lane planned SP sums in global quarter scope.",
    )
    parser.add_argument("--write", action="store_true", help="Write quarter-goal.json.")
    args = parser.parse_args(argv)

    config = load_quarterly_reporting_config(CONFIG_PATH)
    initiative = config.goal.sizing_source_initiative or config.quarter.initiative_key
    profiles_dir = os.environ["ARTIFACT_PROFILES_DIR"]
    adapter = AtlassianAdapter.from_profile("atlassian", profiles_dir)
    aliases = adapter._resolve_field_aliases()
    sp_field = aliases.get("Story Points") or "customfield_10026"

    payload = fetch_initiative_goal(
        adapter,
        initiative,
        limit=args.limit,
        max_epics=args.max_epics,
    )
    output = {
        "quarter": config.quarter.slug,
        "plannedStoryPoints": payload["totalStoryPoints"],
        **{k: v for k, v in payload.items() if k != "sizing"},
    }
    if not args.skip_scope_breakdown:
        scope_breakdown = fetch_scope_breakdown(adapter, config, sp_field)
        output["plannedStoryPointsByScope"] = scope_breakdown
        unpointed = scope_breakdown.get("unpointedStoriesBugs") or {}
        if unpointed:
            output["unpointedStoriesBugs"] = unpointed.get("total")
            output["unpointedStoriesBugsJql"] = unpointed.get("jql")
            if keys := unpointed.get("issueKeys"):
                output["unpointedStoriesBugsIssueKeys"] = keys

    text = json.dumps(output, indent=2)
    print(text)

    if args.write:
        path = out_path("quarter-goal.json")
        path.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
