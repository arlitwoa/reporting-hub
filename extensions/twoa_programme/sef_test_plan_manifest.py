"""SEF Test Plan registry and PDE Block bindings (config/sef-project-plan-blocks.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_PATH = _REPO_ROOT / "config" / "sef-project-plan-blocks.json"

REPORTING_HUB_SITE_BASE = "https://arlitwoa.github.io/reporting-hub"
SEF_JIRA_PLAN_URL = (
    "https://twoa.atlassian.net/jira/plans/959/scenarios/959/timeline?vid=1053"
)
INTEGRATED_PROJECT_PLAN_TITLE = "SEF | Integrated Project Plan"

_LEGACY_SLUG_MAP: dict[str, str] = {
    "payroll-parallel": "payrollParallel",
    "testing-stream": "testingStream",
}


@dataclass(frozen=True)
class TestPlanReportingHub:
    site_path: str
    site_base: str = REPORTING_HUB_SITE_BASE

    def site_url(self) -> str:
        base = self.site_base.rstrip("/")
        path = self.site_path.lstrip("/")
        return f"{base}/{path}"


@dataclass(frozen=True)
class TestPlanConfig:
    slug: str
    title: str
    summary_prefix: str | None = None
    confluence_page_id: str | None = None
    confluence_url: str | None = None
    stream_parents: dict[str, str] = field(default_factory=dict)
    p1_rollup_block: str | None = None
    details: dict[str, str] = field(default_factory=dict)
    nip_details: dict[str, str] = field(default_factory=dict)
    reporting_hub: TestPlanReportingHub | None = None
    jira_plan_url: str = SEF_JIRA_PLAN_URL

    def all_block_keys(self) -> list[str]:
        keys: list[str] = []
        if self.p1_rollup_block:
            keys.append(self.p1_rollup_block)
        keys.extend(self.details.values())
        keys.extend(self.nip_details.values())
        return list(dict.fromkeys(keys))

    def stream_parent_keys(self) -> list[str]:
        return list(dict.fromkeys(self.stream_parents.values()))


def default_manifest_path(repo_root: Path | None = None) -> Path:
    root = repo_root or _REPO_ROOT
    return root / "config" / "sef-project-plan-blocks.json"


def load_project_plan_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or DEFAULT_MANIFEST_PATH
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _reporting_hub_from_raw(raw: dict[str, Any] | None) -> TestPlanReportingHub | None:
    if not raw:
        return None
    site_path = str(raw.get("sitePath") or "").strip()
    if not site_path:
        return None
    return TestPlanReportingHub(
        site_path=site_path,
        site_base=str(raw.get("siteBase") or REPORTING_HUB_SITE_BASE),
    )


def _test_plan_from_raw(slug: str, raw: dict[str, Any]) -> TestPlanConfig:
    blocks = dict(raw.get("blocks") or {})
    details = dict(blocks.get("details") or raw.get("details") or {})
    nip_details = dict(blocks.get("nipDetails") or raw.get("nipDetails") or {})
    return TestPlanConfig(
        slug=slug,
        title=str(raw.get("title") or slug),
        summary_prefix=(str(raw["summaryPrefix"]) if raw.get("summaryPrefix") else None),
        confluence_page_id=(str(raw["confluencePageId"]) if raw.get("confluencePageId") else None),
        confluence_url=(str(raw["confluenceUrl"]) if raw.get("confluenceUrl") else None),
        stream_parents={str(k): str(v) for k, v in (raw.get("streamParents") or {}).items()},
        p1_rollup_block=(str(raw["p1RollupBlock"]) if raw.get("p1RollupBlock") else None),
        details={str(k): str(v) for k, v in details.items()},
        nip_details={str(k): str(v) for k, v in nip_details.items()},
        reporting_hub=_reporting_hub_from_raw(raw.get("reportingHub")),
        jira_plan_url=str(raw.get("jiraPlanUrl") or SEF_JIRA_PLAN_URL),
    )


def _legacy_test_plan(slug: str, manifest: dict[str, Any]) -> TestPlanConfig | None:
    legacy_key = _LEGACY_SLUG_MAP.get(slug)
    if not legacy_key:
        return None
    raw = manifest.get(legacy_key)
    if not raw:
        return None
    merged = dict(raw)
    if slug == "payroll-parallel":
        merged.setdefault("title", "SEF | Test Plan | Payroll Parallel")
        merged.setdefault(
            "reportingHub",
            {"sitePath": "sef/plans/payroll-parallel.html"},
        )
    elif slug == "testing-stream":
        merged.setdefault("title", "SEF | Test Plan | Testing Stream")
        merged.setdefault(
            "reportingHub",
            {"sitePath": "sef/plans/testing-stream.html"},
        )
    return _test_plan_from_raw(slug, merged)


def get_test_plan(
    manifest: dict[str, Any],
    slug: str,
) -> TestPlanConfig | None:
    test_plans = manifest.get("testPlans") or {}
    raw = test_plans.get(slug)
    if raw:
        return _test_plan_from_raw(slug, raw)
    return _legacy_test_plan(slug, manifest)


def list_test_plans(manifest: dict[str, Any]) -> list[TestPlanConfig]:
    slugs: list[str] = list((manifest.get("testPlans") or {}).keys())
    for slug in _LEGACY_SLUG_MAP:
        if slug not in slugs and _legacy_test_plan(slug, manifest):
            slugs.append(slug)
    plans = [get_test_plan(manifest, slug) for slug in slugs]
    return [plan for plan in plans if plan is not None]


def list_published_test_plans(manifest: dict[str, Any]) -> list[TestPlanConfig]:
    return [plan for plan in list_test_plans(manifest) if plan.confluence_page_id or plan.confluence_url]


def merge_test_plan_manifest_section(
    manifest: dict[str, Any],
    slug: str,
    *,
    title: str,
    confluence_page_id: str | None = None,
    confluence_url: str | None = None,
    stream_parents: dict[str, str] | None = None,
    p1_rollup_block: str | None = None,
    details: dict[str, str] | None = None,
    nip_details: dict[str, str] | None = None,
    summary_prefix: str | None = None,
    reporting_hub_site_path: str | None = None,
) -> dict[str, Any]:
    """Update testPlans[slug] and the legacy payrollParallel/testingStream section."""
    test_plans = dict(manifest.get("testPlans") or {})
    existing = dict(test_plans.get(slug) or {})
    entry: dict[str, Any] = {
        **existing,
        "title": title,
        "streamParents": stream_parents or existing.get("streamParents") or {},
        "blocks": {
            "details": details or (existing.get("blocks") or {}).get("details") or existing.get("details") or {},
            "nipDetails": nip_details
            or (existing.get("blocks") or {}).get("nipDetails")
            or existing.get("nipDetails")
            or {},
        },
        "jiraPlanUrl": existing.get("jiraPlanUrl") or SEF_JIRA_PLAN_URL,
    }
    if summary_prefix is not None:
        entry["summaryPrefix"] = summary_prefix
    elif existing.get("summaryPrefix"):
        entry["summaryPrefix"] = existing["summaryPrefix"]
    if confluence_page_id:
        entry["confluencePageId"] = confluence_page_id
    if confluence_url:
        entry["confluenceUrl"] = confluence_url
    if p1_rollup_block:
        entry["p1RollupBlock"] = p1_rollup_block
    hub_path = reporting_hub_site_path or (existing.get("reportingHub") or {}).get("sitePath")
    if hub_path:
        entry["reportingHub"] = {
            "sitePath": hub_path,
            "siteBase": REPORTING_HUB_SITE_BASE,
        }
    test_plans[slug] = entry
    manifest["testPlans"] = test_plans

    legacy_key = _LEGACY_SLUG_MAP.get(slug)
    if legacy_key:
        legacy = {
            "confluencePageId": entry.get("confluencePageId"),
            "confluenceUrl": entry.get("confluenceUrl"),
            "streamParents": entry.get("streamParents") or {},
            "details": entry["blocks"]["details"],
        }
        if entry.get("p1RollupBlock"):
            legacy["p1RollupBlock"] = entry["p1RollupBlock"]
        if entry["blocks"]["nipDetails"]:
            legacy["nipDetails"] = entry["blocks"]["nipDetails"]
        if slug == "testing-stream":
            legacy["testStrategyPageId"] = manifest.get("testingStream", {}).get("testStrategyPageId")
            legacy["testStrategyUrl"] = manifest.get("testingStream", {}).get("testStrategyUrl")
            legacy["architectConfigureUrl"] = manifest.get("testingStream", {}).get("architectConfigureUrl")
        manifest[legacy_key] = legacy
    return manifest
