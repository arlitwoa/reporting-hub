"""Tests for deploy-or-done credit resolution."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.quarterly.jira_burn import (
    align_milestone_credit_events,
    credit_ledger_from_status_transitions,
    earned_events_for_scope_keys,
    ledger_currently_credited,
    load_done_statuses,
    resolve_deploy_or_done_credit,
)


class DeployOrDoneCreditTests(unittest.TestCase):
    def test_prefers_deploy_when_both_present(self):
        deploy_at = datetime(2026, 4, 10, tzinfo=timezone.utc)
        done_at = datetime(2026, 4, 20, tzinfo=timezone.utc)
        credit_at, status, mode = resolve_deploy_or_done_credit(
            deploy_at=deploy_at,
            deploy_status="Awaiting STG",
            done_at=done_at,
            done_status="Done",
        )
        self.assertEqual(credit_at, deploy_at)
        self.assertEqual(status, "Awaiting STG")
        self.assertEqual(mode, "deploy")

    def test_falls_back_to_done_without_deploy(self):
        done_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        credit_at, status, mode = resolve_deploy_or_done_credit(
            deploy_at=None,
            deploy_status=None,
            done_at=done_at,
            done_status="Done",
        )
        self.assertEqual(credit_at, done_at)
        self.assertEqual(status, "Done")
        self.assertEqual(mode, "done")

    def test_credit_ledger_revokes_when_leaving_done(self):
        done_at = datetime(2026, 4, 10, tzinfo=timezone.utc)
        revoke_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        ledger = credit_ledger_from_status_transitions(
            [
                (done_at, "In Progress", "Done"),
                (revoke_at, "Done", "In Progress"),
            ],
            deploy_statuses={"Awaiting STG"},
            done_statuses={"Done"},
        )
        self.assertEqual(len(ledger), 2)
        self.assertEqual(ledger[0]["delta"], 1)
        self.assertEqual(ledger[1]["delta"], -1)
        self.assertEqual(ledger[1]["credit_mode"], "revoke")
        self.assertFalse(ledger_currently_credited(ledger))

    def test_credit_ledger_keeps_credit_when_moving_between_earned_statuses(self):
        ledger = credit_ledger_from_status_transitions(
            [
                (datetime(2026, 4, 1, tzinfo=timezone.utc), "In Progress", "Done"),
                (datetime(2026, 4, 5, tzinfo=timezone.utc), "Done", "Closed"),
            ],
            deploy_statuses=set(),
            done_statuses={"Done", "Closed"},
        )
        self.assertEqual(len(ledger), 1)
        self.assertTrue(ledger_currently_credited(ledger))

    def test_burn_events_from_ledger_emits_negative_revoke(self):
        from scripts.quarterly.jira_burn import _burn_events_from_ledger

        issue = {
            "key": "EPCE-1725",
            "fields": {
                "summary": "Reopened story",
                "issuetype": {"name": "Story"},
                "status": {"name": "In Progress"},
                "customfield_10026": 5.0,
            },
        }
        events = _burn_events_from_ledger(
            [
                {
                    "credit_at": "2026-04-10T12:00:00+00:00",
                    "delta": 1,
                    "status_at_credit": "Done",
                    "credit_mode": "done",
                },
                {
                    "credit_at": "2026-05-01T12:00:00+00:00",
                    "delta": -1,
                    "status_at_credit": "In Progress",
                    "credit_mode": "revoke",
                },
            ],
            issue=issue,
            sp_val=5.0,
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["story_points"], 5.0)
        self.assertEqual(events[1]["story_points"], -5.0)
        self.assertEqual(events[1]["credit_mode"], "revoke")

    def test_load_done_statuses_includes_drive_mapped_and_done(self):
        done = load_done_statuses(velocity_credit_status="Done")
        self.assertIn("Done", done)
        self.assertIn("Closed", done)


class MilestoneScopeEarnedTests(unittest.TestCase):
    def test_earned_events_for_scope_keys_resolves_missing_from_jira(self):
        window_start = datetime(2026, 4, 1).date()
        window_end = datetime(2026, 8, 20).date()
        adapter = MagicMock()
        cache_path = Path(self._get_temp_cache())
        done_at = datetime(2026, 5, 10, 12, tzinfo=timezone.utc)
        with patch(
            "scripts.quarterly.jira_burn.search_all",
            return_value=[
                {
                    "key": "EPCE-9001",
                    "fields": {
                        "summary": "Done story",
                        "issuetype": {"name": "Story"},
                        "status": {"name": "Done"},
                        "customfield_10026": 8.0,
                        "fixVersions": [],
                    },
                }
            ],
        ), patch(
            "scripts.quarterly.jira_burn.fetch_deploy_or_done_credit_ledger",
            return_value=[
                {
                    "credit_at": done_at.isoformat(),
                    "delta": 1,
                    "status_at_credit": "Done",
                    "credit_mode": "done",
                }
            ],
        ):
            events = earned_events_for_scope_keys(
                adapter,
                {"EPCE-9001"},
                sp_field="customfield_10026",
                deploy_statuses={"Awaiting STG"},
                done_statuses={"Done"},
                cache_path=cache_path,
                window_start=window_start,
                window_end=window_end,
            )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["key"], "EPCE-9001")
        self.assertEqual(events[0]["story_points"], 8.0)
        self.assertEqual(events[0]["credit_mode"], "done")
        self.assertEqual(events[0]["creditSource"], "milestone_scope")

    def test_clamps_pre_start_credit_to_milestone_start(self):
        events = align_milestone_credit_events(
            [
                {
                    "key": "EPCE-9001",
                    "story_points": 20.0,
                    "credit_at": "2026-03-19T00:34:26+00:00",
                    "credit_date": "2026-03-19",
                }
            ],
            window_start=datetime(2026, 4, 1).date(),
            window_end=datetime(2026, 8, 20).date(),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["credit_date"], "2026-04-01")

    def _get_temp_cache(self) -> str:
        import tempfile

        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        handle.write(b"{}")
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name


if __name__ == "__main__":
    unittest.main()
