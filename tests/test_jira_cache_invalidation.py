"""Persisted Jira caches must only be reused while the issue is unchanged."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from extensions.twoa_programme.milestone_timeline import (
    cached_changelog_histories,
    fetch_scope_changelogs,
    store_changelog_histories,
)
from scripts.quarterly.jira_burn import (
    _credit_cache_key,
    _load_cache,
    _resolve_credit_ledger,
)

UPDATED_1 = "2026-10-13T09:00:45.123+1300"
UPDATED_2 = "2026-10-13T10:15:00.000+1300"


class ChangelogCacheTests(unittest.TestCase):
    def test_hit_only_when_updated_matches(self):
        cache: dict = {}
        store_changelog_histories(cache, "EPCE-1", UPDATED_1, [{"id": "1"}])
        self.assertEqual(cached_changelog_histories(cache, "EPCE-1", UPDATED_1), [{"id": "1"}])
        self.assertIsNone(cached_changelog_histories(cache, "EPCE-1", UPDATED_2))

    def test_missing_updated_is_never_cached(self):
        cache: dict = {}
        store_changelog_histories(cache, "EPCE-1", None, [{"id": "1"}])
        self.assertEqual(cache, {})
        cache["EPCE-1"] = {"updated": UPDATED_1, "histories": []}
        self.assertIsNone(cached_changelog_histories(cache, "EPCE-1", None))

    def test_legacy_list_entry_is_a_miss(self):
        self.assertIsNone(cached_changelog_histories({"EPCE-1": [{"id": "1"}]}, "EPCE-1", UPDATED_1))

    def test_fetch_scope_changelogs_refetches_only_changed_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            adapter = MagicMock()
            calls: list[str] = []

            def fake_fetch(_adapter, key):
                calls.append(key)
                return [{"id": f"{key}-{len(calls)}"}]

            with patch("extensions.twoa_programme.milestone_timeline.fetch_issue_changelog_histories", fake_fetch):
                first = fetch_scope_changelogs(
                    adapter,
                    ["A-1", "A-2"],
                    cache_path=path,
                    updated_by_key={"A-1": UPDATED_1, "A-2": UPDATED_1},
                )
                self.assertEqual(calls, ["A-1", "A-2"])

                calls.clear()
                second = fetch_scope_changelogs(
                    adapter,
                    ["A-1", "A-2"],
                    cache_path=path,
                    updated_by_key={"A-1": UPDATED_1, "A-2": UPDATED_2},
                )
                self.assertEqual(calls, ["A-2"])
                self.assertEqual(second["A-1"], first["A-1"])
                self.assertNotEqual(second["A-2"], first["A-2"])

    def test_without_updated_everything_is_fetched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            calls: list[str] = []

            def fake_fetch(_adapter, key):
                calls.append(key)
                return []

            with patch("extensions.twoa_programme.milestone_timeline.fetch_issue_changelog_histories", fake_fetch):
                fetch_scope_changelogs(MagicMock(), ["A-1"], cache_path=path)
                fetch_scope_changelogs(MagicMock(), ["A-1"], cache_path=path)
            self.assertEqual(calls, ["A-1", "A-1"])


class CreditLedgerCacheTests(unittest.TestCase):
    deploy = {"Awaiting STG"}
    done = {"Done"}

    def _key(self, issue, *, scope="global", deploy=None, done=None):
        return _credit_cache_key(
            scope,
            "EPCE-1",
            issue,
            deploy_statuses=deploy or self.deploy,
            done_statuses=done or self.done,
        )

    def test_key_changes_with_updated_and_status_config(self):
        a = self._key({"fields": {"updated": UPDATED_1}})
        b = self._key({"fields": {"updated": UPDATED_2}})
        c = self._key({"fields": {"updated": UPDATED_1}}, done={"Done", "Closed"})
        self.assertEqual(len({a, b, c}), 3)

    def test_no_updated_means_no_caching(self):
        self.assertIsNone(self._key({"fields": {}}))

    def test_resolve_uses_cache_then_refetches_after_update_and_prunes(self):
        cache: dict = {}
        ledger_1 = [{"credit_at": "2026-05-01T00:00:00+00:00", "delta": 1}]
        ledger_2 = ledger_1 + [{"credit_at": "2026-05-02T00:00:00+00:00", "delta": -1}]
        issue_1 = {"fields": {"updated": UPDATED_1}}
        issue_2 = {"fields": {"updated": UPDATED_2}}
        # An unrelated issue sharing the id prefix must not be pruned.
        cache["credit:v4:global:EPCE-10:sig:" + UPDATED_1] = json.dumps([])

        with patch("scripts.quarterly.jira_burn.fetch_deploy_or_done_credit_ledger") as fetch:
            fetch.side_effect = [ledger_1, ledger_2]
            key_1 = self._key(issue_1)
            self.assertEqual(
                _resolve_credit_ledger(MagicMock(), "EPCE-1", self.deploy, self.done, cache=cache, cache_key=key_1),
                ledger_1,
            )
            self.assertEqual(
                _resolve_credit_ledger(MagicMock(), "EPCE-1", self.deploy, self.done, cache=cache, cache_key=key_1),
                ledger_1,
            )
            self.assertEqual(fetch.call_count, 1)

            key_2 = self._key(issue_2)
            self.assertEqual(
                _resolve_credit_ledger(MagicMock(), "EPCE-1", self.deploy, self.done, cache=cache, cache_key=key_2),
                ledger_2,
            )
            self.assertEqual(fetch.call_count, 2)

        self.assertNotIn(key_1, cache)
        self.assertIn(key_2, cache)
        self.assertIn("credit:v4:global:EPCE-10:sig:" + UPDATED_1, cache)

    def test_uncacheable_issue_always_fetches_and_stores_nothing(self):
        cache: dict = {}
        with patch("scripts.quarterly.jira_burn.fetch_deploy_or_done_credit_ledger", return_value=[]) as fetch:
            for _ in range(2):
                _resolve_credit_ledger(MagicMock(), "EPCE-1", self.deploy, self.done, cache=cache, cache_key=None)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(cache, {})

    def test_load_cache_drops_legacy_and_corrupt_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            path.write_text(json.dumps({"credit:v3:global:EPCE-1": "[]", "credit:v4:global:EPCE-1:s:u": "[]"}))
            self.assertEqual(list(_load_cache(path)), ["credit:v4:global:EPCE-1:s:u"])
            path.write_text("{not json")
            self.assertEqual(_load_cache(path), {})


if __name__ == "__main__":
    unittest.main()
