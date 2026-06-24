"""Table row builders for quarterly dashboard."""

from __future__ import annotations

from datetime import date

import html
from pathlib import Path

from extensions.twoa_programme.quarterly_dashboard_constants import (
    JIRA_SERVER,
    TIP_BEHIND,
    TIP_NO_GOAL,
    TIP_ON_TRACK,
    TIP_SQUAD_BASELINE,
    TIP_SQUAD_CREDIT,
)
from extensions.twoa_programme.quarterly_dashboard_links import _browse_link, _fmt_num
from extensions.twoa_programme.quarterly_dashboard_markup import _goal_pace_tip
def _track_pill(on_track: bool | None, *, goal_target: date) -> str:
    if on_track is True:
        inner = '<span class="health-pill green">On track</span>'
        return (
            f'<abbr title="{html.escape(_goal_pace_tip(TIP_ON_TRACK, goal_target), quote=True)}" '
            f'class="metric-tip">{inner}</abbr>'
        )
    if on_track is False:
        inner = '<span class="health-pill red">Behind</span>'
        return (
            f'<abbr title="{html.escape(_goal_pace_tip(TIP_BEHIND, goal_target), quote=True)}" '
            f'class="metric-tip">{inner}</abbr>'
        )
    inner = '<span class="health-pill neutral">No goal set</span>'
    return (
        f'<abbr title="{html.escape(TIP_NO_GOAL, quote=True)}" class="metric-tip">'
        f"{inner}</abbr>"
    )


def _education_cloud_squad_table_rows(
    squad: dict,
    *,
    include_board: bool = False,
) -> str:
    """Render all configured Education Cloud squads, merging squad_velocity.json with delivery-health."""
    import json as _json

    from extensions.twoa_programme.delivery_health import load_delivery_health_config
    from extensions.twoa_programme.quarterly_reporting import load_quarterly_reporting_config

    config_path = Path(__file__).resolve().parents[2] / "config" / "quarterly-reporting.json"
    health_path = Path(__file__).resolve().parents[2] / "config" / "delivery-health.json"
    qconfig = load_quarterly_reporting_config(config_path)
    dh = load_delivery_health_config()
    health_payload = _json.loads(health_path.read_text(encoding="utf-8"))
    squads_data = squad.get("squads") or {}
    rows = ""
    for slug in qconfig.education_cloud.squads:
        row = squads_data.get(slug) or {}
        squad_cfg = dh.squads.get(slug)
        squad_meta = (health_payload.get("squads") or {}).get(slug) or {}
        label = row.get("label") or (squad_cfg.label if squad_cfg else slug)
        board_id = row.get("boardId") or (squad_cfg.board_id if squad_cfg else "")
        board_name = row.get("boardName") or squad_meta.get("boardName") or label
        sprint_count = row.get("sprintCount", 0)
        total_credit = row.get("totalDeployCredit", 0.0)
        baseline = row.get("baselineVelocity", 0.0)
        if include_board:
            board_url = f"{JIRA_SERVER}/jira/software/c/projects/EPCE/boards/{board_id}"
            board_cell = (
                f'<td><a href="{board_url}" target="_blank" rel="noopener">{html.escape(board_name)}</a></td>'
                if board_id
                else "<td>&mdash;</td>"
            )
            rows += (
                "<tr>"
                f"<td>{html.escape(label)}</td>"
                f"{board_cell}"
                f'<td class="num">{sprint_count}</td>'
                f'<td class="num">{_fmt_num(total_credit)}</td>'
                f'<td class="num">{_fmt_num(baseline)}</td>'
                "</tr>"
            )
        else:
            rows += (
                "<tr>"
                f"<td>{html.escape(label)}</td>"
                f'<td style="text-align:right">{sprint_count}</td>'
                f'<td style="text-align:right">{_fmt_num(total_credit)}</td>'
                f'<td style="text-align:right">{_fmt_num(baseline)}</td>'
                "</tr>"
            )
    return rows

