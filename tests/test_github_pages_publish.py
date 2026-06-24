"""Tests for GitHub Pages dashboard publish."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from extensions.twoa_programme.github_pages_publish import (
    SiteIndexReport,
    build_github_pages_site_index_html,
    site_root_index_path,
    write_pages_snapshot,
)
from extensions.twoa_programme.quarterly_reporting import GitHubPagesPublish, load_quarterly_reporting_config


class GitHubPagesPublishTests(unittest.TestCase):
    def test_config_loads_github_pages(self):
        config = load_quarterly_reporting_config()
        self.assertIsNotNone(config.github_pages)
        pages = config.github_pages
        assert pages is not None
        self.assertEqual(pages.publish_dir, "docs/quarter")
        self.assertEqual(pages.index_file, "index.html")
        self.assertEqual(pages.site_path, "quarter")

    def test_site_url(self):
        pages = GitHubPagesPublish(
            publish_dir="docs/quarter",
            index_file="index.html",
            site_path="quarter",
            github_user="barlconz",
            repo_name="artifact-consumer-twoa",
        )
        self.assertEqual(
            pages.site_url(),
            "https://barlconz.github.io/artifact-consumer-twoa/quarter/",
        )

    def test_publish_path(self):
        pages = GitHubPagesPublish(
            publish_dir="docs/quarter",
            index_file="index.html",
        )
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            pages.publish_path(root),
            root / "docs" / "quarter" / "index.html",
        )

    def test_write_pages_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "docs" / "quarter" / "index.html"
            write_pages_snapshot("<html>ok</html>", dest)
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.read_text(encoding="utf-8"), "<html>ok</html>")

    def test_site_index_html_lists_reports(self):
        html_doc = build_github_pages_site_index_html(
            [
                SiteIndexReport(href="quarter/", title="Quarter dashboard"),
                SiteIndexReport(href="sprint-health/", title="Sprint Health"),
            ],
            generated_on="19 Jun 2026 05:00 NZST",
            site_url="https://barlconz.github.io/artifact-consumer-twoa/",
        )
        self.assertIn("EPCE delivery reports", html_doc)
        self.assertIn('href="quarter/"', html_doc)
        self.assertIn('href="sprint-health/"', html_doc)
        self.assertIn("barlconz.github.io/artifact-consumer-twoa/", html_doc)

    def test_site_root_index_path(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(site_root_index_path(root), root / "docs" / "index.html")


if __name__ == "__main__":
    unittest.main()
