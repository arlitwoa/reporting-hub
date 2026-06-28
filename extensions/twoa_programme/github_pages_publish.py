"""GitHub Pages site hub and programme landing pages."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SITE_CONFIG_NAME = "github-pages-site.json"


@dataclass(frozen=True)
class SiteIndexReport:
    href: str
    title: str
    description: str = ""


@dataclass(frozen=True)
class SiteProgrammeReport:
    href: str
    title: str
    description: str = ""


@dataclass(frozen=True)
class SiteProgramme:
    id: str
    title: str
    description: str
    reports: tuple[SiteProgrammeReport, ...]


@dataclass(frozen=True)
class GitHubPagesSiteConfig:
    site_title: str
    site_intro: str
    programmes: tuple[SiteProgramme, ...]


_SITE_CSS = """
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2rem; color: #172b4d; max-width: 52rem; }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
    h2 { font-size: 1.15rem; margin: 1.75rem 0 0.35rem; }
    h2 a { color: #172b4d; text-decoration: none; }
    h2 a:hover { text-decoration: underline; }
    ul { line-height: 1.8; padding-left: 1.25rem; margin: 0.35rem 0 0; }
    .desc, .note, .empty { color: #5e6c84; font-size: 0.95rem; }
    .programme-desc { color: #5e6c84; font-size: 0.95rem; margin: 0 0 0.25rem; }
    .breadcrumb { font-size: 0.9rem; margin-bottom: 1.25rem; }
    .breadcrumb a { color: #0052cc; text-decoration: none; }
    .breadcrumb a:hover { text-decoration: underline; }
    footer { margin-top: 2rem; color: #5e6c84; font-size: 0.85rem; }
"""


def site_root_index_path(repo_root: Path) -> Path:
    return repo_root / "docs" / "index.html"


def programme_hub_path(repo_root: Path, programme_id: str) -> Path:
    return repo_root / "docs" / programme_id / "index.html"


def load_github_pages_site_config(
    path: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> GitHubPagesSiteConfig:
    root = repo_root or _REPO_ROOT
    config_path = path or root / "config" / _SITE_CONFIG_NAME
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    programmes: list[SiteProgramme] = []
    for block in raw.get("programmes") or []:
        reports = tuple(
            SiteProgrammeReport(
                href=str(row.get("href") or ""),
                title=str(row.get("title") or ""),
                description=str(row.get("description") or ""),
            )
            for row in block.get("reports") or []
        )
        programmes.append(
            SiteProgramme(
                id=str(block.get("id") or ""),
                title=str(block.get("title") or ""),
                description=str(block.get("description") or ""),
                reports=reports,
            )
        )
    return GitHubPagesSiteConfig(
        site_title=str(raw.get("siteTitle") or "TWoA reporting hub"),
        site_intro=str(
            raw.get("siteIntro")
            or "Hosted snapshots refreshed from Jira. Each report is overwritten when the pipeline runs."
        ),
        programmes=tuple(programmes),
    )


def _report_list_items(
    reports: list[SiteProgrammeReport],
    *,
    href_for: Callable[[SiteProgrammeReport], str],
) -> str:
    items: list[str] = []
    for report in reports:
        title = html.escape(report.title)
        href = html.escape(href_for(report))
        if report.description:
            desc = html.escape(report.description)
            items.append(f'<li><a href="{href}">{title}</a><span class="desc"> — {desc}</span></li>')
        else:
            items.append(f'<li><a href="{href}">{title}</a></li>')
    return "\n      ".join(items)


def _href_from_programme_hub(programme_id: str, site_href: str) -> str:
    prefix = f"{programme_id}/"
    if site_href.startswith(prefix):
        return site_href[len(prefix) :]
    return f"../{site_href}"


def build_github_pages_root_index_html(
    config: GitHubPagesSiteConfig,
    *,
    generated_on: str,
    site_url: str | None = None,
) -> str:
    sections: list[str] = []
    for programme in config.programmes:
        hub_href = html.escape(f"{programme.id}/")
        title = html.escape(programme.title)
        description = html.escape(programme.description)
        if programme.reports:
            preview = _report_list_items(
                list(programme.reports[:3]),
                href_for=lambda report: report.href,
            )
            more = ""
            if len(programme.reports) > 3:
                more = f'\n      <li><a href="{hub_href}">View all {title} reports</a></li>'
            report_block = f"<ul>\n      {preview}{more}\n    </ul>"
        else:
            report_block = '<p class="empty">No published reports yet.</p>'
        sections.append(
            f"""    <section>
      <h2><a href="{hub_href}">{title}</a></h2>
      <p class="programme-desc">{description}</p>
{report_block}
    </section>"""
        )
    programme_sections = "\n".join(sections)
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
  <title>{html.escape(config.site_title)}</title>
  <style>{_SITE_CSS}</style>
</head>
<body>
  <main>
    <h1>{html.escape(config.site_title)}</h1>
    <p>{html.escape(config.site_intro)}</p>
{programme_sections}
    {site_note}
    <footer>Generated {html.escape(generated_on)}.</footer>
  </main>
</body>
</html>
"""


def build_github_pages_programme_hub_html(
    programme: SiteProgramme,
    *,
    site_title: str,
    generated_on: str,
    site_url: str | None = None,
) -> str:
    if programme.reports:
        report_list = _report_list_items(
            list(programme.reports),
            href_for=lambda report: _href_from_programme_hub(programme.id, report.href),
        )
        reports_block = f"<ul>\n      {report_list}\n    </ul>"
    else:
        reports_block = '<p class="empty">No published reports yet.</p>'
    site_note = ""
    if site_url:
        site_note = (
            f'<p class="note">Site home: '
            f'<a href="{html.escape(site_url)}">{html.escape(site_url)}</a>.</p>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(programme.title)} | {html.escape(site_title)}</title>
  <style>{_SITE_CSS}</style>
</head>
<body>
  <main>
    <p class="breadcrumb"><a href="../">← {html.escape(site_title)}</a></p>
    <h1>{html.escape(programme.title)}</h1>
    <p class="programme-desc">{html.escape(programme.description)}</p>
    {reports_block}
    {site_note}
    <footer>Generated {html.escape(generated_on)}.</footer>
  </main>
</body>
</html>
"""


def build_github_pages_site_index_html(
    reports: list[SiteIndexReport],
    *,
    generated_on: str,
    site_url: str | None = None,
) -> str:
    """Legacy flat index builder — prefer build_github_pages_root_index_html."""
    items = []
    for report in reports:
        title = html.escape(report.title)
        href = html.escape(report.href)
        if report.description:
            desc = html.escape(report.description)
            items.append(f'<li><a href="{href}">{title}</a><span class="desc"> — {desc}</span></li>')
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
  <style>{_SITE_CSS}</style>
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


def write_pages_snapshot(html_doc: str, dest: Path) -> None:
    """Write dashboard HTML; create parent dirs if needed."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html_doc, encoding="utf-8")
