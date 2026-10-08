from __future__ import annotations

import unittest

from extensions.twoa_programme.sefk_testlet_burndown import (
    _y_axis_ticks,
    build_sefk_testlet_burndown_html,
    build_sefk_testlet_burndown_payload,
)


class SefkTestletBurndownTests(unittest.TestCase):
    def test_y_axis_top_tick_equals_scoped_total(self) -> None:
        self.assertEqual(_y_axis_ticks(82), (0, 41, 82))
        self.assertEqual(_y_axis_ticks(401), (0, 200, 401))

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
        self.assertEqual(payload["forecastDate"], "2026-10-09")
        self.assertEqual(
            [row["remaining"] for row in payload["daily"]],
            [1, 1, 0, 0, 1],
        )
        document = build_sefk_testlet_burndown_html(payload, generated_on="05 Oct 2026")
        self.assertIn('class="actual-point"', document)
        self.assertIn("1 Oct 2026: 1 of 2 Unit Testlet remaining\nResolved: 0\nCreated: 1", document)
        self.assertIn("2 Oct 2026: 1 of 2 Unit Testlet remaining\nResolved: 1\nCreated: 1", document)
        self.assertIn("3 Oct 2026: 0 of 2 Unit Testlets remaining\nResolved: 0\nCreated: 0", document)
        self.assertIn("5 Oct 2026: 1 of 2 Unit Testlet remaining\nResolved: 0\nCreated: 0", document)
        self.assertNotIn("daily delta", document)
        self.assertIn('class="ideal"', document)
        self.assertIn('points="64.0,42.0 625.2,332.0" class="ideal"', document)
        self.assertIn('class="trend"', document)
        self.assertNotIn('class="as-of-marker"', document)
        self.assertIn('class="target-marker"', document)
        self.assertIn("Target 9 Oct", document)
        self.assertIn('y="22" text-anchor="middle" class="target-label"', document)
        self.assertIn('y="35" text-anchor="middle" class="forecast-label"', document)
        self.assertIn('class="weekend-band"', document)
        self.assertIn(".weekend-band { fill: #e8ebef; }", document)
        self.assertIn("class=\"week-grid\"", document)
        self.assertIn(">1 Oct</text>", document)
        self.assertIn(">8 Oct</text>", document)
        self.assertIn(">14 Oct</text>", document)
        self.assertIn("Forecast 2026-10-09", document)
        self.assertIn("Ideal pace (2026-10-01 to 2026-10-09)", document)
        self.assertIn("Unit Testlets remaining from 2026-10-01 to 2026-10-14", document)

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

        self.assertIn("SEFK Unit Testlet burndown", document)
        self.assertIn("Actual remaining", document)
        self.assertIn("Jira resolution history", document)
        self.assertIn("Currently resolved in Jira", document)
        self.assertIn("Ideal pace (2026-10-01 to 2026-10-09)", document)
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

        self.assertEqual(payload["completedTestlets"], 0)
        self.assertEqual(payload["remainingTestlets"], 1)
        self.assertEqual([row["remaining"] for row in payload["daily"]], [1, 1])

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
            "7 Oct 2026: 33 of 75 Unit Testlets remaining\nResolved: 42\nCreated: 33",
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

        self.assertIn("SEFK System Integration Testlet burndown", document)
        self.assertIn(
            "5 Oct 2026: 1 of 1 System Integration Testlet remaining\nResolved: 0\nCreated: 0",
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
        self.assertNotIn("project%20%3D%20SEFK", document)


if __name__ == "__main__":
    unittest.main()