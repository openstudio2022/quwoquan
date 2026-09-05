"""Authority-backed final environment-stability receipt aggregation.

The aggregator calculates a verdict only.  Authority comes from the canonical
ReleaseEvidenceManifest artifact closure, GitHub artifact-attestation
verification, and canonical hosted-ledger readbacks.  Fields inside an input
JSON document never establish their own authority.

本包由原单文件 ``environment_stability_final_acceptance.py`` 拆分而来，
按职责切分为：

- ``model``：常量、数据类、类型别名与 ``_Evaluation``。
- ``receipt_io``：typed receipt 载入、canonical 摘要与通用校验原语。
- ``provider_readiness``：Provider readiness 的 canonical 重推导与绑定校验。
- ``artifact_closure``：ReleaseEvidenceManifest 闭包与 manifest 绑定输入校验。
- ``pilot_content``：pilot 发布身份、内容生命周期与 Green Matrix 校验。
- ``attested_evidence``：GitHub OIDC attestation 与 CI / prod-sim 证据校验。
- ``hosted_prod``：prod hosted readback 与 hosted soak authority 校验。
- ``verdict``：聚合评估、终局 verdict 计算与原子写出。

对外导入路径保持不变：``from quwoquan_ops.cli.lib.environment_stability_final_acceptance import ...``。
"""
from __future__ import annotations

# 测试通过 "quwoquan_ops.cli.lib.environment_stability_final_acceptance.subprocess.run"
# monkeypatch 子进程调用，包属性必须保留 subprocess 模块引用。
import subprocess  # noqa: F401

import yaml  # noqa: F401

from quwoquan_ops.ci import render_release_lifecycle_receipts as lifecycle  # noqa: F401
from quwoquan_ops.cli.lib import (  # noqa: F401
    external_provider_governance,
    provider_conformance,
)
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (  # noqa: F401
    validate_release_attestations,
)
from quwoquan_ops.cli.prod import oci_supply_chain  # noqa: F401
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (  # noqa: F401
    DIGEST_PATTERN,
    canonical_release_composition_id,
    canonical_manifest_digest,
    sha256_file,
    validate_manifest,
    validate_manifest_files,
)

from quwoquan_ops.cli.lib.environment_stability_final_acceptance.artifact_closure import (  # noqa: F401
    _artifact_binding_matches,
    _artifact_closure,
    _bound_descriptor,
    _validate_manifest_bound_acceptance_inputs,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.attested_evidence import (  # noqa: F401
    _attestation_has_subject_digest,
    _validate_ci_evidence,
    _validate_prod_sim,
    _verify_authority,
    verify_github_actions_receipt,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.hosted_prod import (  # noqa: F401
    _bound_stage_readback,
    _manifest_contains_receipt_id,
    _service_from_readback,
    _validate_hosted_readbacks,
    _validate_soak_authority,
    verify_canonical_hosted_prod_soak,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.model import (  # noqa: F401
    BLOCKED_VERDICT,
    BLOCKER_CODES,
    DEVICE_WORKFLOW,
    ENVIRONMENTS,
    GITHUB_ATTESTED_WORKFLOW_BY_KIND,
    MAX_FUTURE_SKEW_SECONDS,
    PROMOTABLE_VERDICT,
    PROVIDER_NONPROD_ENVIRONMENTS,
    REQUIRED_SOAK_CLAIMS,
    SCHEMA,
    SCHEMA_PATH,
    ArtifactClosureVerifier,
    AttestationVerifier,
    CommandRunner,
    FinalAcceptanceInputs,
    LoadedReceipt,
    ProviderReadinessVerifier,
    SoakAuthorityVerifier,
    VerifiedAuthority,
    _Evaluation,
    _FORBIDDEN_INPUT_NAMES,
    _GIT_SHA,
    _RECEIPT_ID,
    _SELF_AUTHORITY_FIELDS,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.pilot_content import (  # noqa: F401
    _pilot_identity,
    _validate_content_lifecycle,
    _validate_green_matrix,
    _verify_checksum,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.provider_readiness import (  # noqa: F401
    _provider_layers,
    verify_canonical_provider_readiness,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.receipt_io import (  # noqa: F401
    _canonical_bytes,
    _canonical_digest,
    _load_receipt,
    _passed,
    _reject_self_asserted_authority,
    _resolve_artifact_root,
    _schema,
    _sha256,
    _timestamp,
    _walk,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.verdict import (  # noqa: F401
    _descriptor,
    _input_projection,
    evaluate_final_acceptance,
    write_final_acceptance,
)
