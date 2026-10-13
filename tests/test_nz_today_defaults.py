"""Report defaults must use today's NZ date, not the (UTC) CI runner's date."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from extensions.twoa_programme import quarterly_dashboard_data, sef_test_plan_schedule
from extensions.twoa_programme.sef_test_plan_manifest import TestPlanConfig as _PlanConfig

# 14 Oct 07:06 NZDT is still 13 Oct 18:06 UTC on a CI runner.
_INSTANT = datetime(2026, 10, 13, 18, 6, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return _INSTANT.astimezone(tz) if tz else _INSTANT.replace(tzinfo=None)


class _UtcRunnerDate(date):
    """What date.today() returns on a UTC runner at that instant."""

    @classmethod
    def today(cls):
        return cls(2026, 10, 13)


def _freeze(module):
    return (
        patch.object(module, "datetime", _FrozenDatetime),
        patch.object(module, "date", _UtcRunnerDate),
    )


class NzTodayDefaultsTests(unittest.TestCase):
    def test_quarterly_dashboard_report_date_defaults_to_nz_today(self) -> None:
        datetime_patch, date_patch = _freeze(quarterly_dashboard_data)
        with datetime_patch, date_patch:
            self.assertEqual(quarterly_dashboard_data._parse_report_date(None), date(2026, 10, 14))
            self.assertEqual(quarterly_dashboard_data._parse_report_date("2026-10-01"), date(2026, 10, 1))

    def test_next_open_block_anchors_undated_blocks_at_nz_today(self) -> None:
        plan = _PlanConfig(slug="p", title="P", details={"B": "SEF-2", "A": "SEF-1"})
        issues = {
            # B starts on the NZ date; A has no dates so it is anchored at "today".
            "SEF-2": {"fields": {"summary": "B", "status": {"name": "To Do"}, "customfield_10015": "2026-10-14"}},
            "SEF-1": {"fields": {"summary": "A", "status": {"name": "To Do"}}},
        }
        datetime_patch, date_patch = _freeze(sef_test_plan_schedule)
        with datetime_patch, date_patch:
            # On NZ's 14 Oct both anchor at 14 Oct, so plan order decides: B (listed first).
            # With the UTC date (13 Oct) the undated block A would wrongly sort ahead.
            self.assertEqual(sef_test_plan_schedule.next_open_block_label(issues, plan), "B")


if __name__ == "__main__":
    unittest.main()
