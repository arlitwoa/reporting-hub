import unittest

from scripts.github_copilot_governance_summary import _render_html


class CopilotGovernanceSummaryTests(unittest.TestCase):
    def test_rendered_html_displays_generated_timestamp(self):
        summary = {
            "monthly": {"month": "2026-10", "net_total_nzd": 0.0},
            "groups": [],
            "grouped_users": [],
            "additions": [],
            "removals": [],
            "unmapped": [],
            "currency": "NZD",
            "billing": {"rows": [], "alert_recipients": [], "org_enforced": False},
        }

        html_doc = _render_html(summary, generated_on="11 Oct 2026 08:21 NZDT")

        self.assertIn('class="meta generated">Generated 11 Oct 2026 08:21 NZDT', html_doc)


if __name__ == "__main__":
    unittest.main()