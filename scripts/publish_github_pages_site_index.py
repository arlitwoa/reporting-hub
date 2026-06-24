#!/usr/bin/env python3
"""Write docs/index.html hub for the GitHub Pages site root."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from extensions.twoa_programme.github_pages_publish import (  # noqa: E402
    SiteIndexReport,
    build_github_pages_site_index_html,
    site_root_index_path,
    write_pages_snapshot,
)
from extensions.twoa_programme.quarterly_reporting import (  # noqa: E402
    NZ_TZ,
    load_quarterly_reporting_config,
)


def publish_site_index(repo_root: Path) -> Path:
    quarter_config = load_quarterly_reporting_config()
    quarter_pages = quarter_config.github_pages
    if quarter_pages is None:
        raise SystemExit("config/quarterly-reporting.json has no githubPages section.")

    site_url = (
        f"https://{quarter_pages.github_user}.github.io/{quarter_pages.repo_name}/"
        if quarter_pages.github_user and quarter_pages.repo_name
        else None
    )
    reports = [
        SiteIndexReport(
            href="quarter/",
            title="Current Quarter | EPC Delivery Dashboard",
            description="cumulative burn, lane breakdown, sprint and release credit",
        ),
        SiteIndexReport(
            href="quarter/milestone.html",
            title="Milestone scope report",
            description="quarter milestone scope snapshot",
        ),
        SiteIndexReport(
            href="sprint-health/",
            title="EPCE Sprint Health",
            description="per-squad active sprint scope and forecast",
        ),
        SiteIndexReport(
            href="dev-done-risk/",
            title="Dev Done Risk",
            description="in-cycle engine development-done risk",
        ),
    ]
    generated_on = datetime.now(NZ_TZ).strftime("%d %b %Y %H:%M NZST")
    html_doc = build_github_pages_site_index_html(
        reports,
        generated_on=generated_on,
        site_url=site_url,
    )
    dest = site_root_index_path(repo_root)
    write_pages_snapshot(html_doc, dest)
    return dest


def main() -> int:
    dest = publish_site_index(_REPO_ROOT)
    print("Wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
