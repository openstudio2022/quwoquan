#!/usr/bin/env python3
"""领域服务自治目录的唯一仓库门禁（稳定 CLI 入口）。

该门禁只读取可版本控制的事实：服务本地 contracts、源码路径、四环境入口和
Kustomize 基线。它不读取服务注册表、人工 topology、readiness 或迁移清单。

实现单轨落在 ``service_architecture/`` 包内；本文件做 sys.path bootstrap、
为既有消费者 re-export 包 API，并保留两段必须留在入口的字面量：

- ``Verification.verify_kind_aware_object_implementation``：
  ``object_path_map_lib/claims.py`` 经 AST 解析本文件比对 ``required_layers``
  字面量（云侧 kind 规则防漂移），该方法不能搬入包内。
- ``main``：实例化上述最终 ``Verification`` 类。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BOOTSTRAP = next(
    path
    for path in Path(__file__).resolve().parents
    if (path / "repository_root.py").is_file()
)
if str(_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP))

from repository_root import repository_root  # noqa: E402

_REPO_ROOT = repository_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.gate.service_architecture import (  # noqa: E402
    ALLOWED_OPS_ENVIRONMENT_ROOT_DIRS,
    ALLOWED_OPS_ENVIRONMENT_ROOT_FILES,
    BANNED_PATHS,
    CANONICAL_EVENT_REF_RE,
    COMMON_RESOURCE_ROOT_ROLES,
    ENVIRONMENTS,
    FUZZY_DIRECTORIES,
    GENERATED_OBJECT_SOURCE_RE,
    GENERIC_OBJECT_DESCRIPTION_RE,
    KINDS,
    LAYERS,
    LIFECYCLE_CONSUMER_IDEMPOTENCY,
    LIFECYCLE_CONSUMER_KINDS,
    LIFECYCLE_ONLY_ENTRYPOINT_KINDS,
    MIGRATION_RE,
    OBJECT_ACCESS_BY_KIND,
    OBJECT_PRIVATE_IMPORT_RE,
    OBJECT_VERSION_SOURCE_BY_KIND,
    OPS_ROOT,
    PROCESS_MANAGER_PUBLIC_QUERY_ACCESS,
    ROOT,
    RUNTIME_ENTRYPOINT_KIND_BY_OBJECT_KIND,
    SERVICE_IMPORT_RE,
    SERVICE_ROOT,
    SERVICES_ROOT,
    SKILL_PACKAGE_RUNTIME_RELATIVE_ROOT,
    SKILL_PACKAGE_SOURCE_RELATIVE_ROOT,
    VerificationCore,
    camel_to_snake,
    compose_ownership_violations,
    domain_service_names,
    go_import_declarations,
    is_substantive_implementation_source,
    is_substantive_test_source,
    lifecycle_authored_consumers,
    lifecycle_handler_binding_issues,
    load_yaml,
    object_contract_semantic_issues,
    object_entrypoint_mode,
    physical_service_roots,
    relative,
    service_roots,
    snake_to_pascal,
    valid_object_test_spec_refs,
)

__all__ = [
    "ALLOWED_OPS_ENVIRONMENT_ROOT_DIRS",
    "ALLOWED_OPS_ENVIRONMENT_ROOT_FILES",
    "BANNED_PATHS",
    "CANONICAL_EVENT_REF_RE",
    "COMMON_RESOURCE_ROOT_ROLES",
    "ENVIRONMENTS",
    "FUZZY_DIRECTORIES",
    "GENERATED_OBJECT_SOURCE_RE",
    "GENERIC_OBJECT_DESCRIPTION_RE",
    "KINDS",
    "LAYERS",
    "LIFECYCLE_CONSUMER_IDEMPOTENCY",
    "LIFECYCLE_CONSUMER_KINDS",
    "LIFECYCLE_ONLY_ENTRYPOINT_KINDS",
    "MIGRATION_RE",
    "OBJECT_ACCESS_BY_KIND",
    "OBJECT_PRIVATE_IMPORT_RE",
    "OBJECT_VERSION_SOURCE_BY_KIND",
    "OPS_ROOT",
    "PROCESS_MANAGER_PUBLIC_QUERY_ACCESS",
    "ROOT",
    "RUNTIME_ENTRYPOINT_KIND_BY_OBJECT_KIND",
    "SERVICE_IMPORT_RE",
    "SERVICE_ROOT",
    "SERVICES_ROOT",
    "SKILL_PACKAGE_RUNTIME_RELATIVE_ROOT",
    "SKILL_PACKAGE_SOURCE_RELATIVE_ROOT",
    "Verification",
    "VerificationCore",
    "camel_to_snake",
    "compose_ownership_violations",
    "domain_service_names",
    "go_import_declarations",
    "is_substantive_implementation_source",
    "is_substantive_test_source",
    "lifecycle_authored_consumers",
    "lifecycle_handler_binding_issues",
    "load_yaml",
    "main",
    "object_contract_semantic_issues",
    "object_entrypoint_mode",
    "physical_service_roots",
    "relative",
    "service_roots",
    "snake_to_pascal",
    "valid_object_test_spec_refs",
]


class Verification(VerificationCore):
    """最终门禁判定类。

    仅补齐 ``verify_kind_aware_object_implementation``：该方法的
    ``required_layers`` 字面量被 ``object_path_map_lib/claims.py`` AST 镜像
    锚定在本文件，方法体自原实现逐字搬移，不得改写或移入包内。
    """

    def verify_kind_aware_object_implementation(self) -> None:
        required_layers = {
            "aggregate_root": {"domain", "application", "infrastructure"},
            "append_only_fact": {"domain", "application", "infrastructure"},
            # saga 三层缺一不可：domain 放状态机与补偿规则，application 放编排，
            # infrastructure 放 checkpoint 持久化。
            "process_manager": {"domain", "application", "infrastructure"},
            "projection": {"application", "infrastructure"},
            "runtime_session": {"domain", "application", "infrastructure"},
        }
        for key, (owner, object_path, document) in sorted(self.objects.items()):
            if owner not in domain_service_names() and owner != "platform-ops":
                continue
            kind = str(document.get("kind") or "")
            actual = {
                layer
                for layer, sources in self.layer_sources.get(key, {}).items()
                if sources
            }
            missing = required_layers.get(kind, set()) - actual
            if kind == "external_reference":
                if "application" not in actual:
                    missing.add("application")
                if not actual & {"adapters", "infrastructure"}:
                    missing.add("adapters-or-infrastructure")
            if key in self.routed_objects and "adapters" not in actual:
                missing.add("adapters")
            if (
                self.runtime_entrypoint_kinds.get(key)
                in {"projector", "subscription", "internal_port", "external_port"}
                and "adapters" not in actual
            ):
                missing.add("adapters")
            if key in self.lifecycle_entrypoint_objects and "adapters" not in actual:
                missing.add("adapters")
            if missing:
                self.error(
                    f"{relative(object_path.parent)}: kind={kind} requires substantive "
                    f"object-local layers; missing={sorted(missing)} actual={sorted(actual)}"
                )


def main() -> int:
    verification = Verification()
    verification.verify()
    if verification.errors:
        print("[verify-service-architecture] FAIL")
        for error in verification.errors:
            print(f"  - {error}")
        return 1
    summary = {
        "services": len(service_roots()),
        "contexts": len(verification.contexts),
        "objects": len(verification.objects),
        "objectKinds": dict(sorted(verification.object_kinds.items())),
        "aggregateMembers": verification.aggregate_members,
        "sourceObjects": len(verification.source_owners),
        "serviceEnvironmentEntries": len(service_roots()) * len(ENVIRONMENTS),
        "opsEnvironmentEntries": len(ENVIRONMENTS),
    }
    print("[verify-service-architecture] OK")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
