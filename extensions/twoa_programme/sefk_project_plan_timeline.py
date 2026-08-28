"""SEFK integrated project plan Gantt — Phase → Sub-Phase → Work Stream → Epic."""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from artifact.atlassian import AtlassianAdapter

from extensions.twoa_programme.epic_timeline import EPIC_CHART_PX_PER_DAY
from extensions.twoa_programme.field_maps import field_aliases
from extensions.twoa_programme.github_pages_nav import BREADCRUMB_CSS
from extensions.twoa_programme.milestone_scope_chart import (
    DTRAIN_PHASE_FILL,
    aggregate_milestone_scope,
    chart_dtrain_phases,
)
from extensions.twoa_programme.sefk_scope import (
    resolve_sefk_issue_dtrain_phase,
    rollup_sefk_epic_phases,
    sefk_epic_scope_jql,
)
from extensions.twoa_programme.milestone_timeline import MILESTONE_TIMELINE_EXTRA_CSS
from extensions.twoa_programme.quarter_scope import issue_excluded_from_analysis
from extensions.twoa_programme.quarterly_dashboard_constants import ATL, JIRA_SERVER, SVG_FONT
from extensions.twoa_programme.quarterly_dashboard_markup import REPORT_CSS, _svg_embedded_title
from extensions.twoa_programme.quarterly_dashboard_svg_core import (
    QUARTERLY_REPORT_MAX_SVG_WIDTH,
    QUARTERLY_REPORT_MIN_PLOT_WIDTH,
    _append_today_marker,
    _chart_today_in_quarter,
    _svg_x_axis_labels,
    _svg_x_bottom_margin,
)
from extensions.twoa_programme.sef_block_scope import (
    build_block_scope_rollups,
    linked_scope_targets,
)
from extensions.twoa_programme.sef_project_plan_timeline import (
    BAR_OPACITY,
    BLOCK_BORDER_WIDTH,
    BLOCK_GAP,
    BLOCK_PAD_Y,
    CALENDAR_TOP,
    CHAPTER_BAR_HEIGHT,
    CHAPTER_ROW_HEIGHT,
    LABEL_MAX_CHARS,
    LABEL_PAD_X,
    LABEL_WIDTH,
    PHASE_BAR_HEIGHT,
    PHASE_GAP,
    PHASE_ROW_HEIGHT,
    RIGHT_PAD,
    SCOPE_OVERLAY_OPACITY,
    START_DATE_FIELD,
    STREAM_BAR_HEIGHT,
    STREAM_ROW_HEIGHT,
    SUB_LABEL_INDENT,
    _append_label_link,
    _append_label_text,
    _append_timeline_bar,
    _bar_tooltip,
    _child_keys_for_types,
    _fetch_children,
    _issue_start_sort_key,
    _issue_timeline_row,
    _issue_type_name,
    _sort_sibling_keys,
    _label_with_duration_metrics,
    _parse_day,
    _truncate_label,
)
from extensions.twoa_programme.sefk_project_plan_reporting import (
    SefkProjectPlanReportingConfig,
    discover_phase_hub_issues,
    resolve_scope_filter_jql,
)
from extensions.twoa_programme.jira_search import search_all

_REPO_ROOT = Path(__file__).resolve().parents[2]
EPIC_ROW_HEIGHT = 22
EPIC_BAR_HEIGHT = EPIC_ROW_HEIGHT - 4
EPIC_LABEL_INDENT = 52
DTRAIN_BASE_FILL = ATL["grid"]
SUB_PHASE_BAR_HEIGHT = CHAPTER_BAR_HEIGHT
SUB_PHASE_ROW_HEIGHT = CHAPTER_ROW_HEIGHT
WORK_STREAM_ROW_HEIGHT = STREAM_ROW_HEIGHT
WORK_STREAM_BAR_HEIGHT = STREAM_BAR_HEIGHT
SEFK_LABEL_WIDTH_CAP = 420
SEFK_WORK_STREAM_LABEL_MAX_CHARS = 32
SEFK_EPIC_LABEL_MAX_CHARS = 36

SEFK_EXTRA_CSS = """
.chart-wrap-sefk.chart-wrap-timeline {
  max-height: none;
  overflow-x: auto;
  overflow-y: visible;
}
.chart-wrap-sefk svg {
  display: block;
  width: 100%;
  height: auto;
  min-width: 0;
}
.chart-wrap-sefk svg a text { text-decoration: none; }
.chart-wrap-sefk svg a:hover text { text-decoration: underline; }
.chart-key--dtrain .chart-key-phase-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin: 8px 0 4px;
}
.chart-key--dtrain .chart-key-phase-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}
.chart-wrap-sefk svg text[id^="sefk-chev-"] {
  cursor: pointer;
  user-select: none;
}
"""

SEFK_COLLAPSE_SCRIPT = """
(function () {
  'use strict';

  function cfg(name, fallback) {
    var el = document.getElementById('sefk-cfg');
    if (!el) return fallback;
    var raw = el.getAttribute('data-' + name);
    var n = parseFloat(raw);
    return isFinite(n) ? n : fallback;
  }

  var BLOCK_PAD_Y = cfg('block-pad-y', 10);
  var SUB_PHASE_ROW_H = cfg('sub-phase-row-h', 36);
  var WORK_STREAM_ROW_H = cfg('work-stream-row-h', 24);
  var EPIC_ROW_H = cfg('epic-row-h', 22);

  function parseManifest(attr) {
    var el = document.getElementById('sefk-cm-sp');
    if (!el) return [];
    try {
      return JSON.parse((el.getAttribute(attr) || '[]').replace(/&quot;/g, '"'));
    } catch (_err) {
      return [];
    }
  }

  function resizeSvg(svg, delta) {
    if (!svg || !isFinite(delta) || delta === 0) return;
    var vb = (svg.getAttribute('viewBox') || '0 0 0 0').split(' ').map(Number);
    if (vb.length < 4) return;
    vb[3] = Math.max(100, vb[3] + delta);
    svg.setAttribute('viewBox', vb.join(' '));
    var h = parseFloat(svg.getAttribute('height') || '0');
    if (isFinite(h)) svg.setAttribute('height', String(Math.max(100, h + delta)));
  }

  function isHidden(node) {
    return !node || node.getAttribute('visibility') === 'hidden' || node.style.display === 'none';
  }

  function workStreamBlockHeight(wsKey) {
    var sub = document.getElementById('sefk-sub-ws-' + wsKey);
    var epicH = parseInt((document.getElementById('sefk-ws-' + wsKey) || {}).getAttribute('data-epic-h') || '0', 10) || 0;
    if (isHidden(sub)) return WORK_STREAM_ROW_H;
    return WORK_STREAM_ROW_H + epicH;
  }

  function reflowSubPhaseContent(spKey) {
    var border = document.getElementById('sefk-bd-' + spKey);
    var spGroup = document.getElementById('sefk-sp-' + spKey);
    var sub = document.getElementById('sefk-sub-sp-' + spKey);
    if (!border || !spGroup || !sub) return 0;

    var y = BLOCK_PAD_Y + SUB_PHASE_ROW_H;
    var wsKeys = (sub.getAttribute('data-work-stream-keys') || '').split(',').filter(Boolean);
    wsKeys.forEach(function (wsKey) {
      var wsGroup = document.getElementById('sefk-ws-' + wsKey);
      if (!wsGroup || isHidden(wsGroup)) return;
      wsGroup.setAttribute('transform', 'translate(0,' + y + ')');
      y += workStreamBlockHeight(wsKey);
    });

    var collapsedH = parseInt(spGroup.getAttribute('data-collapsed-h'), 10) || (BLOCK_PAD_Y * 2 + SUB_PHASE_ROW_H);
    var subHidden = isHidden(sub);
    var newH = subHidden ? collapsedH : (y + BLOCK_PAD_Y);
    border.setAttribute('height', String(newH));

    var subH = Math.max(0, newH - collapsedH);
    spGroup.setAttribute('data-sub-h', String(subH));
    return newH;
  }

  function reflowSubPhaseBlocks() {
    var chapters = parseManifest('data-chapters');
    var cumulativeShift = 0;
    chapters.forEach(function (ch) {
      var g = document.getElementById('sefk-sp-' + ch.key);
      if (!g) return;
      g.setAttribute('transform', cumulativeShift ? ('translate(0,' + cumulativeShift + ')') : 'translate(0,0)');
      var sub = document.getElementById('sefk-sub-sp-' + ch.key);
      var collapsed = isHidden(sub);
      if (collapsed) cumulativeShift -= parseInt(ch.subH, 10) || 0;
    });
  }

  window.sefkToggleWorkStream = function (evt, wsKey) {
    if (evt) evt.stopPropagation();
    var sub = document.getElementById('sefk-sub-ws-' + wsKey);
    var chev = document.getElementById('sefk-chev-ws-' + wsKey);
    var wsGroup = document.getElementById('sefk-ws-' + wsKey);
    if (!sub || !wsGroup) return;

    var spKey = (wsGroup.getAttribute('data-sp-key') || '').trim();
    var epicH = parseInt(wsGroup.getAttribute('data-epic-h'), 10) || 0;
    var open = isHidden(sub);
    var delta = open ? epicH : -epicH;

    if (open) {
      sub.setAttribute('visibility', 'visible');
      sub.style.display = '';
      if (chev) chev.textContent = '\\u25BC';
    } else {
      sub.setAttribute('visibility', 'hidden');
      sub.style.display = 'none';
      if (chev) chev.textContent = '\\u25B6';
    }

    if (spKey) {
      reflowSubPhaseContent(spKey);
      reflowSubPhaseBlocks();
      var chapters = parseManifest('data-chapters');
      var entry = chapters.find(function (c) { return c.key === spKey; });
      if (entry) entry.subH = parseInt((document.getElementById('sefk-sp-' + spKey) || {}).getAttribute('data-sub-h') || '0', 10) || entry.subH;
    }

    var svg = wsGroup.closest('svg');
    resizeSvg(svg, delta);
  };

  window.sefkToggleSubPhase = function (evt, spKey) {
    if (evt) evt.stopPropagation();
    var sub = document.getElementById('sefk-sub-sp-' + spKey);
    var border = document.getElementById('sefk-bd-' + spKey);
    var chev = document.getElementById('sefk-chev-sp-' + spKey);
    var spGroup = document.getElementById('sefk-sp-' + spKey);
    if (!sub || !spGroup) return;

    var open = isHidden(sub);
    var subH = parseInt(spGroup.getAttribute('data-sub-h'), 10) || 0;
    var collapsedH = parseInt(spGroup.getAttribute('data-collapsed-h'), 10) || 0;

    if (open) {
      sub.setAttribute('visibility', 'visible');
      sub.style.display = '';
      if (chev) chev.textContent = '\\u25BC';
      if (border) border.setAttribute('height', String(collapsedH + subH));
    } else {
      sub.setAttribute('visibility', 'hidden');
      sub.style.display = 'none';
      if (chev) chev.textContent = '\\u25B6';
      if (border) border.setAttribute('height', String(collapsedH));
    }

    reflowSubPhaseBlocks();
    var svg = spGroup.closest('svg');
    resizeSvg(svg, open ? subH : -subH);
  };

  document.querySelectorAll('.chart-wrap-sefk').forEach(function (wrap) {
    wrap.addEventListener('wheel', function (evt) {
      if (wrap.scrollWidth <= wrap.clientWidth) return;
      var useHorizontal = evt.shiftKey || Math.abs(evt.deltaX) > Math.abs(evt.deltaY);
      if (!useHorizontal && Math.abs(evt.deltaY) > 0.01) useHorizontal = true;
      if (!useHorizontal) return;
      var delta = Math.abs(evt.deltaX) > 0.01 ? evt.deltaX : evt.deltaY;
      wrap.scrollLeft += delta;
      evt.preventDefault();
    }, { passive: false });
  });
})();
"""


def _sefk_truncate_label(text: str, max_chars: int = LABEL_MAX_CHARS) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max_chars - 1]}…"


def _sefk_work_stream_display_label(
    work_stream: dict[str, Any],
    sub_phase: dict[str, Any],
) -> str:
    summary = str(work_stream.get("summary") or work_stream.get("key") or "").strip()
    parent = str(sub_phase.get("summary") or "").strip()
    prefix = f"{parent} | "
    if parent and summary.lower().startswith(prefix.lower()):
        summary = summary[len(prefix) :].strip()
    return summary.replace("-", " ").replace("_", " ")


def _sefk_label_column_width(phases: list[dict[str, Any]]) -> float:
    labels: list[str] = []
    for phase in phases:
        phase_label = _label_with_duration_metrics(
            str(phase.get("summary") or phase.get("key") or ""),
            phase,
        )
        labels.append(phase_label)
        for sub_phase in phase.get("subPhases") or []:
            sub_label = _label_with_duration_metrics(
                str(sub_phase.get("summary") or sub_phase.get("key") or ""),
                sub_phase,
            )
            labels.append(sub_label)
            for work_stream in sub_phase.get("workStreams") or []:
                ws_label = _label_with_duration_metrics(
                    _sefk_work_stream_display_label(work_stream, sub_phase),
                    work_stream,
                )
                labels.append(ws_label)
                for epic in work_stream.get("epics") or []:
                    labels.append(
                        _sefk_truncate_label(
                            str(epic.get("summary") or epic.get("key") or ""),
                            SEFK_EPIC_LABEL_MAX_CHARS,
                        )
                    )
    longest = max((len(item.strip()) for item in labels if str(item).strip()), default=0)
    dynamic = 24 + (longest * 6.4)
    return min(max(float(LABEL_WIDTH), dynamic), float(SEFK_LABEL_WIDTH_CAP))


def default_sefk_project_plan_timeline_path(repo_root: Path | None = None) -> Path:
    from extensions.twoa_programme.sefk_project_plan_reporting import load_sefk_project_plan_reporting_config

    root = repo_root or _REPO_ROOT
    config = load_sefk_project_plan_reporting_config(repo_root=root)
    return config.timeline_path(root)


def load_sefk_project_plan_timeline_payload(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_sefk_rows(phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for phase in phases:
        rows.append(phase)
        for sub_phase in phase.get("subPhases") or []:
            rows.append(sub_phase)
            for work_stream in sub_phase.get("workStreams") or []:
                rows.append(work_stream)
                rows.extend(work_stream.get("epics") or [])
    return rows


def resolve_chart_window_for_phases(phases: list[dict[str, Any]]) -> tuple[date, date]:
    starts: list[date] = []
    ends: list[date] = []
    for row in _iter_sefk_rows(phases):
        start = _parse_day(str(row.get("startDate") or "")[:10])
        end = _parse_day(str(row.get("endDate") or "")[:10])
        if start:
            starts.append(start)
        if end:
            ends.append(end)
    if not starts or not ends:
        return date(2026, 6, 1), date(2027, 12, 31)
    return min(starts), max(ends)


def _merge_scope_rollups(rollups: list[dict[str, Any]]) -> dict[str, Any] | None:
    active = [rollup for rollup in rollups if float(rollup.get("totalWeight") or 0) > 0]
    if not active:
        return None
    lanes = {str(index): rollup for index, rollup in enumerate(active)}
    return aggregate_milestone_scope(lanes)


def _bubble_scope_rollups(phases: list[dict[str, Any]]) -> None:
    for phase in phases:
        for sub_phase in phase.get("subPhases") or []:
            for work_stream in sub_phase.get("workStreams") or []:
                epic_rollups = [
                    epic.get("scopeRollup")
                    for epic in work_stream.get("epics") or []
                    if isinstance(epic.get("scopeRollup"), dict)
                ]
                merged = _merge_scope_rollups(epic_rollups)
                if merged and not work_stream.get("scopeRollup"):
                    work_stream["scopeRollup"] = merged
            ws_rollups = [
                work_stream.get("scopeRollup")
                for work_stream in sub_phase.get("workStreams") or []
                if isinstance(work_stream.get("scopeRollup"), dict)
            ]
            merged_sp = _merge_scope_rollups(ws_rollups)
            if merged_sp:
                sub_phase["scopeRollup"] = merged_sp
        sp_rollups = [
            sub_phase.get("scopeRollup")
            for sub_phase in phase.get("subPhases") or []
            if isinstance(sub_phase.get("scopeRollup"), dict)
        ]
        merged_phase = _merge_scope_rollups(sp_rollups)
        if merged_phase:
            phase["scopeRollup"] = merged_phase


def _linked_epic_keys(work_stream_issue: dict[str, Any], *, epic_issue_type: str) -> list[str]:
    keys: list[str] = []
    for target in linked_scope_targets(work_stream_issue):
        itype = str(((target.get("fields") or {}).get("issuetype") or {}).get("name") or "")
        key = str(target.get("key") or "")
        if key and itype == epic_issue_type:
            keys.append(key)
    return keys


def _attach_epic_scope_rollups(
    adapter: "AtlassianAdapter",
    epic_issues: dict[str, dict[str, Any]],
    *,
    config: SefkProjectPlanReportingConfig,
) -> dict[str, dict[str, Any]]:
    if not epic_issues:
        return {}
    epic_keys = sorted(epic_issues.keys())
    child_jql = sefk_epic_scope_jql(
        parent_keys_csv=", ".join(epic_keys),
        scope_issue_types=config.scope_issue_types,
    )
    scope_fields = ["parent", "issuetype", "status"]
    children = search_all(adapter, child_jql, scope_fields)
    return rollup_sefk_epic_phases(
        children,
        epic_keys=epic_keys,
        scope_issue_types=config.scope_issue_types,
        status_map=config.status_dtrain,
        skip_issue=issue_excluded_from_analysis,
    )


def _fetch_work_stream_epics(
    adapter: "AtlassianAdapter",
    config: SefkProjectPlanReportingConfig,
    *,
    work_stream_issue: dict[str, Any],
    fallback_start: date,
    fallback_end: date,
    fields: list[str],
    epic_issues: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    work_stream_key = str(work_stream_issue.get("key") or "")
    epic_rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for epic_issue in _fetch_children(
        adapter,
        parent_key=work_stream_key,
        issue_type=config.epic_issue_type,
        fields=fields,
    ):
        epic_key = str(epic_issue.get("key") or "")
        if not epic_key or epic_key in seen:
            continue
        seen.add(epic_key)
        epic_issues[epic_key] = epic_issue
        epic_rows.append(
            _issue_timeline_row(
                epic_issue,
                fallback_start=fallback_start,
                fallback_end=fallback_end,
                milestone_issue_types=(),
            )
        )

    for epic_key in _linked_epic_keys(work_stream_issue, epic_issue_type=config.epic_issue_type):
        if epic_key in seen:
            continue
        epic_issue_list = search_all(adapter, f"key = {epic_key}", fields)
        if not epic_issue_list:
            continue
        epic_issue = epic_issue_list[0]
        seen.add(epic_key)
        epic_issues[epic_key] = epic_issue
        epic_rows.append(
            _issue_timeline_row(
                epic_issue,
                fallback_start=fallback_start,
                fallback_end=fallback_end,
                milestone_issue_types=(),
            )
        )

    epic_rows.sort(key=lambda row: (str(row.get("startDate") or ""), str(row.get("key") or "")))
    return epic_rows


def _epics_for_work_stream(
    work_stream_key: str,
    work_stream_issue: dict[str, Any],
    *,
    by_key: dict[str, dict[str, Any]],
    children_of: dict[str, list[str]],
    config: SefkProjectPlanReportingConfig,
    fallback_start: date,
    fallback_end: date,
) -> list[dict[str, Any]]:
    epic_type = {config.epic_issue_type}
    epic_rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for epic_key in _child_keys_for_types(
        work_stream_key,
        children_of=children_of,
        by_key=by_key,
        issue_types=epic_type,
    ):
        if epic_key not in by_key:
            continue
        seen.add(epic_key)
        epic_rows.append(
            _issue_timeline_row(
                by_key[epic_key],
                fallback_start=fallback_start,
                fallback_end=fallback_end,
                milestone_issue_types=(),
            )
        )

    for epic_key in _linked_epic_keys(work_stream_issue, epic_issue_type=config.epic_issue_type):
        if epic_key in seen or epic_key not in by_key:
            continue
        seen.add(epic_key)
        epic_rows.append(
            _issue_timeline_row(
                by_key[epic_key],
                fallback_start=fallback_start,
                fallback_end=fallback_end,
                milestone_issue_types=(),
            )
        )

    epic_rows.sort(key=lambda row: (str(row.get("startDate") or ""), str(row.get("key") or "")))
    return epic_rows


def _build_sefk_hierarchy_from_flat(
    issues: list[dict[str, Any]],
    config: SefkProjectPlanReportingConfig,
    *,
    fallback_start: date,
    fallback_end: date,
) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build phase→subPhase→workStream→epic hierarchy from a flat issue list.

    Returns (phases, hub_keys, warnings, block_issues, epic_issues).
    """
    allowed_types = {
        config.phase_hub_issue_type,
        config.sub_phase_issue_type,
        config.work_stream_issue_type,
        config.epic_issue_type,
    }
    by_key: dict[str, dict[str, Any]] = {}
    for issue in issues:
        key = str(issue.get("key") or "")
        if not key:
            continue
        if _issue_type_name(issue) in allowed_types:
            by_key[key] = issue

    children_of: dict[str, list[str]] = {}
    for key, issue in by_key.items():
        parent_key = ((issue.get("fields") or {}).get("parent") or {}).get("key") or ""
        children_of.setdefault(parent_key, []).append(key)

    hub_keys = _sort_sibling_keys(
        [
            key
            for key, issue in by_key.items()
            if _issue_type_name(issue) == config.phase_hub_issue_type
        ],
        by_key,
    )
    warnings: list[str] = []
    sub_phase_types = {config.sub_phase_issue_type}
    work_stream_types = {config.work_stream_issue_type}

    block_issues: dict[str, dict[str, Any]] = {}
    epic_issues: dict[str, dict[str, Any]] = {}

    def make_work_stream(key: str) -> dict[str, Any]:
        block_issues[key] = by_key[key]
        row = _issue_timeline_row(
            by_key[key],
            fallback_start=fallback_start,
            fallback_end=fallback_end,
            milestone_issue_types=(),
        )
        row["epics"] = _epics_for_work_stream(
            key,
            by_key[key],
            by_key=by_key,
            children_of=children_of,
            config=config,
            fallback_start=fallback_start,
            fallback_end=fallback_end,
        )
        for epic in row["epics"]:
            epic_key = str(epic.get("key") or "")
            if epic_key in by_key:
                epic_issues[epic_key] = by_key[epic_key]
        return row

    def make_sub_phase(key: str) -> dict[str, Any]:
        block_issues[key] = by_key[key]
        row = _issue_timeline_row(
            by_key[key],
            fallback_start=fallback_start,
            fallback_end=fallback_end,
            milestone_issue_types=(),
        )
        ws_keys = _child_keys_for_types(
            key,
            children_of=children_of,
            by_key=by_key,
            issue_types=work_stream_types,
        )
        row["workStreams"] = [
            make_work_stream(ws_key)
            for ws_key in ws_keys
            if ws_key in by_key and _issue_type_name(by_key[ws_key]) in work_stream_types
        ]
        return row

    phases: list[dict[str, Any]] = []
    for hub_key in hub_keys:
        block_issues[hub_key] = by_key[hub_key]
        phase_row = _issue_timeline_row(
            by_key[hub_key],
            fallback_start=fallback_start,
            fallback_end=fallback_end,
            milestone_issue_types=(),
        )
        sub_phase_keys = _child_keys_for_types(
            hub_key,
            children_of=children_of,
            by_key=by_key,
            issue_types=sub_phase_types,
        )
        phase_row["subPhases"] = [
            make_sub_phase(sp_key)
            for sp_key in sub_phase_keys
            if sp_key in by_key and _issue_type_name(by_key[sp_key]) in sub_phase_types
        ]
        phases.append(phase_row)

    if not phases:
        warnings.append(
            f"Scope filter returned no {config.phase_hub_issue_type} (phase hub) issues."
        )
    return phases, hub_keys, warnings, block_issues, epic_issues


def _attach_rollups_to_phases(
    adapter: "AtlassianAdapter",
    phases: list[dict[str, Any]],
    *,
    config: SefkProjectPlanReportingConfig,
    block_issues: dict[str, dict[str, Any]],
    epic_issues: dict[str, dict[str, Any]],
) -> None:
    epic_rollups = _attach_epic_scope_rollups(
        adapter,
        epic_issues,
        config=config,
    )
    for phase in phases:
        for sub_phase in phase.get("subPhases") or []:
            for work_stream in sub_phase.get("workStreams") or []:
                for epic in work_stream.get("epics") or []:
                    epic_key = str(epic.get("key") or "")
                    rollup = epic_rollups.get(epic_key)
                    if rollup and float(rollup.get("totalWeight") or 0) > 0:
                        epic["scopeRollup"] = rollup

    story_points_field = field_aliases()["Story Points"]
    scope_rollups = build_block_scope_rollups(
        adapter,
        block_issues=block_issues,
        story_points_field=story_points_field,
    )
    for phase in phases:
        phase_key = str(phase.get("key") or "")
        if phase_key in scope_rollups:
            phase["scopeRollup"] = scope_rollups[phase_key]
        for sub_phase in phase.get("subPhases") or []:
            sub_phase_key = str(sub_phase.get("key") or "")
            if sub_phase_key in scope_rollups:
                sub_phase["scopeRollup"] = scope_rollups[sub_phase_key]
            for work_stream in sub_phase.get("workStreams") or []:
                work_stream_key = str(work_stream.get("key") or "")
                if work_stream_key in scope_rollups and not work_stream.get("scopeRollup"):
                    work_stream["scopeRollup"] = scope_rollups[work_stream_key]

    _bubble_scope_rollups(phases)


def _fetch_sefk_via_phase_hubs(
    adapter: "AtlassianAdapter",
    config: SefkProjectPlanReportingConfig,
    *,
    fields: list[str],
    scope_fields: list[str],
    fallback_start: date,
    fallback_end: date,
) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    hub_issues, hub_warnings = discover_phase_hub_issues(adapter, config, fields=fields)
    phases: list[dict[str, Any]] = []
    block_issues: dict[str, dict[str, Any]] = {}
    epic_issues: dict[str, dict[str, Any]] = {}

    for hub in hub_issues:
        hub_key = str(hub.get("key") or "")
        if not hub_key:
            continue
        block_issues[hub_key] = hub
        phase_row = _issue_timeline_row(
            hub,
            fallback_start=fallback_start,
            fallback_end=fallback_end,
            milestone_issue_types=(),
        )
        sub_phases_raw = _fetch_children(
            adapter,
            parent_key=hub_key,
            issue_type=config.sub_phase_issue_type,
            fields=scope_fields,
        )
        sub_phases_raw = sorted(sub_phases_raw, key=_issue_start_sort_key)
        sub_phases: list[dict[str, Any]] = []
        for sub_phase_issue in sub_phases_raw:
            sub_phase_key = str(sub_phase_issue.get("key") or "")
            block_issues[sub_phase_key] = sub_phase_issue
            sub_phase_row = _issue_timeline_row(
                sub_phase_issue,
                fallback_start=fallback_start,
                fallback_end=fallback_end,
                milestone_issue_types=(),
            )
            work_streams_raw = _fetch_children(
                adapter,
                parent_key=sub_phase_key,
                issue_type=config.work_stream_issue_type,
                fields=scope_fields,
            )
            work_streams_raw = sorted(work_streams_raw, key=_issue_start_sort_key)
            work_streams: list[dict[str, Any]] = []
            for work_stream_issue in work_streams_raw:
                work_stream_key = str(work_stream_issue.get("key") or "")
                block_issues[work_stream_key] = work_stream_issue
                work_stream_row = _issue_timeline_row(
                    work_stream_issue,
                    fallback_start=fallback_start,
                    fallback_end=fallback_end,
                    milestone_issue_types=(),
                )
                work_stream_row["epics"] = _fetch_work_stream_epics(
                    adapter,
                    config,
                    work_stream_issue=work_stream_issue,
                    fallback_start=fallback_start,
                    fallback_end=fallback_end,
                    fields=scope_fields,
                    epic_issues=epic_issues,
                )
                work_streams.append(work_stream_row)
            sub_phase_row["workStreams"] = work_streams
            sub_phases.append(sub_phase_row)
        phase_row["subPhases"] = sub_phases
        phases.append(phase_row)

    return phases, [str(issue.get("key") or "") for issue in hub_issues if issue.get("key")], hub_warnings, block_issues, epic_issues


def fetch_sefk_project_plan_timeline(
    adapter: "AtlassianAdapter",
    config: SefkProjectPlanReportingConfig,
) -> dict[str, Any]:
    fallback_start = date.fromisoformat(config.chart_window_start)
    fallback_end = date.fromisoformat(config.chart_window_end)
    fields = [
        "summary",
        "status",
        "issuetype",
        "created",
        "duedate",
        START_DATE_FIELD,
        "issuelinks",
        "parent",
    ]
    scope_fields = [*fields]

    scope_filter_jql = resolve_scope_filter_jql(adapter, config)
    warnings: list[str] = []
    hub_keys: list[str] = []

    if scope_filter_jql:
        all_issues = search_all(adapter, scope_filter_jql, scope_fields)
        phases, hub_keys, build_warnings, block_issues, epic_issues = _build_sefk_hierarchy_from_flat(
            all_issues,
            config,
            fallback_start=fallback_start,
            fallback_end=fallback_end,
        )
        warnings.extend(build_warnings)
    else:
        phases, hub_keys, hub_warnings, block_issues, epic_issues = _fetch_sefk_via_phase_hubs(
            adapter,
            config,
            fields=fields,
            scope_fields=scope_fields,
            fallback_start=fallback_start,
            fallback_end=fallback_end,
        )
        warnings.extend(hub_warnings)

    _attach_rollups_to_phases(
        adapter,
        phases,
        config=config,
        block_issues=block_issues,
        epic_issues=epic_issues,
    )
    window_start, window_end = resolve_chart_window_for_phases(phases)
    return {
        "projectKey": config.project_key,
        "pageTitle": config.page_title,
        "scopeFilterName": config.scope_filter_name,
        "chartWindowStart": window_start.isoformat(),
        "chartWindowEnd": window_end.isoformat(),
        "phaseHubKeys": hub_keys,
        "phases": phases,
        "warnings": warnings,
        "statusDtrain": dict(config.status_dtrain),
    }


def _sub_phase_block_height(sub_phase: dict[str, Any]) -> float:
    height = BLOCK_PAD_Y * 2 + SUB_PHASE_ROW_HEIGHT
    for work_stream in sub_phase.get("workStreams") or []:
        height += WORK_STREAM_ROW_HEIGHT + len(work_stream.get("epics") or []) * EPIC_ROW_HEIGHT
    return height


def _sefk_scope_has_story_points(scope: dict[str, Any]) -> bool:
    return float(scope.get("storyPoints") or 0) > 0


def _sefk_status_bar_fill(row: dict[str, Any], *, status_map: dict[str, str] | None = None) -> str:
    phase = resolve_sefk_issue_dtrain_phase(str(row.get("status") or ""), status_map=status_map)
    return DTRAIN_PHASE_FILL.get(phase, DTRAIN_PHASE_FILL.get("Unknown", "#c1c7d0"))


def _sefk_bar_fill(row: dict[str, Any], *, status_map: dict[str, str] | None = None) -> str:
    scope = row.get("scopeRollup")
    if isinstance(scope, dict) and _sefk_scope_has_story_points(scope):
        return DTRAIN_BASE_FILL
    return _sefk_status_bar_fill(row, status_map=status_map)


def _sefk_render_scope_overlay(row: dict[str, Any]) -> bool:
    scope = row.get("scopeRollup")
    return isinstance(scope, dict) and _sefk_scope_has_story_points(scope)


def sefk_dtrain_key_html() -> str:
    phase_items = []
    for phase in chart_dtrain_phases():
        phase_items.append(
            f'<span class="chart-key-phase-item">'
            f'<span class="legend-swatch" style="background:{DTRAIN_PHASE_FILL[phase]}"></span>'
            f"{html.escape(phase)}</span>"
        )
    return (
        '<div class="chart-key chart-key--dtrain">'
        '<p class="chart-key-title"><strong>Key</strong></p>'
        '<div class="chart-key-row">'
        '<span class="legend-swatch" style="background:#0052cc;opacity:0.85"></span> '
        "Schedule window (start date through due date)"
        "</div>"
        '<div class="chart-key-row">'
        "Scope bars: D-Train phases left to right with "
        '<span class="legend-swatch" style="background:#00875a"></span> Drive '
        "through "
        '<span class="legend-swatch" style="background:#de350b"></span> Dream '
        "(matches milestone report palette)"
        "</div>"
        f'<div class="chart-key-phase-strip">{"".join(phase_items)}</div>'
        f'<div class="chart-key-row">'
        f"Items without scoped Story Points use a solid bar coloured by their Jira status "
        f"(mapped to D-Train phase above)."
        f"</div>"
        "</div>"
    )


def sefk_project_plan_timeline_svg(payload: dict[str, Any]) -> str:
    phases = payload.get("phases") or []
    if not phases:
        return '<p class="footnote">No phases. Run fetch_sefk_project_plan_timeline.py --write.</p>'

    status_map = dict(payload.get("statusDtrain") or {})

    def _append_sefk_bar(
        parts_list: list[str],
        *,
        row: dict[str, Any],
        role: str,
        x1: float,
        bar_y: float,
        bar_w: float,
        bar_h: float,
    ) -> None:
        _append_timeline_bar(
            parts_list,
            row=row,
            x1=x1,
            bar_y=bar_y,
            bar_w=bar_w,
            bar_h=bar_h,
            fill=_sefk_bar_fill(row, status_map=status_map),
            opacity=BAR_OPACITY,
            role=role,
            scope_overlay_opacity=SCOPE_OVERLAY_OPACITY,
            render_scope_overlay=_sefk_render_scope_overlay(row),
        )

    x_min, x_max = resolve_chart_window_for_phases(phases)
    span_days = max((x_max - x_min).days, 1)
    px_per_day = EPIC_CHART_PX_PER_DAY
    plot_width = max(
        QUARTERLY_REPORT_MIN_PLOT_WIDTH,
        min(int(span_days * px_per_day), QUARTERLY_REPORT_MAX_SVG_WIDTH),
    )
    plot_left = _sefk_label_column_width(phases)
    plot_right = plot_left + plot_width
    svg_width = plot_right + RIGHT_PAD

    plot_height = 0.0
    for phase_index, phase in enumerate(phases):
        if phase_index > 0:
            plot_height += PHASE_GAP
        plot_height += PHASE_ROW_HEIGHT
        for sub_phase_index, sub_phase in enumerate(phase.get("subPhases") or []):
            if sub_phase_index > 0:
                plot_height += BLOCK_GAP
            plot_height += _sub_phase_block_height(sub_phase)

    calendar_top = CALENDAR_TOP
    plot_top = calendar_top + 28
    plot_bottom = plot_top + plot_height
    bottom_margin = _svg_x_bottom_margin()
    svg_height = plot_bottom + bottom_margin

    def x_for(day: date) -> float:
        return plot_left + ((day - x_min).days / span_days) * plot_width

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width:.0f}" '
        f'height="{svg_height:.0f}" viewBox="0 0 {svg_width:.0f} {svg_height:.0f}">',
        "<defs>",
        f'<clipPath id="sef-plan-label-col">'
        f'<rect x="0" y="{plot_top:.1f}" width="{plot_left - 8:.1f}" height="{plot_height:.1f}"/>'
        f"</clipPath>",
        f'<clipPath id="sef-plan-label-col-x">'
        f'<rect x="0" y="-10000" width="{plot_left - 8:.1f}" height="20000"/>'
        f"</clipPath>",
        "</defs>",
    ]
    parts.append(
        f'<line x1="{plot_left:.1f}" y1="{plot_top:.1f}" x2="{plot_right:.1f}" y2="{plot_top:.1f}" '
        f'stroke="{ATL["line"]}" stroke-width="1"/>'
    )

    y_cursor = plot_top
    sub_phase_manifest: list[dict[str, Any]] = []
    for phase_index, phase in enumerate(phases):
        if phase_index > 0:
            y_cursor += PHASE_GAP
            parts.append(
                f'<rect x="0" y="{y_cursor - PHASE_GAP / 2:.1f}" width="{plot_right:.1f}" '
                f'height="{PHASE_GAP:.1f}" fill="{ATL["page"]}"/>'
            )

        phase_key = str(phase.get("key") or "")
        phase_label = str(phase.get("summary") or phase_key)
        phase_start = date.fromisoformat(str(phase.get("startDate"))[:10])
        phase_end = date.fromisoformat(str(phase.get("endDate"))[:10])
        phase_row_cy = y_cursor + PHASE_ROW_HEIGHT / 2
        phase_x1 = x_for(phase_start)
        phase_x2 = x_for(phase_end)
        phase_bar_w = max(phase_x2 - phase_x1, 2.0)
        phase_bar_y = y_cursor + (PHASE_ROW_HEIGHT - PHASE_BAR_HEIGHT) / 2

        if phase_key:
            _append_sefk_bar(
                parts,
                row=phase,
                x1=phase_x1,
                bar_y=phase_bar_y,
                bar_w=phase_bar_w,
                bar_h=PHASE_BAR_HEIGHT,
                role="phase-bar",
            )
            _append_label_link(
                parts,
                text=_label_with_duration_metrics(phase_label, phase),
                x=LABEL_PAD_X,
                y_center=phase_row_cy,
                url=f"{JIRA_SERVER}/browse/{html.escape(phase_key)}",
                tooltip=_bar_tooltip(phase),
                font_size=13,
                font_weight="700",
            )
        y_cursor += PHASE_ROW_HEIGHT

        for sub_phase_index, sub_phase in enumerate(phase.get("subPhases") or []):
            if sub_phase_index > 0:
                y_cursor += BLOCK_GAP
            block_h = _sub_phase_block_height(sub_phase)
            block_y = y_cursor
            y0 = block_y + BLOCK_PAD_Y
            row_cy = y0 + SUB_PHASE_ROW_HEIGHT / 2
            sub_phase_key = str(sub_phase.get("key") or "")
            sub_phase_label = str(sub_phase.get("summary") or sub_phase_key)
            work_streams = sub_phase.get("workStreams") or []
            has_work_streams = bool(work_streams)
            ws_keys = [str(ws.get("key") or "") for ws in work_streams if str(ws.get("key") or "")]
            sub_content_h = max(0, int(block_h - BLOCK_PAD_Y * 2 - SUB_PHASE_ROW_HEIGHT))
            collapsed_h = int(BLOCK_PAD_Y * 2 + SUB_PHASE_ROW_HEIGHT)

            if sub_phase_key:
                parts.append(
                    f'<g id="sefk-sp-{html.escape(sub_phase_key)}" transform="translate(0,0)" '
                    f'data-sub-h="{sub_content_h}" data-collapsed-h="{collapsed_h}">'
                )
                parts.append(
                    f'<rect id="sefk-bd-{html.escape(sub_phase_key)}" '
                    f'x="0" y="{block_y:.1f}" width="{plot_right:.1f}" height="{block_h:.1f}" '
                    f'data-sefk-key="{html.escape(sub_phase_key)}" data-sef-row="1" '
                    f'data-sef-role="sub-phase-border" data-sef-orig-y="{block_y:.1f}" '
                    f'data-sef-orig-height="{block_h:.1f}" '
                    f'fill="none" stroke="{ATL["ink"]}" stroke-width="{BLOCK_BORDER_WIDTH}"/>'
                )
                start_day = date.fromisoformat(str(sub_phase.get("startDate"))[:10])
                end_day = date.fromisoformat(str(sub_phase.get("endDate"))[:10])
                x1 = x_for(start_day)
                x2 = x_for(end_day)
                bar_w = max(x2 - x1, 2.0)
                bar_y = y0 + (SUB_PHASE_ROW_HEIGHT - SUB_PHASE_BAR_HEIGHT) / 2
                _append_sefk_bar(
                    parts,
                    row=sub_phase,
                    x1=x1,
                    bar_y=bar_y,
                    bar_w=bar_w,
                    bar_h=SUB_PHASE_BAR_HEIGHT,
                    role="sub-phase-bar",
                )
                _append_label_link(
                    parts,
                    text=_label_with_duration_metrics(sub_phase_label, sub_phase),
                    x=LABEL_PAD_X + SUB_LABEL_INDENT,
                    y_center=row_cy,
                    url=f"{JIRA_SERVER}/browse/{html.escape(sub_phase_key)}",
                    tooltip=_bar_tooltip(sub_phase),
                    font_weight="600",
                )
                if has_work_streams:
                    chev_x = max(LABEL_PAD_X - 3, 6)
                    parts.append(
                        f'<text id="sefk-chev-sp-{html.escape(sub_phase_key)}" '
                        f'data-sefk-key="{html.escape(sub_phase_key)}" data-sef-row="1" '
                        f'x="{chev_x:.1f}" y="{row_cy + 4:.1f}" '
                        f'font-family="{SVG_FONT}" font-size="10" fill="{ATL["ink"]}" '
                        f'style="cursor:pointer;user-select:none" text-anchor="end" '
                        f'onclick="sefkToggleSubPhase(event,&apos;{html.escape(sub_phase_key)}&apos;)">'
                        f"&#x25BC;</text>"
                    )
                    parts.append(
                        f'<g id="sefk-sub-sp-{html.escape(sub_phase_key)}" '
                        f'transform="translate(0,{block_y:.1f})" '
                        f'data-work-stream-keys="{html.escape(",".join(ws_keys))}">'
                    )

            ws_cursor = BLOCK_PAD_Y + SUB_PHASE_ROW_HEIGHT
            for work_stream in work_streams:
                work_stream_key = str(work_stream.get("key") or "")
                work_stream_label = str(work_stream.get("summary") or work_stream_key)
                epics = work_stream.get("epics") or []
                epic_h = len(epics) * EPIC_ROW_HEIGHT
                ws_rel_y = ws_cursor
                ws_bar_y_rel = (WORK_STREAM_ROW_HEIGHT - WORK_STREAM_BAR_HEIGHT) / 2
                ws_row_cy_rel = WORK_STREAM_ROW_HEIGHT / 2
                ws_start = date.fromisoformat(str(work_stream.get("startDate"))[:10])
                ws_end = date.fromisoformat(str(work_stream.get("endDate"))[:10])
                wx1 = x_for(ws_start)
                wx2 = x_for(ws_end)
                ws_bar_w = max(wx2 - wx1, 2.0)
                sub_cy = block_y + ws_rel_y + ws_row_cy_rel

                if sub_phase_key and work_stream_key:
                    parts.append(
                        f'<g id="sefk-ws-{html.escape(work_stream_key)}" '
                        f'transform="translate(0,{ws_rel_y:.1f})" '
                        f'data-epic-h="{int(epic_h)}" data-sp-key="{html.escape(sub_phase_key)}">'
                    )

                bar_y = (block_y + ws_rel_y + ws_bar_y_rel) if not (sub_phase_key and work_stream_key) else ws_bar_y_rel
                _append_sefk_bar(
                    parts,
                    row=work_stream,
                    x1=wx1,
                    bar_y=bar_y,
                    bar_w=ws_bar_w,
                    bar_h=WORK_STREAM_BAR_HEIGHT,
                    role="work-stream-bar",
                )
                ws_display = _sefk_work_stream_display_label(work_stream, sub_phase)
                if work_stream_key:
                    if epics:
                        chev_ws_x = LABEL_PAD_X + SUB_LABEL_INDENT * 2 - 8
                        chev_ws_y = (ws_row_cy_rel + 4) if (sub_phase_key and work_stream_key) else (sub_cy + 4)
                        parts.append(
                            f'<text id="sefk-chev-ws-{html.escape(work_stream_key)}" '
                            f'data-sefk-key="{html.escape(work_stream_key)}" data-sef-row="1" '
                            f'x="{chev_ws_x:.1f}" y="{chev_ws_y:.1f}" '
                            f'font-family="{SVG_FONT}" font-size="9" fill="{ATL["ink"]}" '
                            f'style="cursor:pointer;user-select:none" text-anchor="end" '
                            f'onclick="sefkToggleWorkStream(event,&apos;{html.escape(work_stream_key)}&apos;)">'
                            f"&#x25BC;</text>"
                        )
                    label_y = ws_row_cy_rel if (sub_phase_key and work_stream_key) else sub_cy
                    ws_label_text = _sefk_truncate_label(
                        _label_with_duration_metrics(ws_display, work_stream),
                        SEFK_WORK_STREAM_LABEL_MAX_CHARS,
                    )
                    _append_label_link(
                        parts,
                        text=ws_label_text,
                        x=LABEL_PAD_X + SUB_LABEL_INDENT * 2,
                        y_center=label_y,
                        url=f"{JIRA_SERVER}/browse/{html.escape(work_stream_key)}",
                        tooltip=_bar_tooltip(work_stream),
                        font_size=11,
                        clip_path="sef-plan-label-col-x" if (sub_phase_key and work_stream_key) else "sef-plan-label-col",
                    )
                else:
                    _append_label_text(
                        parts,
                        text=_sefk_truncate_label(
                            _label_with_duration_metrics(ws_display, work_stream),
                            SEFK_WORK_STREAM_LABEL_MAX_CHARS,
                        ),
                        x=LABEL_PAD_X + SUB_LABEL_INDENT * 2,
                        y_center=sub_cy,
                        tooltip=_bar_tooltip(work_stream),
                        font_size=11,
                    )

                if epics and sub_phase_key and work_stream_key:
                    parts.append(f'<g id="sefk-sub-ws-{html.escape(work_stream_key)}">')

                for epic_index, epic in enumerate(epics):
                    epic_key = str(epic.get("key") or "")
                    epic_label = str(epic.get("summary") or epic_key)
                    epic_rel_y = WORK_STREAM_ROW_HEIGHT + epic_index * EPIC_ROW_HEIGHT
                    epic_bar_y_rel = epic_rel_y + (EPIC_ROW_HEIGHT - EPIC_BAR_HEIGHT) / 2
                    epic_cy_rel = epic_rel_y + EPIC_ROW_HEIGHT / 2
                    epic_cy = epic_cy_rel if (sub_phase_key and work_stream_key) else (block_y + ws_rel_y + epic_cy_rel)
                    epic_start = date.fromisoformat(str(epic.get("startDate"))[:10])
                    epic_end = date.fromisoformat(str(epic.get("endDate"))[:10])
                    ex1 = x_for(epic_start)
                    ex2 = x_for(epic_end)
                    epic_bar_w = max(ex2 - ex1, 2.0)
                    epic_bar_y = epic_bar_y_rel if (sub_phase_key and work_stream_key) else (block_y + ws_rel_y + epic_bar_y_rel)
                    _append_sefk_bar(
                        parts,
                        row=epic,
                        x1=ex1,
                        bar_y=epic_bar_y,
                        bar_w=epic_bar_w,
                        bar_h=EPIC_BAR_HEIGHT,
                        role="epic-bar",
                    )
                    if epic_key:
                        _append_label_link(
                            parts,
                            text=_sefk_truncate_label(epic_label, SEFK_EPIC_LABEL_MAX_CHARS),
                            x=LABEL_PAD_X + EPIC_LABEL_INDENT,
                            y_center=epic_cy,
                            url=f"{JIRA_SERVER}/browse/{html.escape(epic_key)}",
                            tooltip=_bar_tooltip(epic),
                            font_size=10,
                            clip_path="sef-plan-label-col-x" if (sub_phase_key and work_stream_key) else "sef-plan-label-col",
                        )

                if epics and sub_phase_key and work_stream_key:
                    parts.append("</g>")
                if sub_phase_key and work_stream_key:
                    parts.append("</g>")
                ws_cursor += WORK_STREAM_ROW_HEIGHT + epic_h

            if sub_phase_key:
                if has_work_streams:
                    parts.append("</g>")
                sub_phase_manifest.append(
                    {
                        "key": sub_phase_key,
                        "subH": sub_content_h,
                        "collapsedH": collapsed_h,
                    }
                )
                parts.append("</g>")

            y_cursor += block_h

    today = _chart_today_in_quarter(x_min, x_max)
    if today is not None:
        _append_today_marker(
            parts,
            today=today,
            x_for=x_for,
            plot_top=plot_top,
            plot_bottom=plot_bottom,
        )

    _svg_x_axis_labels(
        parts,
        x_min=x_min,
        x_max=x_max,
        plot_bottom=plot_bottom,
        plot_left=plot_left,
        plot_right=plot_right,
        x_for=x_for,
    )

    if sub_phase_manifest:
        manifest_str = json.dumps(sub_phase_manifest).replace('"', "&quot;")
        parts.append(
            f'<text id="sefk-cm-sp" data-chapters="{manifest_str}" '
            f'visibility="hidden" fill="none">.</text>'
        )

    parts.append(
        f'<text id="sefk-cfg" data-block-pad-y="{BLOCK_PAD_Y}" '
        f'data-sub-phase-row-h="{SUB_PHASE_ROW_HEIGHT}" '
        f'data-work-stream-row-h="{WORK_STREAM_ROW_HEIGHT}" '
        f'data-epic-row-h="{EPIC_ROW_HEIGHT}" '
        f'visibility="hidden" fill="none">.</text>'
    )

    parts.append("</svg>")
    return "".join(parts)


def build_sefk_project_plan_report_html(
    payload: dict[str, Any],
    *,
    generated_on: str,
    page_title: str | None = None,
    breadcrumb_nav: str = "",
) -> str:
    title = page_title or str(payload.get("pageTitle") or "SEFK | Integrated Project Plan")
    chart = sefk_project_plan_timeline_svg(payload)
    window_start = str(payload.get("chartWindowStart") or "")[:10]
    window_end = str(payload.get("chartWindowEnd") or "")[:10]
    sub_phase_count = sum(len(phase.get("subPhases") or []) for phase in payload.get("phases") or [])
    work_stream_count = sum(
        len(sub_phase.get("workStreams") or [])
        for phase in payload.get("phases") or []
        for sub_phase in phase.get("subPhases") or []
    )
    epic_count = sum(
        len(work_stream.get("epics") or [])
        for phase in payload.get("phases") or []
        for sub_phase in phase.get("subPhases") or []
        for work_stream in sub_phase.get("workStreams") or []
    )
    footnote = (
        f"{sub_phase_count} sub-phases, {work_stream_count} work streams, and {epic_count} epics "
        f"from SEFK schedule items ({window_start} to {window_end}). "
        "Each bar runs from start date through due date. "
        "Bar colours show D-Train scope composition (Drive left, Dream right). "
        "Use ▼ beside sub-phases and work streams to collapse or expand rows."
    )
    nav_block = f"\n      {breadcrumb_nav}" if breadcrumb_nav else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(title)}</title>
  <style>{REPORT_CSS}{BREADCRUMB_CSS}{MILESTONE_TIMELINE_EXTRA_CSS}{SEFK_EXTRA_CSS}</style>
</head>
<body>
  <main class="report-shell">{nav_block}
    <header class="report-header">
      <h1>{html.escape(title)}</h1>
      <p class="report-subtitle">Generated {html.escape(generated_on)}</p>
      <p class="footnote">{html.escape(footnote)}</p>
    </header>
    <section class="report-card chart-section">
      <div class="chart-wrap chart-wrap-timeline chart-wrap-milestone chart-wrap-sefk">{chart}</div>
      {sefk_dtrain_key_html()}
    </section>
  </main>
  <script>{SEFK_COLLAPSE_SCRIPT}</script>
</body>
</html>
"""
