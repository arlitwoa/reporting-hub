"""Tests for SEF project plan component colour mapping."""

from __future__ import annotations

import unittest
from pathlib import Path

from extensions.twoa_programme.sef_project_plan_component_colors import (
    load_sef_project_plan_component_colors,
)

_REPO = Path(__file__).resolve().parents[1]


class SefProjectPlanComponentColorsTests(unittest.TestCase):
    def test_loads_jira_plans_palette(self) -> None:
        colors = load_sef_project_plan_component_colors(_REPO / "config" / "sef-project-plan-component-colors.json")
        self.assertEqual(colors.default_fill, "#7A869A")
        self.assertEqual(colors.components["Payroll"], "#FFE380")
        self.assertEqual(colors.components["Testing"], "#00875A")
        self.assertEqual(colors.components["Change"], "#998DD9")

    def test_fill_for_row_uses_first_matching_component(self) -> None:
        colors = load_sef_project_plan_component_colors(_REPO / "config" / "sef-project-plan-component-colors.json")
        self.assertEqual(colors.fill_for_row({"components": ["HCM"]}), "#FF8B66")
        self.assertEqual(colors.fill_for_row({"components": ["Change"]}), "#998DD9")
        self.assertEqual(colors.fill_for_row({"components": []}), "#7A869A")
        self.assertEqual(colors.fill_for_row({}), "#7A869A")


if __name__ == "__main__":
    unittest.main()
