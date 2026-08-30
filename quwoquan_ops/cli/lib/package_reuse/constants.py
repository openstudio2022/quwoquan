"""package_reuse 包的共享 schema/字段集合常量。"""

from __future__ import annotations

from pathlib import Path

from quwoquan_ops.cli.lib.currentness import (
    CURRENTNESS_TIMEOUT_DETAIL_PREFIX,
    CURRENTNESS_TIMEOUT_SECONDS,
)

# 本文件位于包目录内，比原单文件多一层，因此取 parents[4] 才是仓库根。
ROOT = Path(__file__).resolve().parents[4]
FINGERPRINT_NAME = "package-fingerprint.json"
FINGERPRINT_SCHEMA = "stackctl-package-reuse-fingerprint"
PACKAGE_INPUT_CAPSULE_SCHEMA = "stackctl-package-input-capsule.v1"
PACKAGE_INPUT_CAPSULE_DIRECTORY = "input-capsule"
PACKAGE_VALIDATION_PURPOSES = frozenset({"self_verify", "currentness"})
_FINGERPRINT_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "target",
        "candidateType",
        "includeServices",
        "servicePackages",
        "reportRef",
        "baselineId",
        "sourceRevision",
        "workspaceStatusDigest",
        "deploymentInputs",
        "packageContent",
        "releaseInputClassification",
        "contractGraphDigest",
        "graphqlReadRegistry",
        "appLaunchBundle",
    }
)
_DIGEST_FIELDS = frozenset({"digest", "fileCount"})
_DEPLOYMENT_INPUT_FIELDS = frozenset({"roots", "capsuleRef", *_DIGEST_FIELDS})
_CAPSULE_FIELDS = frozenset(
    {
        "schema",
        "baselineId",
        "sourceRevision",
        "workspaceStatusDigest",
        "deploymentInputRoots",
        "deploymentInputDigest",
        "deploymentInputFileCount",
        "entries",
    }
)
_CAPSULE_ENTRY_FIELDS = frozenset(
    {"logicalPath", "capsulePath", "kind", "digest", "size", "mode"}
)
