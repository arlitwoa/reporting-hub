#!/usr/bin/env python3
"""Emit quarter burn/velocity tracking scaffold vs end-of-quarter goal (EPCE-6745)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from extensions.twoa_programme.quarterly_reporting import load_quarterly_reporting_config  # noqa: E402

from scripts.quarterly.common import CONFIG_PATH, out_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Quarter progress snapshot: elapsed time, ideal burn, goal variance."
    )
    parser.add_argument(
        "--earned-sp",
        type=float,
        default=None,
        help="Deploy-earned story points to date (omit for scaffold with zero earned).",
    )
    parser.add_argument(
        "--from-burn",
        action="store_true",
        help="Read earned SP from output/quarterly/{slug}/deploy_burn.json.",
    )
    parser.add_argument(
        "--from-goal",
        action="store_true",
        help="Read planned SP from output/quarterly/{slug}/quarter-goal.json (size-epics on initiative).",
    )
    parser.add_argument(
        "--planned-sp",
        type=float,
        default=None,
        help="Override quarterGoal.plannedStoryPoints for what-if runs.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write JSON snapshot to output/quarterly/{slug}/quarter-status.json",
    )
    args = parser.parse_args(argv)

    config = load_quarterly_reporting_config(CONFIG_PATH)

    from dataclasses import replace

    goal_path = out_path("quarter-goal.json")
    if args.planned_sp is not None:
        config = replace(
            config,
            goal=replace(config.goal, planned_story_points=args.planned_sp),
        )
    elif args.from_goal or goal_path.is_file():
        if not goal_path.is_file():
            print(f"Missing {goal_path}; run fetch_quarter_goal.py --write first.", file=sys.stderr)
            return 1
        goal = json.loads(goal_path.read_text(encoding="utf-8"))
        if goal.get("plannedStoryPoints") is not None:
            config = replace(
                config,
                goal=replace(
                    config.goal,
                    planned_story_points=float(goal["plannedStoryPoints"]),
                ),
            )

    burn: dict | None = None
    earned = args.earned_sp
    if args.from_burn:
        burn_path = out_path("deploy_burn.json")
        if not burn_path.exists():
            print(f"Missing {burn_path}; run deploy_burn.py --write first.", file=sys.stderr)
            return 1
        burn = json.loads(burn_path.read_text(encoding="utf-8"))
        earned = float(burn.get("totalStoryPointsEarned") or 0.0)
    elif earned is None:
        earned = 0.0

    snapshot = config.tracking_snapshot(earned_story_points=earned)
    snapshot["lanes"] = {
        "educationCloud": {
            "label": config.education_cloud.label,
            "squads": list(config.education_cloud.squads),
            "doneDefinition": config.education_cloud.done_definition,
        },
        "integration": {
            "label": config.integration.label,
            "boardId": config.integration.board_id,
            "doneDefinition": config.integration.done_definition,
        },
        "dataMigration": {
            "label": config.data_migration.label,
            "boardId": config.data_migration.board_id,
            "doneDefinition": config.data_migration.done_definition,
        },
        "unassigned": {
            "label": config.unassigned.label,
            "doneDefinition": config.unassigned.done_definition,
            "filter": config.scope.unassigned_filter,
        },
    }
    if burn is not None:
        snapshot["burnByLane"] = {
            lane: burn["lanes"][lane]["totalStoryPointsEarned"]
            for lane in burn.get("lanes", {})
        }
        snapshot["scopeCoverage"] = {
            "globalEarnedStoryPoints": float(burn.get("totalStoryPointsEarned") or 0.0),
            "laneBreakdownSum": burn.get("laneBreakdownSum"),
            "quarterFilter": (burn.get("scope") or {}).get("quarterFilter"),
            "unassignedFilter": (burn.get("scope") or {}).get("unassignedFilter"),
            "overlapPolicy": (burn.get("scope") or {}).get("overlapPolicy"),
        }
        if "unassigned" in burn.get("lanes", {}):
            snapshot["scopeCoverage"]["unassignedEarnedStoryPoints"] = burn["lanes"]["unassigned"][
                "totalStoryPointsEarned"
            ]
    snapshot["storyKey"] = config.story_key

    text = json.dumps(snapshot, indent=2)
    print(text)

    if args.write:
        path = out_path("quarter-status.json")
        path.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
