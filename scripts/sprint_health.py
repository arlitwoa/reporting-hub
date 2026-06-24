#!/usr/bin/env python3
"""Generate TWoA EPCE Sprint Health HTML reports via Artifact core delivery_health engine."""

from __future__ import annotations

import sys
from pathlib import Path

from artifact import AtlassianAdapter
from artifact.delivery_health.gateway import ArtifactJiraGateway
from artifact.delivery_health.sprint_engine import parse_args, run_sprint_health_reports

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from extensions.twoa_programme.delivery_health import load_delivery_health_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_delivery_health_config()

    profiles_dir = Path(
        __import__("os").environ.get("ARTIFACT_PROFILES_DIR", str(_REPO_ROOT / "config" / "profiles"))
    )
    profile_name = "atlassian"
    if argv:
        for i, token in enumerate(argv):
            if token == "--profile" and i + 1 < len(argv):
                profile_name = argv[i + 1]

    if args.squad:
        unknown_slugs = set(args.squad) - set(config.squads)
        if unknown_slugs:
            raise SystemExit(f"Unknown squad slug(s): {sorted(unknown_slugs)}")

    adapter = AtlassianAdapter.from_profile(profile_name, profiles_dir=str(profiles_dir))
    gateway = ArtifactJiraGateway(adapter.http)

    if args.output_dir == Path("reports"):
        args.output_dir = _REPO_ROOT / "output" / "sprint_health"

    written = run_sprint_health_reports(config, gateway, args)
    print("\nWrote:")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
