import os
import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from extensions.twoa_programme.quarterly_reporting import (
    aggregate_daily_burn,
    filter_events_in_quarter,
    load_quarterly_reporting_config,
    sprint_overlaps_quarter,
)


class QuarterlyReportingConfigTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        os.environ.setdefault(
            "ARTIFACT_PROGRAMME_REGISTRY",
            str(root / "config" / "programme-registry.json"),
        )

    def test_loads_three_lanes_and_quarter(self):
        config = load_quarterly_reporting_config()
        self.assertEqual(config.story_key, "EPCE-6745")
        self.assertEqual(config.quarter.slug, "2026-Q2")
        self.assertEqual(config.quarter.initiative_key, "EPCE-3897")
        self.assertEqual(config.scope.parent_initiative, "EPCE-3897")
        self.assertEqual(config.scope.quarter_filter, config.quarter.current_quarter_filter)
        self.assertIn(f"filter = {config.scope.quarter_filter}", config.education_cloud.scope_jql)
        self.assertIn("status != Rejected", config.scope.global_scope_jql)
        self.assertIn("Kākāriki Krew", config.education_cloud.scope_jql)
        self.assertIn("azure-integration-services", config.integration.scope_jql)
        self.assertEqual(config.integration.board_id, 3032)
        self.assertIn("Data Migration", config.data_migration.scope_jql)
        self.assertEqual(config.data_migration.board_id, 2730)
        self.assertEqual(config.education_cloud.squads, ("kakariki", "kikorangi", "waiporoporo"))

    def test_delivery_milestones_in_scope_filter_optional(self):
        config = load_quarterly_reporting_config()
        self.assertEqual(config.delivery_milestones.milestone_link_type, "Milestone")
        self.assertEqual(config.delivery_milestones.in_scope_filter_id, "15858")
        self.assertEqual(config.delivery_milestones.in_scope_filter, "smart-milestone-report")
        self.assertEqual(config.delivery_milestones.milestone_report_project, "PDE")

    def test_quarter_elapsed_and_days_remaining(self):
        config = load_quarterly_reporting_config()
        mid = date(2026, 5, 15)
        aug = date(2026, 8, 15)
        self.assertTrue(config.quarter.contains(mid))
        self.assertTrue(config.quarter.contains(aug))
        self.assertEqual(config.quarter.end_date, date(2026, 8, 20))
        self.assertGreater(config.quarter.elapsed_days(mid), 0)
        self.assertGreater(config.quarter.days_remaining(mid), 0)

    def test_tracking_snapshot_scaffold(self):
        config = load_quarterly_reporting_config()
        snap = config.tracking_snapshot(earned_story_points=100.0, as_of=date(2026, 5, 15))
        self.assertEqual(snap["quarter"], "2026-Q2")
        self.assertEqual(snap["earnedStoryPoints"], 100.0)
        self.assertIsNone(snap["plannedStoryPoints"])
        self.assertIn("idealBurnFraction", snap)

    def test_burn_tracking_loads_goal_target(self):
        config = load_quarterly_reporting_config()
        root = Path(__file__).resolve().parents[1]
        raw = json.loads((root / "config" / "quarterly-reporting.json").read_text(encoding="utf-8"))
        expected_goal_target = date.fromisoformat(raw["burnTracking"]["goalTargetDate"])
        self.assertEqual(config.burn_tracking.ideal_curve, "linear_to_goal_target")
        self.assertEqual(config.burn_tracking.goal_target_date, expected_goal_target)
        self.assertEqual(config.burn_tracking.resolve_goal_target(config.quarter), expected_goal_target)

    def test_goal_target_raises_ideal_burn_vs_quarter_end(self):
        from dataclasses import replace

        config = load_quarterly_reporting_config()
        config = replace(config, goal=replace(config.goal, planned_story_points=1000.0))
        as_of = date(2026, 5, 15)
        snap = config.tracking_snapshot(earned_story_points=0.0, as_of=as_of)
        goal_target = config.burn_tracking.resolve_goal_target(config.quarter)
        self.assertEqual(
            snap["goalTargetDate"],
            goal_target.isoformat(),
        )
        elapsed_fraction = config.quarter.elapsed_fraction(as_of)
        if goal_target < config.quarter.end_date:
            self.assertGreater(snap["idealBurnFraction"], elapsed_fraction)
        elif goal_target > config.quarter.end_date:
            self.assertLess(snap["idealBurnFraction"], elapsed_fraction)
        else:
            self.assertAlmostEqual(snap["idealBurnFraction"], elapsed_fraction, places=4)

        quarter_end_curve = replace(
            config,
            burn_tracking=replace(
                config.burn_tracking,
                ideal_curve="linear_to_quarter_end",
                goal_target_date=None,
            ),
        )
        snap_end = quarter_end_curve.tracking_snapshot(earned_story_points=0.0, as_of=as_of)
        self.assertEqual(snap_end["goalTargetDate"], "2026-08-20")
        if goal_target < config.quarter.end_date:
            self.assertLess(snap_end["idealBurnFraction"], snap["idealBurnFraction"])
        elif goal_target > config.quarter.end_date:
            self.assertGreater(snap_end["idealBurnFraction"], snap["idealBurnFraction"])
        else:
            self.assertAlmostEqual(
                snap_end["idealBurnFraction"],
                snap["idealBurnFraction"],
                places=4,
            )

    def test_required_velocity_uses_goal_target_days(self):
        from dataclasses import replace

        config = load_quarterly_reporting_config()
        config = replace(config, goal=replace(config.goal, planned_story_points=1000.0))
        as_of = date(2026, 7, 15)
        snap = config.tracking_snapshot(earned_story_points=400.0, as_of=as_of)
        days_left = snap["goalDaysRemaining"]
        self.assertEqual(
            days_left,
            (config.burn_tracking.resolve_goal_target(config.quarter) - as_of).days,
        )
        self.assertAlmostEqual(
            float(snap["requiredDailyVelocity"]),
            (1000.0 - 400.0) / days_left,
            places=1,
        )

    def test_burn_variance_with_planned_goal(self):
        config = load_quarterly_reporting_config()
        from dataclasses import replace

        config = replace(config, goal=replace(config.goal, planned_story_points=1000.0))
        as_of = date(2026, 5, 15)
        snap = config.tracking_snapshot(earned_story_points=400.0, as_of=as_of)
        self.assertIsNotNone(snap["idealEarnedStoryPoints"])
        self.assertIsNotNone(snap["burnVariance"])
        self.assertIsNotNone(snap["requiredDailyVelocity"])

    def test_filter_events_in_quarter_nz_date(self):
        config = load_quarterly_reporting_config()
        events = [
            {
                "key": "EPCE-1",
                "story_points": 3,
                "credit_at": "2026-03-31T11:00:00+00:00",
                "credit_date": "2026-04-01",
            },
            {
                "key": "EPCE-2",
                "story_points": 5,
                "credit_at": "2026-04-01T10:00:00+00:00",
                "credit_date": "2026-04-01",
            },
            {
                "key": "EPCE-3",
                "story_points": 2,
                "credit_at": "2026-07-01T00:00:00+00:00",
                "credit_date": "2026-07-01",
            },
        ]
        in_q = filter_events_in_quarter(events, config.quarter)
        self.assertEqual([e["key"] for e in in_q], ["EPCE-1", "EPCE-2", "EPCE-3"])

    def test_sprint_overlaps_quarter(self):
        config = load_quarterly_reporting_config()
        q = config.quarter
        self.assertTrue(sprint_overlaps_quarter(date(2026, 5, 1), date(2026, 5, 14), q))
        self.assertTrue(sprint_overlaps_quarter(date(2026, 7, 1), date(2026, 7, 14), q))
        self.assertFalse(sprint_overlaps_quarter(date(2026, 9, 1), date(2026, 9, 14), q))
        self.assertFalse(sprint_overlaps_quarter(None, None, q))

    def test_aggregate_daily_burn(self):
        events = [
            {"credit_date": "2026-04-02", "story_points": 3},
            {"credit_date": "2026-04-02", "story_points": 2},
            {"credit_date": "2026-04-05", "story_points": 5},
        ]
        daily, total = aggregate_daily_burn(events)
        self.assertEqual(total, 10.0)
        self.assertEqual(len(daily), 2)
        self.assertEqual(daily[-1]["cumulative_story_points"], 10.0)

    def test_extend_daily_burn_to_as_of(self):
        from extensions.twoa_programme.quarterly_reporting import extend_daily_burn_to_as_of

        daily = [
            {"date": "2026-06-08", "earned_that_day": 5.0, "cumulative_story_points": 433.0},
            {"date": "2026-06-09", "earned_that_day": 1.0, "cumulative_story_points": 434.0},
        ]
        extended = extend_daily_burn_to_as_of(
            daily, "2026-06-10", quarter_end="2026-08-20"
        )
        self.assertEqual(len(extended), 3)
        self.assertEqual(extended[-1]["date"], "2026-06-10")
        self.assertEqual(extended[-1]["earned_that_day"], 0.0)
        self.assertEqual(extended[-1]["cumulative_story_points"], 434.0)

        unchanged = extend_daily_burn_to_as_of(daily, "2026-06-09")
        self.assertEqual(len(unchanged), 2)

    def test_resolve_chart_as_of_uses_nz_today_when_status_is_stale(self):
        from datetime import datetime
        from unittest.mock import patch
        from zoneinfo import ZoneInfo

        from extensions.twoa_programme.quarterly_reporting import resolve_chart_as_of

        with patch(
            "extensions.twoa_programme.quarterly_reporting.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 12, 10, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            resolved = resolve_chart_as_of("2026-06-10", quarter_end="2026-08-20")
        self.assertEqual(resolved, date(2026, 6, 12))

    def test_dynamic_dates_derive_from_milestone_timeline_artifact(self):
        root = Path(__file__).resolve().parents[1]
        source_cfg = json.loads(
            (root / "config" / "quarterly-reporting.json").read_text(encoding="utf-8")
        )
        with TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            cfg_dir = tmp_root / "config"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            cfg_path = cfg_dir / "quarterly-reporting.json"
            cfg_path.write_text(json.dumps(source_cfg), encoding="utf-8")

            out_dir = tmp_root / "output" / "quarterly" / source_cfg["quarter"]["slug"]
            out_dir.mkdir(parents=True, exist_ok=True)
            timeline_payload = {
                "milestones": [
                    {"startDate": "2026-05-10", "dueDate": "2026-06-20"},
                    {"created": "2026-05-01", "dueDate": "2026-07-15"},
                ]
            }
            (out_dir / "milestone-timeline.json").write_text(
                json.dumps(timeline_payload),
                encoding="utf-8",
            )

            config = load_quarterly_reporting_config(
                cfg_path,
                dynamic_dates=True,
                repo_root=tmp_root,
            )

        self.assertEqual(config.quarter.start_date, date(2026, 5, 1))
        self.assertEqual(config.quarter.end_date, date(2026, 7, 15))
        self.assertEqual(config.burn_tracking.goal_target_date, date(2026, 7, 15))

    def test_dynamic_dates_fall_back_to_config_when_artifacts_missing(self):
        root = Path(__file__).resolve().parents[1]
        source_cfg = json.loads(
            (root / "config" / "quarterly-reporting.json").read_text(encoding="utf-8")
        )
        with TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            cfg_dir = tmp_root / "config"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            cfg_path = cfg_dir / "quarterly-reporting.json"
            cfg_path.write_text(json.dumps(source_cfg), encoding="utf-8")

            config = load_quarterly_reporting_config(
                cfg_path,
                dynamic_dates=True,
                repo_root=tmp_root,
            )

        self.assertEqual(config.quarter.start_date, date(2026, 4, 1))
        self.assertEqual(config.quarter.end_date, date(2026, 8, 20))
        self.assertEqual(config.burn_tracking.goal_target_date, date(2026, 9, 30))

    def test_dynamic_dates_prefer_milestone_goal_target_date(self):
        root = Path(__file__).resolve().parents[1]
        source_cfg = json.loads(
            (root / "config" / "quarterly-reporting.json").read_text(encoding="utf-8")
        )
        with TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            cfg_dir = tmp_root / "config"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            cfg_path = cfg_dir / "quarterly-reporting.json"
            cfg_path.write_text(json.dumps(source_cfg), encoding="utf-8")

            out_dir = tmp_root / "output" / "quarterly" / source_cfg["quarter"]["slug"]
            out_dir.mkdir(parents=True, exist_ok=True)
            timeline_payload = {
                "milestones": [
                    {
                        "startDate": "2026-05-10",
                        "dueDate": "2026-06-20",
                        "goalTargetDate": "2026-07-25",
                    },
                    {"created": "2026-05-01", "dueDate": "2026-07-15"},
                ]
            }
            (out_dir / "milestone-timeline.json").write_text(
                json.dumps(timeline_payload),
                encoding="utf-8",
            )

            config = load_quarterly_reporting_config(
                cfg_path,
                dynamic_dates=True,
                repo_root=tmp_root,
            )

        self.assertEqual(config.quarter.start_date, date(2026, 5, 1))
        self.assertEqual(config.quarter.end_date, date(2026, 7, 15))
        self.assertEqual(config.burn_tracking.goal_target_date, date(2026, 7, 25))


if __name__ == "__main__":
    unittest.main()
