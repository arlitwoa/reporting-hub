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

    def test_replays_created_done_reopened_and_done_without_history(self) -> None:
        issues = [
            {
                "key": "SEFK-1",
                "fields": {
                    "created": "2026-10-01T09:00:00.000+0000",
                    "status": {"statusCategory": {"key": "new"}},
                },
            },
            {
                "key": "SEFK-2",
                "fields": {
                    "created": "2026-10-02T09:00:00.000+0000",
                    "status": {"statusCategory": {"key": "done"}},
                },
            },
        ]
        histories = {
            "SEFK-1": [
                {
                    "created": "2026-10-03T09:00:00.000+0000",
                    "items": [{"field": "status", "from": "1", "to": "3"}],
                },
                {
                    "created": "2026-10-05T09:00:00.000+0000",
                    "items": [{"field": "status", "from": "3", "to": "2"}],
                },
            ]
        }

        payload = build_sefk_testlet_burndown_payload(
            issues,
            histories,
            {"1": "new", "2": "new", "3": "done"},
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
        self.assertIn('class="ideal"', document)
        self.assertIn('points="64.0,24.0 625.2,332.0" class="ideal"', document)
        self.assertIn('class="trend"', document)
        self.assertNotIn('class="as-of-marker"', document)
        self.assertIn('class="target-marker"', document)
        self.assertIn("Target 9 Oct", document)
        self.assertIn('class="weekend-band"', document)
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
                        "status": {"statusCategory": {"key": "new"}},
                    },
                }
            ],
            {},
            {},
            ideal_start="2026-10-01",
            ideal_end="2026-10-09",
            as_of="2026-10-02",
        )

        document = build_sefk_testlet_burndown_html(payload, generated_on="02 Oct 2026")

        self.assertIn("SEFK Unit Testlet burndown", document)
        self.assertIn("Actual remaining", document)
        self.assertIn("Ideal pace (2026-10-01 to 2026-10-09)", document)
        self.assertIn("cf%5B10145%5D%20%3D%20%22Unit%22", document)
        self.assertIn("2026-10-02", document)

    def test_html_supports_system_integration_scope_and_bounds_issue(self) -> None:
        payload = build_sefk_testlet_burndown_payload(
            [
                {
                    "key": "SEFK-4",
                    "fields": {
                        "created": "2026-10-01",
                        "status": {"statusCategory": {"key": "new"}},
                    },
                }
            ],
            {},
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
        self.assertIn("System Integration Testlets in scope", document)
        self.assertIn("System%20Integration", document)
        self.assertIn("azure-integration-services", document)
        self.assertIn("cf%5B10079%5D%20%3D%20%22azure-integration-services%22", document)
        self.assertIn("SEFK-1216's Start date", document)
        self.assertIn("2026-10-05 to 2026-10-23", document)
        self.assertIn("System Integration Testlets remaining from 2026-10-05 to 2026-10-23", document)


if __name__ == "__main__":
    unittest.main()