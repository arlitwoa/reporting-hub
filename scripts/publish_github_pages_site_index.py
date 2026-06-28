#!/usr/bin/env python3
"""Write docs/index.html and programme hub pages for the GitHub Pages site."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from extensions.twoa_programme.github_pages_publish import (  # noqa: E402
    build_github_pages_programme_hub_html,
    build_github_pages_root_index_html,
    load_github_pages_site_config,
    programme_hub_path,
    site_root_index_path,
    write_pages_snapshot,
)
from extensions.twoa_programme.quarterly_reporting import (  # noqa: E402
    NZ_TZ,
    load_quarterly_reporting_config,
)


def publish_site_index(repo_root: Path) -> list[Path]:
    site_config = load_github_pages_site_config(repo_root=repo_root)
    quarter_config = load_quarterly_reporting_config()
    quarter_pages = quarter_config.github_pages
    if quarter_pages is None:
        raise SystemExit("config/quarterly-reporting.json has no githubPages section.")

    site_url = (
        f"https://{quarter_pages.github_user}.github.io/{quarter_pages.repo_name}/"
        if quarter_pages.github_user and quarter_pages.repo_name
        else None
    )
    generated_on = datetime.now(NZ_TZ).strftime("%d %b %Y %H:%M NZST")

    written: list[Path] = []
    root_html = build_github_pages_root_index_html(
        site_config,
        generated_on=generated_on,
        site_url=site_url,
    )
    root_dest = site_root_index_path(repo_root)
    write_pages_snapshot(root_html, root_dest)
    written.append(root_dest)

    for programme in site_config.programmes:
        hub_html = build_github_pages_programme_hub_html(
            programme,
            site_title=site_config.site_title,
            generated_on=generated_on,
            site_url=site_url,
        )
        hub_dest = programme_hub_path(repo_root, programme.id)
        write_pages_snapshot(hub_html, hub_dest)
        written.append(hub_dest)

    return written


def main() -> int:
    written = publish_site_index(_REPO_ROOT)
    for path in written:
        print("Wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
