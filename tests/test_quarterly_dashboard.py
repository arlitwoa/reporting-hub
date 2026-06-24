import re
import unittest
from datetime import date
from pathlib import Path

from extensions.twoa_programme.pde_engine_releases import release_code_label
from extensions.twoa_programme.quarterly_dashboard import (
    ATL,
    LANE_STACK_FILL,
    _aligned_lane_cumulative,
    _allocation_tables,
    _burn_svg,
    _chart_legend_html,
    _layout_release_labels,
    _load_delivery_milestones,
    _lane_burn_stacked_svg,
    _release_code_cell,
    _sprint_is_future,
    _week_start_dates,
    _y_tick_step,
    _y_ticks,
    build_confluence_body,
    build_confluence_template_body,
    build_dashboard_html,
)
from extensions.twoa_programme.quarterly_dashboard_markup import _unpointed_cell


_RELEASE_LABEL_SVG = (
    'font-size="8" fill="#5e6c84" font-weight="600" transform="rotate(-90"'
)


class QuarterlyDashboardTests(unittest.TestCase):
    def _sample_payload(self) -> dict:
        return {
            "status": {
                "quarter": "2026-Q2",
                "initiativeKey": "EPCE-3897",
                "asOf": "2026-06-04",
                "quarterStart": "2026-04-01",
                "quarterEnd": "2026-06-30",
                "daysRemaining": 26,
                "elapsedFraction": 0.7143,
                "plannedStoryPoints": 1000.0,
                "earnedStoryPoints": 48.0,
                "idealEarnedStoryPoints": 714.3,
                "burnVariance": -666.3,
                "requiredDailyVelocity": 36.6,
                "onTrack": False,
            },
            "burn": {
                "combinedDaily": [
                    {"date": "2026-04-22", "cumulative_story_points": 13.0},
                    {"date": "2026-06-04", "cumulative_story_points": 48.0},
                ],
                "lanes": {
                    "educationCloud": {
                        "label": "Lane 1",
                        "totalStoryPointsEarned": 14.0,
                        "earnedEventCount": 2,
                        "scopeJql": "project = EPCE",
                        "daily": [
                            {"date": "2026-04-22", "cumulative_story_points": 13.0},
                            {"date": "2026-06-04", "cumulative_story_points": 14.0},
                        ],
                        "events": [
                            {
                                "key": "EPCE-100",
                                "story_points": 5,
                                "credit_date": "2026-04-22",
                                "summary": "Sample story",
                            }
                        ],
                    }
                },
            },
            "squad": {
                "squads": {
                    "kakariki": {
                        "label": "Kākāriki",
                        "boardId": 893,
                        "sprintCount": 2,
                        "totalDeployCredit": 0.0,
                        "baselineVelocity": 12.5,
                        "sprints": [
                            {
                                "name": "Kākāriki | Sprint 22",
                                "sprintStartNz": "2026-04-13",
                                "sprintEndNz": "2026-04-23",
                            },
                            {
                                "name": "Kākāriki | Sprint 23",
                                "sprintStartNz": "2026-04-27",
                                "sprintEndNz": "2026-05-08",
                            },
                        ],
                    }
                }
            },
            "releasePlan": {
                "sprints": [
                    {
                        "name": "Sprint 22",
                        "startDate": "2026-04-13",
                        "endDate": "2026-04-23",
                    },
                    {
                        "name": "Sprint 23",
                        "startDate": "2026-04-27",
                        "endDate": "2026-05-08",
                    },
                ],
                "inCycleReleases": [
                    {
                        "name": "20260528-engine",
                        "releaseDate": "2026-05-28",
                        "carriageType": "In Cycle",
                    },
                ],
            },
        }

    def test_build_dashboard_html_contains_metrics(self):
        payload = self._sample_payload()
        payload["status"]["storyKey"] = "EPCE-6745"
        payload["status"]["plannedStoryPoints"] = 1000.0
        html_doc = build_dashboard_html(
            payload,
            generated_on="05 Jun 2026 07:22 NZST",
            page_title="Q2 2026 EPCE | Quarterly Dashboard",
        )
        self.assertIn("Q2 2026 EPCE | Quarterly Dashboard", html_doc)
        self.assertIn("EPCE-3897", html_doc)
        self.assertNotIn("EPCE-6745", html_doc)
        self.assertIn("05 Jun 2026 07:22 NZST", html_doc)
        self.assertNotIn("As of", html_doc)
        self.assertIn("48.0", html_doc)
        self.assertIn("Goal SP", html_doc)
        self.assertIn("section-l2", html_doc)
        self.assertIn("health-pill red", html_doc)
        self.assertIn("<svg", html_doc)
        self.assertIn(ATL["sprint_a"], html_doc)
        self.assertIn(ATL["blue"], html_doc)
        self.assertIn("issues/?jql=", html_doc)
        self.assertIn("Story Points Achieved by Lane", html_doc)
        self.assertNotIn("Credit events", html_doc)
        self.assertNotIn("Scope Coverage", html_doc)
        self.assertNotIn("Earned SP by scope", html_doc)
        self.assertIn("slice-inactive", html_doc)
        self.assertIn(LANE_STACK_FILL["educationCloud"], html_doc)
        self.assertNotIn("Deploy Burn by Lane", html_doc)
        self.assertIn("20260528-engine", html_doc)
        self.assertIn(">S22<", html_doc)
        self.assertNotIn(_RELEASE_LABEL_SVG, html_doc)
        self.assertIn("chart-key", html_doc)
        self.assertIn(">Key<", html_doc)
        self.assertIn('class="metric-tip"', html_doc)
        self.assertIn("Initiative sizing (size-epics", html_doc)
        self.assertIn("<title>20260528-engine · 2026-05-28 | In Cycle | Code</title>", html_doc)

    def test_dashboard_shows_goal_target_when_before_quarter_end(self):
        payload = self._sample_payload()
        payload["status"]["goalTargetDate"] = "2026-06-15"
        payload["status"]["goalDaysRemaining"] = 11
        html_doc = build_dashboard_html(
            payload,
            generated_on="05 Jun 2026 07:22 NZST",
            page_title="Q2 2026 EPCE | Quarterly Dashboard",
        )
        self.assertIn("Goal target 2026-06-15", html_doc)
        self.assertIn("Goal days left", html_doc)

    def test_burn_svg_goal_line_flattens_after_target(self):
        svg = _burn_svg(
            [{"date": "2026-04-01", "cumulative_story_points": 0.0}],
            planned=1000.0,
            quarter_start="2026-04-01",
            quarter_end="2026-06-30",
            goal_target="2026-06-15",
        )
        self.assertIn("2026-06-15", svg)
        self.assertEqual(svg.count('stroke-dasharray="6 4"'), 1)

    def test_dashboard_charts_fit_report_page(self):
        from extensions.twoa_programme.quarterly_dashboard_constants import Y_AXIS_LEFT
        from extensions.twoa_programme.quarterly_dashboard_svg_core import (
            QUARTERLY_REPORT_DEFAULT_RIGHT_PAD,
            QUARTERLY_REPORT_MAX_SVG_WIDTH,
            report_plot_width,
        )
        from extensions.twoa_programme.epic_timeline import EPIC_LABEL_WIDTH

        span_days = 141
        burn_plot = report_plot_width(
            span_days,
            px_per_day=11.0,
            plot_left=Y_AXIS_LEFT,
            plot_right_pad=QUARTERLY_REPORT_DEFAULT_RIGHT_PAD,
        )
        self.assertLessEqual(
            Y_AXIS_LEFT + burn_plot + QUARTERLY_REPORT_DEFAULT_RIGHT_PAD,
            QUARTERLY_REPORT_MAX_SVG_WIDTH,
        )
        epic_plot = report_plot_width(
            span_days,
            px_per_day=11.0,
            plot_left=EPIC_LABEL_WIDTH,
            plot_right_pad=QUARTERLY_REPORT_DEFAULT_RIGHT_PAD,
        )
        self.assertLessEqual(
            EPIC_LABEL_WIDTH + epic_plot + QUARTERLY_REPORT_DEFAULT_RIGHT_PAD,
            QUARTERLY_REPORT_MAX_SVG_WIDTH,
        )

        payload = self._sample_payload()
        html_doc = build_dashboard_html(
            payload,
            generated_on="05 Jun 2026 07:22 NZST",
            page_title="Q2 2026 EPCE | Quarterly Dashboard",
        )
        self.assertIn("overflow-x: hidden", html_doc)
        self.assertIn('width="100%"', html_doc)
        self.assertIn("viewBox=", html_doc)

    def test_education_cloud_squad_table_lists_all_configured_squads(self):
        payload = self._sample_payload()
        payload["squad"] = {"squads": {}}  # no velocity data yet
        html_doc = build_dashboard_html(
            payload,
            generated_on="05 Jun 2026 07:22 NZST",
            page_title="Q2 2026 EPCE | Quarterly Dashboard",
        )
        self.assertIn("Kākāriki", html_doc)
        self.assertIn("Kikorangi", html_doc)
        self.assertIn("Waiporoporo", html_doc)
        self.assertIn("Kākāriki Krew Scrum | Delivery", html_doc)
        self.assertIn("Kikorangi Tima Scrum | Delivery", html_doc)
        self.assertIn("Waiporoporo Scrum", html_doc)
        self.assertIn("/boards/893", html_doc)

    def test_y_tick_granularity(self):
        self.assertEqual(_y_tick_step(48.0), 5.0)
        ticks = _y_ticks(48.0)
        self.assertEqual(ticks[:3], [0.0, 5.0, 10.0])

    def test_week_start_dates(self):
        weeks = _week_start_dates(
            __import__("datetime").date(2026, 4, 1),
            __import__("datetime").date(2026, 4, 30),
        )
        self.assertEqual(weeks[0].isoformat(), "2026-04-06")
        self.assertEqual(len(weeks), 4)

    def test_release_code_label(self):
        self.assertEqual(release_code_label("2026-04-22", "Out Of Cycle"), "0422OC")
        self.assertEqual(release_code_label("2026-04-16", "In Cycle"), "0416IC")
        self.assertEqual(release_code_label("2026-04-16", "In Cycle Data"), "0416ID")
        self.assertEqual(release_code_label("2026-04-16", "Out Of Cycle Data"), "0416OD")

    def test_y_ticks_and_release_label_alignment(self):
        ticks = _y_ticks(48.0)
        self.assertIn(0.0, ticks)
        self.assertTrue(max(ticks) >= 48.0)
        labels = _layout_release_labels(
            [
                {
                    "name": "20260420-engine",
                    "releaseDate": "2026-04-20",
                    "carriageType": "Out Of Cycle",
                },
                {
                    "name": "20260422-engine",
                    "releaseDate": "2026-04-22",
                    "carriageType": "Out Of Cycle",
                },
            ],
            x_for=lambda d: float(d.day),
            x_min=__import__("datetime").date(2026, 4, 1),
            x_max=__import__("datetime").date(2026, 6, 30),
        )
        self.assertEqual(len(labels), 2)
        self.assertEqual(labels[0][1], "0420OC")
        self.assertEqual(labels[1][1], "0422OC")
        self.assertEqual(labels[0][2]["carriageType"], "Out Of Cycle")

    def test_lane_stacked_chart(self):
        payload = self._sample_payload()
        burn = payload["burn"]
        goal = {
            "plannedStoryPointsByScope": {
                "educationCloud": {"plannedStoryPoints": 400.0},
                "integration": {"plannedStoryPoints": 200.0},
                "inGlobalQuarter": {"plannedStoryPoints": 600.0},
            }
        }
        dates, series = _aligned_lane_cumulative(burn["lanes"], burn["combinedDaily"])
        self.assertEqual(len(dates), 2)
        self.assertEqual(series["educationCloud"][-1], 14.0)
        svg = _lane_burn_stacked_svg(
            burn,
            quarter_start="2026-04-01",
            quarter_end="2026-06-30",
            goal=goal,
            sprint_bands=[
                {
                    "label": "Sprint 22",
                    "sprintNumber": 22,
                    "start": date(2026, 4, 13),
                    "end": date(2026, 4, 23),
                    "fill": ATL["sprint_a"],
                }
            ],
            releases=[
                {
                    "name": "20260528-engine",
                    "releaseDate": "2026-05-28",
                    "carriageType": "In Cycle",
                }
            ],
        )
        self.assertIn("<polygon", svg)
        self.assertIn(LANE_STACK_FILL["educationCloud"], svg)
        self.assertIn("stroke-dasharray=\"5 4\"", svg)
        self.assertIn(ATL["neutral"], svg)
        self.assertIn(">S22<", svg)
        self.assertNotIn(_RELEASE_LABEL_SVG, svg)
        self.assertIn("<title>20260528-engine · 2026-05-28 | In Cycle | Code</title>", svg)
        self.assertIn(">Date<", svg)
        self.assertIn(ATL["blue"], svg)

    def test_lane_table_includes_education_cloud_squad_subrows(self):
        payload = self._sample_payload()
        payload["goal"] = {
            "plannedStoryPointsByScope": {
                "educationCloud": {"plannedStoryPoints": 14.0, "jql": "project = EPCE"},
                "educationCloudSquads": {
                    "kakariki": {
                        "label": "Kākāriki",
                        "scopeJql": "project = EPCE AND squad = kakariki",
                        "burnJql": "project = EPCE AND squad = kakariki AND type = Story",
                        "plannedStoryPoints": 14.0,
                        "unpointedStoriesBugs": 2,
                        "unpointedStoriesBugsJql": "project = EPCE AND squad = kakariki AND SP is EMPTY",
                        "unpointedIssueKeys": ["EPCE-1001", "EPCE-1002"],
                    },
                },
            }
        }
        payload["burn"]["lanes"]["educationCloud"]["events"][0]["deliverySquads"] = [
            "Kākāriki Krew"
        ]
        html_doc = build_dashboard_html(
            payload,
            generated_on="05 Jun 2026 07:22 NZST",
            page_title="Q2 2026 EPCE | Quarterly Dashboard",
        )
        self.assertIn('class="slice-squad"', html_doc)
        self.assertIn("Kikorangi", html_doc)
        self.assertIn("Waiporoporo", html_doc)
        self.assertIn("issue%20in%20%28EPCE-1001%2C%20EPCE-1002%29", html_doc)

    def test_unpointed_cell_prefers_issue_keys_over_jql(self):
        cell = _unpointed_cell(
            2,
            'project = EPCE AND "Story Points" is EMPTY',
            issue_keys=["EPCE-1", "EPCE-2"],
        )
        self.assertIn("issue%20in%20%28EPCE-1%2C%20EPCE-2%29", cell)
        self.assertNotIn("Story%20Points", cell)

    def test_release_code_cell_tooltip(self):
        cell = _release_code_cell(
            {
                "releaseDate": "2026-04-22",
                "carriageType": "Out Of Cycle",
                "releaseCode": "0422OC",
            }
        )
        self.assertIn('title="2026-04-22 | Out Of Cycle | Code"', cell)
        self.assertIn("release-code", cell)

    def test_release_code_cell_tooltip_data_carriage(self):
        cell = _release_code_cell(
            {
                "releaseDate": "2026-04-16",
                "carriageType": "Out Of Cycle Data",
                "releaseCode": "0416OD",
            }
        )
        self.assertIn('title="2026-04-16 | Out Of Cycle | Data"', cell)

    def test_allocation_table_release_code_tooltip(self):
        allocation = {
            "sprints": [],
            "inCycleReleases": [
                {
                    "name": "20260422-engine",
                    "releaseDate": "2026-04-22",
                    "carriageType": "Out Of Cycle",
                    "releaseCode": "0422OC",
                    "claimedStoryPoints": 5.0,
                    "events": [{"key": "EPCE-1"}],
                }
            ],
        }
        html_doc = _allocation_tables(allocation)
        self.assertIn('title="2026-04-22 | Out Of Cycle | Code"', html_doc)
        self.assertIn("0422OC", html_doc)

    def test_sprint_is_future(self):
        self.assertFalse(
            _sprint_is_future({"startDate": "2026-05-25"}, date(2026, 6, 5))
        )
        self.assertTrue(
            _sprint_is_future({"startDate": "2026-06-08"}, date(2026, 6, 5))
        )

    def test_allocation_table_greys_future_sprints(self):
        allocation = {
            "sprints": [
                {
                    "name": "Sprint 24",
                    "startDate": "2026-05-11",
                    "endDate": "2026-05-24",
                    "claimedStoryPoints": 10.0,
                    "events": [{"key": "EPCE-1"}],
                },
                {
                    "name": "Sprint 26",
                    "startDate": "2026-06-08",
                    "endDate": "2026-06-21",
                    "claimedStoryPoints": 0.0,
                    "events": [],
                },
            ],
            "inCycleReleases": [],
        }
        html_doc = _allocation_tables(allocation, as_of="2026-06-05")
        self.assertNotIn('class="row-projected">Sprint 24', html_doc.replace(" ", ""))
        self.assertIn('class="row-projected"', html_doc)
        self.assertIn("Sprint 26", html_doc)

    def test_allocation_table_greys_in_progress_sprint_metrics(self):
        allocation = {
            "sprints": [
                {
                    "name": "Sprint 26",
                    "startDate": "2026-06-08",
                    "endDate": "2026-06-21",
                    "claimedStoryPoints": 0.0,
                    "events": [],
                    "inProgress": True,
                    "scopedStoryPoints": 42.0,
                    "scopedIssueCount": 3,
                    "scopedIssueKeys": ["EPCE-1", "EPCE-2", "EPCE-3"],
                }
            ],
            "inCycleReleases": [],
        }
        html_doc = _allocation_tables(allocation, as_of="2026-06-09")
        self.assertIn("pending-metric", html_doc)
        self.assertIn("42.0", html_doc)
        self.assertIn("EPCE-1", html_doc)

    def test_allocation_table_greys_active_release_metrics(self):
        allocation = {
            "sprints": [],
            "inCycleReleases": [
                {
                    "name": "20260611-engine",
                    "releaseDate": "2026-06-11",
                    "projected": False,
                    "claimedStoryPoints": 0.0,
                    "events": [],
                    "inProgress": True,
                    "scopedStoryPoints": 100.0,
                    "scopedIssueCount": 17,
                    "scopedIssueKeys": ["EPCE-10"],
                },
                {
                    "name": "20260625-engine",
                    "releaseDate": "2026-06-25",
                    "projected": False,
                    "claimedStoryPoints": 0.0,
                    "events": [],
                },
            ],
        }
        html_doc = _allocation_tables(allocation, as_of="2026-06-09")
        self.assertIn("pending-metric", html_doc)
        self.assertIn("100.0", html_doc)
        self.assertIn("20260611-engine", html_doc)

    def test_build_confluence_template_body_scaffold(self):
        body = build_confluence_template_body(
            quarter_label="Q2 2026 delivery quarter",
            quarter_slug="2026-Q2",
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
            initiative_key="EPCE-3897",
            goal_target_date="2026-07-31",
            github_pages_url="https://example.github.io/quarter/",
            generated_on="11 Jun 2026 10:00 NZST",
        )
        self.assertIn("Awaiting first refresh", body)
        self.assertIn("2026-07-31", body)
        self.assertIn("EPCE-6745", body)
        self.assertIn("EPCE-3897", body)
        self.assertIn("EPC Programme Delivery Model", body)
        self.assertIn("Pending", body)
        self.assertIn("data-layout=\"full-width\"", body)
        self.assertNotIn("—", body)
        self.assertNotIn('ac:name="info"', body)

    def test_build_confluence_body_lane_table(self):
        body = build_confluence_body(self._sample_payload(), generated_on="4 Jun 2026")
        self.assertIn("Deploy Burn by Lane", body)
        self.assertIn("<strong>", body)
        self.assertNotIn("<h2>", body)
        self.assertIn("Kākāriki", body)

    def test_load_delivery_milestones_from_artifact(self):
        fixture = Path(__file__).resolve().parent / "fixtures" / "delivery-milestones.json"
        milestones = _load_delivery_milestones(fixture)
        self.assertGreaterEqual(len(milestones), 3)
        self.assertEqual(milestones[0]["date"], "2026-06-11")
        self.assertEqual(milestones[0]["label"], "ED Cloud Data within Fabric")

    def test_burn_svg_extends_flat_to_as_of(self):
        svg = _burn_svg(
            [{"date": "2026-06-09", "cumulative_story_points": 434.0}],
            planned=100.0,
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
            as_of="2026-06-10",
        )
        self.assertIn('stroke="#0052cc"', svg)
        match = re.search(
            r'<polyline fill="none" stroke="#0052cc"[^>]*points="([\d.]+),([\d.]+) ([\d.]+),\2"',
            svg,
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertGreater(float(match.group(3)), float(match.group(1)))

    def test_burn_svg_vertical_markers_render_above_series(self):
        svg = _burn_svg(
            [{"date": "2026-04-01", "cumulative_story_points": 10.0}],
            planned=100.0,
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
        )
        series_idx = svg.rfind('stroke="#0052cc"')
        markers_idx = svg.find("chart-vertical-markers")
        self.assertGreater(markers_idx, series_idx)

    def test_burn_svg_includes_today_line_in_quarter(self):
        from datetime import datetime
        from unittest.mock import patch
        from zoneinfo import ZoneInfo

        with patch("extensions.twoa_programme.quarterly_dashboard_svg_core.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                2026, 6, 12, 9, 0, tzinfo=ZoneInfo("Pacific/Auckland")
            )
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            svg = _burn_svg(
                [{"date": "2026-06-09", "cumulative_story_points": 434.0}],
                planned=100.0,
                quarter_start="2026-04-01",
                quarter_end="2026-08-20",
                as_of="2026-06-10",
            )
        self.assertIn("chart-today-line", svg)
        self.assertIn("Today: 2026-06-12 (Pacific/Auckland)", svg)

    def test_chart_legend_includes_today_row(self):
        legend = _chart_legend_html()
        self.assertIn("Today (NZ)", legend)

    def test_burn_svg_renders_clickable_milestone_line(self):
        milestones = [
            {"label": "ED Cloud Data within Fabric", "date": "2026-06-11", "key": "PDE-3834"}
        ]
        svg = _burn_svg(
            [{"date": "2026-04-22", "cumulative_story_points": 10.0}],
            planned=100.0,
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
            milestones=milestones,
        )
        self.assertIn("chart-milestone-line", svg)
        self.assertIn("chart-milestone-link", svg)
        self.assertIn("/browse/PDE-3834", svg)
        self.assertNotIn(">A</text>", svg)

    def test_chart_legend_includes_milestone_row(self):
        legend = _chart_legend_html()
        self.assertIn("Delivery milestone", legend)
        self.assertNotIn("chart-milestones", legend)

    def test_lane_burn_stacked_svg_renders_delivery_milestones(self):
        milestones = [{"label": "Curriculum Lifecycle", "date": "2026-07-06"}]
        svg = _lane_burn_stacked_svg(
            {
                "combinedDaily": [{"date": "2026-04-22", "cumulative_story_points": 10.0}],
                "lanes": {
                    "educationCloud": {
                        "daily": [{"date": "2026-04-22", "cumulative_story_points": 10.0}],
                    }
                },
            },
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
            milestones=milestones,
        )
        self.assertIn("chart-milestone-line", svg)
        self.assertNotIn(">A</text>", svg)

    def test_milestone_tooltip_plain_includes_header(self):
        from extensions.twoa_programme.delivery_milestones import milestone_tooltip_plain

        tip = milestone_tooltip_plain(
            {
                "label": "ED Cloud Data within Fabric",
                "date": "2026-06-11",
                "key": "PDE-3834",
                "description": "• SDR Reporting",
            }
        )
        self.assertIn("ED Cloud Data within Fabric | 2026-06-11 (PDE-3834)", tip)
        self.assertIn("SDR Reporting", tip)


if __name__ == "__main__":
    unittest.main()
