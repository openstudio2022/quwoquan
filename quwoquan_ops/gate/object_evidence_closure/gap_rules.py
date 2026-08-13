"""维度分层、发布 seam 缺口详情与领域事件显式表态规则。"""
from __future__ import annotations

from pathlib import Path

from .constants import (
    BLINDSPOT,
    EVIDENCE_CLASS_BY_DIMENSION,
    RESULT,
    ROOT,
    SERVICE_ROOT,
    STRUCTURAL,
)
from .models import Gap


def object_contract_dir(source_path: str) -> Path | None:
    """`<domain>/<context>/<object>/object.yaml` → 该对象在仓库里的契约目录。

    对象契约既可能属于 `services/<svc>`，也可能属于 `control-plane/<plane>`
    （platform_ops context 就在后者），两处都必须扫。
    """
    parts = Path(source_path).parts
    if len(parts) < 4:
        return None
    context, object_name = parts[1], parts[2]
    for parent in ("services", "control-plane"):
        for candidate in sorted((SERVICE_ROOT / parent).glob(
            f"*/contracts/{context}/{object_name}"
        )):
            if candidate.is_dir():
                return candidate
    return None


def slice_owner_object(reference: str, known_objects: set[str] | None = None) -> str | None:
    """`<object_id>.projection.<slice>` / `<object_id>.aggregate` → 对象 ID。"""
    reference = reference.strip()
    if known_objects is not None and reference in known_objects:
        return reference
    for separator in (".projection.", ".aggregate", ".entity"):
        if separator in reference:
            owner = reference.split(separator, 1)[0].strip()
            return owner or None
    return None

def publication_gap_detail(key: str, packet: dict | None) -> str:
    """给发布 seam 的三条互斥缺口补上「哪张存储」，让缺口可直接关闭。

    判定不在这里重算：`publicationStores` / `unannotatedStores` 由 loader 从对象自己的
    `storage.yaml` 的 `publication_role` 派生，`outbox` 证据是「存储名 → 写入位置」绑定。
    """
    if packet is None:
        return ""
    if key == "contract.storage_publication_unannotated":
        stores = packet.get("unannotatedStores") or []
        return (
            "存储未标注 publication_role，无法判别哪张是发布 seam："
            f"{', '.join(stores)}；标注后本缺口自动关闭"
        )
    if key == "contract.storage_publication_undeclared":
        return (
            "标注齐全但没有任何存储被标注为 transactional_outbox / "
            "transactional_event_log，与它声明的投递型领域事件相互否定"
        )
    if key == "implementation.outbox":
        declared = packet.get("publicationStores") or []
        unproven = [
            store
            for store in declared
            if store not in bound_storages(packet, "service", "outbox")
        ]
        return (
            "声明了发布 seam 但服务内未观测到持有事务句柄的函数对它写入："
            f"{', '.join(unproven or declared)}"
        )
    if key == "implementation.publication_delivery":
        declared = packet.get("deliveryStores") or []
        undelivered = [
            store
            for store in declared
            if store not in bound_storages(packet, "", "publicationDelivery")
        ]
        return (
            "发件箱有事务性追加但没有任何投递实现（没有代码读取它并推进进度）："
            f"{', '.join(undelivered or declared)}"
        )
    if key == "contract.storage_declaration_missing":
        return (
            "对象实现树里事务性写入了全仓无人声明的关系："
            f"{', '.join(packet.get('undeclaredStorageWrites') or [])}"
        )
    if key == "blindspot.publication_write_tracking":
        return (
            "关系名在服务里被绑定过，但写入发生在 Go AST 跟不动的位置（构造参数注入的"
            "句柄 / 调用方传入的事务上下文）："
            f"{', '.join(packet.get('unresolvedPublicationWrites') or [])}"
        )
    if key == "blindspot.publication_delivery_tracking":
        return (
            "投递实现在扫描范围之外（表名参数化地交给共享 dispatcher）："
            f"{', '.join(packet.get('unresolvedPublicationDelivery') or [])}"
        )
    if key == "blindspot.python_store_invisible":
        return "实现树含 Python 生产代码，Go AST 对它完全不可见"
    return ""


def bound_storages(packet: dict, producer: str, field: str) -> set[str]:
    evidence = packet.get(producer) or {} if producer else packet
    return {
        artifact.get("storage")
        for artifact in evidence.get(field) or []
        if artifact.get("storage")
    }

def domain_event_declaration_gaps(
    object_id: str,
    kind: str,
    stage: str,
    entry: dict,
) -> list[Gap]:
    """有命令的状态所有者（聚合根 / 长流程编排器）必须显式表态是否发布领域事件。

    `implementation.outbox` 的必需性来自这份声明，所以「没有 events.yaml」不能等价于
    「声明不发事件」：那会让发件箱要求被静默跳过。写下 `events: []` 是显式否认，可以；
    连文件都不存在则报缺口，由契约 owner 表态。
    """
    contract_dir = object_contract_dir(str(entry.get("sourcePath") or ""))
    if contract_dir is None:
        return [
            Gap(object_id, kind, stage, "contract.domain_events_undeclared",
                f"无法定位契约目录（sourcePath={entry.get('sourcePath')!r}）")
        ]
    if (contract_dir / "events.yaml").is_file():
        return []
    return [
        Gap(
            object_id,
            kind,
            stage,
            "contract.domain_events_undeclared",
            f"{contract_dir.relative_to(ROOT)} 没有 events.yaml：既没声明领域事件也没写下 "
            "`events: []`，会静默跳过 implementation.outbox 要求",
        )
    ]

def evidence_class(dimension: str) -> str:
    """维度的证据层。未登记的维度按结构性处理并在主流程里 BLOCK：新维度必须显式分层，
    默认落进「不阻断」那侧会让新缺口悄悄消失。"""
    return EVIDENCE_CLASS_BY_DIMENSION.get(dimension, STRUCTURAL)


def partition_by_evidence_class(gaps: list[Gap]) -> dict[str, list[Gap]]:
    partitions: dict[str, list[Gap]] = {STRUCTURAL: [], RESULT: [], BLINDSPOT: []}
    for gap in gaps:
        partitions[evidence_class(gap.dimension)].append(gap)
    return partitions


def unclassified_dimensions(gaps: list[Gap]) -> list[str]:
    return sorted(
        {
            gap.dimension
            for gap in gaps
            if gap.dimension not in EVIDENCE_CLASS_BY_DIMENSION
        }
    )
