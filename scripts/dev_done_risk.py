#!/usr/bin/env python3
"""Generate TWoA EPCE Dev Done milestone risk HTML report via Artifact core."""

from __future__ import annotations

import sys
from pathlib import Path

from artifact import AtlassianAdapter
from artifact.delivery_health.dev_done_engine import parse_dev_done_args, run_dev_done_risk_report
from artifact.delivery_health.gateway import ArtifactJiraGateway

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from extensions.twoa_programme.delivery_health import load_delivery_health_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = parse_dev_done_args(argv)
    config = load_delivery_health_config()
    if config.dev_done_risk is None:
        raise SystemExit("config/delivery-health.json has no devDoneRisk section.")

    profiles_dir = Path(
        __import__("os").environ.get("ARTIFACT_PROFILES_DIR", str(_REPO_ROOT / "config" / "profiles"))
    )
    profile_name = "atlassian"
    if argv:
        for i, token in enumerate(argv):
            if token == "--profile" and i + 1 < len(argv):
                profile_name = argv[i + 1]

    adapter = AtlassianAdapter.from_profile(profile_name, profiles_dir=str(profiles_dir))
    gateway = ArtifactJiraGateway(adapter.http)

    if args.output_dir == Path("reports"):
        args.output_dir = _REPO_ROOT / "output" / "dev_done_risk"

    path = run_dev_done_risk_report(config, gateway, args)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
