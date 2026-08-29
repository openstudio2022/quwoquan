"""Research 隔离的策略快照与契约可用性判定。

与 `research_isolation_verification` 的分工是「判据从哪来」对「回执怎么裁」：
本模块只回答运行时策略当前长什么样、canonical 契约是否已提供所需操作，以及
在证据不成立时该报哪条 blocker；它不读写任何 verify run 回执。

这些判定是 PASS 的前置条件而非结论：策略字段缺失或契约里没有对应操作时，
下游必须 fail closed，不得以「探针跑过了」代替契约在场。
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from core.io import read_json
from core.paths import REPO_ROOT

IDENTITY_CONTRACT = (
    REPO_ROOT / "quwoquan_service/services/user-service/contracts/account/"
    "account_session/operations.yaml"
)
SIGNED_MEDIA_CONTRACT = (
    REPO_ROOT / "quwoquan_service/services/content-service/contracts/media/"
    "original_access_quota/operations.yaml"
)
SIGNED_MEDIA_POLICY = (
    REPO_ROOT / "quwoquan_service/services/content-service/contracts/media/"
    "original_access_quota/original_access_policy.yaml"
)
REQUIRED_IDENTITY_OPERATION = "IssueWhitelistedResearchSession"
REQUIRED_SIGNED_MEDIA_OPERATION = "ReserveOriginalImageAccessGrant"
REQUIRED_TRUE = (
    "identityWhitelistRequired",
    "sharingDisabled",
    "exportDisabled",
    "internalAppSignatureRequired",
    "researchBadgeRequired",
    "shortLivedSignedMediaUrlsRequired",
    "mediaAccessAuditLogRequired",
)
REQUIRED_FALSE = (
    "anonymousContentAccess",
    "anonymousMediaAccess",
    "publicContentDistribution",
    "searchIndexingDisabled",
)


class ResearchIsolationVerificationError(ValueError):
    """Research isolation evidence is unsafe, drifted, or not canonical."""


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def safe_segment(value: str, *, label: str) -> str:
    text = str(value or "").strip()
    candidate = Path(text)
    if (
        not text
        or text in {".", ".."}
        or candidate.is_absolute()
        or len(candidate.parts) != 1
        or "/" in text
        or "\\" in text
    ):
        raise ResearchIsolationVerificationError(f"{label} must be one safe segment")
    return text


def json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise ResearchIsolationVerificationError(
            f"{label} is unreadable: {path}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ResearchIsolationVerificationError(f"{label} must be an object: {path}")
    return dict(value)


def yaml_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ResearchIsolationVerificationError(
            f"{label} is unreadable: {path}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ResearchIsolationVerificationError(f"{label} must be an object: {path}")
    return dict(value)


def repository_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ResearchIsolationVerificationError(
            f"research isolation evidence must be repository-owned: {path}"
        ) from exc


def policy_snapshot(
    environment: str,
) -> tuple[Path, str, list[str], int | None]:
    path = REPO_ROOT / "quwoquan_ops/environments" / environment / "runtime.yaml"
    payload = yaml_object(path, label="research runtime policy")
    issues: list[str] = []
    if payload.get("productLifecycleState") != "research":
        issues.append("productLifecycleState must be research")
    isolation = payload.get("researchContentIsolation")
    if not isinstance(isolation, Mapping):
        issues.append("researchContentIsolation must be an object")
        isolation = {}
    issues.extend(
        f"researchContentIsolation.{field} must be true"
        for field in REQUIRED_TRUE
        if isolation.get(field) is not True
    )
    issues.extend(
        f"researchContentIsolation.{field} must be false"
        for field in REQUIRED_FALSE
        if isolation.get(field) is not False
    )
    ttl = isolation.get("signedMediaUrlMaxTtlSeconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= 900:
        issues.append(
            "researchContentIsolation.signedMediaUrlMaxTtlSeconds must be 1..900"
        )
        ttl = None
    return path, digest_bytes(path.read_bytes()), issues, ttl


def identity_contract_available() -> bool:
    payload = yaml_object(IDENTITY_CONTRACT, label="account session operations")
    routes = payload.get("api_routes")
    if not isinstance(routes, list):
        return False
    for raw in routes:
        if not isinstance(raw, Mapping):
            continue
        security = raw.get("security")
        response_fields = raw.get("response_fields")
        if (
            raw.get("operation") == REQUIRED_IDENTITY_OPERATION
            and raw.get("method") == "POST"
            and isinstance(security, Mapping)
            and security.get("auth_mode") == "required"
            and security.get("anonymous_policy") == "deny"
            and isinstance(response_fields, list)
            and {"subjectHash", "attestationId"}.issubset(response_fields)
        ):
            return True
    return False


def signed_media_contract_available() -> bool:
    payload = yaml_object(SIGNED_MEDIA_CONTRACT, label="signed media operations")
    policy = yaml_object(SIGNED_MEDIA_POLICY, label="signed media policy")
    routes = payload.get("api_routes")
    ttl = policy.get("grant_ttl_seconds")
    if not isinstance(routes, list) or not isinstance(ttl, int) or not 1 <= ttl <= 900:
        return False
    for raw in routes:
        if not isinstance(raw, Mapping):
            continue
        security = raw.get("security")
        fields = raw.get("response_fields")
        if (
            raw.get("operation") == REQUIRED_SIGNED_MEDIA_OPERATION
            and isinstance(security, Mapping)
            and security.get("auth_mode") == "required"
            and security.get("anonymous_policy") == "deny"
            and isinstance(fields, list)
            and {"originalUrl", "ttlSeconds", "auditId"}.issubset(fields)
        ):
            return True
    return False


def blocker(
    *,
    policy_issues: list[str],
) -> tuple[str, str, list[str]]:
    if policy_issues:
        return (
            "DATA.RESEARCH.ISOLATION_POLICY_INVALID",
            "; ".join(policy_issues),
            [],
        )
    if not identity_contract_available():
        return (
            "DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE",
            (
                "No canonical whitelisted research identity issuance/attestation "
                "operation is available"
            ),
            [repository_ref(IDENTITY_CONTRACT)],
        )
    if not signed_media_contract_available():
        return (
            "DATA.RESEARCH.SIGNED_MEDIA_ADAPTER_UNAVAILABLE",
            (
                "No canonical authenticated short-lived signed-media operation "
                "with audit identity is available"
            ),
            [
                repository_ref(SIGNED_MEDIA_CONTRACT),
                repository_ref(SIGNED_MEDIA_POLICY),
            ],
        )
    return (
        "DATA.RESEARCH.RUNTIME_PROOF_INCOMPLETE",
        (
            "Runtime identity, internal App, anonymous denial, egress denial and "
            "exact release readback probes are not implemented"
        ),
        [
            repository_ref(IDENTITY_CONTRACT),
            repository_ref(SIGNED_MEDIA_CONTRACT),
        ],
    )
