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
    cached_changelog_histories,
    fetch_issue_changelog_histories,
    issue_updated,
    load_scope_changelog_cache,
    save_scope_changelog_cache,
    store_changelog_histories,
)
from extensions.twoa_programme.sefk_testlet_burndown import (  # noqa: E402
    FLAGGED_FIELD,
    build_sefk_testlet_burndown_html,
    build_sefk_testlet_burndown_payload,
    testlet_scope_jql,
)

START_DATE_FIELD = "customfield_10015"
END_DATE_FIELD = "duedate"
UNIT_REPORT_PATH = _REPO_ROOT / "docs" / "sefk" / "testlet-burndown.html"
CACHE_PATH = _REPO_ROOT / "output" / "sefk-testlet-burndown-changelog-cache.json"
NZ_TZ = ZoneInfo("Pacific/Auckland")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the SEFK Testlet burndown report.")
    parser.add_argument("--write", action="store_true", help="Write the HTML report snapshot.")
    parser.add_argument("--test-type", default="Unit", help="Exact Jira Test Types option to report.")
    parser.add_argument("--bounds-issue", default="SEFK-1274", help="Issue providing Start/Due dates.")
    parser.add_argument("--platform", default=None, help="Optional exact Jira Platform value to report.")
    parser.add_argument("--profile", default="atlassian", help="Artifact Atlassian profile to use.")
    parser.add_argument(
        "--include-all-engine-versions",
        action="store_true",
        help="Include System Integration Testlets outside the current-engine filter.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Override the HTML output path.")
    args = parser.parse_args(argv)

    test_type = args.test_type.strip()
    if not test_type:
        parser.error("--test-type must not be empty")
    jql = testlet_scope_jql(
        test_type,
        args.platform,
        include_all_engine_versions=args.include_all_engine_versions,
    )
    report_path = UNIT_REPORT_PATH if test_type == "Unit" else (
        _REPO_ROOT / "docs" / "sefk" / f"{test_type.lower().replace(' ', '-')}-testlet-burndown.html"
    )
    adapter = AtlassianAdapter.from_profile(args.profile, os.environ["ARTIFACT_PROFILES_DIR"])
    fields = [
        "created",
        "updated",
        "resolution",
        "resolutiondate",
        "status",
        "issuetype",
        "customfield_10145",
        FLAGGED_FIELD,
    ]
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
    # Cache entries are validated against each issue's Jira ``updated`` timestamp, so a
    # persisted cache can never serve stale histories.
    cache = load_scope_changelog_cache(CACHE_PATH)
    changelogs: dict[str, list] = {}
    fetched = 0
    for index, issue in enumerate(issues, start=1):
        key = str(issue.get("key") or "")
        if not key:
            continue
        updated = issue_updated(issue)
        histories = cached_changelog_histories(cache, key, updated)
        if histories is None:
            print(f"Testlet changelog {index}/{len(issues)} {key}...", file=sys.stderr, flush=True)
            histories = fetch_issue_changelog_histories(adapter, key)
            store_changelog_histories(cache, key, updated, histories)
            fetched += 1
            if fetched % 50 == 0:
                save_scope_changelog_cache(CACHE_PATH, cache)
        changelogs[key] = histories
    if fetched:
        save_scope_changelog_cache(CACHE_PATH, cache)
    print(
        f"Testlet changelogs: {len(changelogs) - fetched} cached, {fetched} fetched",
        file=sys.stderr,
        flush=True,
    )

    payload = build_sefk_testlet_burndown_payload(
        issues,
        changelogs,
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
        include_all_engine_versions=args.include_all_engine_versions,
    )
    output_path = args.output or report_path
    if args.write or args.output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(document, encoding="utf-8")
        print(f"Wrote {output_path}", file=sys.stderr)
    else:
        print(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())