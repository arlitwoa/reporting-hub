"""Tests for SEF integrated project plan Block Gantt scaffold."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from extensions.twoa_programme.sef_project_plan_reporting import load_sef_project_plan_reporting_config
from extensions.twoa_programme.sef_project_plan_timeline import (
    build_sef_project_plan_report_html,
    resolve_chart_window_for_phases,
    sef_project_plan_key_html,
    sef_project_plan_timeline_svg,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sef-project-plan-timeline.json"
_REPO = Path(__file__).resolve().parents[1]


class SefProjectPlanTimelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    def test_config_loads_hub_keys(self) -> None:
        config = load_sef_project_plan_reporting_config(_REPO / "config" / "sef-project-plan-reporting.json")
        self.assertEqual(config.phase_hub_keys[0], "PDE-4072")
        self.assertEqual(config.detail_issue_type, "Block Level Minus One")
        self.assertEqual(config.pages_publish_path, "docs/sef/project-plan.html")

    def test_chart_window_spans_full_project_delivery(self) -> None:
        start, end = resolve_chart_window_for_phases(self.payload["phases"])
        self.assertLessEqual(start.isoformat(), "2026-06-01")
        self.assertGreaterEqual(end.isoformat(), "2027-12-03")

    def test_svg_renders_phase_hub_chapters_streams_and_details(self) -> None:
        svg = sef_project_plan_timeline_svg(self.payload)
        self.assertIn("SEF Phase 1 | HCM and Payroll", svg)
        self.assertIn("PDE-4072", svg)
        self.assertIn("Mobilisation", svg)
        self.assertIn("Functional - HCM Stream", svg)
        self.assertIn("SIT cycle 1", svg)
        self.assertIn("PDE-4086", svg)
        self.assertIn("PDE-4078", svg)
        self.assertIn("<svg ", svg)

    def test_html_report_shell(self) -> None:
        html_doc = build_sef_project_plan_report_html(
            self.payload,
            generated_on="01 Jan 2026 12:00 NZDT",
            page_title="SEF | Integrated Project Plan",
        )
        self.assertIn("Project plan timeline", html_doc)
        self.assertIn("chart-wrap-sef-plan", html_doc)

    def test_legend_matches_status_bar_colours(self) -> None:
        svg = sef_project_plan_timeline_svg(self.payload)
        todo_fill = "#6b778c"
        self.assertIn(f'fill="{todo_fill}"', svg)
        key = sef_project_plan_key_html()
        self.assertIn(f"background:{todo_fill}", key)
        self.assertIn("Block Level Minus One", key)
        self.assertNotIn("background:#0052cc;opacity:0.85\"></span> Chapter", key)
        self.assertIn("Today (NZ)", key)

    def test_svg_includes_today_marker_when_in_chart_window(self) -> None:
        svg = sef_project_plan_timeline_svg(self.payload)
        self.assertIn('class="chart-today-marker"', svg)
        self.assertIn('class="chart-today-line"', svg)

    def test_svg_renders_scope_overlay_when_scope_rollup_present(self) -> None:
        svg = sef_project_plan_timeline_svg(self.payload)
        self.assertIn('class="block-scope-segment"', svg)
        self.assertIn("Scope overlay", sef_project_plan_key_html())


if __name__ == "__main__":
    unittest.main()
