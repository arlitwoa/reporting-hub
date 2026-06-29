#!/usr/bin/env python3
"""Build filtered SEF Test Plan Block Gantt HTML snapshots for GitHub Pages."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from artifact.atlassian import AtlassianAdapter  # noqa: E402

from extensions.twoa_programme.quarterly_reporting import NZ_TZ  # noqa: E402
from extensions.twoa_programme.sef_project_plan_timeline import build_sef_project_plan_report_html  # noqa: E402
from extensions.twoa_programme.github_pages_nav import programme_report_breadcrumbs, SEF_PROGRAMME_ID, SEF_PROGRAMME_TITLE  # noqa: E402
from extensions.twoa_programme.sef_test_plan_manifest import (  # noqa: E402
    default_manifest_path,
    get_test_plan,
    list_test_plans,
    load_project_plan_manifest,
)
from extensions.twoa_programme.sef_test_plan_schedule import fetch_test_plan_timeline_payload  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SEF Test Plan Block Gantt HTML reports.")
    parser.add_argument("--write", action="store_true", help="Write HTML under docs/sef/plans/.")
    parser.add_argument("--slug", action="append", help="Test plan slug (repeatable). Default: all.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Override sef-project-plan-blocks.json path.",
    )
    args = parser.parse_args(argv)

    manifest_path = args.manifest or default_manifest_path(_REPO_ROOT)
    manifest = load_project_plan_manifest(manifest_path)
    slugs = args.slug or [plan.slug for plan in list_test_plans(manifest)]
    if not slugs:
        print("No test plans in manifest.", file=sys.stderr)
        return 1

    profiles_dir = os.environ.get("ARTIFACT_PROFILES_DIR", str(_REPO_ROOT / "config" / "profiles"))
    adapter = AtlassianAdapter.from_profile("atlassian", profiles_dir=profiles_dir)
    generated = datetime.now(NZ_TZ).strftime("%d %b %Y %H:%M %Z")

    wrote = 0
    for slug in slugs:
        plan = get_test_plan(manifest, slug)
        if plan is None:
            print(f"Unknown test plan slug: {slug}", file=sys.stderr)
            return 1
        if not plan.reporting_hub:
            print(f"Skipping {slug}: no reportingHub.sitePath", file=sys.stderr)
            continue
        payload = fetch_test_plan_timeline_payload(adapter, plan)
        page_title = str(payload.get("pageTitle") or plan.title)
        breadcrumb = programme_report_breadcrumbs(
            publish_path=plan.reporting_hub.site_path,
            programme_id=SEF_PROGRAMME_ID,
            programme_title=SEF_PROGRAMME_TITLE,
            report_title=page_title,
        )
        html_doc = build_sef_project_plan_report_html(
            payload,
            generated_on=generated,
            page_title=page_title,
            breadcrumb_nav=breadcrumb,
        )
        pages_path = _REPO_ROOT / "docs" / plan.reporting_hub.site_path
        if args.write:
            pages_path.parent.mkdir(parents=True, exist_ok=True)
            pages_path.write_text(html_doc, encoding="utf-8")
            print(f"Wrote {pages_path}", file=sys.stderr)
            wrote += 1
        else:
            print(html_doc)

    if args.write and wrote == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
