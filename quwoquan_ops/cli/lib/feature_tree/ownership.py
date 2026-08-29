"""工程归属解析与领域服务归属校验。"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from . import context
from .nodes import Node, node_for_spec
from .parsing import (
    app_journey_engineering_roots,
    engineering_claims,
    engineering_roots,
    headings,
)
from .patterns import APP_TEST_LAYERS, PATH_RE

_DEC_BLOCK_RE = re.compile(
    r'<a\s+id=["\'](dec-\d{3,})["\']\s*></a>([\s\S]*?)'
    r'(?=<a\s+id=["\']dec-\d{3,}["\']\s*></a>|\Z)',
    re.IGNORECASE,
)
_STORY_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#]+/spec\.md)(?:#[^)]+)?\)")
_REQ_RE = re.compile(r"\bREQ-\d{3,}\b")
_ACCEPTANCE_RE = re.compile(r"\b(?:UAT|DOM|SIT|GWT)-\d{3,}\b")


@dataclass(frozen=True)
class DesignOwnership:
    """L2 DEC 对工程根和唯一 Story 的精确归属。"""

    l2: Node
    anchor: str
    roots: tuple[str, ...]
    story: Node
    requirement_anchors: tuple[str, ...]
    acceptance_anchors: tuple[str, ...]


@dataclass(frozen=True)
class TargetResolution:
    """owner resolver 的单一结果，供开发与 Review 共用。"""

    node: Node
    l1_owner: Node | None
    target: Path
    ownership_target: Path
    design_ownership: DesignOwnership | None = None


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
    # 保留 domain 后的完整对象路径，否则
    # ``test/<layer>/design_system/pageflip/**`` 会被折叠为
    # ``lib/design_system``，L2 DEC 就无法和 production path 共用同一 owner。
    return context.REPO_ROOT / "quwoquan_app" / "lib" / Path(*parts[3:])


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


def _field(block: str, label: str) -> str:
    match = re.search(
        rf"^-\s+{re.escape(label)}：(.+?)\s*$",
        block,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def _design_ownerships(
    nodes: Iterable[Node],
    l1_owner: Node | None = None,
) -> list[DesignOwnership]:
    """从 L2 design 直接解析 DEC 工程归属，不维护第二份 registry。"""

    result: list[DesignOwnership] = []
    all_nodes = list(nodes)
    for l2 in (
        item
        for item in all_nodes
        if item.level == 2
        and item.design.is_file()
        and (l1_owner is None or item.directory.parent == l1_owner.directory)
    ):
        text = l2.design.read_text(encoding="utf-8")
        for match in _DEC_BLOCK_RE.finditer(text):
            anchor = match.group(1).lower()
            block = match.group(2)
            root_field = _field(block, "适用工程根")
            if not root_field:
                continue
            roots = tuple(sorted({root.rstrip("/") for root in PATH_RE.findall(root_field)}))
            if not roots:
                raise ValueError(
                    f"GATE_BLOCK: {l2.design.relative_to(context.REPO_ROOT)}#{anchor} "
                    "声明了适用工程根，但未包含 canonical 仓库路径"
                )

            story_nodes: set[Node] = set()
            for raw_link in _STORY_LINK_RE.findall(_field(block, "影响 Story")):
                story = node_for_spec((l2.directory / raw_link).resolve(), all_nodes)
                if (
                    story is not None
                    and story.level == 3
                    and story.directory.parent == l2.directory
                ):
                    story_nodes.add(story)
            if len(story_nodes) != 1:
                story_ids = sorted(item.node_id for item in story_nodes)
                raise ValueError(
                    f"GATE_BLOCK: {l2.design.relative_to(context.REPO_ROOT)}#{anchor} "
                    "的适用工程根必须指向唯一直属 Story；"
                    f"当前={story_ids or '无'}"
                )
            story = next(iter(story_nodes))
            requirement_anchors = tuple(
                item.lower() for item in _REQ_RE.findall(_field(block, "关联要求"))
            )
            acceptance_anchors = tuple(
                item.lower()
                for item in _ACCEPTANCE_RE.findall(_field(block, "关联验收"))
            )
            story_anchors = headings(story.spec)
            missing = sorted(
                (set(requirement_anchors) | set(acceptance_anchors)) - story_anchors
            )
            if missing:
                raise ValueError(
                    f"GATE_BLOCK: {l2.design.relative_to(context.REPO_ROOT)}#{anchor} "
                    f"引用了 {story.rel} 不存在的锚点：{', '.join(missing)}"
                )
            result.append(
                DesignOwnership(
                    l2=l2,
                    anchor=anchor,
                    roots=roots,
                    story=story,
                    requirement_anchors=requirement_anchors,
                    acceptance_anchors=acceptance_anchors,
                )
            )
    return result


def _design_owner_for_path(
    target: Path,
    l1_owner: Node,
    nodes: list[Node],
) -> DesignOwnership | None:
    try:
        rel = target.resolve().relative_to(context.REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return None
    matches: list[tuple[int, DesignOwnership]] = []
    for owner in _design_ownerships(nodes, l1_owner):
        for root in owner.roots:
            if rel == root or rel.startswith(root + "/"):
                matches.append((len(root), owner))
    if not matches:
        return None
    longest = max(length for length, _ in matches)
    owners = sorted(
        {owner for length, owner in matches if length == longest},
        key=lambda item: (item.l2.node_id, item.anchor),
    )
    if len(owners) != 1:
        labels = ", ".join(f"{item.l2.node_id}#{item.anchor}" for item in owners)
        raise ValueError(
            f"GATE_BLOCK: {rel} 被多个 L2 DEC 同优先级认领：{labels}"
        )
    return owners[0]


def resolve_target_details(raw: str | Path, nodes: list[Node]) -> TargetResolution:
    """解析唯一 L1 后再按 L2 DEC 工程根收窄到唯一 Story。"""

    raw_path = str(raw).partition("#")[0]
    target = Path(raw_path)
    if not target.is_absolute():
        target = context.REPO_ROOT / target
    if target.is_dir() and (target / "spec.md").is_file():
        target = target / "spec.md"
    if target.name == "design.md" and (target.parent / "spec.md").is_file():
        target = target.parent / "spec.md"
    direct = node_for_spec(target, nodes)
    if direct:
        l1_owner = next(
            (
                item
                for item in nodes
                if item.level == 1
                and (
                    direct == item
                    or direct.directory.resolve().is_relative_to(item.directory.resolve())
                )
            ),
            None,
        )
        return TargetResolution(
            node=direct,
            l1_owner=l1_owner,
            target=target,
            ownership_target=target,
        )
    app_test_owners = owners_for_app_test_path(target, nodes)
    projected = canonical_app_test_owner_target(target)
    ownership_target = projected if projected is not None else target
    owners = (
        app_test_owners
        if app_test_owners is not None
        else owners_for_path(target, nodes)
    )
    if len(owners) == 1:
        l1_owner = owners[0]
        design_owner = _design_owner_for_path(ownership_target, l1_owner, nodes)
        return TargetResolution(
            node=design_owner.story if design_owner else l1_owner,
            l1_owner=l1_owner,
            target=target,
            ownership_target=ownership_target,
            design_ownership=design_owner,
        )
    if not owners:
        raise ValueError(f"GATE_BLOCK: {raw} 未被任何 L1 工程归属认领")
    raise ValueError(
        f"GATE_BLOCK: {raw} 被多个 L1 同优先级认领："
        f"{', '.join(item.node_id for item in owners)}"
    )


def resolve_target(raw: str | Path, nodes: list[Node]) -> Node:
    """兼容旧调用方的 Node 返回值，实际语义由共享 resolver 提供。"""

    return resolve_target_details(raw, nodes).node
