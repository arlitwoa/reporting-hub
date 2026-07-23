"""Tests for milestone scope burn-up charts."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from extensions.twoa_programme.milestone_burn_up import (
    MILESTONE_BURN_PX_PER_DAY,
    MILESTONE_BURN_SVG_INSET_LEFT,
    MILESTONE_BURN_SVG_INSET_RIGHT,
    _milestone_ideal_earned_at,
    build_milestone_burn_payload,
    build_milestone_burn_up_section_html,
    build_milestone_scope_report_html,
    burn_up_phase_stack_order,
    milestone_burn_phase_key_html,
    milestone_burn_up_plot_width,
    milestone_burn_up_svg,
)
from extensions.twoa_programme.pde_engine_releases import in_cycle_releases_only
from extensions.twoa_programme.milestone_timeline import MILESTONE_TIMELINE_MAX_SVG_WIDTH
from extensions.twoa_programme.quarterly_dashboard_constants import Y_AXIS_LEFT
from extensions.twoa_programme.milestone_scope_history import phase_stack_order

_TIMELINE = Path(__file__).resolve().parent / "fixtures" / "milestone-timeline.json"
_BURN_SNIPPET = Path(__file__).resolve().parent / "fixtures" / "milestone-burn-events-snippet.json"


class MilestoneScopeHistoryTests(unittest.TestCase):
    def test_build_milestone_scope_daily_sums_issues(self):
        from extensions.twoa_programme.milestone_scope_history import build_milestone_scope_daily

        issues = [
            {
                "key": "EPCE-9001",
                "fields": {"created": "2026-04-05T10:00:00.000+0000", "customfield_10026": 5.0},
            },
            {
                "key": "EPCE-9002",
                "fields": {"created": "2026-04-12T10:00:00.000+0000", "customfield_10026": 3.0},
            },
        ]
        changelogs = {
            "EPCE-9001": [
                {
                    "created": "2026-04-10T12:00:00.000+0000",
                    "items": [{"field": "Story Points", "toString": "5"}],
                }
            ],
            "EPCE-9002": [
                {
                    "created": "2026-04-12T12:00:00.000+0000",
                    "items": [{"field": "Story Points", "toString": "3"}],
                }
            ],
        }
        daily, total = build_milestone_scope_daily(
            issues,
            changelogs,
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
        )
        self.assertEqual(total, 8.0)
        self.assertEqual(daily[-1]["cumulative_story_points"], 8.0)

    def test_issue_scope_delta_events_tracks_sp_changes(self):
        from extensions.twoa_programme.milestone_scope_history import issue_scope_delta_events

        issue = {
            "key": "EPCE-9001",
            "fields": {
                "created": "2026-04-05T10:00:00.000+0000",
                "customfield_10026": 8.0,
            },
        }
        histories = [
            {
                "created": "2026-04-10T12:00:00.000+0000",
                "items": [{"field": "Story Points", "toString": "5"}],
            },
            {
                "created": "2026-05-01T12:00:00.000+0000",
                "items": [{"field": "Story Points", "toString": "8"}],
            },
        ]
        events = issue_scope_delta_events(
            issue,
            histories,
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 8, 20),
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(sum(row["delta"] for row in events), 8.0)


class MilestoneBurnUpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.timeline = json.loads(_TIMELINE.read_text(encoding="utf-8"))
        self.timeline["milestones"][0]["scopeIssueKeys"] = ["EPCE-1001", "EPCE-1002", "EPCE-1003"]
        self.deploy_burn = json.loads(_BURN_SNIPPET.read_text(encoding="utf-8"))

    def test_build_milestone_burn_payload_splits_earned_phases(self):
        payload = build_milestone_burn_payload(self.timeline, self.deploy_burn)
        milestone = payload["milestones"][0]
        self.assertEqual(milestone["totalStoryPointsEarned"], 16.0)
        self.assertGreater(milestone["earnedPhases"]["Drive"]["totalStoryPointsEarned"], 0)
        self.assertEqual(milestone["creditedIssueKeys"], ["EPCE-1001", "EPCE-1002", "EPCE-1003"])

    def test_burn_meta_links_credited_issues_separately_from_scope(self):
        payload = build_milestone_burn_payload(self.timeline, self.deploy_burn)
        section = build_milestone_burn_up_section_html(
            payload,
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 8, 20),
        )
        self.assertIn("EPCE-1001", section)
        self.assertIn("EPCE-1003", section)
        self.assertNotIn("key in ()", section)

    def test_burn_up_phase_stack_order_is_inverted(self):
        normal = phase_stack_order()
        inverted = burn_up_phase_stack_order()
        self.assertEqual(inverted[0], "Drive")
        self.assertEqual(inverted[-2], "Dream")
        self.assertEqual(inverted[-1], "Unknown")
        self.assertEqual(inverted, (*reversed(normal[:-1]), "Unknown"))

    def test_burn_up_plot_width_capped_to_report_page(self):
        span_days = 141
        plot_w = milestone_burn_up_plot_width(span_days)
        plot_left = Y_AXIS_LEFT + MILESTONE_BURN_SVG_INSET_LEFT
        self.assertLessEqual(
            plot_left + plot_w + MILESTONE_BURN_SVG_INSET_RIGHT,
            MILESTONE_TIMELINE_MAX_SVG_WIDTH,
        )
        self.assertLess(plot_w, span_days * MILESTONE_BURN_PX_PER_DAY)

    def test_svg_fits_page_without_fixed_pixel_width(self):
        payload = build_milestone_burn_payload(self.timeline, self.deploy_burn)
        milestone = payload["milestones"][0]
        svg = milestone_burn_up_svg(
            milestone,
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
        )
        svg_open = svg.split(">", 1)[0]
        self.assertIn('width="100%"', svg_open)
        self.assertIn("viewBox=", svg_open)

    def test_svg_renders_inverted_scope_stack_and_earned_line_only(self):
        payload = build_milestone_burn_payload(self.timeline, self.deploy_burn)
        milestone = payload["milestones"][0]
        svg = milestone_burn_up_svg(
            milestone,
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
        )
        self.assertIn("Milestone scope burn-up", svg)
        self.assertIn("<polygon", svg)
        self.assertIn("Deploy — 8 SP", svg)
        self.assertIn('stroke="#0052cc"', svg)
        self.assertIn("stroke-dasharray", svg)
        self.assertIn("#c1c7d0", svg)
        self.assertIn("Unpointed — 2 issues", svg)
        self.assertIn("Story points (+ unpointed weight)", svg)
        self.assertIn('opacity="0.75"', svg)
        for tag in svg.split("<polygon"):
            if not tag.startswith(" points"):
                continue
            polygon_attrs = tag.split(">", 1)[0]
            if "opacity" in polygon_attrs:
                self.assertIn('opacity="0.75"', polygon_attrs)
            self.assertIn('stroke="none"', polygon_attrs)
        key_html = milestone_burn_phase_key_html()
        self.assertIn("Scope target", key_html)
        self.assertNotIn("Earned SP (stacked", key_html)
        self.assertIn("bottom → top", key_html)
        self.assertIn("Unpointed in-scope", key_html)

    def test_burn_section_html_shows_unpointed_weight(self):
        payload = build_milestone_burn_payload(self.timeline, self.deploy_burn)
        section = build_milestone_burn_up_section_html(
            payload,
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 8, 20),
            chart_as_of="2026-05-15",
        )
        self.assertIn("30 total weight", section)
        self.assertIn("unpointed", section)
        self.assertIn("grey band above scoped SP", section)

    def test_flat_unpointed_daily(self):
        from extensions.twoa_programme.milestone_scope_history import flat_unpointed_daily

        daily = flat_unpointed_daily(
            2,
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
            as_of="2026-05-15",
        )
        self.assertEqual(len(daily), 2)
        self.assertEqual(daily[-1]["cumulative_story_points"], 2.0)

    def test_burn_section_html(self):
        payload = build_milestone_burn_payload(self.timeline, self.deploy_burn)
        section = build_milestone_burn_up_section_html(
            payload,
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 8, 20),
            chart_as_of="2026-05-15",
        )
        self.assertIn("Milestone scope burn-up", section)
        self.assertIn("Scope target", section)
        self.assertIn("Drive at the bottom", section)
        self.assertNotIn("darker bands", section)
        self.assertIn("milestone-summary-card", section)
        self.assertIn("milestone-earned-label", section)
        self.assertIn("Earned detail", section)
        self.assertIn("milestone-description-card", section)
        self.assertIn("Deliver ED Cloud data products", section)
        self.assertIn("milestone-stat-lead", section)
        self.assertIn("<dt>Status</dt>", section)
        self.assertIn("<dt>Due date</dt>", section)
        self.assertIn(">Doing<", section)
        self.assertIn("2026-06-11", section)
        self.assertIn("milestone-notes-card", section)
        self.assertIn("milestone-notes-updated", section)
        self.assertIn("Current State", section)
        self.assertIn("updated 15 Jun 2026", section)
        self.assertIn("milestone-burn-intro", section)
        self.assertIn("Fabric rollout depends on ED Cloud data lake readiness.", section)
        self.assertIn("2026-06-11", section)
        self.assertIn("/browse/PDE-3834", section)
        self.assertIn("issues/?jql=", section)
        self.assertIn("on pace today", section)

    def test_milestone_ideal_earned_at(self):
        ideal = _milestone_ideal_earned_at(
            planned=211.0,
            start=date(2026, 4, 1),
            goal_target=date(2026, 8, 6),
            as_of=date(2026, 6, 12),
        )
        self.assertIsNotNone(ideal)
        assert ideal is not None
        self.assertGreater(ideal, 70)
        self.assertLess(ideal, 130)

    def test_scope_only_milestone_shows_composition_target(self):
        timeline = json.loads(_TIMELINE.read_text(encoding="utf-8"))
        timeline["milestones"][0]["scopeIssueKeys"] = []
        deploy_burn = json.loads(_BURN_SNIPPET.read_text(encoding="utf-8"))
        payload = build_milestone_burn_payload(timeline, deploy_burn)
        svg = milestone_burn_up_svg(
            payload["milestones"][0],
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
        )
        self.assertGreaterEqual(svg.count("<polygon"), 2)
        self.assertIn('stroke="none"', svg)

    def test_in_cycle_releases_only_drops_ooc(self):
        releases = [
            {"releaseDate": "2026-05-28", "carriageType": "In Cycle", "name": "ic"},
            {"releaseDate": "2026-04-22", "carriageType": "Out Of Cycle", "name": "ooc"},
        ]
        filtered = in_cycle_releases_only(releases)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["name"], "ic")

    def test_burn_intro_card_order(self):
        payload = build_milestone_burn_payload(self.timeline, self.deploy_burn)
        section = build_milestone_burn_up_section_html(
            payload,
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 8, 20),
        )
        desc_pos = section.index("milestone-description-card")
        notes_pos = section.index("milestone-notes-card")
        earned_pos = section.index("milestone-earned-label")
        self.assertLess(desc_pos, notes_pos)
        self.assertLess(notes_pos, earned_pos)

    def test_milestone_report_omits_out_of_cycle_legend(self):
        payload = build_milestone_burn_payload(self.timeline, self.deploy_burn)
        releases = [
            {"releaseDate": "2026-05-28", "carriageType": "In Cycle", "name": "ic"},
            {"releaseDate": "2026-04-22", "carriageType": "Out Of Cycle", "name": "ooc"},
        ]
        html_doc = build_milestone_scope_report_html(
            self.timeline,
            payload,
            generated_on="24 Jun 2026",
            page_title="Milestone report",
            releases=releases,
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 8, 20),
        )
        self.assertNotIn("Out-of-cycle / other release", html_doc)
        self.assertIn("In-cycle engine release", html_doc)
        self.assertIn("How to update this report", html_doc)
        self.assertIn("smart-milestone-report", html_doc)
        self.assertIn("https://twoa.atlassian.net/issues/?filter=15858", html_doc)
        self.assertIn("Report dates are derived from the Milestones returned by that filter", html_doc)
        self.assertIn("credited from Deploy/Done status transitions", html_doc)


if __name__ == "__main__":
    unittest.main()
