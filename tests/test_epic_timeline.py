"""Tests for epic timeline helpers and dashboard rendering."""

import re
import unittest
from datetime import date

from extensions.twoa_programme.epic_timeline import (
    EPIC_BAR_OPACITY_EARNED,
    EPIC_BAR_OPACITY_SCOPE,
    EPIC_EC_SQUAD_HEADER,
    EPIC_ROW_HEIGHT,
    EPIC_SWIMLANE_HEADER,
    LANE_DISPLAY_ORDER,
    build_epic_timeline_rows,
    build_release_date_lookup,
    classify_epic_ec_squad,
    classify_epic_lane,
    epic_timeline_plot_height,
    group_ec_epics_by_squad,
    group_epics_by_lane,
    resolve_epic_timeline_heights,
    resolve_epic_window,
    summarize_epic_children,
)
from extensions.twoa_programme.quarterly_dashboard import (
    ATL,
    LANE_STACK_FILL,
    _epic_timeline_svg,
    build_dashboard_html,
)
from extensions.twoa_programme.quarterly_dashboard_svg_core import (
    QUARTERLY_REPORT_MAX_EPIC_TIMELINE_SVG_HEIGHT,
    _svg_x_bottom_margin,
)


def _fields(
    *,
    squads: list[str] | None = None,
    change_types: list[str] | None = None,
    platform: str | None = None,
    sp: float | None = 5.0,
) -> dict:
    return {
        "issuetype": {"name": "Story"},
        "status": {"name": "Doing"},
        "customfield_11102": [{"value": v} for v in (squads or [])],
        "customfield_10079": [{"value": v} for v in (change_types or [])],
        "customfield_10120": {"value": platform} if platform else None,
        "customfield_10026": sp,
        "issuelinks": [],
    }


class EpicTimelineTests(unittest.TestCase):
    def test_resolve_epic_window_uses_release_lookup(self):
        lookup = {"20260528-engine": date(2026, 5, 28)}
        start, end, fv = resolve_epic_window(
            created="2026-04-10",
            epic_fix_versions=[],
            child_fix_versions=["20260528-engine", "20260528-engine"],
            release_lookup=lookup,
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 8, 20),
        )
        self.assertEqual(fv, "20260528-engine")
        self.assertEqual(start, date(2026, 4, 10))
        self.assertEqual(end, date(2026, 5, 28))

    def test_classify_epic_lane_by_child_story_points(self):
        epic = {"fields": _fields(squads=["Kākāriki Krew"])}
        children = [
            {"fields": _fields(squads=["Kākāriki Krew"], sp=10.0)},
            {"fields": _fields(platform="azure-integration-services", sp=20.0)},
        ]
        lane = classify_epic_lane(
            epic,
            children,
            delivery_squad_field="customfield_11102",
            change_types_field="customfield_10079",
            platform_field="customfield_10120",
            story_points_field="customfield_10026",
        )
        self.assertEqual(lane, "integration")

    def test_group_epics_by_lane_preserves_slice_order(self):
        grouped = group_epics_by_lane(
            [
                {"key": "EPCE-2", "lane": "integration", "endDate": "2026-05-01"},
                {"key": "EPCE-1", "lane": "educationCloud", "endDate": "2026-04-01"},
            ]
        )
        self.assertEqual([e["key"] for e in grouped["educationCloud"]], ["EPCE-1"])
        self.assertEqual([e["key"] for e in grouped["integration"]], ["EPCE-2"])
        self.assertEqual(list(LANE_DISPLAY_ORDER)[0], "educationCloud")

    def test_classify_epic_ec_squad_by_child_delivery_squad(self):
        epic = {"fields": _fields(squads=["Kikorangi Tīma"])}
        children = [
            {"fields": _fields(squads=["Kākāriki Krew"], sp=10.0)},
            {"fields": _fields(squads=["Kikorangi Tīma"], sp=25.0)},
        ]
        squad = classify_epic_ec_squad(
            epic,
            children,
            delivery_squad_field="customfield_11102",
            change_types_field="customfield_10079",
            platform_field="customfield_10120",
            story_points_field="customfield_10026",
        )
        self.assertEqual(squad, "kikorangi")

    def test_group_ec_epics_by_squad(self):
        grouped = group_ec_epics_by_squad(
            [
                {"key": "EPCE-1", "ecSquad": "waiporoporo", "endDate": "2026-05-01"},
                {"key": "EPCE-2", "ecSquad": "kakariki", "endDate": "2026-04-01"},
            ]
        )
        self.assertEqual([e["key"] for e in grouped["kakariki"]], ["EPCE-2"])

    def test_summarize_epic_children_counts_story_bug_only(self):
        deploy_statuses = {"Deploy", "PRD"}
        children = [
            {"fields": _fields(sp=5.0)},
            {"fields": {**_fields(sp=3.0), "issuetype": {"name": "Bug"}, "status": {"name": "Deploy"}}},
            {"fields": {**_fields(sp=4.0), "issuetype": {"name": "Story"}, "status": {"name": "Done"}}},
            {"fields": {**_fields(sp=2.0), "issuetype": {"name": "Spike"}}},
            {"fields": {**_fields(sp=None), "issuetype": {"name": "Story"}}},
        ]
        metrics = summarize_epic_children(
            children,
            story_points_field="customfield_10026",
            change_types_field="customfield_10079",
            delivery_squad_field="customfield_11102",
            deploy_statuses=deploy_statuses,
            done_statuses={"Done", "Closed"},
        )
        self.assertEqual(metrics["childCount"], 4)
        self.assertEqual(metrics["storyPoints"], 12.0)
        self.assertEqual(metrics["earnedStoryPoints"], 7.0)
        self.assertEqual(metrics["unpointedCount"], 1)

    def test_build_epic_timeline_rows_skips_empty_ec_squads(self):
        grouped = group_epics_by_lane(
            [
                {
                    "key": "EPCE-100",
                    "lane": "educationCloud",
                    "ecSquad": "kakariki",
                    "endDate": "2026-05-01",
                },
                {
                    "key": "EPCE-101",
                    "lane": "educationCloud",
                    "ecSquad": "waiporoporo",
                    "endDate": "2026-06-01",
                },
            ]
        )
        rows = build_epic_timeline_rows(grouped, lane_labels={"educationCloud": "Education Cloud"})
        squad_rows = [row for row in rows if row["kind"] == "squad"]
        self.assertEqual([row["label"] for row in squad_rows], ["Kākāriki", "Waiporoporo"])
        self.assertEqual(
            epic_timeline_plot_height(rows),
            EPIC_SWIMLANE_HEADER + 2 * EPIC_EC_SQUAD_HEADER + 2 * EPIC_ROW_HEIGHT,
        )

    def test_epic_timeline_label_and_bar_share_row(self):
        svg = _epic_timeline_svg(
            [
                {
                    "key": "EPCE-100",
                    "summary": "Sample epic",
                    "status": "Doing",
                    "lane": "educationCloud",
                    "ecSquad": "kakariki",
                    "startDate": "2026-04-13",
                    "endDate": "2026-05-28",
                    "fixVersion": "20260528-engine",
                    "childCount": 4,
                    "storyPoints": 20.0,
                    "earnedStoryPoints": 10.0,
                    "unpointedCount": 1,
                },
                {
                    "key": "EPCE-200",
                    "summary": "Integration epic",
                    "status": "Doing",
                    "lane": "integration",
                    "startDate": "2026-04-01",
                    "endDate": "2026-06-11",
                    "storyPoints": 5.0,
                    "earnedStoryPoints": 0.0,
                    "childCount": 1,
                    "unpointedCount": 0,
                },
            ],
            quarter_start="2026-04-01",
            quarter_end="2026-06-30",
        )
        for key in ("EPCE-100", "EPCE-200"):
            label_match = re.search(
                rf'browse/{key}".*?<text x="212" y="([0-9.]+)"[^>]*dominant-baseline="middle"',
                svg,
                re.DOTALL,
            )
            bar_match = re.search(
                rf"<g><title>{key}[^<]*</title>.*?rect x=\"[0-9.]+\" y=\"([0-9.]+)\"",
                svg,
                re.DOTALL,
            )
            self.assertIsNotNone(label_match, key)
            self.assertIsNotNone(bar_match, key)
            label_y = float(label_match.group(1))
            bar_y = float(bar_match.group(1))
            bar_h = EPIC_ROW_HEIGHT - 6.0
            bar_center = bar_y + bar_h / 2
            self.assertAlmostEqual(label_y, bar_center, delta=0.5, msg=key)

    def test_epic_timeline_svg_fits_report_page(self):
        svg = _epic_timeline_svg(
            [
                {
                    "key": "EPCE-100",
                    "summary": "Sample epic",
                    "status": "Doing",
                    "lane": "educationCloud",
                    "startDate": "2026-04-13",
                    "endDate": "2026-05-28",
                    "childCount": 4,
                    "storyPoints": 20.0,
                    "earnedStoryPoints": 10.0,
                    "unpointedCount": 0,
                }
            ],
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
        )
        svg_open = svg.split(">", 1)[0]
        self.assertIn('width="100%"', svg_open)
        self.assertIn("viewBox=", svg_open)

    def test_epic_timeline_svg_renders_clickable_dtrain_scope_segments(self):
        svg = _epic_timeline_svg(
            [
                {
                    "key": "EPCE-100",
                    "summary": "Scoped epic",
                    "status": "Doing",
                    "lane": "educationCloud",
                    "startDate": "2026-04-13",
                    "endDate": "2026-05-28",
                    "childCount": 3,
                    "storyPoints": 13.0,
                    "earnedStoryPoints": 5.0,
                    "unpointedCount": 1,
                    "scopeRollup": {
                        "phases": {
                            "Dream": 0.0,
                            "Discover": 0.0,
                            "Design": 5.0,
                            "Develop": 8.0,
                            "Deliver": 0.0,
                            "Demonstrate": 0.0,
                            "Deploy": 0.0,
                            "Drive": 0.0,
                            "Unknown": 0.0,
                        },
                        "phaseIssueKeys": {
                            "Design": ["EPCE-501"],
                            "Develop": ["EPCE-502", "EPCE-503"],
                        },
                        "unpointedCount": 1,
                        "unpointedIssueKeys": ["EPCE-504"],
                        "storyPoints": 13.0,
                        "totalWeight": 14.0,
                    },
                }
            ],
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
        )
        self.assertIn('class="milestone-scope-segment"', svg)
        self.assertIn("key%20in%20%28EPCE-501%29", svg)
        self.assertIn("key%20in%20%28EPCE-502%2C%20EPCE-503%29", svg)
        self.assertIn("key%20in%20%28EPCE-504%29", svg)
        self.assertIn("#9f4c22", svg)  # Design phase fill
        self.assertIn("#7f582d", svg)  # Develop phase fill

    def test_epic_timeline_svg_height_capped_to_report_page(self):
        epics = [
            {
                "key": f"EPCE-{100 + index}",
                "summary": f"Epic {index}",
                "status": "Doing",
                "lane": "educationCloud",
                "ecSquad": "kakariki" if index % 2 == 0 else "kikorangi",
                "startDate": "2026-04-01",
                "endDate": "2026-06-30",
                "storyPoints": 5.0,
                "earnedStoryPoints": 0.0,
                "childCount": 1,
                "unpointedCount": 0,
            }
            for index in range(40)
        ]
        svg = _epic_timeline_svg(
            epics,
            quarter_start="2026-04-01",
            quarter_end="2026-08-20",
        )
        height_match = re.search(r'height="(\d+)"', svg.split(">", 1)[0])
        self.assertIsNotNone(height_match)
        svg_height = int(height_match.group(1))
        self.assertLessEqual(svg_height, QUARTERLY_REPORT_MAX_EPIC_TIMELINE_SVG_HEIGHT)
        grouped = group_epics_by_lane(epics)
        rows = build_epic_timeline_rows(grouped, lane_labels={"educationCloud": "Education Cloud"})
        natural = epic_timeline_plot_height(rows)
        scaled = resolve_epic_timeline_heights(
            rows,
            plot_top=56,
            bottom_margin=_svg_x_bottom_margin(),
            max_svg_height=QUARTERLY_REPORT_MAX_EPIC_TIMELINE_SVG_HEIGHT,
        )
        self.assertLess(scaled["plot_h"], natural)
        self.assertLess(scaled["scale"], 1.0)

    def test_epic_timeline_svg_reuses_sprint_and_release_overlay_with_swimlanes(self):
        svg = _epic_timeline_svg(
            [
                {
                    "key": "EPCE-100",
                    "summary": "Sample epic",
                    "status": "Doing",
                    "lane": "educationCloud",
                    "ecSquad": "kakariki",
                    "startDate": "2026-04-13",
                    "endDate": "2026-05-28",
                    "fixVersion": "20260528-engine",
                    "childCount": 4,
                    "storyPoints": 20.0,
                    "earnedStoryPoints": 10.0,
                    "unpointedCount": 1,
                },
                {
                    "key": "EPCE-101",
                    "summary": "Kikorangi epic",
                    "status": "Doing",
                    "lane": "educationCloud",
                    "ecSquad": "kikorangi",
                    "startDate": "2026-04-01",
                    "endDate": "2026-06-11",
                },
                {
                    "key": "EPCE-200",
                    "summary": "Integration epic",
                    "status": "Doing",
                    "lane": "integration",
                    "startDate": "2026-04-01",
                    "endDate": "2026-06-11",
                },
            ],
            quarter_start="2026-04-01",
            quarter_end="2026-06-30",
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
            milestones=[{"label": "ED Cloud Data within Fabric", "date": "2026-06-11"}],
        )
        self.assertIn("Epic delivery timeline by lane", svg)
        self.assertIn("Education Cloud", svg)
        self.assertIn("chart-milestone-line", svg)
        self.assertNotIn(">A</text>", svg)
        self.assertIn("Kākāriki", svg)
        self.assertIn("Kikorangi", svg)
        self.assertIn("Integration", svg)
        self.assertIn(LANE_STACK_FILL["educationCloud"], svg)
        self.assertIn(">S22<", svg)
        self.assertIn("<title>20260528-engine · 2026-05-28 | In Cycle | Code</title>", svg)
        self.assertIn("EPCE-100", svg)
        self.assertIn("EPCE-200", svg)
        self.assertIn('href="https://twoa.atlassian.net/browse/EPCE-100"', svg)
        self.assertIn(f'opacity="{EPIC_BAR_OPACITY_SCOPE}"', svg)
        self.assertIn(f'opacity="{EPIC_BAR_OPACITY_EARNED}"', svg)
        self.assertIn("Children (Story/Bug): 4", svg)
        self.assertIn("Unpointed children: 1", svg)

    def test_dashboard_includes_epic_timeline_section(self):
        payload = {
            "status": {
                "quarter": "2026-Q2",
                "storyKey": "EPCE-6745",
                "goalInitiativeKey": "EPCE-3897",
                "quarterStart": "2026-04-01",
                "quarterEnd": "2026-06-30",
                "asOf": "2026-06-04",
                "elapsedFraction": 0.5,
                "daysRemaining": 26,
                "earnedStoryPoints": 10.0,
                "plannedStoryPoints": 100.0,
                "idealEarnedStoryPoints": 50.0,
                "burnVariance": -40.0,
                "requiredDailyVelocity": 3.0,
                "onTrack": False,
            },
            "burn": {"combinedDaily": [{"date": "2026-04-22", "cumulative_story_points": 10.0}]},
            "epicTimeline": {
                "epics": [
                    {
                        "key": "EPCE-200",
                        "summary": "Timeline epic",
                        "status": "Doing",
                        "lane": "educationCloud",
                        "startDate": "2026-04-01",
                        "endDate": "2026-05-28",
                    }
                ]
            },
            "releasePlan": {
                "sprints": [
                    {"name": "Sprint 22", "startDate": "2026-04-13", "endDate": "2026-04-23"}
                ],
                "inCycleReleases": [
                    {"name": "20260528-engine", "releaseDate": "2026-05-28", "carriageType": "In Cycle"}
                ],
            },
        }
        html_doc = build_dashboard_html(
            payload,
            generated_on="08 Jun 2026 12:00 NZST",
            page_title="Q2 2026 EPCE | Quarterly Dashboard",
        )
        self.assertIn("Epic Timeline", html_doc)
        self.assertIn("chart-wrap-epic-timeline", html_doc)
        self.assertIn("Key — bar scope (D-Train)", html_doc)
        self.assertIn("max-height: none", html_doc)
        self.assertIn("overflow-y: visible", html_doc)
        self.assertIn("EPCE-200", html_doc)
        self.assertIn("Initiative <a href=\"https://twoa.atlassian.net/browse/EPCE-3897\"", html_doc)


if __name__ == "__main__":
    unittest.main()
