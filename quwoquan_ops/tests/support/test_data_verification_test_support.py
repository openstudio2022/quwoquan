"""test-data verification 合约测试共享 helpers 与会话替身
（自 test_test_data_verification__local_contract_test 拆分）。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from enum import StrEnum
from pathlib import Path
from threading import Event, Lock
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.test_data.api import (
    AssertionStatus,
    BusinessCaseRunner,
    CaseAssertion,
    CaseExecution,
    CaseRef,
    ExecutedCase,
    ReceiptRef,
)
from quwoquan_ops.cli.lib.test_data.cases import canonical_acceptance_suite
from quwoquan_ops.cli.lib.test_data.capabilities.assistant_service import (
    ASSISTANT_PROMPT_RUN,
)
from quwoquan_ops.cli.lib.test_data.capabilities.common import (
    AcceptanceActorSet,
    ActorRole,
)
from quwoquan_ops.cli.lib.test_data.capabilities.user_service import (
    AUTHENTICATED_ACTORS,
    AuthenticatedActorsParams,
)
from quwoquan_ops.cli.lib.test_data.serialization import (
    case_request_document,
    collect_request_graph,
    load_case_requests,
    request_graph_document,
)
from quwoquan_ops.cli.lib.test_data.model import canonical_digest
from quwoquan_ops.cli.lib.test_data_verification import (
    build_candidate_binding,
    build_provider_evidence_document,
    build_test_data_handoff,
    load_provider_evidence,
    load_test_data_handoff,
    run_test_data_verification,
)


def _manifest() -> dict[str, object]:
    return {
        "sourceRevision": "a" * 40,
        "baselineId": "sha256:" + "1" * 64,
        "packageDigest": "sha256:" + "2" * 64,
        "runtimeConfigDigest": "sha256:" + "3" * 64,
        "release": {
            "candidate": {
                "releaseId": "release-1",
                "releaseDigest": "sha256:" + "4" * 64,
            }
        },
    }


def _readiness(
    *, environment: str = "gamma", release_id: str = "release-1",
    manifest_digest: str = "sha256:" + "4" * 64,
    post_ids: tuple[str, ...] = ("post-1",), entity_ref: str = "entity-1",
    source_identities: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """直接构造并验证现役 Data schema；不填充已退役类别字段。"""
    from quwoquan_ops.cli.commands.app_preflight_readiness import _validate_data_schema

    source_identities = source_identities or [{
        "sourceRevision": "sha256:" + "a" * 64,
        "sourceDigest": "sha256:" + "b" * 64,
        "entityCatalogDigest": "sha256:" + "c" * 64,
        "executionIds": ["execution-1"],
    }]
    source = {
        "sourceIdentities": source_identities,
        "sourceIdentitySetDigest": canonical_digest({
            "schema": "quwoquan_data.source_identity_set",
            "sourceIdentities": source_identities,
        }),
    }
    identity = {"environment": environment, "releaseId": release_id,
                "manifestDigest": manifest_digest}
    prefix = f"env/{environment}/runs/data-release/{release_id}"
    def operation(path: str, page: str) -> dict[str, object]:
        return {"path": path, "pageId": page, "status": 200,
                "requestId": "DATA.fixture", "traceId": "TRACE.fixture",
                "startedAt": "2026-09-09T00:00:00Z",
                "endedAt": "2026-09-09T00:00:00.001Z", "durationMs": 1}
    queries = (
        ("discovery_work", "identity=work&limit=20"),
        ("typed_article", "identity=work&type=article&limit=20"),
        ("typed_image", "identity=work&type=image&limit=20"),
        ("typed_video", "identity=work&type=video&limit=20"),
        ("homepage_recommend", "sort=recommend&channelId=recommend&limit=20"),
        ("premium_stream", "sort=recommend&channelId=premium_stream&limit=20"),
    )
    activation = {
        "schema": "quwoquan_data.environment_activation_envelope", **identity, **source,
        "importRunId": "import-1", "verifyRunId": "verify-1",
        "importReportRef": f"{prefix}/apply-1/import.json",
        "importReportDigest": "sha256:" + "6" * 64,
    }
    readiness = {
        "schema": "quwoquan_data.environment_release_readiness", **identity, **source,
        "sourceOwner": "qwq_data", "releaseKind": "content", "passed": True,
        "containsUnverifiedAssets": True, "authorizationRequiredAssetIds": ["media-1"],
        "rightsStatusCounts": {"verified": 0, "unverified": 1, "restricted": 0, "unknown": 0},
        "researchAcceptedCount": 1, "commercialAcceptedCount": 0,
        "importRunId": "import-1", "verifyRunId": "verify-1",
        "postIds": list(post_ids), "creatorIds": ["creator-1"],
        "entityRefs": [entity_ref], "tagRefs": ["tag-1"], "mediaAssetIds": ["media-1"],
        "counts": {"entities": 1, "posts": len(post_ids), "creators": 1,
                   "avatarAssets": 1, "imageAssets": 1, "tags": 1, "mediaAssets": 1,
                   "discoveryPosts": len(post_ids), "premiumPlayableVideos": 1},
        "guestActorHash": "sha256:" + "7" * 64,
        "guestLogin": operation("/auth/login/anonymous", "user.login.anonymous"),
        "feedQueries": [{"name": name, "path": "/content/feed", "query": query,
                         "status": 200, "releaseBound": True,
                         "matchedPostIds": [post_ids[-1]],
                         "requests": [operation("/content/feed", "content.feed.list")]}
                        for name, query in queries],
        "contentImportReportRef": activation["importReportRef"],
        "creatorAttributionRef": f"{prefix}/apply-1/creator-import.json",
        "tagAttributionRef": f"{prefix}/verify-1/tag-attribution.json",
        "homepageApiVerificationRef": f"{prefix}/verify-1/homepage-api-verification.json",
        "postApiVerificationRef": f"{prefix}/verify-1/post-api-verification.json",
        "mediaManifestRef": f"data/releases/{release_id}/payload/media_manifest.json",
        "mediaManifestDigest": "sha256:" + "8" * 64,
        "activationEnvelope": activation, "activationEnvelopeDigest": canonical_digest(activation),
        "verifiedAt": "2026-09-09T00:00:00Z",
    }
    readiness["verificationChecksum"] = canonical_digest(readiness)
    _validate_data_schema(readiness, "environment_release_readiness")
    return readiness


def _with_checksum(payload: dict[str, object]) -> dict[str, object]:
    unsigned = {
        key: value for key, value in payload.items() if key != "verificationChecksum"
    }
    return {**unsigned, "verificationChecksum": canonical_digest(unsigned)}


class VerificationCaseId(StrEnum):
    ACTORS_READY = "actors-ready"
    ACTORS_READY_2 = "actors-ready-2"
    ACTORS_READY_3 = "actors-ready-3"
    ACTORS_READY_4 = "actors-ready-4"


class ActorsReadyBusinessCase(BusinessCaseRunner[AcceptanceActorSet]):
    result_type = AcceptanceActorSet

    @classmethod
    def execute(cls, value, context):
        return CaseExecution(
            (CaseAssertion("actor-authenticated", AssertionStatus.PASSED),)
        )


class _Session:
    def __init__(self, receipt: ReceiptRef) -> None:
        self._receipt = receipt

    def execute(self, case):
        return ExecutedCase(
            case_id=str(case.case_id.value),
            execution=CaseExecution(
                (CaseAssertion("actor-authenticated", AssertionStatus.PASSED),)
            ),
            candidate_binding_digest="sha256:" + "c" * 64,
            test_data_instance_id="mock-instance",
            request_id=case.request.request_id,
            provision_receipt=self._receipt,
            test_body_receipt=ReceiptRef(
                self._receipt.path.with_name("test-body.json"),
                "sha256:" + "b" * 64,
            ),
            readback_receipts=(
                ReceiptRef(
                    self._receipt.path.with_name("readback.json"),
                    "sha256:" + "d" * 64,
                ),
            ),
            cleanup_receipts=(
                ReceiptRef(
                    self._receipt.path.with_name("cleanup.json"),
                    "sha256:" + "e" * 64,
                ),
            ),
        )


class _ParallelSession:
    def __init__(self, tracker: "_ParallelTracker", receipt: ReceiptRef) -> None:
        self._tracker = tracker
        self._receipt = receipt

    def execute(self, case):
        self._tracker.enter()
        try:
            return _Session(self._receipt).execute(case)
        finally:
            self._tracker.exit()


class _FailedSession(_Session):
    def execute(self, case):
        return ExecutedCase(
            case_id=str(case.case_id.value),
            execution=CaseExecution(
                (CaseAssertion("business-readback", AssertionStatus.FAILED),)
            ),
            candidate_binding_digest="sha256:" + "c" * 64,
            test_data_instance_id="mock-instance",
            request_id=case.request.request_id,
            provision_receipt=self._receipt,
            test_body_receipt=ReceiptRef(
                self._receipt.path.with_name("test-body.json"),
                "sha256:" + "b" * 64,
            ),
            readback_receipts=(
                ReceiptRef(
                    self._receipt.path.with_name("readback.json"),
                    "sha256:" + "d" * 64,
                ),
            ),
            cleanup_receipts=(
                ReceiptRef(
                    self._receipt.path.with_name("cleanup.json"),
                    "sha256:" + "e" * 64,
                ),
            ),
        )


class _ParallelTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._overlap = Event()
        self.active = 0
        self.peak = 0

    def enter(self) -> None:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active >= 2:
                self._overlap.set()
        if not self._overlap.wait(timeout=1):
            raise RuntimeError("selected roots did not overlap")

    def exit(self) -> None:
        with self._lock:
            self.active -= 1


def _run_summary(*, executed: int = 1) -> tuple[dict[str, object], ...]:
    return (
        {
            "loadedProviders": ["user_service"],
            "requiredProviders": ["user_service"],
            "operationCount": 2 * executed,
            "executed": executed,
            "dataPreparationMs": 1,
            "criticalPathMs": 1,
            "maxObservedConcurrency": min(executed, 4),
        },
    )


