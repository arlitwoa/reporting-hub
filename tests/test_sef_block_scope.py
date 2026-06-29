"""Tests for SEF Block Plan scope rollup (Scope issue link)."""

from __future__ import annotations

import unittest

from extensions.twoa_programme.sef_block_scope import (
    BLOCK_SCOPE_LINK_TYPE,
    build_block_scope_rollups,
    linked_scope_targets,
    rollup_scope_issues,
)


def _scope_issue(
    key: str,
    *,
    status: str = "In Development",
    sp: float | None = 3.0,
    itype: str = "Story",
    parent: str | None = "EPCE-100",
) -> dict:
    fields: dict = {
        "issuetype": {"name": itype},
        "status": {"name": status},
        "parent": {"key": parent} if parent else None,
    }
    if sp is not None:
        fields["customfield_10026"] = sp
    return {"key": key, "fields": fields}


class SefBlockScopeTests(unittest.TestCase):
    def test_linked_scope_targets_reads_scope_link(self) -> None:
        issue = {
            "key": "PDE-4085",
            "fields": {
                "issuelinks": [
                    {
                        "type": {"name": BLOCK_SCOPE_LINK_TYPE},
                        "outwardIssue": {
                            "key": "EPCE-500",
                            "fields": {"issuetype": {"name": "Epic"}},
                        },
                    }
                ]
            },
        }
        linked = linked_scope_targets(issue)
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0]["key"], "EPCE-500")

    def test_rollup_scope_issues_maps_dtrain_phases(self) -> None:
        rollup = rollup_scope_issues(
            [
                _scope_issue("EPCE-1", status="In Discovery", sp=5.0),
                _scope_issue("EPCE-2", status="Awaiting Deployment", sp=2.0),
                _scope_issue("EPCE-3", status="To Do", sp=None),
            ],
            story_points_field="customfield_10026",
        )
        self.assertEqual(rollup["storyPoints"], 7.0)
        self.assertEqual(rollup["unpointedCount"], 1)
        self.assertEqual(rollup["totalWeight"], 8.0)
        self.assertGreater(rollup["phases"]["Discover"], 0)
        self.assertGreater(rollup["phases"]["Deploy"], 0)

    def test_build_block_scope_rollups_epic_and_direct(self) -> None:
        class FakeAdapter:
            def __init__(self) -> None:
                self.calls: list[str] = []

            class _Http:
                pass

            http = _Http()

        adapter = FakeAdapter()

        def fake_search_all(_adapter, jql: str, _fields: list[str]) -> list[dict]:
            adapter.calls.append(jql)
            if "parent in (EPCE-500)" in jql:
                return [
                    _scope_issue("EPCE-501", status="In Design", sp=4.0, parent="EPCE-500"),
                ]
            if "key in (EPCE-600)" in jql:
                return [_scope_issue("EPCE-600", status="In Testing", sp=1.0, parent=None)]
            return []

        import extensions.twoa_programme.sef_block_scope as mod

        original = mod.search_all
        mod.search_all = fake_search_all
        try:
            block_issues = {
                "PDE-4085": {
                    "key": "PDE-4085",
                    "fields": {
                        "issuelinks": [
                            {
                                "type": {"name": BLOCK_SCOPE_LINK_TYPE},
                                "outwardIssue": {
                                    "key": "EPCE-500",
                                    "fields": {"issuetype": {"name": "Epic"}},
                                },
                            },
                            {
                                "type": {"name": BLOCK_SCOPE_LINK_TYPE},
                                "inwardIssue": {
                                    "key": "EPCE-600",
                                    "fields": {"issuetype": {"name": "Story"}},
                                },
                            },
                        ]
                    },
                }
            }
            rollups = build_block_scope_rollups(adapter, block_issues=block_issues)
        finally:
            mod.search_all = original

        self.assertIn("PDE-4085", rollups)
        self.assertEqual(rollups["PDE-4085"]["storyPoints"], 5.0)
        self.assertEqual(rollups["PDE-4085"]["totalWeight"], 5.0)


if __name__ == "__main__":
    unittest.main()
