#!/usr/bin/env bash
# Full quarterly dashboard refresh → GitHub Pages snapshot.
# Used locally and by scripts/refresh_github_pages_reports.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python}"
exec "$PY" scripts/quarterly/refresh_quarter_pipeline.py "$@"
