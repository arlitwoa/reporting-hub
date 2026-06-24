"""
TWoA EPCE quarterly reporting configuration — three-lane model (EPCE-6745).

Loads lane rules, quarter boundaries, and quarter-goal tracking settings from
config/quarterly-reporting.json. Reporting engines and HTML runners build on this
config in scripts/quarterly/ (consumer) and artifact.delivery_health (core, later).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from extensions.twoa_programme.quarter_scope import (
    global_burn_jql,
    global_scope_jql,
    planned_scope_jqls,
    unassigned_burn_jql,
    unassigned_scope_jql,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "quarterly-reporting.json"
NZ_TZ = ZoneInfo("Pacific/Auckland")


@dataclass(frozen=True)
class QuarterPeriod:
    slug: str
    label: str
    start_date: date
    end_date: date
    initiative_key: str
    current_quarter_filter: str
    quarterly_reporting_filter: str

    def contains(self, day: date) -> bool:
        return self.start_date <= day <= self.end_date

    def total_days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def elapsed_days(self, as_of: date) -> int:
        if as_of < self.start_date:
            return 0
        if as_of > self.end_date:
            return self.total_days()
        return (as_of - self.start_date).days + 1

    def days_remaining(self, as_of: date) -> int:
        if as_of > self.end_date:
            return 0
        if as_of < self.start_date:
            return self.total_days()
        return (self.end_date - as_of).days

    def elapsed_fraction(self, as_of: date) -> float:
        total = self.total_days()
        if total <= 0:
            return 1.0
        return min(1.0, max(0.0, self.elapsed_days(as_of) / total))

    def ideal_burn_fraction(self, as_of: date) -> float:
        """Linear ideal progress toward quarter-end goal (0 at start, 1 at end)."""
        return self.elapsed_fraction(as_of)


@dataclass(frozen=True)
class QuarterGoal:
    planned_story_points: float | None
    sizing_source_initiative: str | None
    notes: str = ""

    def required_daily_velocity(
        self,
        earned_sp: float,
        as_of: date,
        *,
        goal_target: date,
    ) -> float | None:
        """SP per remaining day needed to hit planned goal from current earned total."""
        if self.planned_story_points is None:
            return None
        remaining = self.planned_story_points - earned_sp
        if remaining <= 0:
            return None
        if as_of > goal_target:
            return float("inf")
        days_left = (goal_target - as_of).days
        if days_left <= 0:
            return float("inf")
        return max(0.0, remaining / days_left)

    def burn_variance(self, earned_sp: float, *, ideal_frac: float) -> float | None:
        """Actual minus ideal earned SP at as_of (positive = ahead of linear plan)."""
        if self.planned_story_points is None:
            return None
        ideal = self.planned_story_points * ideal_frac
        return earned_sp - ideal


@dataclass(frozen=True)
class LaneEducationCloud:
    label: str
    squads: tuple[str, ...]
    board_ids: tuple[int, ...]
    done_definition: str
    scope_jql: str
    deploy_milestone_filter: str
    release_scope_filter_pattern: str


@dataclass(frozen=True)
class LaneIntegration:
    label: str
    board_id: int
    scope_jql: str
    done_definition: str
    velocity_unit: str

    def board_url(self, jira_base: str, *, project_key: str = "EPCE") -> str:
        base = jira_base.rstrip("/")
        return f"{base}/jira/software/c/projects/{project_key}/boards/{self.board_id}"


@dataclass(frozen=True)
class LaneDataMigration:
    label: str
    board_id: int
    scope_jql: str
    workflow_columns: tuple[str, ...]
    done_definition: str
    velocity_credit_status: str
    dat_phase: str

    def board_url(self, jira_base: str, *, project_key: str = "EPCE") -> str:
        base = jira_base.rstrip("/")
        return f"{base}/jira/software/c/projects/{project_key}/boards/{self.board_id}"


@dataclass(frozen=True)
class QuarterScope:
    parent_initiative: str
    quarter_filter: str
    unassigned_filter: str
    overlap_policy: str
    scope_issue_types: tuple[str, ...]
    burn_issue_types: tuple[str, ...]
    global_scope_jql: str
    global_burn_jql: str
    unassigned_scope_jql: str
    unassigned_burn_jql: str
    notes: str = ""


@dataclass(frozen=True)
class LaneUnassigned:
    label: str
    scope_jql: str
    done_definition: str
    notes: str = ""


@dataclass(frozen=True)
class ConfluencePublish:
    space_key: str
    parent_page_id: str
    page_title: str


@dataclass(frozen=True)
class GitHubPagesPublish:
    publish_dir: str
    index_file: str = "index.html"
    site_path: str = ""
    github_user: str = ""
    repo_name: str = ""

    def publish_path(self, repo_root: Path) -> Path:
        return repo_root / self.publish_dir / self.index_file

    def site_url(self) -> str | None:
        """Project-site URL when Pages serves from the /docs folder on the default branch."""
        if not self.github_user or not self.repo_name:
            return None
        base = f"https://{self.github_user}.github.io/{self.repo_name}"
        path = self.site_path.strip("/")
        if not path:
            rel = Path(self.publish_dir) / self.index_file
            if rel.name == "index.html":
                path = str(rel.parent).replace("\\", "/")
            else:
                path = str(rel).replace("\\", "/")
            path = path.strip("/")
        return f"{base}/{path}/" if path else f"{base}/"


@dataclass(frozen=True)
class BurnTracking:
    earned_at: str
    ideal_curve: str
    compare_against: str
    output_dir: str
    goal_target_date: date | None = None
    notes: str = ""

    def resolve_goal_target(self, quarter: QuarterPeriod) -> date:
        """Calendar date when the linear goal line should reach 100% planned SP."""
        if self.ideal_curve == "linear_to_quarter_end":
            return quarter.end_date
        return self.goal_target_date or quarter.end_date

    def goal_span_days(self, quarter: QuarterPeriod) -> int:
        target = self.resolve_goal_target(quarter)
        return max(1, (target - quarter.start_date).days + 1)

    def ideal_burn_fraction(self, as_of: date, quarter: QuarterPeriod) -> float:
        """Linear ideal progress toward goal target (0 at quarter start, 1 at goal target)."""
        target = self.resolve_goal_target(quarter)
        total = self.goal_span_days(quarter)
        if as_of < quarter.start_date:
            return 0.0
        if as_of >= target:
            return 1.0
        elapsed = (as_of - quarter.start_date).days + 1
        return min(1.0, max(0.0, elapsed / total))

    def days_to_goal(self, as_of: date, quarter: QuarterPeriod) -> int:
        """Calendar days remaining until goal target (0 once past target)."""
        target = self.resolve_goal_target(quarter)
        if as_of >= target:
            return 0
        if as_of < quarter.start_date:
            return (target - quarter.start_date).days + 1
        return (target - as_of).days


@dataclass(frozen=True)
class DeliveryMilestones:
    milestone_link_type: str
    in_scope_filter: str | None = None
    in_scope_filter_id: str | None = None
    milestone_report_project: str = "PDE"
    artifact_file: str = "delivery-milestones.json"


@dataclass(frozen=True)
class QuarterlyReportingConfig:
    story_key: str
    quarter: QuarterPeriod
    goal: QuarterGoal
    scope: QuarterScope
    education_cloud: LaneEducationCloud
    integration: LaneIntegration
    data_migration: LaneDataMigration
    unassigned: LaneUnassigned
    burn_tracking: BurnTracking
    delivery_milestones: DeliveryMilestones
    confluence: ConfluencePublish | None
    github_pages: GitHubPagesPublish | None
    standup_primary_view: str
    standup_throw_out_lanes: tuple[str, ...]
    engine_board_id: int

    def output_root(self, repo_root: Path | None = None) -> Path:
        root = repo_root or _REPO_ROOT
        return root / self.burn_tracking.output_dir / self.quarter.slug

    def tracking_snapshot(
        self,
        *,
        earned_story_points: float | None = None,
        as_of: date | None = None,
    ) -> dict[str, object]:
        """Quarter progress scaffold for burn/velocity vs configured goal target."""
        today = as_of or datetime.now(NZ_TZ).date()
        earned = earned_story_points if earned_story_points is not None else 0.0
        planned = self.goal.planned_story_points
        elapsed = self.quarter.elapsed_fraction(today)
        goal_target = self.burn_tracking.resolve_goal_target(self.quarter)
        ideal_frac = self.burn_tracking.ideal_burn_fraction(today, self.quarter)
        variance = self.goal.burn_variance(earned, ideal_frac=ideal_frac) if planned is not None else None
        return {
            "quarter": self.quarter.slug,
            "initiativeKey": self.quarter.initiative_key,
            "asOf": today.isoformat(),
            "quarterStart": self.quarter.start_date.isoformat(),
            "quarterEnd": self.quarter.end_date.isoformat(),
            "goalTargetDate": goal_target.isoformat(),
            "idealCurve": self.burn_tracking.ideal_curve,
            "daysRemaining": self.quarter.days_remaining(today),
            "goalDaysRemaining": self.burn_tracking.days_to_goal(today, self.quarter),
            "elapsedFraction": round(elapsed, 4),
            "idealBurnFraction": round(ideal_frac, 4),
            "plannedStoryPoints": planned,
            "earnedStoryPoints": earned,
            "idealEarnedStoryPoints": round(planned * ideal_frac, 2) if planned else None,
            "burnVariance": round(variance, 2) if variance is not None else None,
            "requiredDailyVelocity": (
                round(req, 2)
                if planned is not None
                and (req := self.goal.required_daily_velocity(earned, today, goal_target=goal_target))
                is not None
                and req != float("inf")
                else None
            ),
            "onTrack": variance >= 0 if variance is not None else None,
        }


def sprint_overlaps_quarter(
    sprint_start: date | None,
    sprint_end: date | None,
    quarter: QuarterPeriod,
) -> bool:
    """True when a closed sprint window intersects the delivery quarter."""
    if sprint_end is None:
        return False
    start = sprint_start or sprint_end
    return start <= quarter.end_date and sprint_end >= quarter.start_date


def credit_date_nz(credit_at: datetime) -> date:
    """Calendar date in Pacific/Auckland for quarter-window filtering."""
    if credit_at.tzinfo is None:
        credit_at = credit_at.replace(tzinfo=timezone.utc)
    return credit_at.astimezone(NZ_TZ).date()


def filter_events_in_quarter(
    events: list[dict],
    quarter: QuarterPeriod,
    *,
    credit_at_key: str = "credit_at",
) -> list[dict]:
    """Keep burn events whose credit timestamp falls within the quarter (NZ date)."""
    kept: list[dict] = []
    for event in events:
        raw = event.get(credit_at_key)
        if not raw:
            continue
        credit_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if quarter.contains(credit_date_nz(credit_at)):
            kept.append(event)
    return kept


def aggregate_daily_burn(
    events: list[dict],
    *,
    date_key: str = "credit_date",
    sp_key: str = "story_points",
) -> tuple[list[dict], float]:
    """Sum story points by credit date and return daily rows plus running total."""
    by_date: dict[str, float] = {}
    for event in events:
        day = event.get(date_key)
        if not day:
            continue
        sp = event.get(sp_key)
        if sp is None:
            continue
        by_date[str(day)] = by_date.get(str(day), 0.0) + float(sp)

    daily: list[dict] = []
    running = 0.0
    for day in sorted(by_date):
        running += by_date[day]
        daily.append(
            {
                "date": day,
                "earned_that_day": by_date[day],
                "cumulative_story_points": running,
            }
        )
    return daily, running


def extend_daily_burn_to_as_of(
    daily: list[dict],
    as_of: date | str,
    *,
    quarter_end: date | str | None = None,
) -> list[dict]:
    """Append a flat cumulative point at as_of when the last credit date is earlier."""
    if not daily:
        return daily
    as_of_day = date.fromisoformat(str(as_of)[:10])
    if quarter_end is not None:
        as_of_day = min(as_of_day, date.fromisoformat(str(quarter_end)[:10]))
    last = daily[-1]
    last_day = date.fromisoformat(str(last["date"])[:10])
    if as_of_day <= last_day:
        return list(daily)
    return [
        *daily,
        {
            "date": as_of_day.isoformat(),
            "earned_that_day": 0.0,
            "cumulative_story_points": last["cumulative_story_points"],
        },
    ]


def resolve_chart_as_of(
    status_as_of: date | str | None,
    *,
    quarter_end: date | str,
) -> date:
    """Chart burn lines extend to NZ today, not only the last pipeline asOf snapshot."""
    today_nz = datetime.now(NZ_TZ).date()
    end = date.fromisoformat(str(quarter_end)[:10])
    target = today_nz
    if status_as_of:
        target = max(target, date.fromisoformat(str(status_as_of)[:10]))
    return min(target, end)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def load_quarterly_reporting_config(
    path: Path | None = None,
) -> QuarterlyReportingConfig:
    config_file = path or _DEFAULT_CONFIG
    payload = json.loads(config_file.read_text(encoding="utf-8"))

    quarter = payload["quarter"]
    goal_payload = payload["quarterGoal"]
    scope_payload = payload.get("scope") or {}
    lanes = payload["lanes"]
    ec = lanes["educationCloud"]
    integration = lanes["integration"]
    migration = lanes["dataMigration"]
    unassigned_lane = lanes.get("unassigned") or {}
    standup = payload["standup"]
    burn = payload["burnTracking"]
    delivery_payload = payload.get("deliveryMilestones") or {}
    conf_payload = payload.get("confluence")
    confluence = None
    if conf_payload:
        confluence = ConfluencePublish(
            space_key=str(conf_payload["spaceKey"]),
            parent_page_id=str(conf_payload["parentPageId"]),
            page_title=str(conf_payload["pageTitle"]),
        )

    pages_payload = payload.get("githubPages")
    github_pages = None
    if pages_payload:
        github_pages = GitHubPagesPublish(
            publish_dir=str(pages_payload["publishDir"]),
            index_file=str(pages_payload.get("indexFile", "index.html")),
            site_path=str(pages_payload.get("sitePath", "")),
            github_user=str(pages_payload.get("githubUser", "")),
            repo_name=str(pages_payload.get("repoName", "")),
        )

    planned_raw = goal_payload.get("plannedStoryPoints")
    planned = float(planned_raw) if planned_raw is not None else None

    quarter_filter = str(
        scope_payload.get("quarterFilter") or quarter.get("currentQuarterFilter", "smart-current-quarter")
    )
    scope = QuarterScope(
        parent_initiative=str(scope_payload.get("parentInitiative") or quarter["initiativeKey"]),
        quarter_filter=quarter_filter,
        unassigned_filter=str(scope_payload.get("unassignedFilter", "smart-quarterly-unassigned")),
        overlap_policy=str(scope_payload.get("overlapPolicy", "priority_exclusive")),
        scope_issue_types=tuple(scope_payload.get("scopeIssueTypes") or ("Story", "Bug", "Spike")),
        burn_issue_types=tuple(scope_payload.get("burnIssueTypes") or ("Story", "Bug")),
        global_scope_jql=global_scope_jql(quarter_filter=quarter_filter),
        global_burn_jql=global_burn_jql(quarter_filter=quarter_filter),
        unassigned_scope_jql=unassigned_scope_jql(quarter_filter=quarter_filter),
        unassigned_burn_jql=unassigned_burn_jql(quarter_filter=quarter_filter),
        notes=str(scope_payload.get("notes", "")),
    )
    lane_jql = planned_scope_jqls(quarter_filter=quarter_filter)

    return QuarterlyReportingConfig(
        story_key=str(payload.get("storyKey", "EPCE-6745")),
        quarter=QuarterPeriod(
            slug=str(quarter["slug"]),
            label=str(quarter["label"]),
            start_date=_parse_date(quarter["startDate"]),
            end_date=_parse_date(quarter["endDate"]),
            initiative_key=str(quarter["initiativeKey"]),
            current_quarter_filter=quarter_filter,
            quarterly_reporting_filter=str(quarter["quarterlyReportingFilter"]),
        ),
        goal=QuarterGoal(
            planned_story_points=planned,
            sizing_source_initiative=goal_payload.get("sizingSourceInitiative"),
            notes=str(goal_payload.get("notes", "")),
        ),
        scope=scope,
        education_cloud=LaneEducationCloud(
            label=str(ec["label"]),
            squads=tuple(str(s) for s in ec["squads"]),
            board_ids=tuple(int(b) for b in ec["boardIds"]),
            done_definition=str(ec["doneDefinition"]),
            scope_jql=lane_jql["educationCloud"],
            deploy_milestone_filter=str(ec["deployMilestoneFilter"]),
            release_scope_filter_pattern=str(ec["releaseScopeFilterPattern"]),
        ),
        integration=LaneIntegration(
            label=str(integration["label"]),
            board_id=int(integration["boardId"]),
            scope_jql=lane_jql["integration"],
            done_definition=str(integration["doneDefinition"]),
            velocity_unit=str(integration["velocityUnit"]),
        ),
        data_migration=LaneDataMigration(
            label=str(migration["label"]),
            board_id=int(migration["boardId"]),
            scope_jql=lane_jql["dataMigration"],
            workflow_columns=tuple(str(c) for c in migration["workflowColumns"]),
            done_definition=str(migration["doneDefinition"]),
            velocity_credit_status=str(migration["velocityCreditStatus"]),
            dat_phase=str(migration["datPhase"]),
        ),
        unassigned=LaneUnassigned(
            label=str(unassigned_lane.get("label", "Unassigned")),
            scope_jql=unassigned_burn_jql(quarter_filter=quarter_filter),
            done_definition=str(unassigned_lane.get("doneDefinition", "deploy_plus")),
            notes=str(unassigned_lane.get("notes", "")),
        ),
        burn_tracking=BurnTracking(
            earned_at=str(burn["earnedAt"]),
            ideal_curve=str(burn["idealCurve"]),
            compare_against=str(burn["compareAgainst"]),
            output_dir=str(burn.get("outputDir", "output/quarterly")),
            goal_target_date=(
                _parse_date(burn["goalTargetDate"]) if burn.get("goalTargetDate") else None
            ),
            notes=str(burn.get("notes", "")),
        ),
        delivery_milestones=DeliveryMilestones(
            milestone_link_type=str(delivery_payload.get("milestoneLinkType", "Milestone")),
            in_scope_filter=delivery_payload.get("inScopeFilter") or None,
            in_scope_filter_id=(
                str(delivery_payload["inScopeFilterId"])
                if delivery_payload.get("inScopeFilterId") is not None
                else None
            ),
            milestone_report_project=str(delivery_payload.get("milestoneReportProject", "PDE")),
            artifact_file=str(delivery_payload.get("artifactFile", "delivery-milestones.json")),
        ),
        confluence=confluence,
        github_pages=github_pages,
        standup_primary_view=str(standup["primaryView"]),
        standup_throw_out_lanes=tuple(str(lane) for lane in standup["throwOutLanes"]),
        engine_board_id=int(standup["engineBoardId"]),
    )
