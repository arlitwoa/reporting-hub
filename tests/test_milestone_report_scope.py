import unittest

from extensions.twoa_programme.milestone_report_scope import (
    milestone_report_page_title,
    milestone_report_timeline_footnote,
)


class MilestoneReportScopeTests(unittest.TestCase):
    def test_page_title_from_report_window(self):
        title = milestone_report_page_title(
            {
                "reportWindowStart": "2026-04-01",
                "reportWindowEnd": "2026-12-31",
                "milestoneCount": 9,
            }
        )
        self.assertEqual(title, "Milestone Report | 01 Apr 2026 to 31 Dec 2026")

    def test_timeline_footnote_uses_report_window(self):
        footnote = milestone_report_timeline_footnote(
            {
                "reportWindowStart": "2026-04-01",
                "reportWindowEnd": "2026-12-31",
                "milestoneCount": 9,
            },
            detail="Each bar runs from milestone start date through due date.",
        )
        self.assertIn("9 milestones in scope", footnote)
        self.assertIn("2026-04-01 to 2026-12-31", footnote)
        self.assertNotIn("quarter", footnote.lower())


if __name__ == "__main__":
    unittest.main()
