"""EPCE-6745 quarter scope JQL — global, exclusive lanes, board union, unassigned."""

from __future__ import annotations

DS = '"Delivery Squad[Select List (multiple choices)]"'
CT = '"Change Types[Select List (multiple choices)]"'
PF = '"Platform[Dropdown]"'

SCOPE_ISSUE_TYPES = ("Story", "Bug", "Spike")
BURN_ISSUE_TYPES = ("Story", "Bug")

EC_SQUADS = ('"Kākāriki Krew"', '"Kikorangi Tīma"', '"Waiporoporo"')
EC_SQUAD_VALUES = frozenset({"Kākāriki Krew", "Kikorangi Tīma", "Waiporoporo"})
EC_SQUAD_SPECS: tuple[tuple[str, str, str], ...] = (
    ("kakariki", "Kākāriki Krew", "Kākāriki"),
    ("kikorangi", "Kikorangi Tīma", "Kikorangi"),
    ("waiporoporo", "Waiporoporo", "Waiporoporo"),
)
EC_SQUAD_NAME_TO_SLUG = {name: slug for slug, name, _ in EC_SQUAD_SPECS}
LANE_KEYS = ("dataMigration", "integration", "educationCloud", "unassigned")
MULTI_PLATFORM_LINK = "multi platform delivery"
EXCLUDED_ANALYSIS_STATUSES = frozenset({"Rejected"})


def analysis_status_jql() -> str:
    """Statuses omitted from quarterly planned/burn/unpointed analyses."""
    return "status != Rejected"


def issue_excluded_from_analysis(issue: dict) -> bool:
    status = ((issue.get("fields") or {}).get("status") or {}).get("name") or ""
    return status in EXCLUDED_ANALYSIS_STATUSES


def _scoped_types_jql(
    quarter_filter: str,
    types: tuple[str, ...],
    *,
    extra: str = "",
) -> str:
    jql = (
        f"filter = {quarter_filter} AND issuetype in ({', '.join(types)}) "
        f"AND {analysis_status_jql()}"
    )
    if extra:
        jql = f"{jql} AND {extra}"
    return jql


def global_scope_jql(*, quarter_filter: str = "smart-current-quarter") -> str:
    return _scoped_types_jql(quarter_filter, SCOPE_ISSUE_TYPES)


def milestone_linked_epic_scope_jql(*, parent_keys_csv: str) -> str:
    """Children under milestone-linked epics — no quarter filter (EPCE-7122)."""
    types = ", ".join(SCOPE_ISSUE_TYPES)
    return (
        f"issuetype in ({types}) "
        f"AND {analysis_status_jql()} "
        f"AND parent in ({parent_keys_csv})"
    )


def global_burn_jql(*, quarter_filter: str = "smart-current-quarter") -> str:
    return _scoped_types_jql(quarter_filter, BURN_ISSUE_TYPES)


def _lane3_predicate() -> str:
    return f'({DS} = "Data Migration" OR {CT} = data)'


def _lane2_predicate() -> str:
    return f'({PF} = azure-integration-services OR issueLinkType = "multi platform delivery")'


def _lane1_predicate() -> str:
    squads = ", ".join(EC_SQUADS)
    return f"({DS} IN ({squads}))"


def _exclusive_lane_predicates() -> tuple[str, str, str]:
    """Priority L3 → L2 → L1 assignment (mutually exclusive)."""
    l3 = _lane3_predicate()
    l2 = f"{_lane2_predicate()} AND NOT {l3}"
    l1 = f"{_lane1_predicate()} AND NOT {l3} AND NOT {_lane2_predicate()}"
    return l1, l2, l3


def _unassigned_predicates() -> str:
    """Negated lane signals (De Morgan). Jira may still under-count vs Python classify."""
    return (
        f"NOT {_lane3_predicate()} "
        f"AND NOT {_lane2_predicate()} "
        f"AND NOT {_lane1_predicate()}"
    )


def _issue_link_values(issue: dict) -> list[dict]:
    return (issue.get("fields") or {}).get("issuelinks") or []


def has_multi_platform_link(issue: dict) -> bool:
    for link in _issue_link_values(issue):
        link_type = link.get("type") or {}
        if (link_type.get("name") or "") == MULTI_PLATFORM_LINK:
            return True
    return False


def _values_from_field(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                out.append(str(item.get("value") or item.get("name") or ""))
            else:
                out.append(str(item))
        return [value for value in out if value]
    if isinstance(raw, dict):
        value = str(raw.get("value") or raw.get("name") or "")
        return [value] if value else []
    return [str(raw)]


def classify_exclusive_lane(
    issue: dict,
    *,
    delivery_squad_field: str,
    change_types_field: str,
    platform_field: str,
) -> str:
    """Priority L3 → L2 → L1 → unassigned (avoids Jira NOT/OR miscounts)."""
    fields = issue.get("fields") or {}
    squads = _values_from_field(fields.get(delivery_squad_field))
    change_types = {value.lower() for value in _values_from_field(fields.get(change_types_field))}
    platforms = _values_from_field(fields.get(platform_field))

    if "Data Migration" in squads or "data" in change_types:
        return "dataMigration"
    if "azure-integration-services" in platforms or has_multi_platform_link(issue):
        return "integration"
    if EC_SQUAD_VALUES.intersection(squads):
        return "educationCloud"
    return "unassigned"


def lane3_data_jql(*, quarter_filter: str = "smart-current-quarter") -> str:
    _, _, l3 = _exclusive_lane_predicates()
    return _scoped_types_jql(quarter_filter, BURN_ISSUE_TYPES, extra=l3)


def lane2_integration_jql(*, quarter_filter: str = "smart-current-quarter") -> str:
    _, l2, _ = _exclusive_lane_predicates()
    return _scoped_types_jql(quarter_filter, BURN_ISSUE_TYPES, extra=l2)


def lane1_education_cloud_jql(*, quarter_filter: str = "smart-current-quarter") -> str:
    l1, _, _ = _exclusive_lane_predicates()
    return _scoped_types_jql(quarter_filter, BURN_ISSUE_TYPES, extra=l1)


def board_union_jql() -> str:
    """Union of live filters for boards 893, 992, 1725, 3032, 2730 (no quarter filter)."""
    return f"""(
  (
    project = EPCE AND filter = smart-project-epce AND type != Incident
    AND {DS} = "Kākāriki Krew"
  ) OR (
    project = EPCE AND filter = smart-project-epce AND type NOT IN (Incident, Initiative)
    AND {DS} = "Kikorangi Tīma"
  ) OR (
    project = EPCE AND filter = smart-project-epce AND type NOT IN (Incident, Initiative)
    AND {DS} = Waiporoporo
  ) OR (
    project = EPCE AND ({PF} = azure-integration-services OR issueLinkType = "multi platform delivery")
  ) OR (
    project = EPCE AND (
      filter = smart-project-epce AND {DS} = "Data Migration"
      OR {CT} = data
    ) AND type != Initiative
  )
)"""


def unassigned_scope_jql(*, quarter_filter: str = "smart-current-quarter") -> str:
    """In global quarter scope but not visible on any delivery board (hygiene filter)."""
    return (
        f"{_scoped_types_jql(quarter_filter, SCOPE_ISSUE_TYPES)} "
        f"AND NOT ({board_union_jql()})"
    )


def unassigned_burn_jql(*, quarter_filter: str = "smart-current-quarter") -> str:
    return _scoped_types_jql(
        quarter_filter,
        BURN_ISSUE_TYPES,
        extra=_unassigned_predicates(),
    )


def planned_scope_jqls(*, quarter_filter: str = "smart-current-quarter") -> dict[str, str]:
    """Exclusive scope JQL for planned SP breakdown (includes Spike)."""
    l1, l2, l3 = _exclusive_lane_predicates()
    base = _scoped_types_jql(quarter_filter, SCOPE_ISSUE_TYPES)
    return {
        "dataMigration": f"{base} AND {l3}",
        "integration": f"{base} AND {l2}",
        "educationCloud": f"{base} AND {l1}",
        "unassigned": f"{base} AND {_unassigned_predicates()}",
    }


def education_cloud_squad_jqls(
    *,
    quarter_filter: str = "smart-current-quarter",
) -> dict[str, dict[str, str]]:
    """Per-squad scope and burn JQL within exclusive Education Cloud lane."""
    ec_scope = planned_scope_jqls(quarter_filter=quarter_filter)["educationCloud"]
    burn_types = ", ".join(BURN_ISSUE_TYPES)
    scope_types = ", ".join(SCOPE_ISSUE_TYPES)
    ec_burn_base = ec_scope.replace(f"issuetype in ({scope_types})", f"issuetype in ({burn_types})")
    out: dict[str, dict[str, str]] = {}
    for slug, squad_name, label in EC_SQUAD_SPECS:
        squad_filter = f'{DS} = "{squad_name}"'
        out[slug] = {
            "slug": slug,
            "label": label,
            "squadName": squad_name,
            "scopeJql": f"{ec_scope} AND {squad_filter}",
            "burnJql": f"{ec_burn_base} AND {squad_filter}",
        }
    return out
