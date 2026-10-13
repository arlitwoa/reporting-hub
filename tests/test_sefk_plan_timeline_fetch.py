"""The SEFK plan timeline fetch reuses one epic-children search and runs reads concurrently."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import extensions.twoa_programme.sefk_project_plan_timeline as mod
from extensions.twoa_programme.sefk_project_plan_reporting import load_sefk_project_plan_reporting_config
from scripts.sefk.common import CONFIG_PATH


def _config():
    return load_sefk_project_plan_reporting_config(CONFIG_PATH)


def _child(key: str, parent: str, status: str = "To Do") -> dict:
    return {
        "key": key,
        "fields": {
            "summary": f"Child {key}",
            "status": {"name": status},
            "issuetype": {"name": _config().scope_issue_types[0]},
            "parent": {"key": parent},
            "created": "2026-06-01T00:00:00.000+1200",
        },
    }


class EpicRollupReuseTests(unittest.TestCase):
    def test_prefetched_children_give_same_rollups_without_searching(self):
        config = _config()
        epic_issues = {"SEFK-1": {"key": "SEFK-1"}, "SEFK-2": {"key": "SEFK-2"}}
        children = [_child("SEFK-10", "SEFK-1"), _child("SEFK-11", "SEFK-1", "Done"), _child("SEFK-12", "SEFK-2")]
        with patch.object(mod, "search_all", return_value=children) as search:
            searched = mod._attach_epic_scope_rollups(MagicMock(), epic_issues, config=config)
            self.assertEqual(search.call_count, 1)
            search.reset_mock()
            reused = mod._attach_epic_scope_rollups(
                MagicMock(), epic_issues, config=config, prefetched_children=children
            )
            search.assert_not_called()
        self.assertEqual(searched, reused)
        self.assertEqual(reused["SEFK-1"]["issueCount"], 2)
        self.assertEqual(reused["SEFK-2"]["issueCount"], 1)

    def test_children_of_other_epics_in_a_superset_search_are_ignored(self):
        config = _config()
        children = [_child("SEFK-10", "SEFK-1"), _child("SEFK-99", "SEFK-OTHER")]
        rollups = mod._attach_epic_scope_rollups(
            MagicMock(), {"SEFK-1": {"key": "SEFK-1"}}, config=config, prefetched_children=children
        )
        self.assertEqual(list(rollups), ["SEFK-1"])
        self.assertEqual(rollups["SEFK-1"]["issueCount"], 1)


class FetchOrchestrationTests(unittest.TestCase):
    def _phases(self):
        return [
            {
                "key": "SEFK-H",
                "subPhases": [
                    {
                        "key": "SEFK-S",
                        "workStreams": [
                            {"key": "SEFK-W", "epics": [{"key": "SEFK-1", "summary": "Epic 1"}]},
                        ],
                    }
                ],
            }
        ]

    def test_one_children_search_is_shared_and_block_rollups_are_used(self):
        config = _config()
        searches: list[str] = []
        children = [_child("SEFK-10", "SEFK-1")]

        def fake_search(_adapter, jql, _fields):
            searches.append(jql)
            return children if "parent in" in jql else []

        block_rollup = {"phases": {}, "totalWeight": 3.0}
        with patch.object(mod, "_resolve_kpmg_reference_field_id", return_value=None), patch.object(
            mod, "_resolve_kpmg_assignee_field_id", return_value=None
        ), patch.object(mod, "resolve_scope_filter_jql", return_value="filter = 1"), patch.object(
            mod, "search_all", side_effect=fake_search
        ), patch.object(
            mod,
            "_build_sefk_hierarchy_from_flat",
            return_value=(
                self._phases(),
                ["SEFK-H"],
                [],
                {"SEFK-W": {"key": "SEFK-W"}},
                {"SEFK-1": {"key": "SEFK-1"}},
            ),
        ), patch.object(
            mod, "_build_block_scope_rollups", return_value={"SEFK-W": block_rollup}
        ), patch.object(mod, "_issue_timeline_row", side_effect=lambda issue, **_kw: {"key": issue["key"]}):
            payload = mod.fetch_sefk_project_plan_timeline(MagicMock(), config)

        self.assertEqual(sum("parent in" in jql for jql in searches), 1)
        epic = payload["phases"][0]["subPhases"][0]["workStreams"][0]["epics"][0]
        self.assertEqual([row["key"] for row in epic["levelZero"]], ["SEFK-10"])
        self.assertEqual(epic["scopeRollup"]["issueCount"], 1)
        self.assertEqual(payload["phases"][0]["subPhases"][0]["workStreams"][0]["scopeRollup"], block_rollup)

    def test_epic_rollups_search_themselves_when_children_search_did_not_cover_them(self):
        config = _config()
        searches: list[str] = []

        def fake_search(_adapter, jql, _fields):
            searches.append(jql)
            return []

        # Rollup epic SEFK-2 is not in the phases, so the shared children search can't be reused.
        with patch.object(mod, "_resolve_kpmg_reference_field_id", return_value=None), patch.object(
            mod, "_resolve_kpmg_assignee_field_id", return_value=None
        ), patch.object(mod, "resolve_scope_filter_jql", return_value="filter = 1"), patch.object(
            mod, "search_all", side_effect=fake_search
        ), patch.object(
            mod,
            "_build_sefk_hierarchy_from_flat",
            return_value=(
                self._phases(),
                ["SEFK-H"],
                [],
                {},
                {"SEFK-1": {"key": "SEFK-1"}, "SEFK-2": {"key": "SEFK-2"}},
            ),
        ), patch.object(mod, "_build_block_scope_rollups", return_value={}), patch.object(
            mod, "_issue_timeline_row", side_effect=lambda issue, **_kw: {"key": issue["key"]}
        ):
            mod.fetch_sefk_project_plan_timeline(MagicMock(), config)

        self.assertEqual(sum("parent in" in jql for jql in searches), 2)


if __name__ == "__main__":
    unittest.main()
