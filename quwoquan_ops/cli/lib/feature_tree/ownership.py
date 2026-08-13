"""工程归属解析与领域服务归属校验。"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from . import context
from .nodes import Node, node_for_spec
from .parsing import app_journey_engineering_roots, engineering_claims, engineering_roots
from .patterns import APP_TEST_LAYERS


def domain_service_roots() -> list[Path]:
    """仅从服务自身的 contracts/domain.yaml 发现领域服务。"""

    services_root = context.REPO_ROOT / "quwoquan_service" / "services"
    if not services_root.is_dir():
        return []
    return sorted(
        domain_file.parent.parent
        for domain_file in services_root.glob("*/contracts/domain.yaml")
        if domain_file.is_file()
    )


def undeclared_service_roots() -> list[Path]:
    services_root = context.REPO_ROOT / "quwoquan_service" / "services"
    if not services_root.is_dir():
        return []
    return sorted(
        service
        for service in services_root.iterdir()
        if service.is_dir() and not (service / "contracts" / "domain.yaml").is_file()
    )


def validate_domain_service_ownership(nodes: Iterable[Node]) -> list[str]:
    """验证领域服务根与共享 metadata 的直接 L1 归属，无服务名册。"""

    errors: list[str] = []
    l1_nodes = [node for node in nodes if node.level == 1]
    claims = {node: engineering_claims(node) for node in l1_nodes}
    for service in undeclared_service_roots():
        errors.append(
            f"{service.relative_to(context.REPO_ROOT)}: 服务根必须声明 contracts/domain.yaml"
        )
    for service in domain_service_roots():
        root = service.relative_to(context.REPO_ROOT).as_posix()
        direct_owners = sorted(
            node.node_id
            for node, node_claims in claims.items()
            if ("Service", root) in node_claims
        )
        if len(direct_owners) != 1:
            errors.append(
                f"{root}: 必须由唯一非宽泛 fallback 的 L1 Service 根直接认领；"
                f"当前={direct_owners or '无'}"
            )
            continue
        resolved = owners_for_path(service, l1_nodes)
        if [node.node_id for node in resolved] != direct_owners:
            errors.append(
                f"{root}: 直接 L1 owner {direct_owners[0]} 与路径解析结果 "
                f"{[node.node_id for node in resolved]} 不一致"
            )

    shared_metadata = (
        context.REPO_ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared"
    )
    if shared_metadata.is_dir():
        shared_root = shared_metadata.relative_to(context.REPO_ROOT).as_posix()
        shared_owners = sorted(
            node.node_id
            for node, node_claims in claims.items()
            if ("Metadata", shared_root) in node_claims
        )
        if shared_owners != ["runtime"]:
            errors.append(
                f"{shared_root}: 必须由 runtime L1 唯一直接拥有；"
                f"当前={shared_owners or '无'}"
            )
        elif [
            node.node_id for node in owners_for_path(shared_metadata, l1_nodes)
        ] != ["runtime"]:
            errors.append(f"{shared_root}: runtime 直接归属未成为路径解析 owner")
    return errors


def owners_for_path(target: Path, nodes: Iterable[Node]) -> list[Node]:
    try:
        rel = target.resolve().relative_to(context.REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return []
    matches: list[tuple[int, Node]] = []
    for node in nodes:
        for root in engineering_roots(node):
            root = root.rstrip("/")
            if rel == root or rel.startswith(root + "/"):
                matches.append((len(root), node))
    if not matches:
        return []
    longest = max(length for length, _ in matches)
    return sorted({node for length, node in matches if length == longest}, key=lambda item: item.node_id)


def canonical_app_test_owner_target(target: Path) -> Path | None:
    """把对象化 App 测试投影到同 domain 的 production engineering root。

    ``runtime`` 对 ``quwoquan_app`` 的项目级声明只拥有构建与平台壳，不能把
    ``test/<layer>/<domain>/<context>/<object>`` 下的业务测试吞成 runtime owner。
    Journey 不按 domain 投影，只接受 ``owners_for_app_test_path`` 解析出的
    精确 L1 Journey root；support 不属于三层对象测试，继续按普通工程路径处理。
    """
    try:
        parts = target.resolve().relative_to(context.REPO_ROOT.resolve()).parts
    except ValueError:
        return None
    if (
        len(parts) < 5
        or parts[:2] != ("quwoquan_app", "test")
        or parts[2] not in APP_TEST_LAYERS
        or parts[3] == "journeys"
    ):
        return None
    if len(parts) >= 7 and parts[3] == "service":
        return context.REPO_ROOT / "quwoquan_app" / "lib" / Path(*parts[3:7])
    return context.REPO_ROOT / "quwoquan_app" / "lib" / parts[3]


def owners_for_app_test_path(target: Path, nodes: Iterable[Node]) -> list[Node] | None:
    try:
        parts = target.resolve().relative_to(context.REPO_ROOT.resolve()).parts
    except ValueError:
        return None
    if (
        len(parts) >= 4
        and parts[:2] == ("quwoquan_app", "test")
        and parts[2] in APP_TEST_LAYERS
        and parts[3] == "journeys"
    ):
        if len(parts) < 6:
            return []
        journey_root = Path(*parts[:5]).as_posix()
        # Resolve the declared Journey root, not the individual test file. This
        # preserves duplicate-owner detection and prevents a project-level App
        # or runtime root from becoming an implicit fallback.
        root_owners = owners_for_path(context.REPO_ROOT / journey_root, nodes)
        return [
            owner
            for owner in root_owners
            if journey_root in app_journey_engineering_roots(owner)
        ]
    projected = canonical_app_test_owner_target(target)
    if projected is None:
        return None
    projected_rel = projected.resolve().relative_to(context.REPO_ROOT.resolve()).as_posix()
    owners = owners_for_path(projected, nodes)
    return [
        owner
        for owner in owners
        if any(
            root.startswith("quwoquan_app/lib/")
            and (projected_rel == root or projected_rel.startswith(root + "/"))
            for root in engineering_roots(owner)
        )
    ]


def resolve_target(raw: str, nodes: list[Node]) -> Node:
    target = Path(raw)
    if not target.is_absolute():
        target = context.REPO_ROOT / target
    if target.is_dir() and (target / "spec.md").is_file():
        target = target / "spec.md"
    direct = node_for_spec(target, nodes)
    if direct:
        return direct
    app_test_owners = owners_for_app_test_path(target, nodes)
    owners = (
        app_test_owners
        if app_test_owners is not None
        else owners_for_path(target, nodes)
    )
    if len(owners) == 1:
        return owners[0]
    if not owners:
        raise ValueError(f"GATE_BLOCK: {raw} 未被任何 L1 工程归属认领")
    raise ValueError(f"GATE_BLOCK: {raw} 被多个 L1 同优先级认领：{', '.join(item.node_id for item in owners)}")
