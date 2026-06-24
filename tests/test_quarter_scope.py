import unittest

from extensions.twoa_programme.quarter_scope import (
    classify_exclusive_lane,
    lane1_education_cloud_jql,
    milestone_linked_epic_scope_jql,
    planned_scope_jqls,
    unassigned_burn_jql,
    unassigned_scope_jql,
)


class QuarterScopeTests(unittest.TestCase):
    def _issue(
        self,
        *,
        squads=None,
        change_types=None,
        platform=None,
        links=None,
    ) -> dict:
        return {
            "fields": {
                "customfield_11102": [{"value": v} for v in (squads or [])],
                "customfield_10079": [{"value": v} for v in (change_types or [])],
                "customfield_10120": {"value": platform} if platform else None,
                "issuelinks": links or [],
            }
        }

    def test_classify_priority_l3_over_l2_over_l1(self):
        issue = self._issue(
            squads=["Data Migration", "Kākāriki Krew"],
            platform="azure-integration-services",
        )
        lane = classify_exclusive_lane(
            issue,
            delivery_squad_field="customfield_11102",
            change_types_field="customfield_10079",
            platform_field="customfield_10120",
        )
        self.assertEqual(lane, "dataMigration")

    def test_classify_unassigned_without_lane_signals(self):
        issue = self._issue()
        lane = classify_exclusive_lane(
            issue,
            delivery_squad_field="customfield_11102",
            change_types_field="customfield_10079",
            platform_field="customfield_10120",
        )
        self.assertEqual(lane, "unassigned")
    def test_exclusive_lane_jql_contains_quarter_filter(self):
        jql = lane1_education_cloud_jql()
        self.assertIn("smart-current-quarter", jql)
        self.assertIn("Kākāriki Krew", jql)
        self.assertIn("status != Rejected", jql)
        self.assertNotIn("Data Migration", jql.split("NOT", 1)[0])

    def test_planned_scopes_are_four_slices(self):
        scopes = planned_scope_jqls()
        self.assertEqual(
            set(scopes.keys()),
            {"educationCloud", "integration", "dataMigration", "unassigned"},
        )

    def test_unassigned_uses_demorgan_not_or_of_exclusive(self):
        exclusive = unassigned_burn_jql()
        self.assertIn('NOT ("Delivery Squad', exclusive)
        self.assertIn("azure-integration-services", exclusive)
        self.assertNotIn("OR (\"Delivery Squad", exclusive)
        planned = planned_scope_jqls()["unassigned"]
        self.assertIn("Change Types", planned)
        self.assertIn("Kākāriki Krew", planned)

    def test_unassigned_differs_board_inverse_from_exclusive_burn(self):
        board_inverse = unassigned_scope_jql()
        exclusive = unassigned_burn_jql()
        self.assertIn("NOT (", board_inverse)
        self.assertIn("NOT (", exclusive)
        self.assertNotEqual(board_inverse, exclusive)

    def test_milestone_linked_epic_scope_omits_quarter_filter(self):
        jql = milestone_linked_epic_scope_jql(parent_keys_csv="EPCE-422, EPCE-423")
        self.assertIn("parent in (EPCE-422, EPCE-423)", jql)
        self.assertIn("status != Rejected", jql)
        self.assertIn("Story", jql)
        self.assertNotIn("smart-current-quarter", jql)
        self.assertNotIn("filter =", jql)


if __name__ == "__main__":
    unittest.main()
