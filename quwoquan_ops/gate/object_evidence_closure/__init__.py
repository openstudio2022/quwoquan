"""对象证据闭合门禁实现包：结构性证据严格零值 + 动态商业 readiness 薄调用。

包内模块职责：

- ``constants``：扫描根、维度分层表、missing 键映射与 packet shape 常量的唯一定义处。
- ``models``：Gap/DynamicEvaluation dataclass 与路径显示、SHA256 摘要助手。
- ``arguments``：CLI 参数定义（模块 docstring 保留原始门禁说明全文，驱动 --help）。
- ``readiness_inputs``：动态 readiness 输入摘要绑定与 canonical Go evaluator 构建。
- ``graph_source``：ContractGraph 现场派生、读取绑定与 producer-separated shape 校验。
- ``reporting``：一次性报告的输入绑定校验、落盘与人类可读缺口打印。
- ``gap_rules``：维度分层、发布 seam 缺口详情与领域事件显式表态规则。
- ``page_runtime``：非页面 runtime execution 消费证据校验。
- ``gate``：主判定流程与既有契约测试的 patch surface。
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

from .arguments import commercial_input_values, parse_args  # noqa: E402
from .constants import (  # noqa: E402
    ARTIFACT_EVIDENCE_FIELDS,
    BLIND_SPOT_CLASSIFICATIONS,
    BLIND_SPOT_IMPLEMENTATION_EVIDENCE,
    BLIND_SPOT_IMPLEMENTED,
    BLIND_SPOT_MISSING,
    BLIND_SPOT_REGISTRY,
    BLINDSPOT,
    DART_NON_CODE_RE,
    EVIDENCE_CLASS_BY_DIMENSION,
    LAYER_BY_MISSING_KEY,
    LEGACY_FLATTENED_EVIDENCE_FIELDS,
    PACKET_ALLOWED_FIELDS,
    PACKET_OPTIONAL_FIELDS,
    PACKET_REQUIRED_FIELDS,
    PACKET_STRING_LIST_FIELDS,
    PAGE_OBJECT_CONTRACT,
    PRODUCER_ARTIFACT_FIELDS,
    PRODUCER_BOOLEAN_FIELDS,
    PRODUCER_STORAGE_FIELDS,
    READINESS_EVALUATOR_BUILD_TIMEOUT_SECONDS,
    READINESS_EVALUATOR_PACKAGE,
    READINESS_EVALUATOR_RUN_TIMEOUT_SECONDS,
    READINESS_METADATA_DIR,
    REPORT_BLIND_SPOT_REGISTRY_FIELD,
    REPORT_GRAPH_FIELD,
    RESULT,
    ROOT,
    RUN_DIR,
    SERVICE_ROOT,
    SHA256_PATTERN,
    STATE_OWNER_KINDS,
    STORAGE_EVIDENCE_FIELDS,
    STRUCTURAL,
)
from .gap_rules import (  # noqa: E402
    bound_storages,
    domain_event_declaration_gaps,
    evidence_class,
    object_contract_dir,
    partition_by_evidence_class,
    publication_gap_detail,
    slice_owner_object,
    unclassified_dimensions,
)
from .gate import (  # noqa: E402
    artifact_gaps,
    artifact_integrity_gaps,
    blind_spot_gaps,
    collect_gaps,
    evaluate_dynamic_readiness,
    is_production_service_source,
    load_blind_spot_registry,
    load_blind_spot_registry_with_digest,
    main,
    page_claims_and_consumers,
    resolve_repository_artifact,
    select_graph_path,
)
from .graph_source import (  # noqa: E402
    derive_contract_graph,
    load_graph,
    load_graph_with_digest,
    validate_contract_graph_shape,
    verify_graph_digest,
)
from .models import DynamicEvaluation, Gap, display_path, sha256_file  # noqa: E402
from .page_runtime import (  # noqa: E402
    runtime_execution_consumers,
    without_dart_non_code,
)
from .readiness_inputs import (  # noqa: E402
    build_readiness_evaluator,
    decode_single_json_document,
    digest_readiness_input,
    readiness_input_bindings,
    verify_readiness_input_bindings,
)
from .reporting import (  # noqa: E402
    cells_from_gaps,
    print_blind_spots,
    print_gap_inventory,
    print_result_layer,
    print_structural_gaps,
    validate_report_graph_binding,
    validate_report_policy_bindings,
    verify_optional_input_digest,
    write_reports,
)

__all__ = [
    "ARTIFACT_EVIDENCE_FIELDS",
    "BLIND_SPOT_CLASSIFICATIONS",
    "BLIND_SPOT_IMPLEMENTATION_EVIDENCE",
    "BLIND_SPOT_IMPLEMENTED",
    "BLIND_SPOT_MISSING",
    "BLIND_SPOT_REGISTRY",
    "BLINDSPOT",
    "DART_NON_CODE_RE",
    "DynamicEvaluation",
    "EVIDENCE_CLASS_BY_DIMENSION",
    "Gap",
    "LAYER_BY_MISSING_KEY",
    "LEGACY_FLATTENED_EVIDENCE_FIELDS",
    "PACKET_ALLOWED_FIELDS",
    "PACKET_OPTIONAL_FIELDS",
    "PACKET_REQUIRED_FIELDS",
    "PACKET_STRING_LIST_FIELDS",
    "PAGE_OBJECT_CONTRACT",
    "PRODUCER_ARTIFACT_FIELDS",
    "PRODUCER_BOOLEAN_FIELDS",
    "PRODUCER_STORAGE_FIELDS",
    "READINESS_EVALUATOR_BUILD_TIMEOUT_SECONDS",
    "READINESS_EVALUATOR_PACKAGE",
    "READINESS_EVALUATOR_RUN_TIMEOUT_SECONDS",
    "READINESS_METADATA_DIR",
    "REPORT_BLIND_SPOT_REGISTRY_FIELD",
    "REPORT_GRAPH_FIELD",
    "RESULT",
    "ROOT",
    "RUN_DIR",
    "SERVICE_ROOT",
    "SHA256_PATTERN",
    "STATE_OWNER_KINDS",
    "STORAGE_EVIDENCE_FIELDS",
    "STRUCTURAL",
    "artifact_gaps",
    "artifact_integrity_gaps",
    "blind_spot_gaps",
    "bound_storages",
    "build_readiness_evaluator",
    "cells_from_gaps",
    "collect_gaps",
    "commercial_input_values",
    "decode_single_json_document",
    "derive_contract_graph",
    "digest_readiness_input",
    "display_path",
    "domain_event_declaration_gaps",
    "evaluate_dynamic_readiness",
    "evidence_class",
    "is_production_service_source",
    "load_blind_spot_registry",
    "load_blind_spot_registry_with_digest",
    "load_graph",
    "load_graph_with_digest",
    "main",
    "object_contract_dir",
    "page_claims_and_consumers",
    "parse_args",
    "partition_by_evidence_class",
    "print_blind_spots",
    "print_gap_inventory",
    "print_result_layer",
    "print_structural_gaps",
    "publication_gap_detail",
    "readiness_input_bindings",
    "resolve_repository_artifact",
    "runtime_execution_consumers",
    "select_graph_path",
    "sha256_file",
    "slice_owner_object",
    "unclassified_dimensions",
    "validate_contract_graph_shape",
    "validate_report_graph_binding",
    "validate_report_policy_bindings",
    "verify_graph_digest",
    "verify_optional_input_digest",
    "verify_readiness_input_bindings",
    "without_dart_non_code",
    "write_reports",
]
