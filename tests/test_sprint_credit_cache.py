"""Sprint credit cache and concurrent delivery-health publishing."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from extensions.twoa_programme.sprint_credit_cache import (
    SprintCreditCache,
    install_sprint_credit_cache,
    prefetch_sprint_credits,
)

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def _config(deploy=("awaiting stg",), terminal=("done",)):
    return SimpleNamespace(
        deploy_statuses=set(deploy),
        terminal_statuses=set(terminal),
        story_points_field="customfield_10026",
        sprint_scope_jql=lambda sprint_id: f"sprint = {sprint_id}",
    )


def _sprint(sprint_id=1, *, state="closed", closed_days_ago=30):
    closed = NOW - timedelta(days=closed_days_ago)
    return {
        "id": sprint_id,
        "state": state,
        "startDate": (closed - timedelta(days=14)).isoformat(),
        "endDate": closed.isoformat(),
        "completeDate": closed.isoformat(),
    }


class SprintCreditCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "cache.json"
        self.calls: list[int] = []
        self.config = _config()

    def _wrapped(self, cache: SprintCreditCache, *, now=NOW):
        def compute(_jira, sprint):
            self.calls.append(sprint["id"])
            return 10.0 + sprint["id"]

        return cache.wrap(compute, lambda: self.config, now=lambda: now)

    def test_memoises_within_a_process_even_when_not_persistable(self):
        cache = SprintCreditCache(self.path)
        fn = self._wrapped(cache)
        recent = _sprint(1, closed_days_ago=1)
        self.assertEqual(fn(None, recent), 11.0)
        self.assertEqual(fn(None, recent), 11.0)
        self.assertEqual(self.calls, [1])
        cache.save()
        self.assertFalse(self.path.exists())  # recently closed: never written to disk

    def test_old_closed_sprint_persists_across_processes(self):
        first = SprintCreditCache(self.path)
        self._wrapped(first)(None, _sprint(1))
        first.save()
        self.assertEqual(self.calls, [1])

        second = SprintCreditCache(self.path)
        self.assertEqual(self._wrapped(second)(None, _sprint(1)), 11.0)
        self.assertEqual(self.calls, [1])  # served from disk

    def test_entry_expires_after_max_age(self):
        first = SprintCreditCache(self.path)
        self._wrapped(first)(None, _sprint(1))
        first.save()

        later = NOW + timedelta(hours=25)
        within = SprintCreditCache(self.path)
        self._wrapped(within, now=NOW + timedelta(hours=23))(None, _sprint(1))
        self.assertEqual(self.calls, [1])  # still fresh

        expired = SprintCreditCache(self.path)
        self._wrapped(expired, now=later)(None, _sprint(1))
        self.assertEqual(self.calls, [1, 1])  # older than max_age: refetched

    def test_status_config_change_is_a_miss_and_replaces_entry(self):
        first = SprintCreditCache(self.path)
        self._wrapped(first)(None, _sprint(1))
        first.save()

        self.config = _config(deploy=("awaiting stg", "awaiting prd"))
        second = SprintCreditCache(self.path)
        self._wrapped(second)(None, _sprint(1))
        second.save()
        self.assertEqual(self.calls, [1, 1])
        self.assertEqual(len(json.loads(self.path.read_text())), 1)

    def test_open_or_undated_sprints_are_not_persisted(self):
        cache = SprintCreditCache(self.path)
        fn = self._wrapped(cache)
        fn(None, _sprint(1, state="active"))
        fn(None, {"id": 2, "state": "closed"})
        cache.save()
        self.assertFalse(self.path.exists())

    def test_corrupt_or_legacy_file_is_ignored(self):
        self.path.write_text("{nope")
        self.assertEqual(SprintCreditCache(self.path)._persisted, {})
        self.path.write_text(json.dumps({"other:key": {"credit": 1}}))
        self.assertEqual(SprintCreditCache(self.path)._persisted, {})


class InstallTests(unittest.TestCase):
    def test_install_patches_engine_once_and_prefetch_dedupes(self):
        from artifact.delivery_health import sprint_engine

        engine = sys.modules[sprint_engine.baseline_velocity.__module__]
        calls: list[int] = []

        def original(_jira, sprint):
            calls.append(sprint["id"])
            return 5.0

        with patch.object(engine, "deploy_credit_for_sprint", original), patch.object(
            engine, "_cfg", return_value=_config()
        ):
            cache = install_sprint_credit_cache(None)
            again = install_sprint_credit_cache(None)
            self.assertIs(cache, again)
            self.assertIsNot(engine.deploy_credit_for_sprint, original)

            sprints = [_sprint(1), _sprint(2), _sprint(1)]
            prefetch_sprint_credits(None, sprints, workers=3)
            self.assertEqual(sorted(calls), [1, 2])
            # baseline_velocity-style call through the module now hits the memo.
            self.assertEqual(engine.deploy_credit_for_sprint(None, _sprint(2)), 5.0)
            self.assertEqual(sorted(calls), [1, 2])


class PublishSnapshotsTests(unittest.TestCase):
    def test_squads_and_dev_done_built_concurrently_but_written_in_order(self):
        import scripts.publish_delivery_health_pages as mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            squads = {
                "b": SimpleNamespace(label="B", board_id=2),
                "a": SimpleNamespace(label="A", board_id=1),
            }
            health_config = SimpleNamespace(
                squads=squads,
                dev_done_risk=SimpleNamespace(),
            )
            pages = MagicMock()
            pages.squad_publish_path.side_effect = lambda _root, slug: root / f"{slug}.html"
            pages.sprint_landing_path.return_value = root / "landing.html"
            pages.dev_done_publish_path.return_value = root / "dev.html"
            pages.dev_done_risk.site_path = "dev-done-risk"
            pages.dev_done_risk.index_file = "index.html"

            def fake_sprint_reports(_config, _gateway, args):
                slug = args.squad[0]
                if slug == "b":
                    raise SystemExit("No active sprint for squad 'b' on board 2.")
                out = args.output_dir / f"{slug}.html"
                out.write_text(f"<html>report {slug}</html>", encoding="utf-8")
                return [out]

            def fake_dev_done(_config, _gateway, args):
                out = args.output_dir / "dev.html"
                out.write_text("<html>dev</html>", encoding="utf-8")
                return out

            writes: list[tuple[str, str]] = []
            with patch.object(mod, "resolve_in_cycle_fix_version", return_value="1.0"), patch.object(
                mod, "bind_delivery_health_config"
            ), patch.object(mod, "install_sprint_credit_cache", return_value=MagicMock()), patch.object(
                mod, "closed_sprints_for_squad", return_value=[]
            ), patch.object(mod, "prefetch_sprint_credits"), patch.object(
                mod, "run_sprint_health_reports", side_effect=fake_sprint_reports
            ), patch.object(mod, "run_dev_done_risk_report", side_effect=fake_dev_done), patch.object(
                mod, "ensure_epc_report_breadcrumb", side_effect=lambda html, **_kw: html
            ), patch.object(mod, "reorder_dev_done_fix_version_section", side_effect=lambda h: h), patch.object(
                mod, "ensure_dev_done_generated_timestamp", side_effect=lambda h, **_kw: h
            ), patch.object(
                mod, "build_no_active_sprint_html", return_value="<html>none</html>"
            ), patch.object(
                mod, "build_sprint_health_landing_html", return_value="<html>landing</html>"
            ), patch.object(
                mod, "write_pages_snapshot", side_effect=lambda html, dest: writes.append((dest.name, html))
            ):
                written = mod.publish_snapshots(
                    gateway=MagicMock(),
                    pages=pages,
                    health_config=health_config,
                    repo_root=root,
                    generated_on="now",
                )

        self.assertEqual([p.name for p in written], ["a.html", "b.html", "landing.html", "dev.html"])
        self.assertEqual(
            writes,
            [
                ("a.html", "<html>report a</html>"),
                ("b.html", "<html>none</html>"),
                ("landing.html", "<html>landing</html>"),
                ("dev.html", "<html>dev</html>"),
            ],
        )


class QuarterGoalBreakdownTests(unittest.TestCase):
    def test_breakdown_assembled_in_original_key_order(self):
        import scripts.quarterly.fetch_quarter_goal as mod

        adapter = MagicMock()
        adapter._resolve_field_aliases.return_value = {"Story Points": "customfield_10026"}
        config = SimpleNamespace(
            scope=SimpleNamespace(
                quarter_filter="qf",
                global_scope_jql="scope jql",
                global_burn_jql="burn jql",
            )
        )
        with patch.object(mod, "planned_scope_jqls", return_value={}), patch.object(
            mod, "sum_story_points_by_exclusive_lane", return_value={"lane": 1}
        ), patch.object(mod, "sum_story_points_in_scope", return_value={"total": 2}), patch.object(
            mod, "count_unpointed_stories_bugs_by_lane", return_value={"total": 3}
        ), patch.object(mod, "education_cloud_squad_scope_breakdown", return_value={"squads": 4}):
            result = mod.fetch_scope_breakdown(adapter, config, "customfield_10026")

        self.assertEqual(
            list(result),
            ["lane", "inGlobalQuarter", "unpointedStoriesBugs", "educationCloudSquads"],
        )
        self.assertEqual(result["inGlobalQuarter"], {"jql": "scope jql", "total": 2})
        self.assertEqual(result["unpointedStoriesBugs"], {"total": 3})
        self.assertEqual(result["educationCloudSquads"], {"squads": 4})


if __name__ == "__main__":
    unittest.main()
