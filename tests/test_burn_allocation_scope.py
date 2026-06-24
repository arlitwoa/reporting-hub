import unittest
from datetime import date

from extensions.twoa_programme.burn_allocation_scope import active_release, sprint_contains


class BurnAllocationScopeTests(unittest.TestCase):
    def test_sprint_contains(self):
        sprint = {"startDate": "2026-06-08", "endDate": "2026-06-21"}
        self.assertTrue(sprint_contains(date(2026, 6, 9), sprint))
        self.assertFalse(sprint_contains(date(2026, 6, 22), sprint))

    def test_active_release_is_next_real_release(self):
        releases = [
            {"name": "20260528-engine", "releaseDate": "2026-05-28", "projected": False},
            {"name": "20260611-engine", "releaseDate": "2026-06-11", "projected": False},
            {"name": "projected-2026-06-25-engine", "releaseDate": "2026-06-25", "projected": True},
        ]
        active = active_release(releases, date(2026, 6, 9))
        self.assertEqual(active["name"], "20260611-engine")


if __name__ == "__main__":
    unittest.main()
