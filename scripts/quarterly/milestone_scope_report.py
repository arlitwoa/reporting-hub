#!/usr/bin/env python3
"""Build milestone timeline and burn-up HTML report from JSON artifacts."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from artifact.atlassian import AtlassianAdapter  # noqa: E402

from extensions.twoa_programme.milestone_burn_up import (  # noqa: E402
    build_milestone_burn_payload,
    build_milestone_scope_report_html,
    load_deploy_burn_payload,
)
from extensions.twoa_programme.github_pages_nav import epc_report_breadcrumbs  # noqa: E402
from extensions.twoa_programme.milestone_report_scope import (  # noqa: E402
    milestone_report_page_title,
    report_window_dates,
)
from extensions.twoa_programme.milestone_timeline import (  # noqa: E402
    default_milestone_timeline_path,
    load_milestone_timeline_calendar,
    load_milestone_timeline_payload,
)
from extensions.twoa_programme.quarterly_reporting import (  # noqa: E402
    NZ_TZ,
    load_quarterly_reporting_config,
    resolve_chart_as_of,
)
from scripts.quarterly.common import CONFIG_PATH, out_path  # noqa: E402
from scripts.quarterly.jira_burn import load_deploy_statuses, load_done_statuses  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build milestone timeline and burn-up HTML report."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write milestone-scope-chart.html to output/quarterly/{slug}/.",
    )
    parser.add_argument("--input", type=Path, default=None, help="Override timeline JSON path.")
    parser.add_argument("--output", type=Path, default=None, help="Override output HTML path.")
    args = parser.parse_args(argv)

    config = load_quarterly_reporting_config(CONFIG_PATH)
    output_dir = config.output_root(_REPO_ROOT)
    artifact_path = args.input or default_milestone_timeline_path()
    timeline_payload = load_milestone_timeline_payload(artifact_path)
    if not timeline_payload:
        print(f"No artifact at {artifact_path}. Run fetch_milestone_timeline.py --write.", file=sys.stderr)
        return 1

    report_start, report_end = report_window_dates(timeline_payload)
    if report_start is None or report_end is None:
        report_start = config.quarter.start_date
        report_end = config.quarter.end_date

    deploy_burn = load_deploy_burn_payload(output_dir)
    if not deploy_burn:
        print(
            f"No deploy_burn.json in {output_dir}. Run deploy_burn.py --write for burn-up charts.",
            file=sys.stderr,
        )
        return 1

    adapter = AtlassianAdapter.from_profile("atlassian", os.environ["ARTIFACT_PROFILES_DIR"])
    aliases = adapter._resolve_field_aliases()
    sp_field = aliases.get("Story Points") or "customfield_10026"
    deploy_statuses = load_deploy_statuses()
    done_statuses = load_done_statuses(
        velocity_credit_status=config.data_migration.velocity_credit_status,
    )
    burn_payload = build_milestone_burn_payload(
        timeline_payload,
        deploy_burn,
        adapter=adapter,
        quarter=config.quarter,
        sp_field=sp_field,
        deploy_statuses=deploy_statuses,
        done_statuses=done_statuses,
        credit_cache_path=out_path("deploy_burn_cache.json"),
    )

    sprint_bands, releases, quarter_start, quarter_end = load_milestone_timeline_calendar(
        output_dir,
        quarter_start=report_start,
        quarter_end=report_end,
    )
    chart_as_of = resolve_chart_as_of(None, quarter_end=report_end.isoformat())

    generated = datetime.now(NZ_TZ).strftime("%d %b %Y %H:%M %Z")
    title = milestone_report_page_title(timeline_payload)
    breadcrumb = epc_report_breadcrumbs(
        publish_path="quarter/milestone.html",
        report_title=title,
    )
    html_doc = build_milestone_scope_report_html(
        timeline_payload,
        burn_payload,
        generated_on=generated,
        page_title=title,
        sprint_bands=sprint_bands,
        releases=releases,
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        chart_as_of=chart_as_of,
        breadcrumb_nav=breadcrumb,
    )

    out_file = args.output or out_path("milestone-scope-chart.html")
    if args.write or args.output:
        out_file.write_text(html_doc, encoding="utf-8")
        print(f"Wrote {out_file}", file=sys.stderr)
    else:
        print(html_doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
