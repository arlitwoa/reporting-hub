#!/usr/bin/env python3
"""Project sprint/PRD calendar to quarter start and claim deploy-earned SP per period."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from artifact.atlassian import AtlassianAdapter  # noqa: E402

from extensions.twoa_programme.burn_allocation_scope import enrich_in_progress_scope  # noqa: E402
from extensions.twoa_programme.quarterly_reporting import (  # noqa: E402
    NZ_TZ,
    load_quarterly_reporting_config,
)
from extensions.twoa_programme.release_plan_calendar import allocate_burn_to_calendar  # noqa: E402
from scripts.quarterly.common import CONFIG_PATH, out_path  # noqa: E402


def _report_as_of(output_dir: Path) -> date:
    status_path = output_dir / "quarter-status.json"
    if status_path.is_file():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        raw = status.get("asOf")
        if raw:
            return date.fromisoformat(str(raw)[:10])
    from datetime import datetime

    return datetime.now(NZ_TZ).date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extend Release Plan cadence to quarter start and allocate burn SP."
    )
    parser.add_argument("--write", action="store_true", help="Write burn-allocation.json")
    parser.add_argument(
        "--skip-scope",
        action="store_true",
        help="Skip Jira scoped SP/issue fetch for in-progress sprint and active release.",
    )
    args = parser.parse_args(argv)

    config = load_quarterly_reporting_config(CONFIG_PATH)
    output_dir = config.output_root(_REPO_ROOT)
    plan_path = output_dir / "release-plan-metadata.json"
    burn_path = output_dir / "deploy_burn.json"
    if not plan_path.is_file():
        raise SystemExit(f"Missing {plan_path}; run import_release_plan.py --write first.")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    burn = json.loads(burn_path.read_text(encoding="utf-8")) if burn_path.is_file() else None

    result = allocate_burn_to_calendar(
        plan,
        burn,
        quarter_start=config.quarter.start_date,
        quarter_end=config.quarter.end_date,
    )
    result["quarter"] = config.quarter.slug

    if not args.skip_scope:
        adapter = AtlassianAdapter.from_profile("atlassian", os.environ["ARTIFACT_PROFILES_DIR"])
        aliases = adapter._resolve_field_aliases()
        story_points_field = aliases.get("Story Points") or "customfield_10026"
        enrich_in_progress_scope(
            result,
            adapter=adapter,
            global_scope_jql=config.scope.global_scope_jql,
            global_burn_jql=config.scope.global_burn_jql,
            story_points_field=story_points_field,
            as_of=_report_as_of(output_dir),
        )

    text = json.dumps(result, indent=2)
    print(text)

    if args.write:
        extended_plan = {
            **plan,
            "sprints": [
                {k: v for k, v in row.items() if k not in ("claimedStoryPoints", "events")}
                for row in result["sprints"]
            ],
            "extended": True,
        }
        out_path("release-plan-metadata.json").write_text(
            json.dumps(extended_plan, indent=2) + "\n",
            encoding="utf-8",
        )
        path = out_path("burn-allocation.json")
        path.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {path}", file=sys.stderr)
        print("Updated release-plan-metadata.json with extended calendar", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
