#!/usr/bin/env python3
"""校验 D0 业务对象商用架构设计冻结合同。"""

from __future__ import annotations

import sys
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]

APP_ROOT_SPEC = "specs/feature-tree/spec.md"
APP_ROOT_DESIGN = "specs/feature-tree/design.md"
APP_ROOT_ACCEPTANCE = "specs/feature-tree/acceptance.yaml"
ARCH_SPEC = (
    "specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md"
)
ARCH_DESIGN = (
    "specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md"
)
ARCH_ACCEPTANCE = (
    "specs/feature-tree/runtime/system-architecture-and-engineering-guide/"
    "acceptance.yaml"
)
JOURNEY_REGISTRY = "specs/feature-tree/journey_scenario_registry.yaml"
METADATA_README = "quwoquan_service/contracts/metadata/README.md"
METADATA_DESIGN = "quwoquan_service/contracts/metadata/DESIGN.md"
CHANGE_RECORD = (
    "specs/changelog/"
    "CR-20260712-084-business-object-commercial-architecture-freeze.yaml"
)
LOCAL_CONTRACT_TEST = (
    "quwoquan_ops/tests/local_contract/"
    "test_business_object_design_freeze__local_contract_test.py"
)

REQUIRED_JOURNEYS = {
    "identity-entry-and-continuation",
    "content-discovery-to-consumption",
    "cross-domain-search",
    "app-root-navigation-safety",
    "message-social-connection",
    "circle-entity-group-collaboration",
    "assistant-omnipresent-private-assistant",
    "external-acquisition-and-deeplink",
    "intersection-action-to-companionship",
    "profile-private-activity-history",
}

COMMERCIAL_UAT_SCENARIOS = {
    "identity-entry-persona-continuation",
    "content-feed-open-detail",
    "global-search-query-and-filter",
    "global-route-edge-pop-contract",
    "message-direct-and-greeting-upgrade",
    "circle-entity-group-handoff",
    "assistant-context-grounded-answering",
    "outbound-object-share-distribution",
    "intersection-action-deepening-on-object",
    "profile-share-interaction-history",
}


def to_snake_case(value: str) -> str:
    value = value.strip()
    if value and value.upper() == value:
        return value.lower()
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()

REQUIRED_TOKENS: dict[str, tuple[str, ...]] = {
    APP_ROOT_SPEC: (
        "商用对象基线",
        "Object Application Facade",
        "Data Ports",
        "Query Slice",
        "local_contract / api_integration / user_acceptance",
        "dual-read/dual-write",
    ),
    APP_ROOT_DESIGN: (
        "D0 业务对象架构冻结",
        "ActorContext.accountId",
        "Object Application Facade",
        "Object Data Ports",
        "统一 URL",
        "页面与体验",
        "零兼容迁移",
    ),
    ARCH_SPEC: (
        "D0 业务对象边界",
        "F1 唯一 ContractGraph compiler",
        "G1 metadata/codegen",
        "content-service",
        "Post + Report",
    ),
    ARCH_DESIGN: (
        "D0/F1/G1 设计",
        "OBJECT-REGISTRY-011",
        "CHILD-ACCESS-012",
        "qwq-contract validate/generate/check/coverage",
        "AggregateStore",
        "named Reader",
        "PostModerationCase",
        "单事务",
    ),
    METADATA_README: (
        "_schemas/",
        "business_object_map.yaml",
        "entity.yaml.object_kind",
        "唯一 ContractGraph",
        "Object Facade",
        "owned entity/value object 只经 aggregate root",
        "Actor 归因",
        "qwq-contract coverage --format json",
    ),
    METADATA_DESIGN: (
        "D0 对象模型冻结",
        "当前 aggregate.yaml 处置",
        "当前 entity.yaml 处置",
        "ContractGraph 两层接口",
        "Object Application Facade",
        "Object Data Ports",
        "严格 compiler 与统计",
    ),
}


def _read_text(relative_path: str, issues: list[str]) -> str:
    path = ROOT / relative_path
    if not path.is_file():
        issues.append(f"缺少必需文件: {relative_path}")
        return ""
    return path.read_text(encoding="utf-8")


def _load_yaml(relative_path: str, issues: list[str]) -> dict[str, Any]:
    text = _read_text(relative_path, issues)
    if not text:
        return {}
    try:
        value = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        issues.append(f"{relative_path} 不是合法 YAML: {exc}")
        return {}
    if not isinstance(value, dict):
        issues.append(f"{relative_path} 顶层必须是 mapping")
        return {}
    return value


def _validate_required_tokens(issues: list[str]) -> None:
    for relative_path, tokens in REQUIRED_TOKENS.items():
        text = _read_text(relative_path, issues)
        for token in tokens:
            if token not in text:
                issues.append(f"{relative_path} 缺少 D0 合同标记: {token}")


def _metadata_object_names(
    file_name: str,
    key: str,
    issues: list[str],
) -> set[str]:
    root = ROOT / "quwoquan_service" / "contracts" / "metadata"
    names: set[str] = set()
    for path in sorted(root.glob(f"**/{file_name}")):
        relative = path.relative_to(ROOT).as_posix()
        if "_control_plane" in path.parts:
            continue
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            issues.append(f"{relative} 不是合法 YAML: {exc}")
            continue
        name = str(
            document.get(key)
            or (document.get("entity_name") if key == "entity" else "")
        ).strip()
        if not name:
            issues.append(
                f"{relative} 缺少 {key}"
                + ("/entity_name" if key == "entity" else "")
            )
            continue
        if name in names:
            issues.append(f"metadata 对象名称重复: {name}")
        names.add(name)
    return names


def _validate_metadata_inventory(issues: list[str]) -> None:
    metadata_root = ROOT / "quwoquan_service" / "contracts" / "metadata"
    object_domains: dict[str, set[str]] = {}
    for file_name, key in (
        ("aggregate.yaml", "aggregate_root"),
        ("entity.yaml", "entity"),
    ):
        for path in sorted(metadata_root.glob(f"**/{file_name}")):
            if "_control_plane" in path.parts:
                continue
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            domain = str(document.get("domain") or "").strip()
            name = str(
                document.get(key) or document.get("entity_name") or ""
            ).strip()
            if domain and name:
                object_domains.setdefault(domain, set()).add(name)
            if document.get("object_kind") == "separate_aggregate":
                issues.append(
                    f"{path.relative_to(ROOT)} 使用非法 separate_aggregate"
                )
            if file_name != "aggregate.yaml":
                continue
            for member in document.get("members") or []:
                if not isinstance(member, dict):
                    continue
                if member.get("object_kind") not in {
                    "owned_entity",
                    "value_object",
                }:
                    issues.append(
                        f"{path.relative_to(ROOT)} 聚合成员 "
                        f"{member.get('entity')} 不是 owned_entity/value_object"
                    )

    maps_by_domain: dict[str, Path] = {}
    registered_objects: dict[str, dict[str, Any]] = {}
    expected_context_policy = {
        "commands": "aggregate_facade_only",
        "queries": "named_reader_slice_only",
        "child_objects": "aggregate_root_only",
        "cross_context": "public_contract_only",
    }
    for path in sorted(metadata_root.glob("**/business_object_map.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        domain = str(document.get("domain") or "").strip()
        forbidden_envelope_fields = sorted(
            field
            for field in ("version", "schemaVersion", "registryRevision")
            if field in document
        )
        if forbidden_envelope_fields:
            issues.append(
                f"{path.relative_to(ROOT)} 包含已退役 Registry 版本字段: "
                f"{forbidden_envelope_fields}"
            )
        if not domain:
            issues.append(f"{path.relative_to(ROOT)} 缺少 domain")
            continue
        if domain in maps_by_domain:
            issues.append(f"domain {domain} 有多个 business_object_map.yaml")
        maps_by_domain[domain] = path
        context_names: set[str] = set()
        for context in document.get("bounded_contexts") or []:
            if not isinstance(context, dict):
                continue
            name = str(context.get("name") or "").strip()
            context_names.add(name)
            expected_context_id = f"{domain}.{to_snake_case(name)}"
            if context.get("context_id") != expected_context_id:
                issues.append(
                    f"{path.relative_to(ROOT)} context {name} 缺少稳定 context_id {expected_context_id}"
                )
            if context.get("access_policy") != expected_context_policy:
                issues.append(
                    f"{path.relative_to(ROOT)} context {name} 访问策略非法"
                )
        for item in document.get("objects") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("canonical_object") or "").strip()
            canonical_id = f"{domain}.{name}"
            if canonical_id in registered_objects:
                issues.append(f"重复 canonical object: {canonical_id}")
            registered_objects[canonical_id] = item
            if item.get("bounded_context") not in context_names:
                issues.append(f"{canonical_id} 引用未登记 bounded context")
            if item.get("object_kind") in {"owned_entity", "value_object"}:
                access = item.get("access") or {}
                if access.get("cross_context") != "forbidden":
                    issues.append(f"{canonical_id} 子对象允许跨上下文访问")

    missing_domains = sorted(set(object_domains) - set(maps_by_domain))
    if missing_domains:
        issues.append(f"存在未登记 metadata domain: {missing_domains}")
    for domain, names in sorted(object_domains.items()):
        for name in sorted(names):
            if f"{domain}.{name}" not in registered_objects:
                issues.append(f"metadata 对象未进入唯一 Registry: {domain}.{name}")
    for canonical_id, item in sorted(registered_objects.items()):
        for relationship in item.get("relationships") or []:
            target = str(relationship.get("target_object") or "").strip()
            targets = [
                str(value).strip()
                for value in (relationship.get("target_objects") or [])
                if str(value).strip()
            ]
            if target and targets:
                issues.append(
                    f"{canonical_id} relationship 同时声明 target_object 与 target_objects"
                )
                continue
            if target:
                targets = [target]
            if not targets:
                issues.append(f"{canonical_id} relationship 缺少目标对象")
                continue
            for target_id in targets:
                if target_id not in registered_objects:
                    issues.append(
                        f"{canonical_id} relationship target 未登记: {target_id}"
                    )

    greeting_path = (
        ROOT
        / "quwoquan_service"
        / "contracts"
        / "metadata"
        / "user"
        / "greeting_request"
        / "entity.yaml"
    )
    greeting = yaml.safe_load(greeting_path.read_text(encoding="utf-8")) or {}
    if greeting.get("object_kind") != "aggregate_root":
        issues.append(
            "user/greeting_request/entity.yaml 必须声明 "
            "object_kind=aggregate_root"
        )

    readme = _read_text(METADATA_README, issues)
    for retired_stat in ("| 聚合根 |", "| 独立实体 |", "| 领域事件 |"):
        if retired_stat in readme:
            issues.append(
                f"{METADATA_README} 仍维护手工统计行: {retired_stat}"
            )


def _validate_journeys(issues: list[str]) -> None:
    registry = _load_yaml(JOURNEY_REGISTRY, issues)
    journeys = registry.get("journeys")
    if not isinstance(journeys, list):
        issues.append(f"{JOURNEY_REGISTRY} journeys 必须是 list")
        return

    journey_by_id = {
        str(item.get("id", "")).strip(): item
        for item in journeys
        if isinstance(item, dict)
    }
    missing = sorted(REQUIRED_JOURNEYS - set(journey_by_id))
    if missing:
        issues.append(f"{JOURNEY_REGISTRY} 缺少十条商用 Journey: {missing}")

    for journey_id in sorted(REQUIRED_JOURNEYS & set(journey_by_id)):
        item = journey_by_id[journey_id]
        for key in ("scenario_refs", "domain_services", "uat_refs"):
            value = item.get(key)
            if not isinstance(value, list) or not value:
                issues.append(
                    f"{JOURNEY_REGISTRY} Journey {journey_id} 缺少 {key}"
                )

    acceptance = _load_yaml(APP_ROOT_ACCEPTANCE, issues)
    uat = (acceptance.get("uat_acceptance") or {}).get(
        "UAT_BUSINESS_OBJECT_COMMERCIALIZATION"
    )
    if not isinstance(uat, dict):
        issues.append(
            f"{APP_ROOT_ACCEPTANCE} 缺少 "
            "UAT_BUSINESS_OBJECT_COMMERCIALIZATION"
        )
        return
    scenario_refs = {
        str(value).strip() for value in uat.get("scenario_refs") or []
    }
    if scenario_refs != COMMERCIAL_UAT_SCENARIOS:
        issues.append(
            "UAT_BUSINESS_OBJECT_COMMERCIALIZATION 必须精确覆盖十个 "
            f"Scenario；当前缺少={sorted(COMMERCIAL_UAT_SCENARIOS - scenario_refs)} "
            f"多余={sorted(scenario_refs - COMMERCIAL_UAT_SCENARIOS)}"
        )


def _validate_architecture_acceptance(issues: list[str]) -> None:
    acceptance = _load_yaml(ARCH_ACCEPTANCE, issues)
    sit4 = (acceptance.get("sit_acceptance") or {}).get("SIT4")
    if not isinstance(sit4, dict):
        issues.append(f"{ARCH_ACCEPTANCE} 缺少 SIT4 D0 设计冻结验收")
        return
    if sit4.get("status") not in {"partial", "implemented", "completed"}:
        issues.append(f"{ARCH_ACCEPTANCE} SIT4 状态非法")
    recorded = (sit4.get("tests") or {}).get("recorded") or []
    recorded_paths = {
        item.get("file") if isinstance(item, dict) else item for item in recorded
    }
    if LOCAL_CONTRACT_TEST not in recorded_paths:
        issues.append(
            f"{ARCH_ACCEPTANCE} SIT4 未记录 {LOCAL_CONTRACT_TEST}"
        )


def _validate_change_record(issues: list[str]) -> None:
    change = _load_yaml(CHANGE_RECORD, issues)
    if change.get("status") not in {"specified", "implemented", "completed"}:
        issues.append(f"{CHANGE_RECORD} status 非法或缺失")
    changed_paths = {
        str(item.get("path", "")).strip()
        for entry in change.get("entries") or []
        if isinstance(entry, dict)
        for item in entry.get("changed_documents") or []
        if isinstance(item, dict)
    }
    for required in (
        APP_ROOT_SPEC,
        APP_ROOT_DESIGN,
        APP_ROOT_ACCEPTANCE,
        JOURNEY_REGISTRY,
        METADATA_README,
        METADATA_DESIGN,
        ARCH_SPEC,
        ARCH_DESIGN,
        ARCH_ACCEPTANCE,
    ):
        if required not in changed_paths:
            issues.append(f"{CHANGE_RECORD} 未登记变更文件: {required}")


def collect_issues() -> list[str]:
    issues: list[str] = []
    _validate_required_tokens(issues)
    _validate_metadata_inventory(issues)
    _validate_journeys(issues)
    _validate_architecture_acceptance(issues)
    _validate_change_record(issues)
    return issues


def main() -> int:
    issues = collect_issues()
    if issues:
        print("[verify_business_object_design_freeze] FAIL", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("[verify_business_object_design_freeze] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
