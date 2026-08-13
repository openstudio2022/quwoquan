"""Provider Conformance 契约常量：九宫格 cell、字段集、模式与测试层根目录。"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import re

from quwoquan_ops.cli.lib import external_provider_governance as governance

ROOT = Path(__file__).resolve().parents[4]

EVIDENCE_SCHEMA = ROOT / "quwoquan_ops" / "environments" / "provider_conformance_evidence.schema.json"
# Alpha/Beta/Gamma exercise Port-equivalent substitutes. Prod owns the
# independent hosted real-Provider rollout receipt.
ENVIRONMENTS = ("alpha", "beta", "gamma")
RELEASE_ENVIRONMENT = "prod"
RELEASE_READINESS_ENVIRONMENTS = frozenset({RELEASE_ENVIRONMENT})
EVIDENCE_ENVIRONMENTS = (*ENVIRONMENTS, RELEASE_ENVIRONMENT)
READINESS_ENVIRONMENTS = EVIDENCE_ENVIRONMENTS
LAYERS = ("local_contract", "api_integration", "user_acceptance")
CELL_PROFILES = {
    ("alpha", "local_contract"): "baseline",
    ("beta", "local_contract"): "baseline",
    ("gamma", "local_contract"): "baseline",
    ("alpha", "api_integration"): "smoke",
    ("beta", "api_integration"): "integration",
    ("gamma", "api_integration"): "release",
    ("alpha", "user_acceptance"): "smoke",
    ("beta", "user_acceptance"): "integration",
    ("gamma", "user_acceptance"): "release",
}


def execution_profile_for(environment: str, layer: str) -> str | None:
    """Return the only permitted profile for a conformance evidence cell."""
    if environment == RELEASE_ENVIRONMENT:
        return "release" if layer == "user_acceptance" else None
    return CELL_PROFILES.get((environment, layer))


def requires_release_readiness(environment: str, layer: str) -> bool:
    return environment in RELEASE_READINESS_ENVIRONMENTS and layer == "user_acceptance"
MESSAGE_TRANSPORT_CAPABILITY_ID = governance.MESSAGE_TRANSPORT_CAPABILITY_ID
MESSAGE_TRANSPORT_METRIC_NAMES = governance.MESSAGE_TRANSPORT_REQUIRED_METRICS
MESSAGE_TRANSPORT_METRIC_REFS = {
    "pending_lag": "prometheus://qwq_message_transport_pending_lag",
    "dead_letter": "prometheus://qwq_message_transport_dead_letter",
    "publish_p95": "promql://qwq_message_transport_publish_p95",
    "consume_p95": "promql://qwq_message_transport_consume_p95",
}
REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "adapterId",
        "capabilityId",
        "bindingRoots",
        "environment",
        "testLayer",
        "executionProfile",
        "status",
        "executedAt",
        "artifactRef",
        "artifactDigest",
        "artifactAttestation",
        "nonPromotable",
        "sourceTreeState",
        "commitReview",
        "candidateStatus",
        "candidateReceiptRef",
        "candidateReceiptDigest",
        "attestationAuthority",
        "testArtifactRef",
        "testArtifactDigest",
        "testSource",
        "testSourceDigest",
        "testCommand",
        "testTarget",
        "typedPort",
        "contractRef",
        "commit",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "assertionCount",
        "assertionIds",
        "networkBoundary",
        "dataDigest",
        "cleanupReceipt",
        "acceptanceRefs",
        "observabilityRefs",
    }
)
RELEASE_READINESS_FIELDS = frozenset(
    {
        "bindingPreflightReceiptRef",
        "adapterHealthReceiptRef",
        "switchCompatibilityReceiptRef",
        "callbackDrainReceiptRef",
        "lastGoodReceiptRef",
        "rollbackReceiptRef",
    }
)
EXECUTION_REPORT_SCHEMA = "provider-conformance-test-report"
EXECUTION_REPORT_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "adapterId",
        "capabilityId",
        "bindingRoots",
        "environment",
        "testLayer",
        "executionProfile",
        "status",
        "executedAt",
        "commit",
        "nonPromotable",
        "sourceTreeState",
        "commitReview",
        "candidateStatus",
        "candidateReceiptRef",
        "candidateReceiptDigest",
        "attestationAuthority",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "testArtifactRef",
        "testArtifactDigest",
        "testSource",
        "testSourceDigest",
        "testCommand",
        "testTarget",
        "typedPort",
        "contractRef",
        "assertionIds",
        "networkBoundary",
        "dataDigest",
        "testSource",
        "testCommand",
        "exitCode",
    }
)
CASE_RESULT_SCHEMA = "provider-conformance-case-results"
CASE_RESULT_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "status",
        "adapterId",
        "capabilityId",
        "environment",
        "testLayer",
        "typedPort",
        "contractRef",
        "networkBoundary",
        "testTarget",
        "configDigest",
        "assertionIds",
        "caseResults",
        "dataDigest",
        "cleanupReceipt",
        "observabilityRefs",
    }
)
CASE_RESULT_RELEASE_FIELDS = frozenset({"releaseReadiness"})
REMOTE_READBACK_SCHEMA = "provider-remote-uat-readback"
CASE_RESULT_REMOTE_FIELDS = frozenset({"nativeReadback"})
NATIVE_READBACK_ARTIFACT_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]*\.native-device-readback\.json$"
)
SOURCE_METADATA_RE = re.compile(
    r"^\s*(?:#|//)\s*provider_conformance:\s*(\{.+\})\s*$"
)
SOURCE_STATIC_BLOCK_RE = re.compile(
    r"\b(?:should[\s_-]*block|gate[\s_-]*block|not[\s_-]*run|dry[\s_-]*run)\b",
    re.IGNORECASE,
)
SOURCE_DYNAMIC_EXECUTOR_RE = re.compile(
    r"(?:QWQ_PROVIDER_CONFORMANCE_EXECUTOR_COMMAND_JSON|"
    r"external_provider_executor)",
)
TEST_LAYER_ROOTS = {
    "local_contract": ROOT / "quwoquan_ops" / "tests" / "local_contract",
    "api_integration": ROOT
    / "quwoquan_ops"
    / "tests"
    / "acceptance"
    / "api_integration",
    "user_acceptance": ROOT
    / "quwoquan_ops"
    / "tests"
    / "acceptance"
    / "user_acceptance",
}
PUBLIC_ASSERTION_IDS = frozenset(
    {
        "provider.success",
        "provider.validation",
        "provider.auth",
        "provider.network_dns",
        "provider.timeout",
        "provider.throttle",
        "provider.retry",
        "provider.idempotency",
        "provider.callback_ordering",
        "provider.redaction",
        "provider.observability",
    }
)
RELEASE_ASSERTION_IDS = frozenset(
    {
        "provider.adapter_health",
        "provider.adapter_switch",
        "provider.adapter_rollback",
    }
)
ALLOWED_FIELDS = REQUIRED_FIELDS | {"failure", "releaseReadiness"}
ADAPTER_PATTERN = re.compile(r"^(?:ext|infra|data|dev|cap)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$")
CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
SHA256_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
ARTIFACT_ATTESTATION_PATTERN = re.compile(
    r"^(?:hmac-sha256|local-sha256):[a-f0-9]{64}$"
)
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{7,64}$")
ASSERTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
RECEIPT_REF_PATTERN = re.compile(r"^receipt:[a-z0-9][a-z0-9._:-]{2,255}$")
SENSITIVE_RECEIPT_REF_PATTERN = re.compile(
    r"(?:endpoint|secret|credential|token|password|https?|://)", re.IGNORECASE
)
MAX_EVIDENCE_AGE = timedelta(hours=24)
