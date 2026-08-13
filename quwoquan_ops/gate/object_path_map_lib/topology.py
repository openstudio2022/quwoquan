"""service/context 物理拓扑派生。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml

from .constants import ROOT, SERVICE_ROOT_GLOBS


def repo_relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def iter_files(root: Path, suffixes: Iterable[str]) -> list[Path]:
    allowed = frozenset(suffixes)
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in allowed and not path.is_symlink()
    )


def is_cloud_test_file(path: Path) -> bool:
    name = path.name
    return (
        name.endswith("_test.go")
        or name.startswith("test_")
        or "__local_contract_test" in name
        or "__api_integration_test" in name
    )


def service_domains() -> dict[str, tuple[str, str]]:
    """扫描 ``contracts/domain.yaml``，返回 service 相对根 → ``(owner, domain)``。"""
    mapping: dict[str, tuple[str, str]] = {}
    for pattern in SERVICE_ROOT_GLOBS:
        for service in sorted(ROOT.glob(pattern)):
            domain_path = service / "contracts" / "domain.yaml"
            if not domain_path.is_file():
                continue
            try:
                document = yaml.safe_load(domain_path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            domain = str(document.get("domain") or "").strip()
            if domain:
                mapping[repo_relative(service)] = (service.name, domain)
    return mapping


def app_service_segment(service_name: str) -> str:
    """把云侧物理 service 目录名规范为 Dart 路径段。"""
    return service_name.replace("-", "_")


@lru_cache(maxsize=1)
def service_context_segments() -> dict[tuple[str, str], str]:
    """从 service contracts 物理树派生 ``(domain, context) → app service``。

    映射不接受人工清单：service → domain 只读 ``contracts/domain.yaml``，context
    只读同一 service 的 ``contracts/<context>/`` 目录。重复 owner 是边界冲突，
    必须在搬迁前阻断，不能靠遍历顺序择一。
    """
    mapping: dict[tuple[str, str], str] = {}
    for service_relative, (owner, domain) in sorted(service_domains().items()):
        contracts = ROOT / service_relative / "contracts"
        for context_root in sorted(contracts.iterdir()):
            if not context_root.is_dir() or context_root.name.startswith("_"):
                continue
            # context 目录必须至少拥有一个 canonical object contract；辅助目录不构成
            # App service 归属。
            if not any(
                child.is_dir() and (child / "object.yaml").is_file()
                for child in context_root.iterdir()
            ):
                continue
            key = (domain, context_root.name)
            segment = app_service_segment(owner)
            previous = mapping.get(key)
            if previous is not None and previous != segment:
                raise ValueError(
                    f"{domain}.{context_root.name} 同时由 {previous} 与 {segment} 拥有"
                )
            mapping[key] = segment
    return dict(sorted(mapping.items()))


@lru_cache(maxsize=1)
def context_to_service() -> dict[str, str]:
    """返回全仓唯一的 ``context → app service`` 映射，并阻断跨域重名。"""
    mapping: dict[str, str] = {}
    owners: dict[str, str] = {}
    for (domain, context), service in service_context_segments().items():
        previous = mapping.get(context)
        if previous is not None and previous != service:
            raise ValueError(
                f"context {context!r} 同时属于 {owners[context]}/{previous} "
                f"与 {domain}/{service}"
            )
        mapping[context] = service
        owners[context] = domain
    return dict(sorted(mapping.items()))


def app_service_for_context(domain: str, context: str) -> str:
    """返回对象 context 的 canonical App service 路径段。"""
    key = (domain, context)
    try:
        return service_context_segments()[key]
    except KeyError as error:
        raise ValueError(
            f"{domain}.{context} 没有由 service contracts 物理树派生出的 owner"
        ) from error
