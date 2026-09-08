"""Tests for SEFK scope exclusion rules."""

from __future__ import annotations

import unittest

from extensions.twoa_programme.sefk_scope import (
    issue_excluded_from_sefk_project_plan,
    issue_has_kpmg_deleted_label,
    rollup_sefk_epic_phases,
    sefk_epic_scope_jql,
    sefk_scope_exclusion_jql,
)


class SefkScopeExclusionTests(unittest.TestCase):
    def test_detects_kpmg_deleted_label(self) -> None:
        issue = {"fields": {"labels": ["kpmg-deleted", "other"]}}
        self.assertTrue(issue_has_kpmg_deleted_label(issue))

    def test_ignores_issues_without_tombstone_label(self) -> None:
        issue = {"fields": {"labels": ["sync-hub"], "status": {"name": "Open"}}}
        self.assertFalse(issue_excluded_from_sefk_project_plan(issue))

    def test_excludes_rejected_and_kpmg_deleted(self) -> None:
        rejected = {"fields": {"labels": [], "status": {"name": "Rejected"}}}
        tombstoned = {"fields": {"labels": ["kpmg-deleted"], "status": {"name": "Open"}}}
        self.assertTrue(issue_excluded_from_sefk_project_plan(rejected))
        self.assertTrue(issue_excluded_from_sefk_project_plan(tombstoned))

    def test_epic_scope_jql_excludes_kpmg_deleted(self) -> None:
        jql = sefk_epic_scope_jql(parent_keys_csv="SEFK-1, SEFK-2")
        self.assertIn(sefk_scope_exclusion_jql(), jql)
        self.assertIn("parent in (SEFK-1, SEFK-2)", jql)

    def test_epic_scope_jql_quotes_multi_word_issue_types(self) -> None:
        jql = sefk_epic_scope_jql(
            parent_keys_csv="SEFK-1",
            scope_issue_types=("Task", "Milestone Level Zero"),
        )
        self.assertIn('issuetype in ("Task", "Milestone Level Zero")', jql)

    def test_scope_exclusion_jql_keeps_unlabeled_issues(self) -> None:
        jql = sefk_scope_exclusion_jql()
        self.assertIn("labels is EMPTY", jql)

    def test_rollup_captures_kpmg_reference_by_key_when_field_given(self) -> None:
        children = [
            {
                "key": "SEFK-201",
                "fields": {
                    "issuetype": {"name": "Task"},
                    "status": {"name": "Not Started"},
                    "parent": {"key": "SEFK-100"},
                    "customfield_15272": "https://gate-pd232.atlassian.net/browse/TWOA-501",
                },
            },
            {
                "key": "SEFK-202",
                "fields": {
                    "issuetype": {"name": "Task"},
                    "status": {"name": "Not Started"},
                    "parent": {"key": "SEFK-100"},
                },
            },
        ]
        buckets = rollup_sefk_epic_phases(
            children,
            epic_keys=["SEFK-100"],
            kpmg_reference_field_id="customfield_15272",
        )
        self.assertEqual(
            buckets["SEFK-100"]["kpmgReferenceByKey"],
            {"SEFK-201": "TWOA-501"},
        )

    def test_rollup_omits_kpmg_reference_by_key_without_field_id(self) -> None:
        children = [
            {
                "key": "SEFK-201",
                "fields": {
                    "issuetype": {"name": "Task"},
                    "status": {"name": "Not Started"},
                    "parent": {"key": "SEFK-100"},
                    "customfield_15272": "https://gate-pd232.atlassian.net/browse/TWOA-501",
                },
            },
        ]
        buckets = rollup_sefk_epic_phases(children, epic_keys=["SEFK-100"])
        self.assertEqual(buckets["SEFK-100"]["kpmgReferenceByKey"], {})


if __name__ == "__main__":
    unittest.main()
