#!/usr/bin/env python3
"""把构建与发布证据归一为唯一、无版本信封的 ReleaseEvidenceManifest。

实现已按职责拆分到 ``finalize_mainline_release_artifact_lib/`` 子包；本文件
保留被门禁 AST/文本扫描钉住的契约常量（``SCHEMA`` / ``FORBIDDEN_FIELDS``
等），并 re-export 子包全部符号，保持既有 import 与 CLI 表面不变。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.render_provider_conformance_source import (  # noqa: F401
    expected_required_cell_count_from_readiness,
)
from quwoquan_ops.cli.lib.app_identity import supported_build_products


SCHEMA = "release-evidence-manifest"
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
TREE_DIGEST_PATTERN = re.compile(r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})")
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
PRE_PROD_ENVIRONMENTS = ENVIRONMENTS[:-1]
STATUSES = frozenset(
    {
        "build-input",
        "component-ready",
        "candidate-ready",
        "deployable",
        "released",
        "rolled-back",
        "rollback-failed",
    }
)
APPLICATION_BUILD_PRODUCTS = supported_build_products()
APPLICATION_PACKAGES = tuple(
    product.build_product_id for product in APPLICATION_BUILD_PRODUCTS
)
if len(APPLICATION_PACKAGES) != 5 or len(set(APPLICATION_PACKAGES)) != 5:
    raise ValueError("ReleaseEvidence App baseline must contain exactly five products")
REQUIRED_RELEASE_EVIDENCE = ("contractGraph", "providerEvidence", "testEvidence")
OPTIONAL_RELEASE_EVIDENCE = ("publicWeb", "androidOfficialRelease")
TEST_LAYERS = ("local_contract", "api_integration", "user_acceptance")
RELEASE_CLOSURE_PATHS = {
    "pilot-release": "evidence/release/pilot-release-attestation.json",
    "pilot-rollback": "evidence/release/pilot-rollback-attestation.json",
    "content-lifecycle-alpha": "evidence/release/lifecycle-exit-alpha.json",
    "content-lifecycle-beta": "evidence/release/lifecycle-exit-beta.json",
    "content-lifecycle-gamma": "evidence/release/lifecycle-exit-gamma.json",
    "green-matrix": "evidence/release/alpha-beta-gamma-green-matrix.json",
}
TEST_RELEASE_CLOSURE_LABELS = frozenset(RELEASE_CLOSURE_PATHS)
ENVIRONMENT_RECEIPT_SCHEMA = "release-environment-receipt"
ROLLOUT_RECEIPT_SCHEMA = "release-rollout-receipt"
ROLLBACK_RECEIPT_SCHEMA = "release-rollback-receipt"
ROOT_FIELDS = frozenset(
    {
        "schema",
        "releaseTrainId",
        "candidateId",
        "status",
        "generatedAt",
        "source",
        "artifactDigest",
        "environmentArtifacts",
        "applicationPackages",
        "opsPortal",
        "contractGraphDigest",
        "requiredEvidence",
        "testEvidence",
        "providerEvidence",
        "environmentReceipts",
        "rolloutReceipt",
        "rollbackReceipt",
        "blockers",
        "missingEvidence",
    }
)
FORBIDDEN_FIELDS = frozenset(
    {
        "artifactName",
        "contractVersion",
        "imageRepositories",
        "manifestDigest",
        "registryRevision",
        "releaseFileDigests",
        "releaseFiles",
        "requiredArtifacts",
        "requiredImages",
        "schemaVersion",
        "versions",
    }
)
RECEIPT_SOURCE_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "status",
        "candidateId",
        "sourceGitSha",
        "sourceTreeDigest",
        "evidenceDigest",
        "evidence",
        "verifiedAt",
    }
)
RECEIPT_DESCRIPTOR_FIELDS = RECEIPT_SOURCE_FIELDS | {"path", "digest"}
APPLICATION_PACKAGE_SCHEMA = "release-application-package"
APPLICATION_PACKAGE_FIELDS = frozenset(
    {
        "schema",
        "buildProductId",
        "buildProfile",
        "platform",
        "sourceGitSha",
        "sourceTreeDigest",
        "packageDigest",
        "artifactManifest",
    }
)
APPLICATION_DESCRIPTOR_FIELDS = frozenset(
    {"path", "digest", "packageDigest", "sourceRef"}
)
APPLICATION_SOURCE_DESCRIPTOR_FIELDS = APPLICATION_DESCRIPTOR_FIELDS | {
    "buildProductId"
}
OPS_PORTAL_SCHEMA = "qwq.ops_portal_package"
OPS_PORTAL_SOURCE_DESCRIPTOR_FIELDS = APPLICATION_DESCRIPTOR_FIELDS | {"evidenceKey"}
OCI_DIGEST_REF_PATTERN = re.compile(
    r"oci://ghcr\.io/[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}"
)

if __name__ == "__main__":
    # 直接以脚本运行时本模块名是 __main__；先把它注册为规范模块名，
    # 使子包反向 import 契约常量时命中本模块，而不是再执行一份副本。
    sys.modules.setdefault(
        "quwoquan_ops.cli.prod.finalize_mainline_release_artifact",
        sys.modules[__name__],
    )

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.canonical_digests import (  # noqa: E402,F401
    _canonical_json_bytes,
    _candidate_projection,
    canonical_bytes,
    canonical_candidate_digest,
    canonical_environment_artifact_digest,
    canonical_manifest_digest,
    canonical_release_train_digest,
    load_json,
    seal_manifest,
    sha256_file,
    sha256_ops_portal_tree,
    sha256_tree,
    utc_now,
    write_summary,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.manifest_validation import (  # noqa: E402,F401
    _bound_file,
    _derive_status,
    _expected_gaps,
    _forbidden_field_paths,
    _require_string_list,
    _validate_application_packages,
    _validate_candidate_evidence,
    _validate_environment_artifacts,
    _validate_images,
    _validate_packages,
    _validate_receipt_descriptor,
    _validate_receipts,
    _validate_relative_path,
    _validate_required_evidence,
    validate_manifest,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.evidence_files import (  # noqa: E402,F401
    _verify_configuration_packages,
    _verify_provider_raw_evidence,
    _verify_receipt_evidence_files,
    _verify_receipt_file,
    application_package_digest,
    load_image_descriptors,
    load_release_evidence,
    validate_application_package_evidence,
    validate_application_package_payload,
    validate_descriptor,
    validate_manifest_files,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.finalize_flow import (  # noqa: E402,F401
    _apply_candidate_evidence,
    _load_environment_receipts,
    _receipt_descriptor,
    finalize,
    main,
    parse_args,
)

if __name__ == "__main__":
    raise SystemExit(main())
