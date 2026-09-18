"""Canonical v2 contract for environment acceptance facts.

The environment scheduler, schema validator, and promotion readers must consume
this single closed field set.  The retired profile-based v1 model is not
accepted here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
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
# lane 验收默认只真跑 Alpha；ImpactPlan 判定 Beta 敏感但用户未显式 opt-in 时，Beta 以该原因码写 typed not_required。
BETA_OPTIONAL_BY_POLICY = "ACCEPTANCE.BETA_OPTIONAL_BY_POLICY"
# 源码合入 origin/dev1.0 默认不启 Alpha live；环境/UAT/Data 激活后移到已发布 SHA。
ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV = "ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV"
NOT_REQUIRED_REASON_CODES = frozenset(
    {NO_LIVE_ENVIRONMENT_REQUIRED, BETA_OPTIONAL_BY_POLICY, ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV}
)


def not_required_allowed(environment: str, reason_code: str) -> bool:
    """Alpha 仅允许延后到已发布 dev；Beta 允许 no-live 或政策跳过；Gamma 不得 not_required。"""
    if environment == "beta":
        return reason_code in {NO_LIVE_ENVIRONMENT_REQUIRED, BETA_OPTIONAL_BY_POLICY}
    if environment == "alpha":
        return reason_code == ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV
    return False


def source_admitted_alpha(fact: Mapping[str, object] | None) -> bool:
    """写入 origin/dev1.0 承认 Alpha passed，或 typed 延后到已发布 SHA。"""
    if not isinstance(fact, Mapping):
        return False
    status = fact.get("status")
    if status == "passed":
        return True
    return status == "not_required" and fact.get("reasonCode") == ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV


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
    "ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV",
    "BETA_OPTIONAL_BY_POLICY",
    "DSSE_PAYLOAD_TYPE",
    "ENVIRONMENTS",
    "NOT_REQUIRED_REASON_CODES",
    "NO_LIVE_ENVIRONMENT_REQUIRED",
    "PREDECESSOR",
    "SCHEMA",
    "SCHEMA_PATH",
    "not_required_allowed",
    "source_admitted_alpha",
]
