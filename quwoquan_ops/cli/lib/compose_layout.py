"""从自治服务目录扫描 Compose 片段，不维护第一方 workload 注册表。"""

from __future__ import annotations

from pathlib import Path

from quwoquan_ops.cli.lib.immutable_image_composition import first_party_service_names


def domain_service_compose_files(repo_root: Path) -> list[Path]:
    services_root = repo_root / "quwoquan_service" / "services"
    active_services = set(first_party_service_names(repo_root))
    return sorted(
        path
        for path in services_root.glob("*/deploy/compose.yaml")
        if path.parents[1].name in active_services
    )


def gamma_service_environment_compose_files(repo_root: Path) -> list[Path]:
    """Return autonomous service-owned gamma Compose overlays."""
    services_root = repo_root / "quwoquan_service" / "services"
    active_services = set(first_party_service_names(repo_root))
    return sorted(
        path
        for path in services_root.glob("*/environments/gamma/deploy/compose.yaml")
        if path.parents[3].name in active_services
    )


def gamma_compose_files(repo_root: Path) -> list[Path]:
    files = [
        repo_root
        / "quwoquan_ops"
        / "environments"
        / "compose"
        / "docker-compose.gamma-local.yaml"
    ]
    files.extend(domain_service_compose_files(repo_root))
    files.extend(gamma_service_environment_compose_files(repo_root))
    files.append(
        repo_root
        / "quwoquan_service"
        / "services"
        / "product-ops-service"
        / "deploy"
        / "local-elasticsearch.compose.yaml"
    )
    files.append(
        repo_root
        / "quwoquan_service"
        / "control-plane"
        / "platform-ops"
        / "deploy"
        / "compose.yaml"
    )
    return files


def compose_file_args(files: list[Path]) -> list[str]:
    args: list[str] = []
    for path in files:
        args.extend(("-f", str(path)))
    return args
