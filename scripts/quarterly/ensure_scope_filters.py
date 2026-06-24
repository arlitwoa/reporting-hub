#!/usr/bin/env python3
"""Create or update Jira saved filter smart-quarterly-unassigned (EPCE-6745)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from artifact.atlassian import AtlassianAdapter  # noqa: E402

from extensions.twoa_programme.quarter_scope import unassigned_scope_jql  # noqa: E402
from extensions.twoa_programme.quarterly_reporting import load_quarterly_reporting_config  # noqa: E402
from scripts.quarterly.common import CONFIG_PATH  # noqa: E402

FILTER_NAME = "smart-quarterly-unassigned"
FILTER_DESCRIPTION = (
    "EPCE-6745: issues in smart-current-quarter (EPCE-3897) not on any delivery board "
    "(893/992/1725/3032/2730). Hygiene and quarterly unassigned bucket."
)


def _find_filter(adapter: AtlassianAdapter, name: str) -> dict | None:
    page = adapter.http.get_json(
        "/rest/api/3/filter/search",
        params={"filterName": name, "maxResults": 20},
    )
    for row in page.get("values") or []:
        if row.get("name") == name:
            return row
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ensure smart-quarterly-unassigned Jira filter exists.")
    parser.add_argument("--dry-run", action="store_true", help="Print JQL only; do not create or update.")
    args = parser.parse_args(argv)

    config = load_quarterly_reporting_config(CONFIG_PATH)
    jql = unassigned_scope_jql(quarter_filter=config.quarter.current_quarter_filter)

    if args.dry_run:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        print(jql)
        return 0

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(jql)

    adapter = AtlassianAdapter.from_profile(
        "atlassian", profiles_dir=os.environ["ARTIFACT_PROFILES_DIR"]
    )
    existing = _find_filter(adapter, FILTER_NAME)
    body = {"name": FILTER_NAME, "description": FILTER_DESCRIPTION, "jql": jql}
    if existing:
        adapter.http.put_json(f"/rest/api/3/filter/{existing['id']}", body)
        print(f"Updated filter {FILTER_NAME} (id {existing['id']})", file=sys.stderr)
    else:
        created = adapter.http.post_json("/rest/api/3/filter", body)
        print(f"Created filter {FILTER_NAME} (id {created.get('id')})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
