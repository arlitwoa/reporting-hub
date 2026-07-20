"""Tests for SEF integrated project plan Block Gantt scaffold."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from extensions.twoa_programme.sef_project_plan_reporting import (
    PhaseHubDiscovery,
    discover_phase_hub_issues,
    load_sef_project_plan_reporting_config,
)
from extensions.twoa_programme.sef_project_plan_timeline import (
    build_sef_project_plan_report_html,
    resolve_chart_window_for_phases,
    sef_project_plan_timeline_svg,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sef-project-plan-timeline.json"
_REPO = Path(__file__).resolve().parents[1]


class SefProjectPlanTimelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    def test_config_loads_phase_hub_discovery(self) -> None:
        config = load_sef_project_plan_reporting_config(_REPO / "config" / "sef-project-plan-reporting.json")
        self.assertIsNotNone(config.phase_hub_discovery)
        assert config.phase_hub_discovery is not None
        self.assertIn("Block Level Two", config.phase_hub_discovery.jql or "")
        self.assertEqual(config.detail_issue_type, "Block Level Minus One")
        self.assertEqual(config.pages_publish_path, "docs/sef/project-plan.html")

    def test_chart_window_spans_full_project_delivery(self) -> None:
        start, end = resolve_chart_window_for_phases(self.payload["phases"])
        self.assertLessEqual(start.isoformat(), "2026-06-04")
        self.assertGreaterEqual(end.isoformat(), "2026-10-23")

    def test_svg_renders_phase_hub_chapters_streams_and_details(self) -> None:
        svg = sef_project_plan_timeline_svg(self.payload)
        self.assertIn("SEF Phase 1 | HCM and Payroll", svg)
        self.assertIn("PDE-4249", svg)
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
        self.assertIn("SEF | Integrated Project Plan", html_doc)
        self.assertIn("chart-wrap-sef-plan", html_doc)

    def test_timeline_bars_use_status_colours(self) -> None:
        svg = sef_project_plan_timeline_svg(self.payload)
        todo_fill = "#6b778c"
        self.assertIn(f'fill="{todo_fill}"', svg)

    def test_svg_includes_today_marker_when_in_chart_window(self) -> None:
        svg = sef_project_plan_timeline_svg(self.payload)
        self.assertIn('class="chart-today-marker"', svg)
        self.assertIn('class="chart-today-line"', svg)

    def test_discover_phase_hub_issues_skips_missing_configured_keys(self) -> None:
        from unittest.mock import MagicMock, patch

        from extensions.twoa_programme.sef_project_plan_reporting import SefProjectPlanReportingConfig

        config = SefProjectPlanReportingConfig(
            project_key="PDE",
            phase_hub_keys=("PDE-MISSING", "PDE-4249"),
            phase_hub_discovery=None,
            manifest_path=_REPO / "config" / "sef-project-plan-blocks.json",
            chart_window_start="2026-06-01",
            chart_window_end="2027-12-03",
            chapter_issue_type="Block Level One",
            package_issue_type="Block Level Zero",
            detail_issue_type="Block Level Minus One",
            scope_filter_id=None,
            scope_filter_name=None,
            timeline_artifact="sef-project-plan-timeline.json",
            html_artifact="sef-project-plan-chart.html",
            pages_publish_path="docs/sef/project-plan.html",
            pages_site_path="sef/project-plan.html",
            page_title="SEF | Integrated Project Plan",
        )
        adapter = MagicMock()
        with patch(
            "extensions.twoa_programme.jira_search.search_all",
            return_value=[
                {
                    "key": "PDE-4249",
                    "fields": {"summary": "SEF Phase 1 | HCM and Payroll", "status": {"name": "To Do"}},
                }
            ],
        ):
            issues, warnings = discover_phase_hub_issues(adapter, config, fields=["summary", "status"])
        self.assertEqual([issue["key"] for issue in issues], ["PDE-4249"])
        self.assertTrue(any("PDE-MISSING" in warning for warning in warnings))

    def test_fetch_timeline_tolerates_empty_phase_discovery(self) -> None:
        from unittest.mock import MagicMock, patch

        from extensions.twoa_programme.sef_project_plan_reporting import SefProjectPlanReportingConfig
        from extensions.twoa_programme.sef_project_plan_timeline import fetch_sef_project_plan_timeline

        config = SefProjectPlanReportingConfig(
            project_key="PDE",
            phase_hub_keys=(),
            phase_hub_discovery=PhaseHubDiscovery(filter_id=None, filter_name=None, jql="project = PDE AND key = PDE-NONE"),
            manifest_path=_REPO / "config" / "sef-project-plan-blocks.json",
            chart_window_start="2026-06-01",
            chart_window_end="2027-12-03",
            chapter_issue_type="Block Level One",
            package_issue_type="Block Level Zero",
            detail_issue_type="Block Level Minus One",
            scope_filter_id=None,
            scope_filter_name=None,
            timeline_artifact="sef-project-plan-timeline.json",
            html_artifact="sef-project-plan-chart.html",
            pages_publish_path="docs/sef/project-plan.html",
            pages_site_path="sef/project-plan.html",
            page_title="SEF | Integrated Project Plan",
        )
        adapter = MagicMock()
        with patch(
            "extensions.twoa_programme.jira_search.search_all",
            return_value=[],
        ):
            payload = fetch_sef_project_plan_timeline(adapter, config)
        self.assertEqual(payload["phases"], [])
        self.assertTrue(payload["warnings"])

    def test_svg_renders_scope_overlay_when_scope_rollup_present(self) -> None:
        svg = sef_project_plan_timeline_svg(self.payload)
        self.assertIn('class="block-scope-segment"', svg)


if __name__ == "__main__":
    unittest.main()
