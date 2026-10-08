#!/usr/bin/env python3
"""Fetch SEFK Testlet histories and build the GitHub Pages burndown snapshot."""

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

from extensions.twoa_programme.jira_search import search_all  # noqa: E402
from extensions.twoa_programme.milestone_timeline import (  # noqa: E402
    fetch_issue_changelog_histories,
    load_scope_changelog_cache,
    save_scope_changelog_cache,
)
from extensions.twoa_programme.sefk_testlet_burndown import (  # noqa: E402
    build_sefk_testlet_burndown_html,
    build_sefk_testlet_burndown_payload,
)

START_DATE_FIELD = "customfield_10015"
END_DATE_FIELD = "duedate"
UNIT_REPORT_PATH = _REPO_ROOT / "docs" / "sefk" / "testlet-burndown.html"
CACHE_PATH = _REPO_ROOT / "output" / "sefk-testlet-burndown-changelog-cache.json"
NZ_TZ = ZoneInfo("Pacific/Auckland")


def _load_status_categories(
    adapter: AtlassianAdapter, status_ids: set[str]
) -> dict[str, str]:
    categories: dict[str, str] = {}
    for status_id in sorted(status_ids):
        status = adapter.http.get_json(f"/rest/api/3/status/{status_id}")
        category = status.get("statusCategory") or {}
        category_key = str(category.get("key") or "").lower()
        if category_key:
            categories[status_id] = category_key
    if not categories:
        raise RuntimeError("Jira returned no status-category mappings; cannot replay Testlet history.")
    return categories


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the SEFK Testlet burndown report.")
    parser.add_argument("--write", action="store_true", help="Write the HTML report snapshot.")
    parser.add_argument("--test-type", default="Unit", help="Exact Jira Test Types option to report.")
    parser.add_argument("--bounds-issue", default="SEFK-1274", help="Issue providing Start/Due dates.")
    parser.add_argument("--platform", default=None, help="Optional exact Jira Platform value to report.")
    parser.add_argument("--output", type=Path, default=None, help="Override the HTML output path.")
    args = parser.parse_args(argv)

    test_type = args.test_type.strip()
    if not test_type:
        parser.error("--test-type must not be empty")
    escaped_test_type = test_type.replace("\\", "\\\\").replace('"', '\\"')
    jql = (
        'project = SEFK AND issuetype = Testlet AND cf[10145] = '
        f'"{escaped_test_type}" ORDER BY created ASC, key ASC'
    )
    if args.platform:
        escaped_platform = args.platform.strip().replace("\\", "\\\\").replace('"', '\\"')
        jql = jql.replace(
            ' ORDER BY created ASC, key ASC',
            f' AND cf[10079] = "{escaped_platform}" ORDER BY created ASC, key ASC',
        )
    report_path = UNIT_REPORT_PATH if test_type == "Unit" else (
        _REPO_ROOT / "docs" / "sefk" / f"{test_type.lower().replace(' ', '-')}-testlet-burndown.html"
    )
    adapter = AtlassianAdapter.from_profile("atlassian", os.environ["ARTIFACT_PROFILES_DIR"])
    fields = ["created", "status", "issuetype", "customfield_10145"]
    if args.platform:
        fields.append("customfield_10079")
    issues = search_all(adapter, jql, fields)
    bounds_issue = adapter.http.get_json(
        f"/rest/api/3/issue/{args.bounds_issue}",
        params={"fields": f"{START_DATE_FIELD},{END_DATE_FIELD}"},
    )
    bounds_fields = bounds_issue.get("fields") or {}
    ideal_start = bounds_fields.get(START_DATE_FIELD)
    ideal_end = bounds_fields.get(END_DATE_FIELD)
    if not ideal_start or not ideal_end:
        raise RuntimeError(
            f"{args.bounds_issue} must have both Start date and Due date set "
            "to draw the ideal pace line."
        )
    changelogs = load_scope_changelog_cache(CACHE_PATH)
    status_ids: set[str] = set()
    for index, issue in enumerate(issues, start=1):
        key = str(issue.get("key") or "")
        if not key:
            continue
        fields = issue.get("fields") or {}
        status_id = str(((fields.get("status") or {}).get("id")) or "")
        if status_id:
            status_ids.add(status_id)
        if key in changelogs:
            histories = changelogs[key]
        else:
            print(f"Testlet changelog {index}/{len(issues)} {key}...", file=sys.stderr, flush=True)
            histories = fetch_issue_changelog_histories(adapter, key)
            changelogs[key] = histories
            save_scope_changelog_cache(CACHE_PATH, changelogs)
        changelogs[key] = histories
        for history in histories:
            for item in history.get("items") or []:
                if str(item.get("field") or "").lower() != "status":
                    continue
                for field in ("from", "to"):
                    value = str(item.get(field) or "")
                    if value:
                        status_ids.add(value)

    status_categories = _load_status_categories(adapter, status_ids)
    payload = build_sefk_testlet_burndown_payload(
        issues,
        changelogs,
        status_categories,
        ideal_start=str(ideal_start),
        ideal_end=str(ideal_end),
    )
    generated = datetime.now(NZ_TZ).strftime("%d %b %Y %H:%M %Z")
    document = build_sefk_testlet_burndown_html(
        payload,
        generated_on=generated,
        test_type=test_type,
        bounds_issue_key=args.bounds_issue,
        platform=args.platform,
    )
    output_path = args.output or report_path
    if args.write or args.output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(document, encoding="utf-8")
        print(f"Wrote {output_path}", file=sys.stderr)
    else:
        print(document)
    CACHE_PATH.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())