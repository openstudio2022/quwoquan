"""Canonical App source roots shared by package and workspace launch projection."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def app_source_capsule_roots() -> tuple[str, ...]:
    services_root = ROOT / "quwoquan_service/services"
    service_runtime_roots = [
        path.relative_to(ROOT).as_posix()
        for service_root in sorted(services_root.iterdir())
        if service_root.is_dir()
        for path in (
            service_root / "contracts",
            service_root / "internal",
            service_root / "cmd",
            service_root / "config",
            service_root / "deploy",
            service_root / "environments",
        )
        if path.is_dir()
    ]
    platform_root = ROOT / "quwoquan_service/control-plane/platform-ops"
    platform_runtime_roots = [
        path.relative_to(ROOT).as_posix()
        for path in (
            platform_root / "contracts",
            platform_root / "internal",
            platform_root / "cmd",
            platform_root / "config",
            platform_root / "deploy",
            platform_root / "environments",
        )
        if path.is_dir()
    ]
    return (
        "quwoquan_app",
        "quwoquan_ops",
        "quwoquan_service/contracts/metadata",
        "quwoquan_service/contracts/runtime_errors/packages/dart/quwoquan_runtime_errors",
        "quwoquan_service/cmd/service-core/composition.yaml",
        "quwoquan_service/runtime",
        *service_runtime_roots,
        *platform_runtime_roots,
    )
