#!/usr/bin/env python3
"""Deploy / Done burn by lane for the current delivery quarter (EPCE-6745 Phase 2)."""

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
from extensions.twoa_programme.quarterly_reporting import (  # noqa: E402
    aggregate_daily_burn,
    load_quarterly_reporting_config,
)
from scripts.quarterly.common import CONFIG_PATH, out_path  # noqa: E402
from scripts.quarterly.jira_burn import (  # noqa: E402
    burn_global_with_lane_split,
    burn_lane,
    load_deploy_statuses,
    load_done_statuses,
)

LANE_CHOICES = ("educationCloud", "integration", "dataMigration", "unassigned")


def _lane_specs(config) -> dict[str, dict]:
    return {
        "educationCloud": {
            "label": config.education_cloud.label,
            "scope_jql": config.education_cloud.scope_jql,
        },
        "integration": {
            "label": config.integration.label,
            "scope_jql": config.integration.scope_jql,
        },
        "dataMigration": {
            "label": config.data_migration.label,
            "scope_jql": config.data_migration.scope_jql,
        },
        "unassigned": {
            "label": config.unassigned.label,
            "scope_jql": config.unassigned.scope_jql,
        },
    }


def _combined_daily(events: list[dict]) -> list[dict]:
    daily, _ = aggregate_daily_burn(events)
    return daily


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Earned SP by lane — credit at first deploy-gate transition, "
            "else first Done/Drive-mapped transition."
        )
    )
    parser.add_argument(
        "--lane",
        choices=[*LANE_CHOICES, "all"],
        default="all",
        help="Lane to scan (default: all).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max issues with SP per lane (dev / smoke test).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write deploy_burn.json to output/quarterly/{slug}/.",
    )
    parser.add_argument(
        "--update-quarter-status",
        action="store_true",
        help="Also write quarter-status.json using combined earned SP.",
    )
    args = parser.parse_args(argv)

    config = load_quarterly_reporting_config(CONFIG_PATH)
    profiles_dir = os.environ["ARTIFACT_PROFILES_DIR"]
    adapter = AtlassianAdapter.from_profile("atlassian", profiles_dir)
    aliases = adapter._resolve_field_aliases()
    sp_field = aliases.get("Story Points") or "customfield_10026"
    delivery_squad_field = aliases.get("Delivery Squad") or "customfield_11102"
    change_types_field = aliases.get("Change Types") or "customfield_10079"

    specs = _lane_specs(config)
    selected = LANE_CHOICES if args.lane == "all" else (args.lane,)
    cache_path = out_path("deploy_burn_cache.json")
    deploy_statuses = load_deploy_statuses()
    done_statuses = load_done_statuses(
        velocity_credit_status=config.data_migration.velocity_credit_status,
    )

    lane_results: dict[str, dict] = {}
    scan_global = args.lane == "all"
    if scan_global:
        print(f"Scanning global (Python lane split): {config.scope.global_burn_jql}", flush=True)
        global_result, lane_results = burn_global_with_lane_split(
            adapter,
            global_scope_jql=config.scope.global_burn_jql,
            quarter=config.quarter,
            sp_field=sp_field,
            lane_specs=specs,
            cache_path=cache_path,
            delivery_squad_field=delivery_squad_field,
            change_types_field=change_types_field,
            platform_field=aliases.get("Platform") or "customfield_10120",
            limit=args.limit,
            deploy_statuses=deploy_statuses,
            done_statuses=done_statuses,
            selected_lanes=selected,
        )
    else:
        global_result = None
        spec = specs[args.lane]
        print(f"Scanning {args.lane}: {spec['scope_jql']}", flush=True)
        lane_results[args.lane] = burn_lane(
            adapter,
            lane_key=args.lane,
            label=spec["label"],
            scope_jql=spec["scope_jql"],
            quarter=config.quarter,
            sp_field=sp_field,
            deploy_statuses=deploy_statuses,
            done_statuses=done_statuses,
            cache_path=cache_path,
            limit=args.limit,
        )

    if global_result is not None:
        total_earned = float(global_result["totalStoryPointsEarned"])
        combined_daily = global_result.get("daily") or []
    else:
        total_earned = sum(lane["totalStoryPointsEarned"] for lane in lane_results.values())
        combined_daily = _combined_daily(
            [event for lane in lane_results.values() for event in lane.get("events") or []]
        )

    lane_breakdown_sum = round(
        sum(float(lane_results[key]["totalStoryPointsEarned"]) for key in LANE_CHOICES if key in lane_results),
        2,
    )
    if global_result is not None and abs(lane_breakdown_sum - total_earned) > 0.01:
        print(
            f"Warning: lane breakdown sum ({lane_breakdown_sum}) != global earned ({total_earned}); "
            "check scope partition.",
            file=sys.stderr,
        )
    scope_jqls = planned_scope_jqls(quarter_filter=config.scope.quarter_filter)

    result = {
        "storyKey": config.story_key,
        "quarter": config.quarter.slug,
        "quarterStart": config.quarter.start_date.isoformat(),
        "quarterEnd": config.quarter.end_date.isoformat(),
        "initiativeKey": config.quarter.initiative_key,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "storyPointsField": sp_field,
        "creditMode": "deploy_or_done",
        "deployStatuses": sorted(deploy_statuses),
        "doneStatuses": sorted(done_statuses),
        "scope": {
            "quarterFilter": config.scope.quarter_filter,
            "unassignedFilter": config.scope.unassigned_filter,
            "overlapPolicy": config.scope.overlap_policy,
            "globalBurnJql": config.scope.global_burn_jql,
            "globalScopeJql": config.scope.global_scope_jql,
            "unassignedScopeJql": config.scope.unassigned_scope_jql,
            "plannedScopeJql": scope_jqls,
        },
        "global": global_result,
        "lanes": lane_results,
        "totalStoryPointsEarned": total_earned,
        "laneBreakdownSum": round(lane_breakdown_sum, 2),
        "combinedDaily": combined_daily,
    }

    text = json.dumps(result, indent=2)
    print(text)

    if args.write or args.update_quarter_status:
        burn_path = out_path("deploy_burn.json")
        burn_path.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {burn_path}", file=sys.stderr)

    if args.update_quarter_status:
        from scripts.quarterly import quarter_status  # noqa: E402

        quarter_status.main(["--from-burn", "--write"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
