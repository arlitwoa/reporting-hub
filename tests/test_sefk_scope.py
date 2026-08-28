"""Tests for SEFK D-Train scope rollups."""

from __future__ import annotations

import unittest

from extensions.twoa_programme.sefk_scope import (
    resolve_sefk_issue_dtrain_phase,
    rollup_sefk_epic_phases,
)


class SefkScopeTests(unittest.TestCase):
    def test_status_maps_to_dtrain_phase(self) -> None:
        self.assertEqual(resolve_sefk_issue_dtrain_phase("Not Started"), "Dream")
        self.assertEqual(resolve_sefk_issue_dtrain_phase("Completed"), "Drive")
        self.assertEqual(resolve_sefk_issue_dtrain_phase("WIP (50%)"), "Develop")

    def test_rollup_counts_children_by_epic_and_phase(self) -> None:
        children = [
            {
                "key": "SEFK-100",
                "fields": {
                    "issuetype": {"name": "Task"},
                    "status": {"name": "Not Started"},
                    "parent": {"key": "SEFK-59"},
                },
            },
            {
                "key": "SEFK-101",
                "fields": {
                    "issuetype": {"name": "Task"},
                    "status": {"name": "Completed"},
                    "parent": {"key": "SEFK-59"},
                },
            },
        ]
        rollups = rollup_sefk_epic_phases(children, epic_keys=["SEFK-59"])
        bucket = rollups["SEFK-59"]
        self.assertEqual(bucket["totalWeight"], 2.0)
        self.assertEqual(bucket["phases"]["Dream"], 1.0)
        self.assertEqual(bucket["phases"]["Drive"], 1.0)


if __name__ == "__main__":
    unittest.main()
