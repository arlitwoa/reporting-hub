"""HTML and Confluence bodies for EPCE quarterly dashboard (EPCE-6745 Phase 4)."""

from __future__ import annotations

from extensions.twoa_programme import (
    quarterly_dashboard_build,
    quarterly_dashboard_calendar,
    quarterly_dashboard_constants,
    quarterly_dashboard_data,
    quarterly_dashboard_links,
    quarterly_dashboard_markup,
    quarterly_dashboard_svg_core,
    quarterly_dashboard_svg_epic,
    quarterly_dashboard_svg_lane,
    quarterly_dashboard_tables,
)

_SUBMODULES = (
    quarterly_dashboard_constants,
    quarterly_dashboard_links,
    quarterly_dashboard_markup,
    quarterly_dashboard_data,
    quarterly_dashboard_calendar,
    quarterly_dashboard_svg_core,
    quarterly_dashboard_svg_lane,
    quarterly_dashboard_svg_epic,
    quarterly_dashboard_tables,
    quarterly_dashboard_build,
)

for _module in _SUBMODULES:
    for _name, _value in vars(_module).items():
        if _name.startswith("__"):
            continue
        globals()[_name] = _value

del _module, _name, _value, _SUBMODULES
