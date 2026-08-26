"""领域服务自治目录门禁实现包。

包内模块职责：

- ``constants``：扫描根、DDD 层/kind 规则表、正则与资源角色常量的唯一定义处。
- ``repository``：YAML 加载、相对路径与服务根发现等仓库物理事实助手。
- ``object_semantics``：对象契约 kind-aware 语义与 DEC-011 入口归属规则。
- ``source_analysis``：实质实现/测试识别、spec_ref 追溯与 lifecycle handler 绑定。
- ``verification_contracts``：Verification 契约/模板检查段（mixin）。
- ``verification_sources``：Verification 源码归属/生成物/依赖边界检查段（mixin）。
- ``verification_operations``：Verification 资源/部署/运维检查段（mixin）。
- ``verification``：VerificationCore 状态容器与 verify 主序列。

``verify_kind_aware_object_implementation`` 与 ``main`` 因 object_path_map 门禁
的 AST 镜像校验留在入口文件 ``verify_service_architecture.py``。
"""
from __future__ import annotations

import sys
from pathlib import Path

_GATE_ROOT = Path(__file__).resolve().parents[1]
if str(_GATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_GATE_ROOT))

from repository_root import repository_root  # noqa: E402

_REPO_ROOT = repository_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from .constants import (  # noqa: E402
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
)
from .object_semantics import (  # noqa: E402
    camel_to_snake,
    lifecycle_authored_consumers,
    object_contract_semantic_issues,
    object_entrypoint_mode,
    snake_to_pascal,
)
from .repository import (  # noqa: E402
    compose_ownership_violations,
    domain_service_names,
    load_yaml,
    physical_service_roots,
    relative,
    service_roots,
)
from .source_analysis import (  # noqa: E402
    go_import_declarations,
    is_substantive_implementation_source,
    is_substantive_test_source,
    lifecycle_handler_binding_issues,
    valid_object_test_spec_refs,
)
from .verification import VerificationCore  # noqa: E402

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
    "object_contract_semantic_issues",
    "object_entrypoint_mode",
    "physical_service_roots",
    "relative",
    "service_roots",
    "snake_to_pascal",
    "valid_object_test_spec_refs",
]
