"""Component colour mapping for SEF project plan Gantt (mirrors Jira Plans Color by → Component)."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "sef-project-plan-component-colors.json"


@dataclass(frozen=True)
class SefProjectPlanComponentColors:
    default_fill: str
    default_label: str
    components: dict[str, str]
    source: str | None = None

    def fill_for_row(self, row: dict[str, Any]) -> str:
        for name in row.get("components") or []:
            component = str(name or "").strip()
            if component in self.components:
                return self.components[component]
        return self.default_fill

    def legend_entries(self) -> list[tuple[str, str]]:
        rows = [(self.default_label, self.default_fill)]
        for name in sorted(self.components):
            rows.append((name, self.components[name]))
        return rows


def load_sef_project_plan_component_colors(
    path: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> SefProjectPlanComponentColors:
    root = repo_root or _REPO_ROOT
    config_path = path or root / "config" / "sef-project-plan-component-colors.json"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    components = {
        str(name): str(fill)
        for name, fill in (raw.get("components") or {}).items()
        if name and fill
    }
    return SefProjectPlanComponentColors(
        default_fill=str(raw.get("defaultFill") or "#7A869A"),
        default_label=str(raw.get("defaultLabel") or "All other work items"),
        components=components,
        source=str(raw.get("source") or "").strip() or None,
    )


def component_names_from_issue(issue: dict[str, Any]) -> list[str]:
    fields = issue.get("fields") or {}
    return [
        str(component.get("name") or "").strip()
        for component in (fields.get("components") or [])
        if str((component or {}).get("name") or "").strip()
    ]


def sef_project_plan_component_legend_html(colors: SefProjectPlanComponentColors) -> str:
    items = []
    for label, fill in colors.legend_entries():
        items.append(
            '<span class="sef-plan-legend-item">'
            f'<span class="sef-plan-legend-swatch" style="background:{html.escape(fill)}"></span>'
            f"{html.escape(label)}"
            "</span>"
        )
    return f'<div class="sef-plan-legend">{"".join(items)}</div>'
