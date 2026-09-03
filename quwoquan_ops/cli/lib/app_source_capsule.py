"""Canonical App source roots shared by package and workspace launch projection."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def app_source_capsule_roots() -> tuple[str, ...]:
    services_root = ROOT / "quwoquan_service/services"
    environment_roots = [
        path.relative_to(ROOT).as_posix()
        for path in sorted(services_root.glob("*/environments"))
        if path.is_dir()
    ]
    platform_environments = (
        ROOT / "quwoquan_service/control-plane/platform-ops/environments"
    )
    if platform_environments.is_dir():
        environment_roots.append(platform_environments.relative_to(ROOT).as_posix())
    return (
        "quwoquan_app",
        "quwoquan_ops",
        "quwoquan_service/contracts/metadata",
        "quwoquan_service/contracts/runtime_errors/packages/dart/quwoquan_runtime_errors",
        "quwoquan_service/services",
        "quwoquan_service/control-plane/platform-ops",
        "quwoquan_service/cmd/service-core/composition.yaml",
        *environment_roots,
    )
