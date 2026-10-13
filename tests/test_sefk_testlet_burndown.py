from __future__ import annotations

import unittest
from datetime import date

from extensions.twoa_programme.sefk_testlet_burndown import (
    _y_axis_ticks,
    _run_rate_metrics,
    build_sefk_testlet_burndown_html,
    build_sefk_testlet_burndown_payload,
    resolved_testlets_for_day_jql as _resolved_testlets_for_day_jql,
    testlet_scope_jql as _testlet_scope_jql,
)


class SefkTestletBurndownTests(unittest.TestCase):
    def test_system_integration_report_titles_match_platform(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [],
            {},
            ideal_start="2026-10-05",
            ideal_end="2026-10-23",
            as_of="2026-10-06",
        )

        for test_type, platform, title in (
            ("Unit", None, "Unit | Unit | Testlet Burndown"),
            (
                "System Integration",
                "azure-integration-services",
                "System Integration | Workday &lt;&gt; AIS &lt;&gt; TWoA | Testlet Burndown",
            ),
            (
                "System Integration",
                "workday",
                "System Integration | Workday &lt;&gt; GPC &lt;&gt; Datapay | Testlet Burndown",
            ),
        ):
            with self.subTest(platform=platform):
                document = build_sefk_testlet_burndown_html(
                    payload,
                    generated_on="06 Oct 2026",
                    test_type=test_type,
                    bounds_issue_key="SEFK-1216",
                    platform=platform,
                )

                self.assertIn(f"<title>SEFK | {title}</title>", document)
                self.assertIn(f"/ {title}</nav>", document)
                self.assertIn(f"<h1>{title}</h1>", document)

    def test_workday_scope_uses_workday_platform_filter(self) -> None:
        jql = _testlet_scope_jql(
            "System Integration",
            "workday",
            include_all_engine_versions=True,
        )

        self.assertIn('"Test Types" = "System Integration"', jql)
        self.assertIn('"Deferred"', jql)
        self.assertIn('cf[10079] = "workday"', jql)
        self.assertNotIn("azure-integration-services", jql)
        self.assertNotIn("smart-sefk-current-engine", jql)
        self.assertIn("smart-sefk-current-engine", _testlet_scope_jql("System Integration", "azure-integration-services"))

    def test_day_jql_uses_full_timestamp_window(self) -> None:
        jql = _resolved_testlets_for_day_jql("Unit", date(2026, 10, 12))

        self.assertIn(
            'status CHANGED TO "Passed" DURING ("2026-10-12 00:00", "2026-10-12 23:59")',
            jql,
        )
        self.assertEqual(jql.count("DURING"), 3)

    def test_workday_wide_scope_applies_to_report_and_chart_links(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [{"fields": {"created": "2026-10-05", "resolution": None}}],
            {},
            ideal_start="2026-10-05",
            ideal_end="2026-10-23",
            as_of="2026-10-06",
        )

        document = build_sefk_testlet_burndown_html(
            payload,
            generated_on="06 Oct 2026",
            test_type="System Integration",
            bounds_issue_key="SEFK-1216",
            platform="workday",
            include_all_engine_versions=True,
        )

        self.assertIn("(all SEFK engine versions)", document)
        self.assertNotIn("smart-sefk-current-engine", document)
        self.assertIn("cf%5B10079%5D%20%3D%20%22workday%22", document)

    def test_y_axis_top_tick_equals_scoped_total(self) -> None:
        self.assertEqual(_y_axis_ticks(82), (0, 41, 82))
        self.assertEqual(_y_axis_ticks(401), (0, 200, 401))

    def test_run_rate_counts_passed_and_failed_status_transitions(self) -> None:
        issues = [
            {
                "key": "SEFK-CYCLE-1",
                "fields": {
                    "created": "2026-10-05",
                    "resolution": {"id": "10000", "name": "Done"},
                    "resolutiondate": "2026-10-09",
                    "status": {"name": "Passed"},
                },
            },
            {
                "key": "SEFK-CYCLE-2",
                "fields": {
                    "created": "2026-10-05",
                    "resolution": {"id": "10000", "name": "Done"},
                    "resolutiondate": "2026-10-08",
                    "status": {"name": "Failed"},
                },
            },
            {
                "key": "SEFK-CYCLE-3",
                "fields": {"created": "2026-10-05", "resolution": None},
            },
        ]
        histories = {
            "SEFK-CYCLE-1": [
                {
                    "created": "2026-10-06",
                    "items": [
                        {"field": "resolution", "from": None, "to": "10000"},
                        {"field": "status", "fromString": "In Testing", "toString": "Failed"},
                    ],
                },
                {
                    "created": "2026-10-07",
                    "items": [{"field": "resolution", "from": "10000", "to": None}],
                },
                {
                    "created": "2026-10-09",
                    "items": [
                        {"field": "resolution", "from": None, "to": "10000"},
                        {"field": "status", "fromString": "In Testing", "toString": "Passed"},
                    ],
                },
            ],
            "SEFK-CYCLE-2": [
                {
                    "created": "2026-10-08",
                    "items": [{"field": "status", "fromString": "In Testing", "toString": "Failed"}],
                }
            ],
        }
        payload = build_sefk_testlet_burndown_payload(
            issues,
            histories,
            ideal_start="2026-10-05",
            ideal_end="2026-10-23",
            as_of="2026-10-09",
        )

        run_rate, successful_rate, required_run_rate = _run_rate_metrics(payload)
        document = build_sefk_testlet_burndown_html(
            payload,
            generated_on="09 Oct 2026",
            test_type="System Integration",
            bounds_issue_key="SEFK-1216",
        )

        self.assertEqual(sum(row["completed"] for row in payload["daily"]), 3)
        self.assertEqual(sum(row["executed"] for row in payload["daily"]), 3)
        self.assertEqual(sum(row["passed"] for row in payload["daily"]), 1)
        self.assertEqual(sum(row["failed"] for row in payload["daily"]), 2)
        self.assertEqual(payload["remainingTestlets"], 2)
        self.assertAlmostEqual(run_rate, 0.6)
        self.assertAlmostEqual(successful_rate, 0.2)
        self.assertAlmostEqual(required_run_rate or 0.0, 2 / 14)
        self.assertEqual(payload["forecastDate"], "2026-10-19")
        self.assertIn('class="forecast-trend"', document)
        self.assertIn(">0.6</strong><span>Execution attempts/day</span>", document)
        self.assertIn(">0.2</strong><span>Successful completions/day</span>", document)
        self.assertIn(">0.1</strong><span>Required completion rate (tests/day)</span>", document)
        self.assertIn("Failed: 1", document)

    def test_replays_created_resolution_reopen_and_resolved_without_history(self) -> None:
        issues = [
            {
                "key": "SEFK-1",
                "fields": {
                    "created": "2026-10-01T09:00:00.000+0000",
                    "resolution": None,
                },
            },
            {
                "key": "SEFK-2",
                "fields": {
                    "created": "2026-10-02T09:00:00.000+0000",
                    "resolution": {"id": "10000", "name": "Done"},
                    "resolutiondate": "2026-10-02T09:00:00.000+0000",
                },
            },
        ]
        histories = {
            "SEFK-1": [
                {
                    "created": "2026-10-03T09:00:00.000+0000",
                    "items": [{"field": "resolution", "from": None, "to": "10000"}],
                },
                {
                    "created": "2026-10-05T09:00:00.000+0000",
                    "items": [{"field": "resolution", "from": "10000", "to": None}],
                },
            ],
            "SEFK-2": [
                {
                    "created": "2026-10-02T09:00:00.000+0000",
                    "items": [{"field": "resolution", "from": None, "to": "10000"}],
                }
            ],
        }

        payload = build_sefk_testlet_burndown_payload(
            issues,
            histories,
            ideal_start="2026-10-01",
            ideal_end="2026-10-09",
            as_of="2026-10-05",
        )

        self.assertEqual(payload["totalTestlets"], 2)
        self.assertEqual(payload["completedTestlets"], 1)
        self.assertEqual(payload["remainingTestlets"], 1)
        self.assertEqual(payload["idealStartDate"], "2026-10-01")
        self.assertEqual(payload["idealEndDate"], "2026-10-09")
        self.assertEqual(payload["idealStartRemaining"], 2)
        self.assertIsNone(payload["forecastDate"])
        self.assertEqual(
            [row["remaining"] for row in payload["daily"]],
            [1, 1, 0, 0, 1],
        )
        document = build_sefk_testlet_burndown_html(payload, generated_on="05 Oct 2026")
        self.assertNotIn("Resolution set", document)
        self.assertNotIn('class="forecast-trend"', document)
        self.assertIn('class="actual-point"', document)
        self.assertIn("1 Oct 2026: 1 of 2 Unit Testlet remaining\nTerminal outcomes: 0\nPassed: 0\nRejected: 0\nDeferred: 0\nExecution attempts: 0\nFailed: 0\nBlocked: 0\nCreated: 1", document)
        self.assertIn('class="actual-point-link"', document)
        self.assertIn('target="_blank" rel="noopener" tabindex="0"', document)
        self.assertIn('status%20CHANGED%20TO%20%22Passed%22', document)
        self.assertIn('status%20CHANGED%20TO%20%22Deferred%22', document)
        self.assertIn("2 Oct 2026: 1 of 2 Unit Testlet remaining\nTerminal outcomes: 0\nPassed: 0\nRejected: 0\nDeferred: 0\nExecution attempts: 0\nFailed: 0\nBlocked: 0\nCreated: 1", document)
        self.assertIn("3 Oct 2026: 0 of 2 Unit Testlets remaining", document)
        self.assertIn("5 Oct 2026: 1 of 2 Unit Testlet remaining\nTerminal outcomes: 0\nPassed: 0\nRejected: 0\nDeferred: 0\nExecution attempts: 0\nFailed: 0\nBlocked: 0\nCreated: 0", document)
        self.assertNotIn("daily delta", document)
        self.assertIn('class="ideal"', document)
        self.assertIn(
            'points="64.0,42.0 976.0,332.0" class="ideal"',
            document,
        )
        self.assertNotIn('class="trend"', document)
        self.assertIn('class="chart-layout"', document)
        self.assertNotIn('class="chart-title"', document)
        self.assertNotIn("Best-fit completion estimate", document)
        self.assertIn('grid-template-columns: repeat(6, minmax(0, 1fr))', document)
        self.assertIn('border-radius: 4px', document)
        self.assertIn('grid-template-columns: repeat(3, minmax(0, 1fr))', document)
        self.assertIn('grid-template-columns: repeat(2, minmax(0, 1fr))', document)
        self.assertIn("--series-actual: #3bbf91", document)
        self.assertIn("--series-ideal: #6041a8", document)
        self.assertIn("--series-forecast: #f5ae0b", document)
        self.assertIn(".swatch.forecast { width: 0; height: 16px; margin-left: 8px; border-top: 0; border-left: 2px dashed var(--series-forecast); }", document)
        self.assertNotIn("Best-fit trend", document)
        self.assertIn("Successful completions/day", document)
        self.assertNotIn('class="actual-label"', document)
        self.assertNotIn('class="as-of-marker"', document)
        self.assertIn('class="target-marker"', document)
        self.assertIn("Target 9 Oct", document)
        self.assertIn('y="22" text-anchor="middle" class="target-label"', document)
        self.assertNotIn('class="forecast-label"', document)
        self.assertIn('class="weekend-band"', document)
        self.assertIn(".weekend-band { fill: #e8ebef; }", document)
        self.assertIn("class=\"week-grid\"", document)
        self.assertIn(">1 Oct</text>", document)
        self.assertIn(">9 Oct</text>", document)
        self.assertIn("Ideal pace", document)
        self.assertIn("Unit Testlets remaining from 2026-10-01 to 2026-10-09", document)

    def test_html_contains_summary_and_burndown_series(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [
                {
                    "key": "SEFK-3",
                    "fields": {
                        "created": "2026-10-01",
                        "resolution": None,
                    },
                }
            ],
            {},
            ideal_start="2026-10-01",
            ideal_end="2026-10-09",
            as_of="2026-10-02",
        )

        document = build_sefk_testlet_burndown_html(payload, generated_on="02 Oct 2026")

        self.assertIn("Unit | Unit | Testlet Burndown", document)
        self.assertIn("Actual remaining", document)
        self.assertIn("Jira resolution and status history", document)
        self.assertIn("Terminal outcomes", document)
        self.assertIn("Passed", document)
        self.assertIn("Rejected / removed", document)
        self.assertIn("Deferred / removed", document)
        self.assertIn("Failed (within Remaining)", document)
        self.assertIn("Ideal pace", document)
        self.assertIn("filter%20%3D%20smart-project-sefk", document)
        self.assertIn("filter%20%3D%20smart-types-tests", document)
        self.assertIn("2026-10-02", document)

    def test_passed_status_without_resolution_remains_open(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [
                {
                    "key": "SEFK-5",
                    "fields": {
                        "created": "2026-10-01",
                        "status": {"name": "Passed", "statusCategory": {"key": "done"}},
                        "resolution": None,
                    },
                }
            ],
            {},
            ideal_start="2026-10-01",
            ideal_end="2026-10-09",
            as_of="2026-10-02",
        )

        self.assertEqual(payload["completedTestlets"], 1)
        self.assertEqual(payload["passedTestlets"], 1)
        self.assertEqual(payload["remainingTestlets"], 0)
        self.assertEqual([row["remaining"] for row in payload["daily"]], [0, 0])

    def test_deferred_status_is_terminal_and_removed_from_remaining(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [{"key": "SEFK-DEFERRED", "fields": {
                "created": "2026-10-01",
                "resolution": None,
                "status": {"name": "Deferred"},
            }}],
            {},
            ideal_start="2026-10-01",
            ideal_end="2026-10-09",
            as_of="2026-10-02",
        )

        self.assertEqual(payload["completedTestlets"], 1)
        self.assertEqual(payload["deferredTestlets"], 1)
        self.assertEqual(payload["passedTestlets"], 0)
        self.assertEqual(payload["remainingTestlets"], 0)
        self.assertEqual(payload["daily"][-1]["executed"], 0)

    def test_current_failed_count_is_a_subset_of_remaining(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [
                {
                    "key": "SEFK-FAILED",
                    "fields": {
                        "created": "2026-10-01",
                        "resolution": None,
                        "status": {"name": "Failed"},
                    },
                }
            ],
            {},
            ideal_start="2026-10-01",
            ideal_end="2026-10-09",
            as_of="2026-10-02",
        )
        document = build_sefk_testlet_burndown_html(payload, generated_on="02 Oct 2026")

        self.assertEqual(payload["failedTestlets"], 1)
        self.assertEqual(payload["remainingTestlets"], 1)
        self.assertEqual(payload["totalTestlets"], 1)
        self.assertIn("Failed (within Remaining)", document)

    def test_flagged_impediment_counts_as_blocked_card_and_daily_tooltip(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [
                {"key": "SEFK-B1", "fields": {
                    "created": "2026-10-01",
                    "resolution": None,
                    "status": {"name": "In Testing"},
                    "customfield_10021": [{"value": "Impediment"}],
                }},
                {"key": "SEFK-B2", "fields": {
                    "created": "2026-10-01",
                    "resolution": None,
                    "status": {"name": "In Testing"},
                    "customfield_10021": None,
                }},
            ],
            {
                "SEFK-B1": [{"created": "2026-10-02T09:00:00.000+0000", "items": [
                    {"field": "Flagged", "fromString": "", "toString": "Impediment"},
                ]}],
                "SEFK-B2": [
                    {"created": "2026-10-02T09:00:00.000+0000", "items": [
                        {"field": "Flagged", "fromString": "", "toString": "Impediment"},
                    ]},
                    {"created": "2026-10-03T09:00:00.000+0000", "items": [
                        {"field": "Flagged", "fromString": "Impediment", "toString": ""},
                    ]},
                ],
            },
            ideal_start="2026-10-01",
            ideal_end="2026-10-09",
            as_of="2026-10-03",
        )
        document = build_sefk_testlet_burndown_html(payload, generated_on="03 Oct 2026")

        self.assertEqual(payload["blockedTestlets"], 1)
        self.assertEqual([row["blocked"] for row in payload["daily"]], [0, 2, 1])
        self.assertIn("Blocked (flagged Impediment)", document)
        self.assertIn("Failed: 0\nBlocked: 2\nCreated: 0", document)

    def test_status_category_controls_scope_even_if_resolution_is_set(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [{"key": "SEFK-FAILED-RESOLVED", "fields": {
                "created": "2026-10-01",
                "resolution": {"id": "10000", "name": "Done"},
                "status": {"name": "Failed", "statusCategory": {"key": "indeterminate"}},
            }}],
            {},
            ideal_start="2026-10-01",
            ideal_end="2026-10-09",
            as_of="2026-10-02",
        )

        self.assertEqual(payload["failedTestlets"], 1)
        self.assertEqual(payload["completedTestlets"], 0)
        self.assertEqual(payload["remainingTestlets"], 1)

    def test_rejected_status_burns_down_and_is_included_in_daily_jira_link(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [
                {
                    "key": "SEFK-REJECTED",
                    "fields": {
                        "created": "2026-10-01",
                        "resolution": None,
                        "status": {"name": "Rejected"},
                    },
                }
            ],
            {
                "SEFK-REJECTED": [
                    {
                        "created": "2026-10-03T09:00:00.000+0000",
                        "items": [
                            {
                                "field": "status",
                                "from": "12345",
                                "fromString": "In Test Development",
                                "to": "12346",
                                "toString": "Rejected",
                            }
                        ],
                    }
                ]
            },
            ideal_start="2026-10-01",
            ideal_end="2026-10-09",
            as_of="2026-10-04",
        )
        document = build_sefk_testlet_burndown_html(payload, generated_on="04 Oct 2026")

        self.assertEqual(payload["completedTestlets"], 1)
        self.assertEqual(payload["rejectedTestlets"], 1)
        self.assertEqual(payload["remainingTestlets"], 0)
        self.assertEqual([row["remaining"] for row in payload["daily"]], [1, 1, 0, 0])
        self.assertEqual(payload["daily"][2]["rejected"], 1)
        self.assertEqual(payload["daily"][2]["executed"], 0)
        self.assertEqual(_run_rate_metrics(payload)[0], 0.0)
        self.assertIn("3 Oct 2026: 0 of 1 Unit Testlets remaining", document)
        self.assertIn('status%20CHANGED%20TO%20%22Rejected%22', document)
        self.assertIn("Jira resolution and status history", document)

    def test_leaving_rejected_reopens_testlet_without_resolution(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [
                {
                    "key": "SEFK-REOPENED",
                    "fields": {
                        "created": "2026-10-01",
                        "resolution": None,
                        "status": {"name": "In Test Development"},
                    },
                }
            ],
            {
                "SEFK-REOPENED": [
                    {
                        "created": "2026-10-03T09:00:00.000+0000",
                        "items": [
                            {
                                "field": "status",
                                "fromString": "In Test Development",
                                "toString": "Rejected",
                            }
                        ],
                    },
                    {
                        "created": "2026-10-04T09:00:00.000+0000",
                        "items": [
                            {
                                "field": "status",
                                "fromString": "Rejected",
                                "toString": "In Test Development",
                            }
                        ],
                    },
                ]
            },
            ideal_start="2026-10-01",
            ideal_end="2026-10-09",
            as_of="2026-10-04",
        )

        self.assertEqual(payload["completedTestlets"], 0)
        self.assertEqual(payload["rejectedTestlets"], 0)
        self.assertEqual(payload["remainingTestlets"], 1)
        self.assertEqual([row["remaining"] for row in payload["daily"]], [1, 1, 0, 1])

    def test_tooltip_separates_resolutions_from_net_burndown(self) -> None:
        issues = [
            {
                "key": f"SEFK-NEW-{index}",
                "fields": {"created": "2026-10-07", "resolution": None},
            }
            for index in range(33)
        ] + [
            {
                "key": f"SEFK-DONE-{index}",
                "fields": {
                    "created": "2026-10-01",
                    "resolution": {"id": "10000", "name": "Done"},
                    "resolutiondate": "2026-10-07T09:00:00.000+0000",
                },
            }
            for index in range(42)
        ]
        histories = {
            f"SEFK-DONE-{index}": [
                {
                    "created": "2026-10-07T09:00:00.000+0000",
                    "items": [{"field": "resolution", "from": None, "to": "10000"}],
                }
            ]
            for index in range(42)
        }

        payload = build_sefk_testlet_burndown_payload(
            issues,
            histories,
            ideal_start="2026-10-01",
            ideal_end="2026-10-09",
            as_of="2026-10-07",
        )
        oct_7 = next(row for row in payload["daily"] if row["date"] == "2026-10-07")
        document = build_sefk_testlet_burndown_html(payload, generated_on="07 Oct 2026")

        self.assertEqual(oct_7["resolutiondateMatches"], 42)
        self.assertEqual(oct_7["created"], 33)
        self.assertEqual(oct_7["remaining"], 33)
        self.assertIn(
            "7 Oct 2026: 33 of 75 Unit Testlets remaining\nTerminal outcomes: 0\nPassed: 0\nRejected: 0\nDeferred: 0\nExecution attempts: 0\nFailed: 0\nBlocked: 0\nCreated: 33",
            document,
        )
        self.assertNotIn("daily delta", document)

    def test_html_supports_system_integration_scope_and_bounds_issue(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [
                {
                    "key": "SEFK-4",
                    "fields": {
                        "created": "2026-10-01",
                        "resolution": None,
                    },
                }
            ],
            {},
            ideal_start="2026-10-05",
            ideal_end="2026-10-23",
            as_of="2026-10-08",
        )

        document = build_sefk_testlet_burndown_html(
            payload,
            generated_on="08 Oct 2026",
            test_type="System Integration",
            bounds_issue_key="SEFK-1216",
            platform="azure-integration-services",
        )

        self.assertIn("Workday &lt;&gt; AIS &lt;&gt; TWoA", document)
        self.assertNotIn('class="chart-title"', document)
        self.assertNotIn("Best-fit completion estimate", document)
        self.assertIn(
            "5 Oct 2026: 1 of 1 System Integration Testlet remaining\nTerminal outcomes: 0\nPassed: 0\nRejected: 0\nDeferred: 0\nExecution attempts: 0\nFailed: 0\nBlocked: 0\nCreated: 0",
            document,
        )
        self.assertIn("System Integration Testlets in scope", document)
        self.assertIn("System%20Integration", document)
        self.assertIn("azure-integration-services", document)
        self.assertIn("cf%5B10079%5D%20%3D%20%22azure-integration-services%22", document)
        self.assertIn("SEFK-1216's Start date", document)
        self.assertIn("2026-10-05 to 2026-10-23", document)
        self.assertIn("System Integration Testlets remaining from 2026-10-05 to 2026-10-23", document)
        self.assertIn("filter%20%3D%20smart-project-sefk", document)
        self.assertIn("status%20in%20%28%22To%20Do%22", document)
        self.assertIn("cf%5B10079%5D%20%3D%20%22azure-integration-services%22", document)
        self.assertIn('status%20CHANGED%20TO%20%22Passed%22', document)
        self.assertIn('status%20CHANGED%20TO%20%22Deferred%22', document)
        self.assertNotIn("project%20%3D%20SEFK", document)


if __name__ == "__main__":
    unittest.main()