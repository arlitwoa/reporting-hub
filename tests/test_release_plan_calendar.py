import unittest
from datetime import date

from extensions.twoa_programme.pde_engine_releases import (
    extend_engine_releases,
    is_placeholder_engine_version,
)
from extensions.twoa_programme.release_plan_calendar import (
    allocate_burn_to_calendar,
    extend_prd_releases,
    extend_sprint_calendar,
)


class ReleasePlanCalendarTests(unittest.TestCase):
    def test_extend_sprints_back_to_april(self):
        sprints = extend_sprint_calendar(
            [{"name": "Sprint 25", "startDate": "2026-05-25", "endDate": "2026-06-07"}],
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 8, 20),
        )
        nums = [row["sprintNumber"] for row in sprints]
        self.assertIn(22, nums)
        self.assertIn(25, nums)
        first = min(sprints, key=lambda row: row["startDate"])
        self.assertEqual(first["startDate"], "2026-04-01")

    def test_extend_prd_back_to_april(self):
        releases = extend_prd_releases(
            [{"releaseDate": "2026-05-28", "env": "PRD"}],
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 8, 20),
        )
        dates = [row["releaseDate"] for row in releases]
        self.assertIn("2026-04-02", dates)
        self.assertIn("2026-05-28", dates)

    def test_allocate_claims_release_on_credit_date(self):
        plan = {
            "extended": True,
            "sprints": [{"name": "Sprint 22", "startDate": "2026-04-13", "endDate": "2026-04-26"}],
            "inCycleReleases": [
                {"name": "20260416-engine", "releaseDate": "2026-04-16", "carriageType": "In Cycle"},
                {"name": "20260422-engine", "releaseDate": "2026-04-22", "carriageType": "Out Of Cycle"},
                {"name": "20260430-engine", "releaseDate": "2026-04-30", "carriageType": "In Cycle"},
            ],
        }
        burn = {
            "lanes": {
                "educationCloud": {
                    "lane": "educationCloud",
                    "events": [
                        {
                            "key": "EPCE-1",
                            "story_points": 13,
                            "credit_date": "2026-04-22",
                            "statusCategory": "done",
                            "fixVersions": ["20260422-engine"],
                        },
                        {
                            "key": "EPCE-2",
                            "story_points": 5,
                            "credit_date": "2026-04-28",
                            "statusCategory": "done",
                            "fixVersions": ["20260430-engine"],
                        },
                    ],
                }
            }
        }
        result = allocate_burn_to_calendar(
            plan,
            burn,
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 4, 30),
        )
        by_code = {row["releaseCode"]: row for row in result["inCycleReleases"]}
        self.assertEqual(by_code["0416IC"]["claimedStoryPoints"], 0.0)
        self.assertEqual(by_code["0422OC"]["claimedStoryPoints"], 13.0)
        self.assertEqual(by_code["0430IC"]["claimedStoryPoints"], 5.0)
        self.assertEqual(result["releaseMarkerCount"], 3)
        self.assertEqual(result["releaseAllocationCount"], 3)

    def test_allocate_claims_release_by_fix_version_not_credit_date(self):
        plan = {
            "extended": True,
            "sprints": [],
            "inCycleReleases": [
                {"name": "20260505-engine", "releaseDate": "2026-05-05", "carriageType": "Out Of Cycle"},
                {"name": "20260514-engine", "releaseDate": "2026-05-14", "carriageType": "In Cycle"},
            ],
        }
        burn = {
            "lanes": {
                "educationCloud": {
                    "lane": "educationCloud",
                    "events": [
                        {
                            "key": "EPCE-5718",
                            "story_points": 5,
                            "credit_date": "2026-05-12",
                            "statusCategory": "done",
                            "fixVersions": ["20260514-engine"],
                        },
                        {
                            "key": "EPCE-5882",
                            "story_points": 13,
                            "credit_date": "2026-05-13",
                            "statusCategory": "done",
                            "fixVersions": ["20260514-engine"],
                        },
                    ],
                }
            }
        }
        result = allocate_burn_to_calendar(
            plan,
            burn,
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 6, 30),
        )
        by_code = {row["releaseCode"]: row for row in result["inCycleReleases"]}
        self.assertEqual(by_code["0514IC"]["claimedStoryPoints"], 18.0)
        self.assertEqual(len(by_code["0514IC"]["events"]), 2)

    def test_allocate_claims_release_by_window_when_untagged(self):
        plan = {
            "extended": True,
            "sprints": [],
            "inCycleReleases": [
                {"name": "20260505-engine", "releaseDate": "2026-05-05", "carriageType": "Out Of Cycle"},
                {"name": "20260514-engine", "releaseDate": "2026-05-14", "carriageType": "In Cycle"},
            ],
        }
        burn = {
            "lanes": {
                "educationCloud": {
                    "lane": "educationCloud",
                    "events": [
                        {
                            "key": "EPCE-6233",
                            "story_points": 3,
                            "credit_date": "2026-05-06",
                        },
                    ],
                }
            }
        }
        result = allocate_burn_to_calendar(
            plan,
            burn,
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 6, 30),
        )
        by_code = {row["releaseCode"]: row for row in result["inCycleReleases"]}
        self.assertEqual(by_code["0514IC"]["claimedStoryPoints"], 3.0)

    def test_allocate_claims_sprint_and_release(self):
        plan = {
            "extended": True,
            "sprints": [{"name": "Sprint 22", "startDate": "2026-04-13", "endDate": "2026-04-26"}],
            "inCycleReleases": [
                {"name": "20260430-engine", "releaseDate": "2026-04-30", "carriageType": "In Cycle"},
            ],
        }
        burn = {
            "lanes": {
                "educationCloud": {
                    "lane": "educationCloud",
                    "events": [
                        {
                            "key": "EPCE-1",
                            "story_points": 5,
                            "credit_date": "2026-04-30",
                            "statusCategory": "done",
                            "fixVersions": ["20260430-engine"],
                        }
                    ],
                }
            }
        }
        result = allocate_burn_to_calendar(
            plan,
            burn,
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 4, 30),
        )
        self.assertEqual(result["sprints"][0]["claimedStoryPoints"], 0.0)
        rel = result["inCycleReleases"][0]
        self.assertEqual(rel["claimedStoryPoints"], 5.0)

    def test_placeholder_versions_ignored(self):
        self.assertTrue(is_placeholder_engine_version("yyyymmdd-engine-none"))
        self.assertTrue(is_placeholder_engine_version("yyymmdd-engine-siding"))
        self.assertFalse(is_placeholder_engine_version("20260528-engine"))

    def test_extend_engine_releases_forward_from_in_cycle(self):
        real = [
            {"name": "20260528-engine", "releaseDate": "2026-05-28", "projected": False},
            {"name": "20260611-engine", "releaseDate": "2026-06-11", "projected": False},
        ]
        extended = extend_engine_releases(
            real,
            in_cycle_name="20260611-engine",
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 8, 20),
            cadence_days=14,
        )
        dates = [row["releaseDate"] for row in extended]
        self.assertIn("2026-05-28", dates)
        self.assertIn("2026-06-11", dates)
        self.assertIn("2026-06-25", dates)
        projected = [row for row in extended if row.get("projected")]
        self.assertTrue(any(row["releaseDate"] == "2026-06-25" for row in projected))


if __name__ == "__main__":
    unittest.main()
