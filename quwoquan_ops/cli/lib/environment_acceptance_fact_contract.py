"""Canonical v2 contract for environment acceptance facts.

The environment scheduler, schema validator, and promotion readers must consume
this single closed field set.  The retired profile-based v1 model is not
accepted here.
"""

from __future__ import annotations

import re
from pathlib import Path

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "environments"
    / "evidence"
    / "environment_acceptance_fact.schema.json"
)
SCHEMA = "quwoquan_ops.environment_acceptance_fact.v2"
DSSE_PAYLOAD_TYPE = "application/vnd.quwoquan.environment-acceptance-fact.v2+json"
ENVIRONMENTS = ("alpha", "beta", "gamma")
ACCEPTANCE_PROFILES = ("smoke", "integration", "release")
PREDECESSOR = {"alpha": None, "beta": "alpha", "gamma": "beta"}
NO_LIVE_ENVIRONMENT_REQUIRED = "IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED"
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_GIT_OID_RE = re.compile(r"^[a-f0-9]{40}(?:[a-f0-9]{24})?$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_EXACT_REF_KEYS = frozenset({"ref", "digest"})
_CANDIDATE_KEYS = frozenset({"candidateId", "commit", "tree"})
_SIGNER_KEYS = frozenset({"identity", "payloadType", "payload", "signature"})
_EVIDENCE_REF_FIELDS = (
    "runtimeIdentity",
    "dataLifecycle",
    "providerReadiness",
    "observabilityReadiness",
    "inspectEvidence",
    "doctorEvidence",
    "cleanupEvidence",
    "leaseClosureEvidence",
)
_EVIDENCE_ROLE_CONTRACT = {
    "runtimeIdentity": ("runtime-identity", frozenset({"passed", "ready"})),
    "dataLifecycle": ("data-lifecycle", frozenset({"passed", "closed"})),
    "providerReadiness": ("provider-readiness", frozenset({"passed", "ready"})),
    "observabilityReadiness": (
        "observability-readiness",
        frozenset({"passed", "ready"}),
    ),
    "inspectEvidence": ("inspect", frozenset({"passed"})),
    "doctorEvidence": ("doctor", frozenset({"passed"})),
    "cleanupEvidence": ("cleanup", frozenset({"closed"})),
    "leaseClosureEvidence": ("lease-closure", frozenset({"released"})),
}
_COMMON_FACT_KEYS = frozenset(
    {
        "schema",
        "factId",
        "environment",
        "profile",
        "status",
        "candidate",
        "impactPlanDigest",
        "caseResultRefs",
        *_EVIDENCE_REF_FIELDS,
        "predecessor",
        "expiresAt",
        "nonPromotable",
        "issuedAt",
        "signer",
    }
)
_FACT_KEYS_BY_STATUS = {
    "passed": _COMMON_FACT_KEYS,
    "not_required": _COMMON_FACT_KEYS | {"reasonCode"},
}

__all__ = [
    "ACCEPTANCE_PROFILES",
    "DSSE_PAYLOAD_TYPE",
    "ENVIRONMENTS",
    "NO_LIVE_ENVIRONMENT_REQUIRED",
    "PREDECESSOR",
    "SCHEMA",
    "SCHEMA_PATH",
]
