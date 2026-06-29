#!/usr/bin/env python3
"""Publish quarterly dashboard HTML for GitHub Pages (static snapshot)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from artifact.atlassian import AtlassianAdapter  # noqa: E402

from extensions.twoa_programme.delivery_health import load_delivery_health_config  # noqa: E402
from extensions.twoa_programme.github_pages_publish import write_pages_snapshot  # noqa: E402
from extensions.twoa_programme.pde_engine_releases import build_quarter_engine_calendar  # noqa: E402
from extensions.twoa_programme.quarterly_dashboard import (  # noqa: E402
    build_dashboard_html,
    load_artifacts,
)
from extensions.twoa_programme.quarterly_reporting import (  # noqa: E402
    NZ_TZ,
    load_quarterly_reporting_config,
)
from extensions.twoa_programme.github_pages_nav import epc_report_breadcrumbs  # noqa: E402
from scripts.quarterly.common import CONFIG_PATH, out_path  # noqa: E402


def build_dashboard_document(config, *, repo_root: Path) -> str:
    """Build self-contained HTML from JSON artifacts in the quarter output folder."""
    output_dir = config.output_root(repo_root)
    payload = load_artifacts(output_dir)

    if "releases" not in payload and os.environ.get("ARTIFACT_PROFILES_DIR"):
        try:
            adapter = AtlassianAdapter.from_profile(
                "atlassian", profiles_dir=os.environ["ARTIFACT_PROFILES_DIR"]
            )
            health = load_delivery_health_config()
            risk = health.dev_done_risk
            if risk is not None:
                calendar = build_quarter_engine_calendar(
                    adapter,
                    quarter_start=config.quarter.start_date,
                    quarter_end=config.quarter.end_date,
                    engine_project_key=risk.engine_project_key,
                    engine_issue_type=risk.engine_issue_type,
                    engine_in_cycle_filter=risk.engine_in_cycle_filter,
                )
                payload["releases"] = calendar["inCycleReleases"]
            cache = output_dir / "engine-releases.json"
            cache.write_text(json.dumps(payload.get("releases", []), indent=2) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: could not fetch engine releases: {exc}", file=sys.stderr)

    generated = datetime.now(NZ_TZ).strftime("%d %b %Y %H:%M %Z")
    title = (
        config.confluence.page_title
        if config.confluence
        else f"{config.quarter.label.split('(')[0].strip()} | Quarterly Dashboard"
    )
    breadcrumb = epc_report_breadcrumbs(
        publish_path="quarter/index.html",
        report_title=title,
    )
    return build_dashboard_html(
        payload,
        generated_on=generated,
        page_title=title,
        breadcrumb_nav=breadcrumb,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy quarterly dashboard HTML into docs/ for GitHub Pages."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write HTML to githubPages.publishDir in config (committed path).",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Rebuild HTML from JSON artifacts before publishing (default: reuse quarter-dashboard.html).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override publish destination (default: config githubPages.publishDir/indexFile).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print destination path and byte size only; do not write.",
    )
    args = parser.parse_args(argv)

    if not args.write and not args.output and not args.dry_run:
        parser.error("Pass --write, --output, or --dry-run.")

    config = load_quarterly_reporting_config(CONFIG_PATH)
    if config.github_pages is None:
        raise SystemExit("quarterly-reporting.json has no githubPages section.")

    pages = config.github_pages
    dest = args.output or pages.publish_path(_REPO_ROOT)
    artifact = out_path("quarter-dashboard.html")

    if args.build or not artifact.is_file():
        if not args.build and not artifact.is_file():
            print(
                f"Note: {artifact} missing — rebuilding from artifacts.",
                file=sys.stderr,
            )
        html_doc = build_dashboard_document(config, repo_root=_REPO_ROOT)
    else:
        html_doc = artifact.read_text(encoding="utf-8")

    if args.dry_run:
        print(f"Would write {len(html_doc.encode('utf-8'))} bytes to {dest}")
        url = pages.site_url()
        if url:
            print(f"Pages URL (after push): {url}")
        return 0

    write_pages_snapshot(html_doc, dest)
    print(f"Wrote {dest}", file=sys.stderr)
    url = pages.site_url()
    if url:
        print(f"After git commit + push, open: {url}", file=sys.stderr)
        print(
            "Enable GitHub Pages: Settings → Pages → branch develop → folder /docs",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
