"""
TWoA EPCE programme Story, Bug, Buglet, and Testlet hygiene grading (SMART quality rubric).

Programme pack implementation — not portable Artifact core.
Canonical rubric: consumer programme extension docs (see docs/programme-extensions.md).
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from artifact.jira_binding import JiraBinding

from extensions.twoa_programme.jira_binding_loader import try_load_jira_binding

# Hygiene output fields (TWoA EPCE programme)
HYGIENE_SCORE_FIELD = "customfield_13468"  # string e.g. "7/10"
HYGIENE_DETAIL_FIELD = "customfield_13469"  # plain text gap summary
HYGIENE_RAG_FIELD = "customfield_13470"  # select

RAG_IDS = {"Red": "14191", "Amber": "14192", "Green": "14193"}


def _load_binding() -> JiraBinding | None:
    """Load jira-binding.json via unified loader; None only when no file is configured."""
    return try_load_jira_binding()


def _statuses_for_phases(binding: JiraBinding, phases: frozenset[str]) -> frozenset[str]:
    return frozenset(s for s, p in binding.status_map.items() if p in phases)


_binding = _load_binding()

# D-Train phases: Dream → (Decide: programme gate, not a Jira status) → Discover → Design → …
# Decide is documented on SMART; only phases with statusMap entries belong here.
# Derived from jira-binding.json statusMap when available; hardcoded TWoA EPCE values as fallback.
_PRE_REFINEMENT_PHASES = frozenset({"Dream", "Discover", "Design"})
_DEVELOP_AND_LATER_PHASES = frozenset({"Develop", "Deliver", "Demonstrate", "Deploy", "Drive"})
_DELIVER_AND_LATER_PHASES = frozenset({"Deliver", "Demonstrate", "Deploy", "Drive"})

if _binding is not None:
    PRE_REFINEMENT_STATUSES: frozenset[str] = _statuses_for_phases(_binding, _PRE_REFINEMENT_PHASES)
    DEVELOP_AND_LATER_STATUSES: frozenset[str] = _statuses_for_phases(_binding, _DEVELOP_AND_LATER_PHASES)
    DTRAIN_DELIVER_AND_LATER_STATUSES: frozenset[str] = _statuses_for_phases(_binding, _DELIVER_AND_LATER_PHASES)
else:
    PRE_REFINEMENT_STATUSES = frozenset({
        "Backlog",
        "Not Started",
        "To Do",
        "Open",
        "Triage",
        "Designated",
        "To Start Next",
        "In Discovery",
        "Analysis",
        "Investigating",
        "In Design",
        "Awaiting Refinement",
    })
    DTRAIN_DELIVER_AND_LATER_STATUSES = frozenset({
        # Deliver
        "Awaiting Testing",
        "In Testing",
        "TST",
        "Failed",
        "Failed Retest",
        "Awaiting Test Development",
        "In Test Development",
        # Demonstrate
        "Demonstrate",
        "Reviewing",
        "Awaiting PRD",
        "Awaiting Delivery",
        # Deploy
        "Awaiting Deployment",
        "Awaiting STG",
        "Awaiting Merge",
        "STG",
    })
    DEVELOP_AND_LATER_STATUSES = frozenset({
        "Awaiting Development",
        "Awaiting Reply",
        "Doing",
        "Doing Next",
        "In Development",
        "Pending",
        "Repair in progress",
        "DAT",
    }) | DTRAIN_DELIVER_AND_LATER_STATUSES

PLACEHOLDER_FIX_VERSIONS = frozenset({"yyyymmdd-engine-none", "yyyymmdd-engine-siding"})

# Default bulk JQL ΓÇö Develop stage or later, not Done, not pre-Develop
BULK_HYGIENE_JQL = (
    "project = EPCE AND issuetype in (Story, Bug) "
    "AND statusCategory != Done "
    "AND status not in ("
    '  Backlog, "Not Started", "To Do", Triage, Designated, "To Start Next", '
    '  "In Discovery", Analysis, Investigating, "In Design", "Awaiting Refinement"'
    ")"
)

# Whanau role pickers (Product Owner, Developer, Tester, Business Analyst)
# Derived from jira-binding.json fieldAliases when available; hardcoded TWoA EPCE values as fallback.
if _binding is not None:
    WHANAU_USER_FIELDS = (
        _binding.field_aliases.get("Product Owner", "customfield_10216"),
        _binding.field_aliases.get("Developer", "customfield_10214"),
        _binding.field_aliases.get("Tester", "customfield_10217"),
        _binding.field_aliases.get("Business Analyst", "customfield_10218"),
    )
else:
    WHANAU_USER_FIELDS = (
        "customfield_10216",
        "customfield_10214",
        "customfield_10217",
        "customfield_10218",
    )

HYGIENE_RAISE_MENTION_TYPES = frozenset({"Bug", "Buglet", "Testlet"})

HYGIENE_COMMENT_USER_FIELDS = [
    "assignee",
    "reporter",
    *WHANAU_USER_FIELDS,
]

STORY_HYGIENE_FIELDS = [
    "summary",
    "status",
    "fixVersions",
    "issuetype",
    "assignee",
    "reporter",
    "customfield_10026",
    "customfield_10020",
    "issuelinks",
    "customfield_10577",
    "customfield_10377",
    "customfield_10378",
    "customfield_10475",
    "customfield_13303",
    "customfield_11671",
    "customfield_11673",
    "customfield_11102",
    "customfield_10079",
    "customfield_10014",
    "customfield_11366",
    "customfield_11433",
    *WHANAU_USER_FIELDS,
]

BUG_HYGIENE_FIELDS = [
    "summary",
    "status",
    "fixVersions",
    "issuetype",
    "assignee",
    "reporter",
    "customfield_10026",
    "customfield_10020",
    "customfield_11498",
    "customfield_10115",
    "customfield_10116",
    "customfield_10114",
    "customfield_11499",
    "customfield_10408",
    "customfield_10079",
    "customfield_11102",
    "customfield_10014",
    "customfield_11433",
    *WHANAU_USER_FIELDS,
]

BUGLET_HYGIENE_FIELDS = [
    "summary",
    "status",
    "fixVersions",
    "issuetype",
    "parent",
    "assignee",
    "reporter",
    "customfield_11498",
    "customfield_10115",
    "customfield_10116",
    "customfield_10114",
    "customfield_11499",
    "customfield_10408",
    *WHANAU_USER_FIELDS,
]

TESTLET_HYGIENE_FIELDS = [
    "summary",
    "status",
    "fixVersions",
    "issuetype",
    "parent",
    "assignee",
    "reporter",
    "attachment",
    "comment",
    "customfield_11564",
    "customfield_10113",
    "customfield_10115",
    "customfield_10145",
    "customfield_10408",
    *WHANAU_USER_FIELDS,
]

CORE_DEFECT_FIELDS = [
    ("customfield_11498", "Bug/Defect Description", 3.0),
    ("customfield_10115", "Expected Behaviour", 1.5),
    ("customfield_10116", "Actual Behaviour", 1.5),
    ("customfield_10114", "Steps to Reproduce", 1.0),
]

CORE_TESTLET_FIELDS = [
    ("customfield_11564", "Test Description", 3.0),
    ("customfield_10113", "Test Steps", 3.0),
    ("customfield_10115", "Expected Behaviour", 1.5),
]

TESTLET_EXECUTED_STATUSES = frozenset({
    "Passed",
    "Failed",
    "Failed Retest",
})

AC_SUFFIX_RE = re.compile(r"\(AC-\d+", re.IGNORECASE)
BAD_SUMMARY_DASH_RE = re.compile(r"[ΓÇöΓÇô]")

HYGIENE_GRADE_FIELDS = list(
    set(
        STORY_HYGIENE_FIELDS
        + BUG_HYGIENE_FIELDS
        + BUGLET_HYGIENE_FIELDS
        + TESTLET_HYGIENE_FIELDS
    )
)

PLACEHOLDER_RE = re.compile(
    r"<[^>]{2,}>"
    r"|\[not filled\]"
    r"|\[screenshot\s*:"
    r"|\[enter\b",
    re.IGNORECASE,
)


def extract_text(value: Any) -> str:
    """Recursively extract plain text from an ADF node, list, or raw string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(filter(None, (extract_text(v) for v in value)))
    if isinstance(value, dict):
        if value.get("type") == "text":
            return value.get("text", "")
        return " ".join(
            filter(None, (extract_text(c) for c in value.get("content", [])))
        )
    return ""


ADF_MEDIA_NODE_TYPES = frozenset({
    "media",
    "mediaInline",
    "mediaGroup",
    "mediaSingle",
})


def has_embedded_media(value: Any) -> bool:
    """True when ADF contains pasted/attached images or other embedded media."""
    if value is None:
        return False
    if isinstance(value, list):
        return any(has_embedded_media(item) for item in value)
    if isinstance(value, dict):
        if value.get("type") in ADF_MEDIA_NODE_TYPES:
            return True
        return any(has_embedded_media(child) for child in value.get("content", []))
    return False


def field_status(value: Any) -> str:
    """
    Return 'empty', 'placeholder', 'partial', or 'ok' for a field value.
    """
    if value is None:
        return "empty"
    text = extract_text(value).strip()
    if not text:
        if has_embedded_media(value):
            return "ok"
        return "empty"
    if PLACEHOLDER_RE.search(text):
        cleaned = PLACEHOLDER_RE.sub("", text).strip()
        if cleaned:
            return "partial"
        return "placeholder"
    return "ok"


def count_list_items(adf_field: Any) -> int:
    """Count bullet/numbered list items in an ADF field."""
    if adf_field is None:
        return 0

    count = [0]

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") in ("listItem", "orderedListItem"):
                count[0] += 1
            for child in node.get("content", []):
                walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(adf_field)

    if count[0] == 0:
        text = extract_text(adf_field)
        count[0] = len(re.findall(r"^\s*\d+[\.\)]\s", text, re.MULTILINE))

    return count[0]


def is_as_a_format(value: Any) -> bool:
    text = extract_text(value).lower()
    return "as " in text and "i want" in text and "so that" in text


def score_to_rag(score: int) -> str:
    if score >= 8:
        return "Green"
    if score >= 5:
        return "Amber"
    return "Red"


def at_or_past_deliver_phase(fields: dict) -> bool:
    """
    True when the issue is in Deliver, Demonstrate, Deploy, or Drive (Done).

    """
    status = fields.get("status") or {}
    name = status.get("name", "")
    if name in DTRAIN_DELIVER_AND_LATER_STATUSES:
        return True
    return (status.get("statusCategory") or {}).get("key") == "done"


def at_or_past_develop_phase(fields: dict) -> bool:
    """True when the issue is in Develop or any later D-Train phase (including Done)."""
    status = fields.get("status") or {}
    name = status.get("name", "")
    if name in DEVELOP_AND_LATER_STATUSES:
        return True
    return (status.get("statusCategory") or {}).get("key") == "done"


def fix_version_names(fields: dict) -> list[str]:
    """Normalized Fix Version names from Jira issue fields."""
    raw = fields.get("fixVersions") or []
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
        elif item:
            names.append(str(item))
    return names


def has_meaningful_fix_version(fields: dict) -> bool:
    """True when at least one Fix Version is set and is not a placeholder release."""
    names = fix_version_names(fields)
    if not names:
        return False
    return any(name not in PLACEHOLDER_FIX_VERSIONS for name in names)


def _apply_develop_fix_version_blocker(
    fields: dict,
    score: float,
    gaps: list[str],
    blocker: bool,
    *,
    parent_fields: dict | None = None,
) -> tuple[float, list[str], bool]:
    """
    BLOCKER when the issue is at or past Develop but has no meaningful Fix Version.

    For Buglet/Testlet, pass parent_fields so Fix Version inherited from the parent Story
    is respected when available.
    """
    if not at_or_past_develop_phase(fields):
        return score, gaps, blocker
    fix_source = parent_fields if parent_fields is not None else fields
    if has_meaningful_fix_version(fix_source):
        return score, gaps, blocker
    score -= 3
    blocker = True
    gaps.append("At or past Develop with no Fix Version (BLOCKER)")
    return score, gaps, blocker


def testing_not_required(fields: dict) -> bool:
    return any(
        (v.get("value") if isinstance(v, dict) else v) == "Testing Not Required"
        for v in (fields.get("customfield_11432") or [])
    )


def platform_is_set(fields: dict) -> bool:
    """Platform is stored in EPCE customfield_10079."""
    return bool(fields.get("customfield_10079"))


def has_sprint_assigned(fields: dict) -> bool:
    """True when the issue is on at least one sprint (customfield_10020)."""
    sprints = fields.get("customfield_10020")
    return bool(sprints) and (not isinstance(sprints, list) or len(sprints) > 0)


def is_past_refinement(fields: dict) -> bool:
    """True when workflow status is past the refinement stage."""
    status = (fields.get("status") or {}).get("name", "")
    return status not in PRE_REFINEMENT_STATUSES


def _story_point_value_set(value: Any) -> bool:
    """True when a story-points field has a non-empty, non-zero estimate."""
    if value is None or value == "":
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return bool(value)


def story_points_estimated(fields: dict, *, for_bug: bool = False) -> bool:
    """True when Story Points (or Story Size alternate for Stories) are set."""
    if for_bug:
        return _story_point_value_set(fields.get("customfield_10026"))
    return _story_point_value_set(fields.get("customfield_10026")) or _story_point_value_set(
        fields.get("customfield_11366")
    )


def environment_values(fields: dict) -> list[str]:
    """Normalized Environment (customfield_10408) option values."""
    raw = fields.get("customfield_10408")
    if raw is None:
        return []
    if isinstance(raw, list):
        values: list[str] = []
        for item in raw:
            if isinstance(item, dict) and item.get("value"):
                values.append(str(item["value"]))
            elif item:
                values.append(str(item))
        return values
    if isinstance(raw, dict) and raw.get("value"):
        return [str(raw["value"])]
    if raw:
        return [str(raw)]
    return []


def environment_includes_tst(fields: dict) -> bool:
    return "TST" in {v.upper() for v in environment_values(fields)}


def summary_has_ac_suffix(summary: str) -> bool:
    return bool(AC_SUFFIX_RE.search(summary or ""))


def summary_has_bad_dash(summary: str) -> bool:
    return bool(BAD_SUMMARY_DASH_RE.search(summary or ""))


def has_execution_evidence(fields: dict) -> bool:
    """True when the issue has comments or attachments (execution evidence)."""
    comment_meta = fields.get("comment") or {}
    if isinstance(comment_meta, dict) and comment_meta.get("total", 0) > 0:
        return True
    attachments = fields.get("attachment")
    return bool(attachments) and len(attachments) > 0


def _apply_core_testlet_rubric(
    fields: dict,
    score: float,
    gaps: list[str],
    blocker: bool,
) -> tuple[float, list[str], bool]:
    """Shared test-documentation checks for Testlet."""
    for cf, label, deduction in CORE_TESTLET_FIELDS:
        status = field_status(fields.get(cf))
        if status == "empty":
            score -= deduction
            blocker = True
            gaps.append(f"{label} null or empty (BLOCKER)")
        elif status == "partial":
            score -= 1.0
            gaps.append(f"{label} contains unfilled template placeholders")
        elif status == "placeholder":
            score -= 0.5
            gaps.append(f"{label} contains placeholder text only")

    steps = fields.get("customfield_10113")
    if field_status(steps) == "ok" and count_list_items(steps) < 1:
        text = extract_text(steps)
        if not re.search(r"^\s*\d+[\.\)]\s", text, re.MULTILINE):
            score -= 0.5
            gaps.append("Test Steps should use numbered steps")

    return score, gaps, blocker


def _apply_core_defect_rubric(
    fields: dict,
    score: float,
    gaps: list[str],
    blocker: bool,
) -> tuple[float, list[str], bool]:
    """Shared defect-field checks for Bug and Buglet."""
    for cf, label, deduction in CORE_DEFECT_FIELDS:
        status = field_status(fields.get(cf))
        if status == "empty":
            score -= deduction
            blocker = True
            gaps.append(f"{label} null or empty (BLOCKER)")
        elif status == "partial":
            score -= 1.0
            gaps.append(f"{label} contains unfilled template placeholders")
        elif status == "placeholder":
            score -= 0.5
            gaps.append(f"{label} contains placeholder text only")
    return score, gaps, blocker


def grade_story(issue: dict) -> tuple[int, str, list[str]]:
    """Apply the Story rubric. Returns (score, rag, gaps)."""
    f = issue.get("fields", {})
    score = 10.0
    gaps: list[str] = []
    blocker = False

    story = f.get("customfield_10577")
    story_status = field_status(story)
    if story_status in ("empty", "placeholder", "partial"):
        score -= 3
        blocker = True
        label = {
            "empty": "null or empty",
            "placeholder": "contains only placeholder template text",
            "partial": "contains unfilled template placeholders",
        }[story_status]
        gaps.append(f"Story field {label} (BLOCKER)")
    elif not is_as_a_format(story):
        score -= 1
        gaps.append("Story field not in As a / I want / So that format")

    ac = f.get("customfield_10377")
    ac_status = field_status(ac)
    if ac_status in ("empty", "placeholder"):
        score -= 3
        blocker = True
        label = (
            "null or empty" if ac_status == "empty" else "contains only placeholder text"
        )
        gaps.append(f"Acceptance Criteria {label} (BLOCKER)")
    elif ac_status == "partial":
        score -= 1
        gaps.append("Acceptance Criteria contains unfilled placeholder items")
    else:
        bg_status = field_status(f.get("customfield_10378"))
        if bg_status == "ok" and count_list_items(ac) <= 1:
            score -= 1
            gaps.append(
                "AC has only one scenario when Background describes context "
                "suggesting multiple paths"
            )

    bg_status = field_status(f.get("customfield_10378"))
    if bg_status in ("empty", "placeholder"):
        score -= 1
        label = "null or empty" if bg_status == "empty" else "not populated (placeholder only)"
        gaps.append(f"Background field {label}")

    if not f.get("customfield_13303"):
        score -= 0.5
        gaps.append("Definition of Ready not set")
    if not f.get("customfield_11671"):
        score -= 0.5
        gaps.append("Definition of Ready Notes not populated")

    on_sprint = has_sprint_assigned(f)
    if on_sprint and not story_points_estimated(f):
        score -= 3
        blocker = True
        gaps.append("On sprint with no Story Points estimated (BLOCKER)")
    elif not story_points_estimated(f):
        score -= 0.5
        gaps.append("Story points not estimated")

    if on_sprint and not is_past_refinement(f):
        score -= 3
        blocker = True
        gaps.append("On sprint before refinement complete (BLOCKER)")

    delivery_methodology = (f.get("customfield_11433") or {}).get("value", "")
    sprints = f.get("customfield_10020")
    if delivery_methodology != "Kanban":
        if not sprints or (isinstance(sprints, list) and len(sprints) == 0):
            score -= 0.5
            gaps.append("No sprint assigned")

    if not f.get("customfield_11102"):
        score -= 0.5
        gaps.append("Delivery Squad not assigned")
    if not platform_is_set(f):
        score -= 3
        blocker = True
        gaps.append("Platform not set (BLOCKER)")
    if not f.get("customfield_10014"):
        score -= 0.5
        gaps.append("Epic/parent link missing")

    dod = f.get("customfield_11673")
    if dod and field_status(dod) == "placeholder":
        score -= 0.5
        gaps.append("Definition of Done Notes contains placeholder text")

    score, gaps, blocker = _apply_develop_fix_version_blocker(f, score, gaps, blocker)

    score = max(0.0, score)
    score_int = round(score)
    if blocker:
        score_int = min(score_int, 4)

    return score_int, score_to_rag(score_int), gaps


def grade_bug(issue: dict) -> tuple[int, str, list[str]]:
    """Apply the Bug rubric. Returns (score, rag, gaps)."""
    f = issue.get("fields", {})
    score = 10.0
    gaps: list[str] = []
    blocker = False

    score, gaps, blocker = _apply_core_defect_rubric(f, score, gaps, blocker)

    if not f.get("customfield_10408"):
        score -= 0.5
        gaps.append("Environment not set")
    if not f.get("customfield_11499"):
        score -= 0.5
        gaps.append("Severity/Impact not set")
    if not platform_is_set(f):
        score -= 3
        blocker = True
        gaps.append("Platform not set (BLOCKER)")

    on_sprint = has_sprint_assigned(f)
    if on_sprint and not story_points_estimated(f, for_bug=True):
        score -= 3
        blocker = True
        gaps.append("On sprint with no Story Points estimated (BLOCKER)")
    elif not story_points_estimated(f, for_bug=True):
        score -= 0.5
        gaps.append("Story points not estimated")

    delivery_methodology = (f.get("customfield_11433") or {}).get("value", "")
    sprints = f.get("customfield_10020")
    if delivery_methodology != "Kanban":
        if not sprints or (isinstance(sprints, list) and len(sprints) == 0):
            score -= 0.5
            gaps.append("No sprint assigned")

    if not f.get("customfield_11102"):
        score -= 0.5
        gaps.append("Delivery Squad not assigned")
    if not f.get("customfield_10014"):
        score -= 0.5
        gaps.append("Epic/parent link missing")

    score, gaps, blocker = _apply_develop_fix_version_blocker(f, score, gaps, blocker)

    score = max(0.0, score)
    score_int = round(score)
    if blocker:
        score_int = min(score_int, 4)

    return score_int, score_to_rag(score_int), gaps


def grade_buglet(
    issue: dict,
    *,
    parent_fields: dict | None = None,
) -> tuple[int, str, list[str]]:
    """
    Apply the Buglet rubric (level -1 test-execution defect under a Story).

    Delivery Squad, fixVersion, and Platform are inherited from the parent Story
    and are not scored on the Buglet.
    """
    f = issue.get("fields", {})
    score = 10.0
    gaps: list[str] = []
    blocker = False

    score, gaps, blocker = _apply_core_defect_rubric(f, score, gaps, blocker)

    parent_key = (f.get("parent") or {}).get("key")
    if not parent_key:
        score -= 3
        blocker = True
        gaps.append("Parent Story not linked (BLOCKER)")

    if not environment_includes_tst(f):
        score -= 0.5
        if environment_values(f):
            gaps.append("Environment should include TST (test execution default)")
        else:
            gaps.append("Environment not set (expected TST)")

    if not f.get("customfield_11499"):
        score -= 0.5
        gaps.append("Severity/Impact not set")

    score, gaps, blocker = _apply_develop_fix_version_blocker(
        f, score, gaps, blocker, parent_fields=parent_fields
    )

    score = max(0.0, score)
    score_int = round(score)
    if blocker:
        score_int = min(score_int, 4)

    return score_int, score_to_rag(score_int), gaps


def grade_testlet(
    issue: dict,
    *,
    parent_fields: dict | None = None,
) -> tuple[int, str, list[str]]:
    """
    Apply the Testlet rubric (level -1 test case under a Story).

    Delivery Squad, Platform, and sprint context are inherited from the parent Story
    and are not scored on the Testlet.
    """
    f = issue.get("fields", {})
    score = 10.0
    gaps: list[str] = []
    blocker = False

    score, gaps, blocker = _apply_core_testlet_rubric(f, score, gaps, blocker)

    summary = f.get("summary") or ""
    if summary_has_ac_suffix(summary):
        score -= 0.5
        gaps.append("Summary uses (AC-##) suffix; map ACs in Test Description instead")
    if summary_has_bad_dash(summary):
        score -= 0.5
        gaps.append("Summary contains em dash or en dash; use pipe separator")

    parent_key = (f.get("parent") or {}).get("key")
    if not parent_key:
        score -= 3
        blocker = True
        gaps.append("Parent Story not linked (BLOCKER)")

    if not f.get("customfield_10145"):
        score -= 0.5
        gaps.append("Test Types not set")

    if not environment_includes_tst(f):
        if environment_values(f):
            gaps.append("Environment should include TST (test execution default)")
        else:
            gaps.append("Environment not set (expected TST)")
        score -= 0.5

    status_name = (f.get("status") or {}).get("name", "")
    if status_name in TESTLET_EXECUTED_STATUSES:
        if not has_execution_evidence(f):
            score -= 2.0
            blocker = True
            gaps.append(
                f"Status is {status_name} but no execution evidence in comments or "
                "attachments (BLOCKER)"
            )
        if not f.get("assignee"):
            score -= 0.5
            gaps.append("Assignee not set (assign owner before execution)")

    score, gaps, blocker = _apply_develop_fix_version_blocker(
        f, score, gaps, blocker, parent_fields=parent_fields
    )

    score = max(0.0, score)
    score_int = round(score)
    if blocker:
        score_int = min(score_int, 4)

    return score_int, score_to_rag(score_int), gaps


def grade_issue(issue: dict) -> dict[str, Any]:
    """
    Grade a Jira issue dict (must include fields.issuetype.name).

    Returns a result dict suitable for MCP responses and Jira writes.
    """
    key = issue.get("key", "")
    issue_type = issue["fields"]["issuetype"]["name"]

    if issue_type == "Story":
        score, rag, gaps = grade_story(issue)
    elif issue_type == "Bug":
        score, rag, gaps = grade_bug(issue)
    elif issue_type == "Buglet":
        score, rag, gaps = grade_buglet(
            issue,
            parent_fields=issue.get("_parent_fields"),
        )
    elif issue_type == "Testlet":
        score, rag, gaps = grade_testlet(
            issue,
            parent_fields=issue.get("_parent_fields"),
        )
    else:
        raise ValueError(
            f"Hygiene grading supports Story, Bug, Buglet, and Testlet only, not "
            f"'{issue_type}' ({key})"
        )

    detail = ". ".join(gaps) if gaps else "No gaps found"
    return {
        "key": key,
        "issue_type": issue_type,
        "score": score,
        "score_display": f"{score}/10",
        "rag": rag,
        "gaps": gaps,
        "detail": detail,
        "has_blocker": any("(BLOCKER)" in g for g in gaps),
    }


def format_hygiene_detail_entry(
    result: dict[str, Any], assessed_at: datetime | None = None
) -> str:
    """Format one timestamped hygiene assessment for the detail history."""
    if assessed_at is None:
        assessed_at = datetime.now().astimezone()
    elif assessed_at.tzinfo is None:
        assessed_at = assessed_at.astimezone()
    timestamp = assessed_at.strftime("%Y-%m-%d %H:%M:%S")
    return f"[{timestamp}] {result['score_display']} {result['rag']} - {result['detail']}"


def append_hygiene_detail(
    existing_detail: Any,
    result: dict[str, Any],
    assessed_at: datetime | None = None,
) -> str:
    """Append the new timestamped assessment without rewriting existing history."""
    new_entry = format_hygiene_detail_entry(result, assessed_at)
    existing_text = existing_detail if isinstance(existing_detail, str) else extract_text(existing_detail)
    existing_text = existing_text.strip()
    if not existing_text:
        return new_entry
    return f"{existing_text}\n\n{new_entry}"


def hygiene_fields_for_write(
    result: dict[str, Any],
    existing_detail: Any = None,
    assessed_at: datetime | None = None,
) -> tuple[dict, dict]:
    """
    Return (v2_fields, v3_fields) for update_issue calls.
    """
    v2 = {
        HYGIENE_SCORE_FIELD: result["score_display"],
        HYGIENE_DETAIL_FIELD: append_hygiene_detail(existing_detail, result, assessed_at),
    }
    v3 = {HYGIENE_RAG_FIELD: {"id": RAG_IDS[result["rag"]]}}
    return v2, v3


def iter_user_picker(field_value: Any) -> list[dict[str, Any]]:
    """Yield user dicts from a Jira user or multi-user picker field."""
    if not field_value:
        return []
    if isinstance(field_value, dict):
        return [field_value] if field_value.get("accountId") else []
    if isinstance(field_value, list):
        return [u for u in field_value if isinstance(u, dict) and u.get("accountId")]
    return []


def first_whanau_user(
    fields: dict[str, Any],
    parent_fields: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """First Whanau role user on the issue, else on the parent Story."""
    for source in (fields, parent_fields or {}):
        for field_id in WHANAU_USER_FIELDS:
            users = iter_user_picker(source.get(field_id))
            if users:
                return users[0]
    return None


def hygiene_red_comment_mentions(
    fields: dict[str, Any],
    issue_type: str,
    *,
    parent_fields: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Resolve @mention targets for a Red hygiene comment.

    Prefer assignee; otherwise the first Whanau role user (issue, then parent Story).
    Bug, Buglet, and Testlet also mention the reporter.
    """
    mentions: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(user: dict[str, Any] | None) -> None:
        if not user:
            return
        account_id = user.get("accountId")
        if not account_id or account_id in seen:
            return
        seen.add(account_id)
        mentions.append(user)

    assignee = fields.get("assignee")
    if assignee and assignee.get("accountId"):
        add(assignee)
    else:
        add(first_whanau_user(fields, parent_fields))

    if issue_type in HYGIENE_RAISE_MENTION_TYPES:
        for user in iter_user_picker(fields.get("reporter")):
            add(user)
            break

    return mentions


def build_hygiene_red_comment_adf(
    detail_text: str,
    mentions: list[dict[str, Any]],
) -> dict[str, Any]:
    """ADF body for a Red hygiene comment (gap detail without timestamp)."""
    inline: list[dict[str, Any]] = []
    for user in mentions:
        display = user.get("displayName") or "user"
        inline.append(
            {
                "type": "mention",
                "attrs": {
                    "id": user["accountId"],
                    "text": f"@{display}",
                    "accessLevel": "",
                },
            }
        )
        inline.append({"type": "text", "text": " "})
    inline.append({"type": "text", "text": detail_text})
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": inline}],
    }


def _resolve_parent_fields_for_hygiene_comment(
    jira: Any,
    fields: dict[str, Any],
) -> dict[str, Any] | None:
    """Load parent Story Whanau/assignee when the child issue has neither."""
    if (fields.get("assignee") or {}).get("accountId"):
        return None
    if any(iter_user_picker(fields.get(field_id)) for field_id in WHANAU_USER_FIELDS):
        return None
    parent_key = (fields.get("parent") or {}).get("key")
    if not parent_key:
        return None
    parent_issue = jira.get_issue(
        parent_key,
        fields=list(WHANAU_USER_FIELDS) + ["assignee"],
    )
    return parent_issue.get("fields")


def post_hygiene_red_comment(
    jira: Any,
    key: str,
    result: dict[str, Any],
    *,
    issue: dict | None = None,
) -> bool:
    """Post a Red RAG hygiene gap comment. Returns True if a comment was created."""
    if result.get("rag") != "Red":
        return False

    detail_text = result.get("detail") or "No gaps found"
    parent_fields: dict[str, Any] | None = None

    if issue:
        fields = issue.get("fields") or {}
        issue_type = (fields.get("issuetype") or {}).get("name", result.get("issue_type", ""))
        parent_fields = issue.get("_parent_fields")
        if parent_fields is None:
            parent_fields = _resolve_parent_fields_for_hygiene_comment(jira, fields)
    else:
        fetch_fields = list(
            {
                HYGIENE_DETAIL_FIELD,
                "issuetype",
                "parent",
                *HYGIENE_COMMENT_USER_FIELDS,
            }
        )
        loaded = jira.get_issue(key, fields=fetch_fields)
        fields = loaded.get("fields") or {}
        issue_type = (fields.get("issuetype") or {}).get("name", result.get("issue_type", ""))
        parent_fields = _resolve_parent_fields_for_hygiene_comment(jira, fields)

    mentions = hygiene_red_comment_mentions(
        fields,
        issue_type,
        parent_fields=parent_fields,
    )
    adf_body = build_hygiene_red_comment_adf(detail_text, mentions)
    jira.add_comment(key, adf_body)
    return True


def write_hygiene_to_jira(
    jira: Any,
    key: str,
    result: dict[str, Any],
    *,
    issue: dict | None = None,
) -> dict[str, Any]:
    """
    Write hygiene score/RAG and append a timestamped detail assessment to Jira.

    When RAG is Red, also posts a Jira comment with gap detail (no timestamp) and
    @mentions for assignee or Whanau, plus reporter on Bug/Buglet/Testlet.

    Returns metadata about the write (e.g. hygiene_red_comment_posted).
    """
    current_issue = jira.get_issue(key, fields=[HYGIENE_DETAIL_FIELD])
    existing_detail = (current_issue.get("fields") or {}).get(HYGIENE_DETAIL_FIELD)
    v2, v3 = hygiene_fields_for_write(result, existing_detail=existing_detail)
    jira.update_issue(key, use_v2=True, fields=v2)
    jira.update_issue(key, use_v2=False, fields=v3)
    red_comment_posted = post_hygiene_red_comment(jira, key, result, issue=issue)
    return {"hygiene_red_comment_posted": red_comment_posted}


HYGIENE_FIELDS = {
    "score": HYGIENE_SCORE_FIELD,
    "detail": HYGIENE_DETAIL_FIELD,
    "rag": HYGIENE_RAG_FIELD,
}

DEFAULT_HYGIENE_ISSUE_TYPES = frozenset({"Story", "Bug", "Buglet", "Testlet"})


def hygiene_grade_fields() -> list[str]:
    return list(HYGIENE_GRADE_FIELDS)


def grade_issue_hygiene(issue: dict[str, Any]) -> dict[str, Any]:
    return grade_issue(issue)


def hygiene_fields_for_jira_write(
    result: dict[str, Any],
    *,
    existing_detail: Any = None,
    assessed_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return hygiene_fields_for_write(result, existing_detail=existing_detail, assessed_at=assessed_at)


def post_red_hygiene_comment(
    bridge: Any,
    issue_key: str,
    result: dict[str, Any],
    *,
    issue: dict[str, Any],
) -> bool:
    return post_hygiene_red_comment(bridge, issue_key, result, issue=issue)


HYGIENE_RAG_IDS = RAG_IDS


def supports_hygiene() -> bool:
    return True
