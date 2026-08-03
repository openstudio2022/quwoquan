"""Fail-closed governed isolation contract for research content releases."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .common import ROOT, load_json_yaml


_REQUIRED_TRUE = (
    "identityWhitelistRequired",
    "sharingDisabled",
    "exportDisabled",
    "searchIndexingDisabled",
    "internalAppSignatureRequired",
    "researchBadgeRequired",
    "shortLivedSignedMediaUrlsRequired",
    "mediaAccessAuditLogRequired",
)
_REQUIRED_FALSE = (
    "anonymousContentAccess",
    "anonymousMediaAccess",
    "publicContentDistribution",
)


def verify_research_content_isolation(environment: str) -> dict[str, Any]:
    path = ROOT / "quwoquan_ops" / "environments" / environment / "runtime.yaml"
    payload = load_json_yaml(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path}: runtime must be an object")
    if payload.get("productLifecycleState") != "research":
        raise ValueError(
            f"{environment}: productLifecycleState must be research"
        )
    isolation = payload.get("researchContentIsolation")
    if not isinstance(isolation, Mapping):
        raise ValueError(
            f"{environment}: researchContentIsolation is missing"
        )
    issues = [
        f"{environment}: researchContentIsolation.{field} must be true"
        for field in _REQUIRED_TRUE
        if isolation.get(field) is not True
    ]
    issues.extend(
        f"{environment}: researchContentIsolation.{field} must be false"
        for field in _REQUIRED_FALSE
        if isolation.get(field) is not False
    )
    ttl = isolation.get("signedMediaUrlMaxTtlSeconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= 900:
        issues.append(
            f"{environment}: signedMediaUrlMaxTtlSeconds must be within 1..900"
        )
    if issues:
        raise ValueError("; ".join(issues))
    return {
        "schema": "quwoquan_ops.research_content_isolation",
        "environment": environment,
        "productLifecycleState": "research",
        "releaseClass": "research",
        "policyRef": path.relative_to(ROOT).as_posix(),
        "identityWhitelistRequired": True,
        "anonymousContentAccess": False,
        "anonymousMediaAccess": False,
        "publicContentDistribution": False,
        "sharingDisabled": True,
        "exportDisabled": True,
        "searchIndexingDisabled": True,
        "internalAppSignatureRequired": True,
        "researchBadgeRequired": True,
        "shortLivedSignedMediaUrlsRequired": True,
        "signedMediaUrlMaxTtlSeconds": ttl,
        "mediaAccessAuditLogRequired": True,
    }


__all__ = ["verify_research_content_isolation"]
