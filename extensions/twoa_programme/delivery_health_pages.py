"""GitHub Pages publish paths for Sprint Health and Dev Done risk reports."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from artifact.delivery_health.config import SquadConfig
from artifact.delivery_health.dev_done_engine import fetch_engine
from artifact.delivery_health.gateway import JiraGateway

from extensions.twoa_programme.quarterly_reporting import GitHubPagesPublish

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_HEALTH = _REPO_ROOT / "config" / "delivery-health.json"


@dataclass(frozen=True)
class DeliveryHealthPagesConfig:
    sprint_health: GitHubPagesPublish
    dev_done_risk: GitHubPagesPublish

    def squad_publish_path(self, repo_root: Path, squad_slug: str) -> Path:
        return repo_root / self.sprint_health.publish_dir / squad_slug / "index.html"

    def sprint_landing_path(self, repo_root: Path) -> Path:
        return repo_root / self.sprint_health.publish_dir / "index.html"

    def dev_done_publish_path(self, repo_root: Path) -> Path:
        return repo_root / self.dev_done_risk.publish_dir / self.dev_done_risk.index_file


def _pages_section(payload: dict[str, Any], key: str, *, github_user: str, repo_name: str) -> GitHubPagesPublish:
    section = payload[key]
    return GitHubPagesPublish(
        publish_dir=str(section["publishDir"]),
        index_file=str(section.get("indexFile", "index.html")),
        site_path=str(section.get("sitePath", "")),
        github_user=github_user,
        repo_name=repo_name,
    )


def load_delivery_health_pages_config(
    *,
    health_path: Path | None = None,
) -> DeliveryHealthPagesConfig | None:
    health_file = health_path or _DEFAULT_HEALTH
    payload = json.loads(health_file.read_text(encoding="utf-8"))
    pages_payload = payload.get("githubPages")
    if not pages_payload:
        return None
    github_user = str(pages_payload.get("githubUser", ""))
    repo_name = str(pages_payload.get("repoName", ""))
    return DeliveryHealthPagesConfig(
        sprint_health=_pages_section(
            pages_payload,
            "sprintHealth",
            github_user=github_user,
            repo_name=repo_name,
        ),
        dev_done_risk=_pages_section(
            pages_payload,
            "devDoneRisk",
            github_user=github_user,
            repo_name=repo_name,
        ),
    )


def resolve_in_cycle_fix_version(
    jira: JiraGateway,
    *,
    dev_done_risk,
) -> str:
    """FixVersion on the current in-cycle PDE Engine (smart-engine-in-cycle)."""
    engine = fetch_engine(jira, dev_done_risk, None)
    engine_fields = engine["fields"]
    fix_versions = engine_fields.get("fixVersions") or []
    if fix_versions:
        return str(fix_versions[0]["name"])
    return str(engine_fields.get("summary") or "engine")


def build_sprint_health_landing_html(
    squads: dict[str, SquadConfig],
    pages: DeliveryHealthPagesConfig,
    *,
    generated_on: str,
) -> str:
    base = pages.sprint_health.site_url() or ""
    items = []
    for slug, squad in sorted(squads.items(), key=lambda item: item[1].label):
        href = f"{slug}/"
        title = html.escape(squad.label)
        items.append(f'<li><a href="{html.escape(href)}">{title}</a></li>')
    squad_list = "\n      ".join(items)
    site_note = ""
    if base:
        site_note = f'<p class="note">Stable URLs under <a href="{html.escape(base)}">{html.escape(base)}</a>.</p>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EPCE Sprint Health</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2rem; color: #172b4d; }}
    h1 {{ font-size: 1.5rem; margin: 0 0 8px; }}
    .report-subtitle {{ margin: 0 0 1rem; color: #5e6c84; font-size: 0.95rem; }}
    ul {{ line-height: 1.8; }}
    .note {{ color: #5e6c84; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <main>
    <h1>EPCE Sprint Health</h1>
    <p class="report-subtitle">Generated {html.escape(generated_on)}</p>
    <p>Per-squad sprint scope, forecast, and delivery health. Each link is overwritten when the snapshot refreshes.</p>
    <ul>
      {squad_list}
    </ul>
    {site_note}
  </main>
</body>
</html>
"""
