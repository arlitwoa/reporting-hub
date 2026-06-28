#!/usr/bin/env bash
# Quarterly dashboard + Sprint Health + Dev Done risk → GitHub Pages snapshots.
# Used locally and by .github/workflows/github-pages-reports.yml
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python}"

bash scripts/quarterly/refresh_dashboard_pages.sh "$@"
"$PY" scripts/quarterly/milestone_scope_report.py --output docs/quarter/milestone.html
"$PY" scripts/sef/fetch_sef_project_plan_timeline.py --write
"$PY" scripts/sef/sef_project_plan_report.py --write
bash scripts/refresh_delivery_health_pages.sh "$@"
"$PY" scripts/publish_github_pages_site_index.py
