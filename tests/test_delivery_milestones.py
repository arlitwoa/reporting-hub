"""Tests for Jira-sourced delivery milestones."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from extensions.twoa_programme.delivery_milestones import (
    adf_text,
    chart_milestone_rows,
    fetch_delivery_milestones,
    find_milestone_hub_key,
    milestone_hub_children_jql,
    milestone_linked_issues,
    milestone_notes_heading,
    milestone_tooltip_plain,
    milestone_work_item_notes,
    notes_field_last_updated,
    normalize_milestone_description,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "delivery-milestones.json"


class DeliveryMilestoneTests(unittest.TestCase):
    def test_find_milestone_hub_key(self):
        initiative = {
            "fields": {
                "issuelinks": [
                    {
                        "type": {"name": "Milestone"},
                        "outwardIssue": {"key": "PDE-3825", "fields": {"summary": "Hub"}},
                    }
                ]
            }
        }
        self.assertEqual(find_milestone_hub_key(initiative), "PDE-3825")

    def test_milestone_hub_children_jql_without_filter(self):
        self.assertEqual(
            milestone_hub_children_jql("PDE-3825"),
            "project = PDE AND parent = PDE-3825 ORDER BY duedate ASC, key ASC",
        )

    def test_milestone_hub_children_jql_with_saved_filter(self):
        self.assertEqual(
            milestone_hub_children_jql("PDE-3825", in_scope_filter="smart-milestone-report"),
            "project = PDE AND parent = PDE-3825 AND filter = smart-milestone-report "
            "ORDER BY duedate ASC, key ASC",
        )

    def test_parse_milestone_report_window_from_filter_15858(self):
        from extensions.twoa_programme.delivery_milestones import parse_milestone_report_window

        start, end = parse_milestone_report_window(
            '"Start date[Date]" > \'2026-04-01\' AND duedate < \'2026-08-31\''
        )
        self.assertEqual(start, date.fromisoformat("2026-04-01"))
        self.assertEqual(end, date.fromisoformat("2026-08-30"))

    def test_milestone_linked_issues_both_directions(self):
        issue = {
            "fields": {
                "issuelinks": [
                    {
                        "type": {"name": "Milestone"},
                        "inwardIssue": {"key": "EPCE-422", "fields": {"summary": "Epic A"}},
                    },
                    {
                        "type": {"name": "Relates"},
                        "outwardIssue": {"key": "EPCE-999", "fields": {}},
                    },
                ]
            }
        }
        linked = milestone_linked_issues(issue)
        self.assertEqual([row["key"] for row in linked], ["EPCE-422"])

    def test_adf_text_preserves_bullet_list(self):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Enable data for"}],
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "SDR Reporting"}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Management Reporting"}],
                                }
                            ],
                        },
                    ],
                },
            ],
        }
        text = normalize_milestone_description(adf_text(doc))
        self.assertIn("Enable data for", text)
        self.assertIn("• SDR Reporting", text)
        self.assertIn("• Management Reporting", text)
        self.assertNotIn("forSDR", text)

    def test_milestone_work_item_notes_from_adf(self):
        notes = milestone_work_item_notes(
            {
                "customfield_10475": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Quarter context for readers."}],
                        }
                    ],
                }
            },
            notes_field="customfield_10475",
        )
        self.assertEqual(notes, "Quarter context for readers.")

    def test_notes_field_last_updated_from_changelog(self):
        histories = [
            {
                "created": "2026-04-01T10:00:00.000+0000",
                "items": [{"field": "summary", "toString": "Renamed"}],
            },
            {
                "created": "2026-06-15T03:05:20.492+0000",
                "items": [{"field": "Notes", "fieldId": "customfield_10475", "toString": "Updated"}],
            },
        ]
        updated = notes_field_last_updated(histories, notes_field_id="customfield_10475")
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.isoformat(), "2026-06-15T03:05:20.492000+00:00")

    def test_milestone_notes_heading_includes_updated_date(self):
        self.assertEqual(
            milestone_notes_heading(notes_updated_at="2026-06-15T03:05:20.492+0000"),
            "Notes · updated 15 Jun 2026",
        )
        self.assertEqual(milestone_notes_heading(), "Notes")

    def test_milestone_tooltip_plain_multiline(self):
        tip = milestone_tooltip_plain(
            {
                "label": "Curriculum Lifecycle",
                "date": "2026-07-06",
                "description": "Line one\n• SDR Reporting\n• Management Reporting",
                "scopeRollup": {"childCount": 6, "storyPoints": 25.0, "unpointedCount": 1},
                "scopeEpics": [{"key": "EPCE-422", "summary": "Fabric Epic"}],
            }
        )
        self.assertIn("Curriculum Lifecycle | 2026-07-06", tip)
        self.assertIn("Scope", tip)
        self.assertIn("6 Story/Bug", tip)
        self.assertIn("Linked epics", tip)
        self.assertIn("EPCE-422", tip)

    def test_chart_milestone_rows_sorted_by_due_date(self):
        payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        rows = chart_milestone_rows(payload)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["date"], "2026-06-11")
        self.assertEqual(rows[0]["label"], "ED Cloud Data within Fabric")
        self.assertEqual(rows[0]["key"], "PDE-3834")
        self.assertIn("description", rows[0])
        self.assertIn("scopeRollup", rows[0])
        self.assertEqual(rows[-1]["date"], "2026-08-20")

    def test_fetch_delivery_milestones_rollup(self):
        adapter = MagicMock()
        adapter.http.get_json.side_effect = [
            {
                "key": "EPCE-3897",
                "fields": {
                    "summary": "Q2 Initiative",
                    "issuelinks": [
                        {
                            "type": {"name": "Milestone"},
                            "outwardIssue": {"key": "PDE-3825"},
                        }
                    ],
                },
            },
            {
                "key": "PDE-3825",
                "fields": {
                    "summary": "Hub",
                    "issuetype": {"name": "Milestone Level One"},
                },
            },
        ]

        child = {
            "key": "PDE-3834",
            "fields": {
                "summary": "Milestone A",
                "description": {"type": "doc", "content": [{"type": "text", "text": "Details"}]},
                "duedate": "2026-06-11",
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Milestone Level Zero"},
                "issuelinks": [
                    {
                        "type": {"name": "Milestone"},
                        "outwardIssue": {
                            "key": "EPCE-422",
                            "fields": {"summary": "Epic", "issuetype": {"name": "Epic"}},
                        },
                    }
                ],
            },
        }
        scope_child = {
            "key": "EPCE-1001",
            "fields": {
                "issuetype": {"name": "Story"},
                "status": {"name": "Deploy"},
                "customfield_10026": 5,
            },
        }

        def search_all(_adapter, jql, fields):
            if "parent = PDE-3825" in jql:
                return [child]
            if "parent in (EPCE-422)" in jql:
                return [scope_child]
            return []

        from extensions.twoa_programme import delivery_milestones as dm

        original = dm.search_all
        dm.search_all = search_all
        try:
            payload = fetch_delivery_milestones(
                adapter,
                initiative_key="EPCE-3897",
                quarter_filter="smart-current-quarter",
                delivery_squad_field="customfield_11102",
                change_types_field="customfield_10079",
                platform_field="customfield_10120",
                story_points_field="customfield_10026",
                deploy_statuses={"Deploy"},
                done_statuses={"Done", "Closed"},
                skip_issue_types=frozenset({"Epic", "Initiative"}),
            )
        finally:
            dm.search_all = original

        self.assertEqual(payload["hubKey"], "PDE-3825")
        self.assertEqual(len(payload["milestones"]), 1)
        ms = payload["milestones"][0]
        self.assertEqual(ms["dueDate"], "2026-06-11")
        self.assertEqual(ms["description"], "Details")
        self.assertEqual(ms["scopeEpics"][0]["key"], "EPCE-422")
        self.assertEqual(ms["scopeRollup"]["childCount"], 1)
        self.assertEqual(ms["scopeRollup"]["storyPoints"], 5.0)


if __name__ == "__main__":
    unittest.main()
