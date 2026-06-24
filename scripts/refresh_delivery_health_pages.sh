#!/usr/bin/env bash
# Sprint Health + Dev Done risk refresh → GitHub Pages snapshots.
# Used locally and by scripts/refresh_github_pages_reports.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python}"
exec "$PY" scripts/publish_delivery_health_pages.py --write "$@"
