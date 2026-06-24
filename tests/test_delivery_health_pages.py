"""Tests for delivery health GitHub Pages publish paths."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from extensions.twoa_programme.delivery_health import load_delivery_health_config
from extensions.twoa_programme.delivery_health_confluence import (
    build_dev_done_risk_template_body,
    build_sprint_health_hub_template_body,
    build_sprint_health_squad_template_body,
    load_delivery_health_confluence_config,
)
from extensions.twoa_programme.delivery_health_pages import (
    build_sprint_health_landing_html,
    load_delivery_health_pages_config,
)
from extensions.twoa_programme.github_pages_publish import write_pages_snapshot


class DeliveryHealthPagesTests(unittest.TestCase):
    def test_config_loads_github_pages(self):
        pages = load_delivery_health_pages_config()
        self.assertIsNotNone(pages)
        assert pages is not None
        self.assertEqual(pages.sprint_health.publish_dir, "docs/sprint-health")
        self.assertEqual(pages.sprint_health.site_path, "sprint-health")
        self.assertEqual(pages.dev_done_risk.publish_dir, "docs/dev-done-risk")
        self.assertEqual(pages.dev_done_risk.site_path, "dev-done-risk")

    def test_stable_publish_paths(self):
        pages = load_delivery_health_pages_config()
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
        pages = load_delivery_health_pages_config()
        assert pages is not None
        self.assertEqual(
            pages.sprint_health.site_url(),
            "https://barlconz.github.io/artifact-consumer-twoa/sprint-health/",
        )
        self.assertEqual(
            pages.dev_done_risk.site_url(),
            "https://barlconz.github.io/artifact-consumer-twoa/dev-done-risk/",
        )

    def test_landing_html_lists_squads(self):
        pages = load_delivery_health_pages_config()
        assert pages is not None
        health = load_delivery_health_config()
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

    def test_confluence_config_loads(self):
        conf = load_delivery_health_confluence_config()
        self.assertIsNotNone(conf)
        assert conf is not None
        self.assertEqual(conf.space_key, "DTRAIN")
        self.assertEqual(conf.sprint_health.hub_title, "Sprint Health | Deliver")
        self.assertEqual(
            conf.sprint_health.squad_page_title("Kākāriki"),
            "Current Sprint | Kākāriki",
        )
        self.assertEqual(conf.dev_done_risk.page_title, "Current Engine | Dev Done Risk")

    def test_confluence_template_bodies(self):
        pages = load_delivery_health_pages_config()
        health = load_delivery_health_config()
        assert pages is not None
        squad_titles = [
            (s.label, f"Current Sprint | {s.label}") for s in health.squads.values()
        ]
        hub = build_sprint_health_hub_template_body(
            squad_page_titles=squad_titles,
            pages=pages,
            generated_on="11 Jun 2026",
        )
        self.assertIn("Squad Reports", hub)
        self.assertIn("Kākāriki", hub)
        self.assertIn("data-layout=\"full-width\"", hub)
        self.assertNotIn("Generated ", hub)
        self.assertNotIn('ac:name="info"', hub)

        squad = build_sprint_health_squad_template_body(
            squad_label="Kākāriki",
            board_name="Kākāriki Krew Scrum | Delivery",
            board_id=893,
            squad_pages_url="https://example.github.io/sprint-health/kakariki/",
            generated_on="11 Jun 2026",
        )
        self.assertIn("Awaiting first refresh", squad)
        self.assertIn("893", squad)
        self.assertNotIn('ac:name="info"', squad)

        dev_done = build_dev_done_risk_template_body(
            dev_done_pages_url="https://example.github.io/dev-done-risk/",
            generated_on="11 Jun 2026",
        )
        self.assertIn("Critical", dev_done)
        self.assertIn("smart-epc-in-cycle", dev_done)
        self.assertNotIn('ac:name="info"', dev_done)


if __name__ == "__main__":
    unittest.main()
