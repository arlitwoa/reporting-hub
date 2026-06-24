"""Shared paths and config for quarterly reporting scripts (EPCE-6745)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from artifact.atlassian.base import AtlassianAdapterBase

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "quarterly-reporting.json"
BINDING_PATH = REPO_ROOT / "config" / "jira-binding.json"

SKIP_ISSUE_TYPES = frozenset({"Epic", "Initiative", "Test Phase"})

EPC_DELIVERY_REPORTS_PAGE_ID = "1457324070"


def find_confluence_page(adapter: AtlassianAdapterBase, *, space: str, title: str) -> str | None:
    cql = f'space = {space} AND title = "{title}"'
    data = adapter.http.get_json(
        "/wiki/rest/api/content/search",
        params={"cql": cql, "limit": 5},
    )
    for row in data.get("results") or []:
        if row.get("title") == title:
            return str(row["id"])
    return None


def confluence_set_page_full_width(adapter: AtlassianAdapterBase, page_id: str) -> None:
    """Set published and draft page appearance to full-width."""
    for key in ("content-appearance-published", "content-appearance-draft"):
        endpoint = f"/wiki/rest/api/content/{page_id}/property/{key}"
        try:
            prop = adapter.http.get_json(endpoint)
        except Exception:
            prop = None
        if prop and prop.get("key") == key:
            version = (prop.get("version") or {}).get("number", 1)
            adapter.http.put_json(
                endpoint,
                body={
                    "key": key,
                    "value": "full-width",
                    "version": {"number": version + 1},
                },
            )
        else:
            adapter.http.post_json(
                endpoint,
                body={"key": key, "value": "full-width"},
            )


def out_path(name: str, *, quarter_slug: str | None = None) -> Path:
    from extensions.twoa_programme.quarterly_reporting import load_quarterly_reporting_config

    config = load_quarterly_reporting_config(CONFIG_PATH)
    root = config.output_root(REPO_ROOT)
    if quarter_slug and quarter_slug != config.quarter.slug:
        root = REPO_ROOT / config.burn_tracking.output_dir / quarter_slug
    root.mkdir(parents=True, exist_ok=True)
    return root / name
