#!/usr/bin/env python3
"""Run the full quarterly dashboard refresh pipeline (idempotent)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

STEPS: list[tuple[str, list[str]]] = [
    ("fetch_quarter_goal", ["scripts/quarterly/fetch_quarter_goal.py", "--write"]),
    ("fetch_delivery_milestones", ["scripts/quarterly/fetch_delivery_milestones.py", "--write"]),
    ("fetch_milestone_timeline", ["scripts/quarterly/fetch_milestone_timeline.py", "--write"]),
    (
        "deploy_burn",
        ["scripts/quarterly/deploy_burn.py", "--write", "--update-quarter-status"],
    ),
    ("import_release_plan", ["scripts/quarterly/import_release_plan.py", "--write"]),
    ("allocate_burn", ["scripts/quarterly/allocate_burn.py", "--write"]),
    ("fetch_epic_timeline", ["scripts/quarterly/fetch_epic_timeline.py", "--write"]),
    ("squad_velocity", ["scripts/quarterly/squad_velocity.py", "--write"]),
    (
        "quarter_status",
        [
            "scripts/quarterly/quarter_status.py",
            "--from-burn",
            "--from-goal",
            "--write",
        ],
    ),
    ("publish_dashboard_pages", ["scripts/quarterly/publish_dashboard_pages.py", "--write", "--build"]),
]


def _run_step(python: str, script_args: list[str]) -> None:
    cmd = [python, *script_args]
    print(f"→ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=_REPO_ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the quarterly dashboard refresh pipeline end to end.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List planned steps without executing them.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable (default: current interpreter).",
    )
    args = parser.parse_args()

    if args.dry_run:
        for name, script_args in STEPS:
            print(f"{name}: {args.python} {' '.join(script_args)}")
        return 0

    failed_step: str | None = None
    for name, script_args in STEPS:
        try:
            _run_step(args.python, script_args)
        except subprocess.CalledProcessError as exc:
            failed_step = name
            print(f"Pipeline failed at step '{name}' (exit {exc.returncode}).", file=sys.stderr)
            print(
                "Re-run this command after fixing the failure; completed steps are safe to repeat.",
                file=sys.stderr,
            )
            return exc.returncode or 1

    print("Done. Commit docs/quarter/index.html to update GitHub Pages when changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
