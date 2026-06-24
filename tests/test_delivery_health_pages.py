"""Tests for delivery health GitHub Pages publish paths."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from extensions.twoa_programme.delivery_health import load_delivery_health_config
from extensions.twoa_programme.delivery_health_pages import (
    build_sprint_health_landing_html,
    load_delivery_health_pages_config,
)
from extensions.twoa_programme.github_pages_publish import write_pages_snapshot

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HEALTH_CONFIG = _REPO_ROOT / "config" / "delivery-health.json"


class DeliveryHealthPagesTests(unittest.TestCase):
    def test_config_loads_github_pages(self):
        pages = load_delivery_health_pages_config(health_path=_HEALTH_CONFIG)
        self.assertIsNotNone(pages)
        assert pages is not None
        self.assertEqual(pages.sprint_health.publish_dir, "docs/sprint-health")
        self.assertEqual(pages.sprint_health.site_path, "sprint-health")
        self.assertEqual(pages.dev_done_risk.publish_dir, "docs/dev-done-risk")
        self.assertEqual(pages.dev_done_risk.site_path, "dev-done-risk")

    def test_stable_publish_paths(self):
        pages = load_delivery_health_pages_config(health_path=_HEALTH_CONFIG)
        assert pages is not None
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            pages.squad_publish_path(root, "kakariki"),
            root / "docs" / "sprint-health" / "kakariki" / "index.html",
        )
        self.assertEqual(
            pages.dev_done_publish_path(root),
            root / "docs" / "dev-done-risk" / "index.html",
        )
        self.assertEqual(
            pages.sprint_landing_path(root),
            root / "docs" / "sprint-health" / "index.html",
        )

    def test_site_urls(self):
        pages = load_delivery_health_pages_config(health_path=_HEALTH_CONFIG)
        assert pages is not None
        self.assertEqual(
            pages.sprint_health.site_url(),
            "https://arlitwoa.github.io/reporting-hub/sprint-health/",
        )
        self.assertEqual(
            pages.dev_done_risk.site_url(),
            "https://arlitwoa.github.io/reporting-hub/dev-done-risk/",
        )

    def test_landing_html_lists_squads(self):
        pages = load_delivery_health_pages_config(health_path=_HEALTH_CONFIG)
        assert pages is not None
        health = load_delivery_health_config(health_path=_HEALTH_CONFIG)
        html_doc = build_sprint_health_landing_html(
            health.squads,
            pages,
            generated_on="10 Jun 2026",
        )
        self.assertIn("Kākāriki", html_doc)
        self.assertIn('href="kakariki/"', html_doc)
        self.assertIn("Waiporoporo", html_doc)
        self.assertIn('class="report-subtitle">Generated 10 Jun 2026</p>', html_doc)

    def test_write_pages_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "docs" / "sprint-health" / "kakariki" / "index.html"
            write_pages_snapshot("<html>ok</html>", dest)
            self.assertTrue(dest.is_file())


if __name__ == "__main__":
    unittest.main()
