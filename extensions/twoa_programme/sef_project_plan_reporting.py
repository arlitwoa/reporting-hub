"""Config loader for SEF integrated project plan Block Gantt (PDE)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_NAME = "sef-project-plan-reporting.json"
_MANIFEST_NAME = "sef-project-plan-blocks.json"


@dataclass(frozen=True)
class SefProjectPlanReportingConfig:
    project_key: str
    phase_hub_keys: tuple[str, ...]
    manifest_path: Path
    chart_window_start: str
    chart_window_end: str
    chapter_issue_type: str
    package_issue_type: str
    detail_issue_type: str
    timeline_artifact: str
    html_artifact: str
    pages_publish_path: str
    pages_site_path: str
    page_title: str

    def output_root(self, repo_root: Path | None = None) -> Path:
        from extensions.twoa_programme.quarterly_reporting import load_quarterly_reporting_config

        root = repo_root or _REPO_ROOT
        config = load_quarterly_reporting_config(root / "config" / "quarterly-reporting.json")
        return config.output_root(root)

    def timeline_path(self, repo_root: Path | None = None) -> Path:
        return self.output_root(repo_root) / self.timeline_artifact

    def html_path(self, repo_root: Path | None = None) -> Path:
        return self.output_root(repo_root) / self.html_artifact


def load_sef_project_plan_reporting_config(
    path: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> SefProjectPlanReportingConfig:
    root = repo_root or _REPO_ROOT
    config_path = path or root / "config" / _CONFIG_NAME
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    manifest_file = str(raw.get("manifestFile") or _MANIFEST_NAME)
    manifest_path = root / "config" / manifest_file
    hubs = raw.get("phaseHubKeys") or []
    window = raw.get("chartWindow") or {}
    issue_types = raw.get("issueTypes") or {}
    artifacts = raw.get("artifacts") or {}
    pages = raw.get("githubPages") or {}
    return SefProjectPlanReportingConfig(
        project_key=str(raw.get("projectKey") or "PDE"),
        phase_hub_keys=tuple(str(key) for key in hubs),
        manifest_path=manifest_path,
        chart_window_start=str(window.get("start") or "2026-06-01"),
        chart_window_end=str(window.get("end") or "2027-12-03"),
        chapter_issue_type=str(issue_types.get("chapter") or "Block Level One"),
        package_issue_type=str(issue_types.get("package") or "Block Level Zero"),
        detail_issue_type=str(issue_types.get("detail") or "Block Level Minus One"),
        timeline_artifact=str(artifacts.get("timelineJson") or "sef-project-plan-timeline.json"),
        html_artifact=str(artifacts.get("htmlFile") or "sef-project-plan-chart.html"),
        pages_publish_path=str(pages.get("publishPath") or "docs/sef/project-plan.html"),
        pages_site_path=str(pages.get("sitePath") or "sef/project-plan.html"),
        page_title=str(pages.get("pageTitle") or "SEF | Integrated Project Plan"),
    )


def load_phase_hub_keys(config: SefProjectPlanReportingConfig) -> list[str]:
    if config.phase_hub_keys:
        return list(config.phase_hub_keys)
    if not config.manifest_path.is_file():
        return []
    manifest = json.loads(config.manifest_path.read_text(encoding="utf-8"))
    keys: list[str] = []
    for phase_key in ("phase1", "phase2"):
        block = manifest.get(phase_key) or {}
        hub = block.get(phase_key)
        if hub:
            keys.append(str(hub))
    return keys
