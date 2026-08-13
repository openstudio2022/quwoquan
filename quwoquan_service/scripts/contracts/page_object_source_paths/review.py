"""伴生风险校验：object-presentation participant 漂移与页面扫描集缺口。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from .dart_analysis import (
    _consumed_public_behavior_symbols,
    _is_application_public_path,
    _looks_like_object_presentation,
    _page_library_evidence,
)
from .models import ReviewFinding


def object_presentation_participant_findings(
    pages: Sequence[dict],
    shape_of: Callable[[str], tuple[str, str, str, str] | None],
    *,
    app_root: Path | None = None,
) -> list[ReviewFinding]:
    """审计所有 object-presentation 页面，而非只看 ``len(object_ids) >= 2``。

    routed 页面自身拥有独立路由，因此 canonical physical owner 必须是 participant；
    embedded/component/helper 只是父页面中的局部装配，允许物理放在某对象的
    presentation 下但不把该对象伪造成 participant。无论 kind，页面 library/part
    中实际引用的跨对象 ``application/public`` behavioral port/provider 才是可证明
    的对象消费，必须出现在 ``object_ids``。纯 typed value、route/navigation
    context、generated、runtime/design-system 不因 import 或路径 token 被误判。
    """

    findings: list[ReviewFinding] = []
    for page in pages:
        source_path = str(page["source_path"]).strip()
        path_parts = Path(source_path).parts
        looks_like_object_presentation = _looks_like_object_presentation(path_parts)
        shape = shape_of(source_path)
        if shape is None and not looks_like_object_presentation:
            continue

        object_ids = page.get("object_ids")
        object_id_values = object_ids if isinstance(object_ids, list) else []
        normalized_object_ids = tuple(
            str(item).strip()
            for item in object_id_values
            if isinstance(item, str)
        )
        participant_set_is_valid = (
            isinstance(object_ids, list)
            and len(normalized_object_ids) == len(object_id_values)
            and all(normalized_object_ids)
            and len(set(normalized_object_ids)) == len(normalized_object_ids)
        )

        physical_owner: str | None = None
        reasons: list[str] = []
        if shape is None:
            reasons.append(
                "canonical service-root presentation 无法从 ContractGraph roster "
                "反推 physical owner"
            )
        else:
            domain, context, object_name, layer = shape
            physical_owner = f"{domain}.{object_name}"
            if layer != "presentation" or not looks_like_object_presentation:
                reasons.append(
                    "source_path 与派生层不一致，不能证明 canonical 单对象 "
                    f"presentation（派生 {domain}.{context}.{object_name}/{layer}）"
                )
            elif page.get("page_kind") == "routed" and physical_owner not in normalized_object_ids:
                reasons.append(
                    f"派生 physical owner {physical_owner} 未出现在 object_ids，"
                    "routed 页面参与集合与物理归属漂移"
                )

        if not participant_set_is_valid:
            reasons.append("object_ids 含空值、非字符串或重复 participant，集合发生漂移")

        missing_public_dependencies: dict[str, list[str]] = {}
        if app_root is not None and shape is not None and layer == "presentation":
            imported_paths, consumed_identifiers = _page_library_evidence(
                app_root,
                source_path,
            )
            for imported_path in imported_paths:
                if not _is_application_public_path(imported_path):
                    continue
                imported_shape = shape_of(imported_path)
                if imported_shape is None or imported_shape[3] != "application":
                    continue
                behavior_symbols = _consumed_public_behavior_symbols(
                    app_root,
                    imported_path,
                    consumed_identifiers,
                )
                if not behavior_symbols:
                    continue
                imported_object_id = f"{imported_shape[0]}.{imported_shape[2]}"
                if imported_object_id == physical_owner:
                    continue
                if imported_object_id in normalized_object_ids:
                    continue
                missing_public_dependencies.setdefault(imported_object_id, []).append(
                    f"{imported_path} [{', '.join(behavior_symbols)}]"
                )
        if missing_public_dependencies:
            evidence = "; ".join(
                f"{object_id} <- {', '.join(sorted(paths))}"
                for object_id, paths in sorted(missing_public_dependencies.items())
            )
            reasons.append(
                "页面 library/part 直接消费跨对象 application/public behavioral "
                "port/provider，"
                f"participant 未声明：{evidence}"
            )

        if not reasons:
            continue

        findings.append(
            ReviewFinding(
                kind="object_presentation_participant_drift",
                page_id=str(page["page_id"]).strip(),
                source_path=source_path,
                detail=(
                    f"声明 {len(object_id_values)} 个 object_ids "
                    f"({', '.join(str(item) for item in object_id_values)})，"
                    f"但{'；'.join(reasons)}；需人工修正 owner/participant 契约，"
                    "不能靠页面 kind、participant 计数或物理目录猜测消红"
                ),
            )
        )
    return findings


def page_scan_set_findings(
    pages: Sequence[dict],
    disk_scan_paths: frozenset[str] | None,
) -> list[ReviewFinding]:
    """``source_path`` 已修正但不在页面扫描集内时如实报告。

    ``verify_page_object_contract.py`` 用 ``matrix_disk_scan_paths`` 判定「磁盘页面
    必须由 metadata 唯一拥有」。本工具不复制那套 Dart 页面识别规则，只消费其
    动态扫描结果，并保证 source 已修正但扫描集未认领的缺口不会无声存在。
    """

    if disk_scan_paths is None:
        return []
    findings: list[ReviewFinding] = []
    for page in pages:
        source_path = str(page["source_path"]).strip()
        if source_path in disk_scan_paths:
            continue
        findings.append(
            ReviewFinding(
                kind="outside_page_scan_set",
                page_id=str(page["page_id"]).strip(),
                source_path=source_path,
                detail=(
                    "已搬出 page_disk_scan_paths.matrix_disk_scan_paths 的扫描范围，"
                    "verify_page_object_contract 会报「canonical source 不在页面扫描集」；"
                    "需要页面质量门禁 owner 扩展扫描规则，本工具不改门禁"
                ),
            )
        )
    return findings
