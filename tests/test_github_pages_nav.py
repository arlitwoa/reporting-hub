"""Tests for reporting-hub breadcrumb navigation."""

from __future__ import annotations

import unittest

from extensions.twoa_programme.github_pages_nav import (
    build_breadcrumb_html,
    docs_relative_href,
    epc_report_breadcrumbs,
    programme_report_breadcrumbs,
)


class GitHubPagesNavTests(unittest.TestCase):
    def test_docs_relative_href_from_nested_plan(self) -> None:
        href = docs_relative_href("sef/plans/payroll-parallel.html", "index.html")
        self.assertEqual(href, "../../index.html")
        self.assertEqual(
            docs_relative_href("sef/plans/payroll-parallel.html", "sef/index.html"),
            "../index.html",
        )

    def test_programme_report_breadcrumbs(self) -> None:
        nav = programme_report_breadcrumbs(
            publish_path="sef/plans/payroll-parallel.html",
            programme_id="sef",
            programme_title="SEF",
            report_title="Payroll Parallel",
        )
        self.assertIn('aria-label="Breadcrumb"', nav)
        self.assertIn("Payroll Parallel", nav)
        self.assertIn('href="../../index.html"', nav)
        self.assertIn('href="../index.html"', nav)

    def test_epc_report_breadcrumbs(self) -> None:
        nav = epc_report_breadcrumbs(
            publish_path="quarter/index.html",
            report_title="Quarter dashboard",
        )
        self.assertIn("EPC delivery", nav)
        self.assertIn("Quarter dashboard", nav)

    def test_build_breadcrumb_html_omits_link_on_current(self) -> None:
        from extensions.twoa_programme.github_pages_nav import NavCrumb

        html_doc = build_breadcrumb_html(
            [NavCrumb("Home", "index.html"), NavCrumb("Current")],
        )
        self.assertIn('<span class="current">Current</span>', html_doc)
        self.assertNotIn('<a href="index.html">Current</a>', html_doc)


if __name__ == "__main__":
    unittest.main()
