#!/usr/bin/env python3
"""Per-squad deploy credit across closed sprints in the delivery quarter (EPCE-6745 Phase 3)."""

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
from artifact.delivery_health.gateway import ArtifactJiraGateway  # noqa: E402
from artifact.delivery_health.sprint_engine import (  # noqa: E402
    baseline_velocity,
    bind_delivery_health_config,
    deploy_credit_for_sprint,
    list_closed_sprints,
    sprint_days,
    sprint_squad_prefix,
    sprint_window,
)

from extensions.twoa_programme.delivery_health import load_delivery_health_config  # noqa: E402
from extensions.twoa_programme.quarterly_reporting import (  # noqa: E402
    credit_date_nz,
    load_quarterly_reporting_config,
    sprint_overlaps_quarter,
)
from scripts.quarterly.common import CONFIG_PATH, out_path  # noqa: E402


def _sprint_dates(sprint: dict) -> tuple:
    start_dt, end_dt = sprint_window(sprint)
    start = credit_date_nz(start_dt) if start_dt else None
    end = credit_date_nz(end_dt) if end_dt else None
    return start, end


def closed_sprints_in_quarter(
    jira: ArtifactJiraGateway,
    board_id: int,
    squad_slug: str,
    quarter,
    *,
    min_sprint_days: int,
) -> list[dict]:
    """Closed squad sprints whose window overlaps the delivery quarter."""
    closed = sorted(
        list_closed_sprints(jira, board_id),
        key=lambda s: s.get("endDate") or "",
    )
    matched: list[dict] = []
    for sprint in closed:
        if sprint_squad_prefix(sprint.get("name", "")) != squad_slug:
            continue
        if sprint_days(sprint) < min_sprint_days:
            continue
        start, end = _sprint_dates(sprint)
        if not sprint_overlaps_quarter(start, end, quarter):
            continue
        matched.append(sprint)
    return matched


def rollup_squad(
    jira: ArtifactJiraGateway,
    *,
    slug: str,
    label: str,
    board_id: int,
    quarter,
    min_sprint_days: int,
    baseline_count: int,
) -> dict:
    sprints = closed_sprints_in_quarter(
        jira, board_id, slug, quarter, min_sprint_days=min_sprint_days
    )
    sprint_rows: list[dict] = []
    total = 0.0
    for sprint in sprints:
        credit = deploy_credit_for_sprint(jira, sprint)
        total += credit
        start, end = _sprint_dates(sprint)
        sprint_rows.append(
            {
                "id": sprint.get("id"),
                "name": sprint.get("name"),
                "state": sprint.get("state"),
                "startDate": sprint.get("startDate"),
                "endDate": sprint.get("endDate"),
                "sprintStartNz": start.isoformat() if start else None,
                "sprintEndNz": end.isoformat() if end else None,
                "deployCredit": round(credit, 2),
            }
        )
    baseline = baseline_velocity(
        jira, board_id, slug, closed_count=baseline_count
    )
    return {
        "slug": slug,
        "label": label,
        "boardId": board_id,
        "sprintCount": len(sprint_rows),
        "totalDeployCredit": round(total, 2),
        "baselineVelocity": round(baseline, 2),
        "sprints": sprint_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deploy credit per squad across closed sprints in the delivery quarter."
    )
    parser.add_argument(
        "--squad",
        action="append",
        dest="squads",
        metavar="SLUG",
        help="Limit to squad slug(s); default all education-cloud squads.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write squad_velocity.json to output/quarterly/{slug}/.",
    )
    args = parser.parse_args(argv)

    qconfig = load_quarterly_reporting_config(CONFIG_PATH)
    dh_config = load_delivery_health_config()
    bind_delivery_health_config(dh_config)

    selected = args.squads or list(qconfig.education_cloud.squads)
    unknown = set(selected) - set(dh_config.squads)
    if unknown:
        raise SystemExit(f"Unknown squad slug(s): {sorted(unknown)}")

    profiles_dir = os.environ["ARTIFACT_PROFILES_DIR"]
    adapter = AtlassianAdapter.from_profile("atlassian", profiles_dir)
    jira = ArtifactJiraGateway(adapter.http)

    squad_results: dict[str, dict] = {}
    for slug in selected:
        squad = dh_config.squads[slug]
        print(f"Rolling up {slug} (board {squad.board_id})...", flush=True)
        squad_results[slug] = rollup_squad(
            jira,
            slug=slug,
            label=squad.label,
            board_id=squad.board_id,
            quarter=qconfig.quarter,
            min_sprint_days=dh_config.min_sprint_days,
            baseline_count=dh_config.baseline_closed_sprint_count,
        )

    total_credit = sum(row["totalDeployCredit"] for row in squad_results.values())
    result = {
        "storyKey": qconfig.story_key,
        "quarter": qconfig.quarter.slug,
        "quarterStart": qconfig.quarter.start_date.isoformat(),
        "quarterEnd": qconfig.quarter.end_date.isoformat(),
        "lane": "educationCloud",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "creditDefinition": "deploy_transition_in_sprint_window",
        "squads": squad_results,
        "totalDeployCredit": round(total_credit, 2),
    }

    text = json.dumps(result, indent=2)
    print(text)

    if args.write:
        path = out_path("squad_velocity.json")
        path.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
