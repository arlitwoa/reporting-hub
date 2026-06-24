"""Copy quarterly dashboard HTML into a GitHub Pages–servable path."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SiteIndexReport:
    href: str
    title: str
    description: str = ""


def site_root_index_path(repo_root: Path) -> Path:
    return repo_root / "docs" / "index.html"


def build_github_pages_site_index_html(
    reports: list[SiteIndexReport],
    *,
    generated_on: str,
    site_url: str | None = None,
) -> str:
    """Hub page for the GitHub Pages site root (docs/index.html)."""
    items = []
    for report in reports:
        title = html.escape(report.title)
        href = html.escape(report.href)
        if report.description:
            desc = html.escape(report.description)
            items.append(
                f'<li><a href="{href}">{title}</a><span class="desc"> — {desc}</span></li>'
            )
        else:
            items.append(f'<li><a href="{href}">{title}</a></li>')
    report_list = "\n      ".join(items)
    site_note = ""
    if site_url:
        site_note = (
            f'<p class="note">Stable URLs under '
            f'<a href="{html.escape(site_url)}">{html.escape(site_url)}</a>.</p>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EPCE delivery reports</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2rem; color: #172b4d; }}
    h1 {{ font-size: 1.5rem; }}
    ul {{ line-height: 1.8; padding-left: 1.25rem; }}
    .desc {{ color: #5e6c84; font-size: 0.95rem; }}
    .note {{ color: #5e6c84; font-size: 0.9rem; }}
    footer {{ margin-top: 2rem; color: #5e6c84; font-size: 0.85rem; }}
  </style>
</head>
<body>
  <main>
    <h1>EPCE delivery reports</h1>
    <p>Hosted snapshots refreshed from Jira. Each link is overwritten when the report pipeline runs.</p>
    <ul>
      {report_list}
    </ul>
    {site_note}
    <footer>Generated {html.escape(generated_on)}.</footer>
  </main>
</body>
</html>
"""


def write_pages_snapshot(html: str, dest: Path) -> None:
    """Write dashboard HTML; create parent dirs if needed."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")
