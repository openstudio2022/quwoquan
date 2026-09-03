"""test-live content binding 的 schema、字段闭集、正则与失败类型。

原单文件 ``test_live_content_binding.py`` 拆分出的共享常量子模块。
"""

from __future__ import annotations

import re

SCHEMA = "stackctl.mutable_test_live_content_binding"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,191}")
_BINDING_FIELDS = frozenset(
    {
        "schema",
        "launchPolicy",
        "nonPromotable",
        "contentBindingState",
        "retentionClass",
        "environment",
        "target",
        "startupAttemptId",
        "startupIdentity",
        "releaseId",
        "verifyRunId",
        "manifestDigest",
        "readinessPhase",
        "releaseAttestationRef",
        "releaseAttestationDigest",
        "readinessReceiptRef",
        "readinessReceiptDigest",
        "dataSourceIdentity",
        "releaseHeaderRef",
        "releaseHeaderDigest",
        "releaseUatSamplePlanRef",
        "releaseUatSamplePlanDigest",
        "appUatPlan",
        "appUatPlanDigest",
        "activationEnvelope",
        "activationEnvelopeDigest",
        "lifecycleExitRef",
        "lifecycleExitDigest",
        "boundAt",
    }
)
_STARTUP_IDENTITY_FIELDS = (
    "sourceRevision",
    "workspaceStatusDigest",
    "mutableStateDigest",
    "composeDigest",
    "configurationDigest",
    "providerRuntimeDigest",
    "observabilityLogSinkDigest",
    "resolverHandoffDigest",
)
_LIFECYCLE_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "sourceOwner",
        "exitRunId",
        "originalReleaseId",
        "originalManifestDigest",
        "originalImportRunId",
        "originalVerifyRunId",
        "originalImportResultRef",
        "originalVerifyResultRef",
        "rollbackToReleaseId",
        "rollbackToManifestDigest",
        "rollbackRunId",
        "rollbackVerifyRunId",
        "rollbackResultRef",
        "rollbackVerifyResultRef",
        "replayImportRunId",
        "replayVerifyRunId",
        "replayManifestDigest",
        "replayImportResultRef",
        "replayVerifyResultRef",
        "recordedAt",
        "verificationChecksum",
        "passed",
    }
)


class UnsafeTestLiveContentBindingPath(ValueError):
    """An evidence or binding path could not be read without following links."""
