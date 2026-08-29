#!/usr/bin/env python3
"""Validate Provider Conformance evidence and derive evidence-backed readiness.

实现单轨落在 ``provider_conformance_lib/`` 包内（constants / evidence_store /
governance_bindings / attestation / candidate / sources / case_results /
evidence_validation / readiness）；本文件是稳定模块与 CLI 入口：

- ``from quwoquan_ops.cli.lib import provider_conformance`` 与
  ``from quwoquan_ops.cli.lib.provider_conformance import X`` 的全部公开符号
  与被测私有符号由这里 re-export；
- ``python3 quwoquan_ops/cli/lib/provider_conformance.py --require-ready <env>``
  仍是 stackctl 消费的唯一 readiness CLI（该路径是 stackctl 与
  verify_stackctl_provider_readiness_contract / verify_ci_cd_evidence_contracts
  的契约，不可移动）。

包内实现对可被测试 patch 的符号（ROOT、TEST_LAYER_ROOTS、_current_commit、
current_source_tree_state、ci_attestation_authority_available、
_binding_preflight_ready、resolve_nonprod_active_candidate、
service_deployment_package_dir、load_startup_attempt、can_reuse_package）
一律经由本模块命名空间在调用时读取，保持与拆分前单文件相同的
mock.patch 语义。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    # 以脚本方式执行时，包内子模块的 `from quwoquan_ops.cli.lib import
    # provider_conformance` 必须解析到当前模块对象，才能与 import 形态共享
    # 同一命名空间（含 mock.patch 语义），且避免同一文件被二次加载。
    sys.modules.setdefault(
        "quwoquan_ops.cli.lib.provider_conformance", sys.modules[__name__]
    )

from quwoquan_ops.cli.lib import external_provider_governance as governance  # noqa: E402,F401
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (  # noqa: E402,F401
    load_candidate_manifest,
)
from quwoquan_ops.cli.lib.immutable_image_composition import (  # noqa: E402,F401
    immutable_image_digest,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: E402,F401
    active_deployment_candidate,
    output_root,
    runtime_shared_deployment_package_dir,
    service_deployment_package_dir,
)
from quwoquan_ops.cli.lib.package_reuse import can_reuse_package  # noqa: E402,F401
from quwoquan_ops.cli.lib.startup_attempt_receipt import (  # noqa: E402,F401
    load_startup_attempt,
    startup_attempt_path,
)

from quwoquan_ops.cli.lib.provider_conformance_lib.constants import (  # noqa: E402,F401
    ADAPTER_PATTERN,
    ALLOWED_FIELDS,
    ARTIFACT_ATTESTATION_PATTERN,
    ASSERTION_ID_PATTERN,
    CAPABILITY_PATTERN,
    CASE_RESULT_RELEASE_FIELDS,
    CASE_RESULT_REMOTE_FIELDS,
    CASE_RESULT_REQUIRED_FIELDS,
    CASE_RESULT_SCHEMA,
    CELL_PROFILES,
    COMMIT_PATTERN,
    ENVIRONMENTS,
    EVIDENCE_ENVIRONMENTS,
    EVIDENCE_SCHEMA,
    EXECUTION_REPORT_REQUIRED_FIELDS,
    EXECUTION_REPORT_SCHEMA,
    LAYERS,
    MAX_EVIDENCE_AGE,
    MESSAGE_TRANSPORT_CAPABILITY_ID,
    MESSAGE_TRANSPORT_METRIC_NAMES,
    MESSAGE_TRANSPORT_METRIC_REFS,
    NATIVE_READBACK_ARTIFACT_RE,
    PUBLIC_ASSERTION_IDS,
    READINESS_ENVIRONMENTS,
    RECEIPT_REF_PATTERN,
    RELEASE_ASSERTION_IDS,
    RELEASE_ENVIRONMENT,
    RELEASE_READINESS_ENVIRONMENTS,
    RELEASE_READINESS_FIELDS,
    REMOTE_READBACK_SCHEMA,
    REQUIRED_FIELDS,
    ROOT,
    SENSITIVE_RECEIPT_REF_PATTERN,
    SHA256_PATTERN,
    SOURCE_DYNAMIC_EXECUTOR_RE,
    SOURCE_METADATA_RE,
    SOURCE_STATIC_BLOCK_RE,
    TEST_LAYER_ROOTS,
    execution_profile_for,
    requires_release_readiness,
)
from quwoquan_ops.cli.lib.provider_conformance_lib.evidence_store import (  # noqa: E402,F401
    _issue,
    _output_path,
    evidence_files,
    load_evidence,
    load_evidence_paths,
)
from quwoquan_ops.cli.lib.provider_conformance_lib.governance_bindings import (  # noqa: E402,F401
    _binding_preflight_ready,
    _binding_root_ids,
    _is_non_empty_string,
    _root_id_list,
    _selected_adapter_id,
    _selected_binding,
    _valid_receipt_ref,
    capability_assertion_id,
    compiled_capability_binding_roots,
    exact_required_cell_issues,
    expected_required_cell_keys,
    network_boundary_for_layer,
    provider_conformance_capability_ids,
    required_metric_refs,
)
from quwoquan_ops.cli.lib.provider_conformance_lib.attestation import (  # noqa: E402,F401
    _commit_digest,
    _current_adapter_digest,
    _current_commit,
    _current_contract_graph_digest,
    _digest,
    _digest_bytes,
    attest_execution_report,
    ci_attestation_authority_available,
    current_source_tree_state,
    evidence_identity,
    evidence_is_promotable,
    implementation_digest,
    sign_execution_report,
)
from quwoquan_ops.cli.lib.provider_conformance_lib.candidate import (  # noqa: E402,F401
    _artifact_reference,
    _inactive_candidate,
    _nonprod_active_candidate_issues,
    active_candidate_receipt_issues,
    binding_config_digest,
    candidate_image_digest,
    resolve_nonprod_active_candidate,
    resolve_prod_active_candidate,
)
from quwoquan_ops.cli.lib.provider_conformance_lib.sources import (  # noqa: E402,F401
    _source_metadata,
    _source_spec_refs,
    discover_test_sources,
    load_test_source,
    local_source_coverage_issues,
    source_coverage_issues,
    source_for_cell,
)
from quwoquan_ops.cli.lib.provider_conformance_lib.case_results import (  # noqa: E402,F401
    _native_readback_valid,
    _observability_refs_valid,
    _release_readiness_valid,
    _validate_execution_report,
    load_case_results,
)
from quwoquan_ops.cli.lib.provider_conformance_lib.evidence_validation import (  # noqa: E402,F401
    validate_evidence,
)
from quwoquan_ops.cli.lib.provider_conformance_lib.readiness import (  # noqa: E402,F401
    _assertion_semantics,
    _cells_share_local_candidate,
    _cells_share_release,
    derive_readiness,
    load_validate_and_derive,
    load_validate_local_functional_readiness,
    local_functional_readiness_issues,
    main,
    readiness_issues,
)

if __name__ == "__main__":
    raise SystemExit(main())
