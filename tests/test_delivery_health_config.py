import os
import unittest
from pathlib import Path

from extensions.twoa_programme.delivery_health import load_delivery_health_config


class TwoaDeliveryHealthConfigTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        os.environ.setdefault(
            "ARTIFACT_PROGRAMME_REGISTRY",
            str(root / "config" / "programme-registry.json"),
        )

    def test_loads_twao_squads_and_drop_field(self):
        config = load_delivery_health_config()
        self.assertEqual(config.project_key, "EPCE")
        self.assertIn("kakariki", config.squads)
        self.assertEqual(config.squads["kakariki"].board_id, 893)
        jql = config.sprint_scope_jql(1837)
        self.assertEqual(
            jql,
            "project = EPCE AND issuetype in (Story, Bug) AND sprint = 1837",
        )
        self.assertNotIn("Drop from Sprint Health", jql)
        self.assertNotIn("13537", jql)
        self.assertIn("customfield_13537", config.issue_fields)

    def test_loads_scoring_curve_config(self):
        config = load_delivery_health_config()
        self.assertAlmostEqual(config.week1_deploy_share, 0.10)
        self.assertAlmostEqual(config.scope_baseline_green_max, 0.90)
        self.assertAlmostEqual(config.scope_baseline_amber_max, 1.15)

    def test_loads_development_done_statuses(self):
        config = load_delivery_health_config()
        self.assertIn("Awaiting Delivery", config.development_done_statuses)
        self.assertIn("Awaiting Testing", config.development_done_statuses)
        self.assertAlmostEqual(config.development_done_forecast_weight, 0.75)
        self.assertAlmostEqual(config.status_fallback_weight["Awaiting Delivery"], 0.75)
        self.assertAlmostEqual(config.status_fallback_weight["Awaiting Testing"], 0.75)

    def test_loads_dev_done_risk_config(self):
        config = load_delivery_health_config()
        self.assertIsNotNone(config.dev_done_risk)
        risk = config.dev_done_risk
        assert risk is not None
        self.assertEqual(risk.engine_project_key, "PDE")
        self.assertEqual(risk.scope_in_cycle_filter, "smart-epc-in-cycle")
        self.assertIn("Awaiting Testing", risk.gate_statuses)
        self.assertIn("In Design", risk.medium_statuses)


if __name__ == "__main__":
    unittest.main()
