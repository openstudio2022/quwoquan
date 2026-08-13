"""startup_attempt_receipt 包共享常量（原单文件顶部常量逐字搬移）。

``verify_external_provider_governance.py`` 按文本扫描本文件的
``"providerRuntimeDigest"`` token；该字段的 wire 名称属于 receipt 契约，
不得改名。
"""

from __future__ import annotations

import re

SCHEMA = "stackctl-local-startup-attempt"
STATUSES = ("prepared", "partial", "running", "stopped")
WORKLOADS = ("full", "content-release", "content-commercial")
RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "attemptId",
        "env",
        "target",
        "status",
        "workload",
        "composeProject",
        "candidateDigest",
        "configurationDigest",
        "providerRuntimeDigest",
        "observabilityLogSinkDigest",
        "imageTransportTag",
        "imageComposition",
        "runRoot",
        "startedAt",
        "updatedAt",
        "failure",
        "cleanupFailure",
    }
)
_TRANSITIONS = {
    None: {"prepared"},
    "prepared": {"partial", "stopped"},
    "partial": {"partial", "running", "stopped"},
    "running": {"stopped"},
    "stopped": {"prepared"},
}
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_IMAGE_ROLE = re.compile(r"[a-z][a-z0-9-]*")
_OCI_SCHEMA = "stackctl-package-oci-images"
_OCI_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "target",
        "configurationDigest",
        "buildInputDigest",
        "imageDigest",
        "images",
    }
)
_OCI_IMAGE_FIELD_SETS = (
    frozenset({"ref", "imageDigest"}),
    frozenset({"buildInputDigest", "ref", "imageDigest"}),
)
_IMAGE_COMPOSITION_FIELDS = frozenset(
    {
        "configurationDigest",
        "buildInputDigest",
        "imageDigest",
        "imageVersion",
        "images",
        "ociImages",
    }
)
_ACTIVE_CANDIDATE_FIELDS = frozenset(
    {
        "schema",
        "candidateType",
        "target",
        "baselineId",
        "candidateDir",
    }
)
_IMMUTABLE_RECEIPT_IDENTITY_FIELDS = (
    "env",
    "target",
    "workload",
    "composeProject",
    "candidateDigest",
    "configurationDigest",
    "providerRuntimeDigest",
    "observabilityLogSinkDigest",
    "imageTransportTag",
    "imageComposition",
    "runRoot",
    "startedAt",
)
_FANOUT_TRANSACTION_SCHEMA = "stackctl-startup-attempt-fanout-transaction"
_FANOUT_TRANSACTION_FIELDS = frozenset(
    {
        "schema",
        "transactionId",
        "newPayload",
        "destinations",
    }
)
_FANOUT_DESTINATION_FIELDS = frozenset({"path", "oldPayload"})
