#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

MINIMAL_OVERLAY_PATHS = (
    "agent_ops/deploy/lib",
    "agent_ops/deploy/print_local_port_profile.py",
    "deploy/shared/gamma_curated_media_bundle.json",
    "deploy/shared/local_env_port_manifest.yaml",
    "deploy/shared/reliable_task_module_catalog.yaml",
    "deploy/shared/reliable_task_retention_policy.yaml",
    "releases/config",
    "quwoquan_app/configs/gamma",
    "quwoquan_app/configs/prod",
    "quwoquan_app/scripts/env/print_app_env_dart_defines.py",
    "quwoquan_app/scripts/gamma",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/app_gamma_seed_manifest.json",
    "quwoquan_service/contracts/metadata/user",
    "quwoquan_service/docker-compose.gamma-local.yaml",
    "quwoquan_service/scripts/gamma/verify_gamma_public_gateway_routing.py",
    "quwoquan_service/scripts/media/verify_gamma_curated_media_routes.py",
    "quwoquan_service/services/assistant-service/configs",
    "quwoquan_service/services/chat-service/configs",
    "quwoquan_service/services/content-service/configs",
    "quwoquan_service/services/product-ops-service/configs",
    "quwoquan_service/services/rec-model-service/configs",
    "quwoquan_service/services/tag-service/configs",
    "quwoquan_service/services/user-service/configs",
    "quwoquan_service/services/user-service/internal/infrastructure/migration",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the minimal gamma hosted overlay upload bundle.",
    )
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    missing = [rel for rel in MINIMAL_OVERLAY_PATHS if not (ROOT / rel).exists()]
    if missing:
        raise SystemExit(
            "missing bundle inputs:\n" + "\n".join(f" - {rel}" for rel in missing)
        )

    with tarfile.open(output_path, "w:gz") as archive:
        for rel in MINIMAL_OVERLAY_PATHS:
            archive.add(ROOT / rel, arcname=rel, recursive=True)

    print(f"[gamma-overlay-bundle] wrote {output_path}")
    print(f"[gamma-overlay-bundle] files={len(MINIMAL_OVERLAY_PATHS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
