"""仓库物理事实读取助手：YAML 加载、相对路径与服务根发现。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .constants import ROOT, SERVICES_ROOT


def load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("expected YAML mapping")
    return document


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def service_roots() -> list[Path]:
    """仅从服务自身的 contracts/domain.yaml 发现领域服务。"""

    if not SERVICES_ROOT.is_dir():
        return []
    return sorted(
        domain_path.parent.parent
        for domain_path in SERVICES_ROOT.glob("*/contracts/domain.yaml")
        if domain_path.is_file()
    )


def physical_service_roots() -> list[Path]:
    if not SERVICES_ROOT.is_dir():
        return []
    return sorted(path for path in SERVICES_ROOT.iterdir() if path.is_dir())


def domain_service_names() -> set[str]:
    return {service.name for service in service_roots()}


def compose_ownership_violations(
    service_name: str, services: Any
) -> list[str] | None:
    """Return sorted illegal Compose service keys, or None when ownership is valid.

    A service fragment must include its primary workload and may also declare
    one-shot companions named `{service}-migrate*`.
    """
    if not isinstance(services, dict):
        return ["<non-mapping services>"]
    names = set(services)
    if service_name not in names:
        return sorted(names)
    illegal = sorted(
        name
        for name in names
        if name != service_name and not name.startswith(f"{service_name}-migrate")
    )
    return illegal or None
