"""Canonical schema and closed-set constants for environment acceptance facts."""

from __future__ import annotations

import re
from pathlib import Path

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "environments"
    / "evidence"
    / "environment_acceptance_fact.schema.json"
)
SCHEMA = "quwoquan_ops.environment_acceptance_fact.v1"
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
PREDECESSOR = {"alpha": None, "beta": "alpha", "gamma": "beta", "prod": "gamma"}
PROD_ROLLOUT_STAGES = ("canary", "5", "20", "50", "100")
ACCEPTANCE_PROFILES = ("environment_promotion", "m1_api_consumer")
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_PLATFORMS = frozenset({"android", "ios"})
_DEVICE_PROFILES = frozenset({"rehearsal", "promotable", "production"})
_ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")
_CARRIERS = ("homepage", "article", "image", "video")
_COMMON_FACT_KEYS = frozenset(
    {
        "schema",
        "factId",
        "acceptanceProfile",
        "environment",
        "target",
        "releaseId",
        "releaseDigest",
        "importRunId",
        "verifyRunId",
        "samplePlanRef",
        "samplePlanDigest",
        "requiredRawResults",
        "dataReadiness",
        "createdAt",
        "sourceFingerprint",
    }
)
_PROMOTION_FACT_KEYS = frozenset(
    {
        "targetBindingRefs",
        "activeCas",
        "lifecycleExit",
        "providerReadiness",
        "observabilityReadiness",
        "rollbackReadiness",
        "predecessorAcceptance",
        "resourceFinalization",
        "prodReleaseFacts",
    }
)
_M1_FACT_KEYS = frozenset({"consumerHealth", "manifestDigest"})
_FACT_KEYS_BY_PROFILE = {
    "environment_promotion": _COMMON_FACT_KEYS | _PROMOTION_FACT_KEYS,
    "m1_api_consumer": _COMMON_FACT_KEYS | _M1_FACT_KEYS,
}
_EXACT_REF_KEYS = frozenset({"ref", "digest"})
_TARGET_BINDING_KEYS = frozenset({"ref", "digest", "platform", "deviceProfile"})
_RAW_RESULT_KEYS = frozenset({"ref", "digest", "slotId", "status"})
_ACTIVE_CAS_KEYS = frozenset(
    {"ref", "digest", "readbackRef", "readbackDigest", "releaseId", "releaseDigest"}
)
_PREDECESSOR_KEYS = frozenset({"environment", "factId", "ref", "digest"})
_FINALIZATION_KEYS = frozenset(
    {"leaseRevocationRefs", "lockReleaseRefs", "gcProtectionRefs"}
)
_PROD_FACT_KEYS = frozenset(
    {"engineeringEligibility", "durableApproval", "rolloutStages", "rollbackReadiness"}
)
__all__ = [
    "ACCEPTANCE_PROFILES",
    "ENVIRONMENTS",
    "PREDECESSOR",
    "PROD_ROLLOUT_STAGES",
    "SCHEMA",
    "SCHEMA_PATH",
]
