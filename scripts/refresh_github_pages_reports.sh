#!/usr/bin/env bash
# Quarterly dashboard + Sprint Health + Dev Done risk → GitHub Pages snapshots.
# Used locally and by .github/workflows/github-pages-reports.yml
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python}"

STAGE_ORDER=(quarterly sef delivery-health site-index)
SELECTED_STAGES=()
PASSTHROUGH_ARGS=()
SKIP_PREFLIGHT=0
PREFLIGHT_ONLY=0

PROGRAMME_REGISTRY="${ARTIFACT_PROGRAMME_REGISTRY:-$ROOT/config/programme-registry.json}"
ROLE_REGISTRY="${ARTIFACT_ROLE_REGISTRY:-$ROOT/config/role-registry.json}"
PROFILES_DIR="${ARTIFACT_PROFILES_DIR:-$ROOT/config/profiles}"
LOCAL_CREDENTIALS="${ARTIFACT_LOCAL_CREDENTIALS:-}"

usage() {
	cat <<'EOF'
Usage: scripts/refresh_github_pages_reports.sh [--stage <name>]... [--list-stages] [--help] [-- <stage-args>]

Stages:
	quarterly      Refresh quarterly dashboard + milestone scope
	sef            Refresh SEF reports
	delivery-health Refresh sprint health and dev done risk pages
	site-index     Rebuild top-level GitHub Pages index

Preflight:
	--preflight-only Run checks and exit (no stages executed)
	--skip-preflight Skip checks (not recommended)

Examples:
	bash scripts/refresh_github_pages_reports.sh
	bash scripts/refresh_github_pages_reports.sh --stage quarterly --stage site-index
	bash scripts/refresh_github_pages_reports.sh --preflight-only
	bash scripts/refresh_github_pages_reports.sh --stage delivery-health -- --as-of 2026-08-31
EOF
}

contains_stage() {
	local target="$1"
	shift
	local value
	for value in "$@"; do
		if [[ "$value" == "$target" ]]; then
			return 0
		fi
	done
	return 1
}

is_valid_stage() {
	local stage="$1"
	contains_stage "$stage" "${STAGE_ORDER[@]}"
}

requires_jira_context() {
	local stage
	for stage in "$@"; do
		if [[ "$stage" == "quarterly" || "$stage" == "sef" || "$stage" == "delivery-health" ]]; then
			return 0
		fi
	done
	return 1
}

assert_file() {
	local path="$1"
	local label="$2"
	if [[ ! -f "$path" ]]; then
		echo "ERROR: Missing $label: $path" >&2
		return 1
	fi
	return 0
}

assert_dir() {
	local path="$1"
	local label="$2"
	if [[ ! -d "$path" ]]; then
		echo "ERROR: Missing $label: $path" >&2
		return 1
	fi
	return 0
}

run_preflight() {
	local failed=0

	echo "==> Preflight"

	if ! command -v "$PY" >/dev/null 2>&1; then
		echo "ERROR: Python command '$PY' not found. Set PYTHON or install Python." >&2
		failed=1
	else
		echo "  OK: python command '$PY'"
	fi

	if ! assert_file "$ROOT/config/github-pages-site.json" "site config"; then
		failed=1
	else
		echo "  OK: site config"
	fi

	if requires_jira_context "${SELECTED_STAGES[@]}"; then
		if ! assert_file "$PROGRAMME_REGISTRY" "programme registry"; then
			failed=1
		else
			echo "  OK: programme registry"
		fi

		if ! assert_file "$ROLE_REGISTRY" "role registry"; then
			failed=1
		else
			echo "  OK: role registry"
		fi

		if ! assert_dir "$PROFILES_DIR" "profiles directory"; then
			failed=1
		else
			echo "  OK: profiles directory"
			if ! assert_file "$PROFILES_DIR/atlassian.json" "Atlassian profile"; then
				failed=1
			else
				echo "  OK: atlassian profile"
			fi
			if ! assert_file "$PROFILES_DIR/twoa-programme.json" "TWoA programme profile"; then
				failed=1
			else
				echo "  OK: twoa-programme profile"
			fi
		fi

		if [[ -z "$LOCAL_CREDENTIALS" ]]; then
			echo "ERROR: ARTIFACT_LOCAL_CREDENTIALS is not set for Jira-backed stages." >&2
			failed=1
		elif ! assert_file "$LOCAL_CREDENTIALS" "local credentials file"; then
			failed=1
		else
			echo "  OK: local credentials"
		fi
	fi

	if [[ $failed -ne 0 ]]; then
		echo "Preflight failed. Fix the missing prerequisites and retry." >&2
		return 1
	fi

	echo "Preflight passed."
	return 0
}

parse_args() {
	while [[ $# -gt 0 ]]; do
		case "$1" in
			--stage)
				if [[ $# -lt 2 ]]; then
					echo "ERROR: --stage requires a value." >&2
					usage >&2
					exit 2
				fi
				if ! is_valid_stage "$2"; then
					echo "ERROR: Unknown stage '$2'." >&2
					usage >&2
					exit 2
				fi
				SELECTED_STAGES+=("$2")
				shift 2
				;;
			--list-stages)
				printf '%s\n' "${STAGE_ORDER[@]}"
				exit 0
				;;
			--skip-preflight)
				SKIP_PREFLIGHT=1
				shift
				;;
			--preflight-only)
				PREFLIGHT_ONLY=1
				shift
				;;
			--help|-h)
				usage
				exit 0
				;;
			--)
				shift
				PASSTHROUGH_ARGS+=("$@")
				break
				;;
			*)
				PASSTHROUGH_ARGS+=("$1")
				shift
				;;
		esac
	done
}

dedupe_stages() {
	local deduped=()
	local stage
	for stage in "$@"; do
		if ! contains_stage "$stage" "${deduped[@]}"; then
			deduped+=("$stage")
		fi
	done
	printf '%s\n' "${deduped[@]}"
}

run_stage_quarterly() {
	bash scripts/quarterly/refresh_dashboard_pages.sh "${PASSTHROUGH_ARGS[@]}"
	"$PY" scripts/quarterly/milestone_scope_report.py --output docs/quarter/milestone.html
}

run_stage_sef() {
	"$PY" scripts/sef/fetch_sef_project_plan_timeline.py --write
	"$PY" scripts/sef/sef_project_plan_report.py --write
	"$PY" scripts/sef/publish_sef_test_plan_reports.py --write
	"$PY" scripts/sef/build_plan_959_test_cycles_report.py --write-mirror
}

run_stage_delivery_health() {
	bash scripts/refresh_delivery_health_pages.sh "${PASSTHROUGH_ARGS[@]}"
}

run_stage_site_index() {
	"$PY" scripts/publish_github_pages_site_index.py
}

run_stage() {
	local stage="$1"
	case "$stage" in
		quarterly) run_stage_quarterly ;;
		sef) run_stage_sef ;;
		delivery-health) run_stage_delivery_health ;;
		site-index) run_stage_site_index ;;
		*)
			echo "ERROR: Unhandled stage '$stage'." >&2
			return 2
			;;
	esac
}

parse_args "$@"

if [[ ${#SELECTED_STAGES[@]} -eq 0 ]]; then
	SELECTED_STAGES=("${STAGE_ORDER[@]}")
else
	mapfile -t SELECTED_STAGES < <(dedupe_stages "${SELECTED_STAGES[@]}")
fi

echo "Running stages: ${SELECTED_STAGES[*]}"

if [[ $SKIP_PREFLIGHT -eq 1 ]]; then
	echo "==> Preflight"
	echo "  SKIPPED (via --skip-preflight)"
else
	run_preflight
fi

if [[ $PREFLIGHT_ONLY -eq 1 ]]; then
	echo "Preflight-only mode complete."
	exit 0
fi

FAILED_STAGES=()
for stage in "${SELECTED_STAGES[@]}"; do
	echo "==> Stage: $stage"
	if run_stage "$stage"; then
		echo "    OK: $stage"
	else
		echo "    FAIL: $stage"
		FAILED_STAGES+=("$stage")
	fi
done

echo "Stage summary:"
for stage in "${SELECTED_STAGES[@]}"; do
	if contains_stage "$stage" "${FAILED_STAGES[@]}"; then
		echo "  - $stage: FAIL"
	else
		echo "  - $stage: OK"
	fi
done

if [[ ${#FAILED_STAGES[@]} -gt 0 ]]; then
	echo "One or more stages failed: ${FAILED_STAGES[*]}" >&2
	exit 1
fi
