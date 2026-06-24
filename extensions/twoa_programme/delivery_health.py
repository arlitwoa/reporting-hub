"""
TWoA EPCE delivery health configuration — loads portable core config from JSON + jira-binding.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dataclasses import dataclass

from artifact.delivery_health.config import DeliveryHealthConfig, DevDoneRiskConfig, SquadConfig
from artifact.delivery_health.phases import deploy_status_names, terminal_status_names
from artifact.jira_binding import JiraBinding

from extensions.twoa_programme.jira_binding_loader import load_jira_binding

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_HEALTH = _REPO_ROOT / "config" / "delivery-health.json"


def load_binding(path: Path | None = None) -> JiraBinding:
    return load_jira_binding(path)


def _load_dev_done_risk(payload: dict, aliases: dict[str, str]) -> DevDoneRiskConfig | None:
    section = payload.get("devDoneRisk")
    if not section:
        return None
    return DevDoneRiskConfig(
        engine_project_key=str(section["engineProjectKey"]),
        engine_issue_type=str(section.get("engineIssueType", "Engine")),
        engine_in_cycle_filter=str(section["engineInCycleFilter"]),
        scope_in_cycle_filter=str(section["scopeInCycleFilter"]),
        scope_filter_id=str(section["scopeFilterId"]),
        scope_label=str(section.get("scopeLabel", section["scopeInCycleFilter"])),
        dev_done_milestone_field=aliases.get(
            "Milestone | Dev Done",
            section.get("devDoneMilestoneField", "customfield_11631"),
        ),
        delivery_squad_field=aliases.get(
            "Delivery Squad",
            section.get("deliverySquadField", "customfield_11102"),
        ),
        engine_board_id=int(section["engineBoardId"]),
        gate_statuses=frozenset(str(s) for s in section["gateStatuses"]),
        critical_statuses=frozenset(str(s) for s in section["criticalStatuses"]),
        high_statuses=frozenset(str(s) for s in section["highStatuses"]),
        medium_statuses=frozenset(str(s) for s in section["mediumStatuses"]),
        failed_statuses=frozenset(str(s) for s in section.get("failedStatuses", ["Failed", "Failed Retest"])),
        large_sp_threshold=int(section.get("largeSpThreshold", 15)),
        report_title=str(section.get("reportTitle", "Dev Done Risk")),
    )


@dataclass(frozen=True)
class TwoaDeliveryHealthConfig(DeliveryHealthConfig):
    """TWoA EPCE delivery health — sprint/release scope includes all in-sprint issues."""

    def sprint_scope_jql(self, sprint_id: int | str) -> str:
        return (
            f"project = {self.project_key} "
            f"AND issuetype in ({self.scope_issue_types_jql()}) "
            f"AND sprint = {sprint_id}"
        )

    def release_scope_jql(self, fix_version: str) -> str:
        quoted = fix_version.replace('"', '\\"')
        return (
            f"project = {self.project_key} "
            f"AND issuetype in ({self.scope_issue_types_jql()}) "
            f'AND fixVersion = "{quoted}"'
        )


def load_delivery_health_config(
    *,
    health_path: Path | None = None,
    binding_path: Path | None = None,
) -> TwoaDeliveryHealthConfig:
    """Build DeliveryHealthConfig for TWoA EPCE from delivery-health.json and jira-binding."""
    health_file = health_path or _DEFAULT_HEALTH
    payload = json.loads(health_file.read_text(encoding="utf-8"))
    binding = load_binding(binding_path)

    aliases = binding.field_aliases

    squads: dict[str, SquadConfig] = {}
    prefixes: dict[str, tuple[str, ...]] = {}
    for slug, squad in payload.get("squads", {}).items():
        squads[slug] = SquadConfig(
            label=str(squad["label"]),
            slug=slug,
            board_id=int(squad["boardId"]),
        )
        prefixes[slug] = tuple(str(p) for p in squad.get("namePrefixes", [slug]))

    extra_deploy = frozenset(str(s) for s in payload.get("extraDeployStatuses", []))
    terminal_defaults = frozenset(str(s) for s in payload.get("terminalStatusDefaults", []))

    issue_fields = (
        "summary",
        "status",
        "issuetype",
        "priority",
        "fixVersions",
        "created",
        aliases.get("Story Points", "customfield_10026"),
        aliases.get("EPCE Platform", "customfield_10079"),
        "customfield_10021",
        aliases.get("Hygiene RAG", "customfield_13470"),
        aliases.get("Drop from Sprint Health", "customfield_13537"),
    )

    return TwoaDeliveryHealthConfig(
        project_key=str(payload.get("projectKey", binding.project_key)),
        scope_issue_types=tuple(payload.get("scopeIssueTypes", ["Story", "Bug"])),
        story_points_field=aliases.get("Story Points", "customfield_10026"),
        platform_field=aliases.get("EPCE Platform", "customfield_10079"),
        flagged_field="customfield_10021",
        hygiene_rag_field=aliases.get("Hygiene RAG", "customfield_13470"),
        drop_from_sprint_health_jql_name=str(
            payload.get("dropFromSprintHealthField", "Drop from Sprint Health")
        ),
        deliver_milestone_filter_id=int(payload["deliverMilestoneFilterId"]),
        deliver_milestone_filter_label=str(payload.get("deliverMilestoneFilterLabel", "deliver-milestone")),
        blocked_flagged_jql=str(payload.get("blockedFlaggedJql", '"Flagged[Checkboxes]" = Impediment')),
        squads=squads,
        squad_name_prefixes=prefixes,
        deploy_statuses=deploy_status_names(binding, extra=extra_deploy),
        terminal_statuses=terminal_status_names(binding, defaults=terminal_defaults),
        open_buglet_statuses=tuple(payload.get("openBugletStatuses", [])),
        risky_statuses=frozenset(payload.get("riskyStatuses", [])),
        status_fallback_weight={
            str(k): float(v) for k, v in payload.get("statusFallbackWeight", {}).items()
        },
        status_workflow_order=list(payload.get("statusWorkflowOrder", [])),
        issue_fields=issue_fields,
        min_sprint_days=int(payload.get("minSprintDays", 5)),
        baseline_closed_sprint_count=int(payload.get("baselineClosedSprintCount", 12)),
        week1_deploy_share=float(payload.get("week1DeployShare", 0.10)),
        scope_baseline_green_max=float(payload.get("scopeBaselineGreenMax", 0.90)),
        scope_baseline_amber_max=float(payload.get("scopeBaselineAmberMax", 1.15)),
        week1_spill_cap=float(payload.get("week1SpillCap", 0.35)),
        development_done_statuses=frozenset(
            str(s) for s in payload.get("developmentDoneStatuses", [])
        ),
        development_done_forecast_weight=float(payload.get("developmentDoneForecastWeight", 0.75)),
        dev_done_risk=_load_dev_done_risk(payload, aliases),
    )


def supports_delivery_health() -> bool:
    return True
