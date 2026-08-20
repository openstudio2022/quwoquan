"""Shared immutable types and identities for source-ready acquisition."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

PUBLIC_ACCESS = {
    "anonymousPublicAccess": True,
    "loginRequired": False,
    "captchaRequired": False,
    "paywallRequired": False,
    "drmProtected": False,
    "accessControlBypass": False,
}
class MediaWikiSourceReadyRejected(ValueError):
    """One object-level source candidate was unavailable or not admissible."""


@dataclass(frozen=True, slots=True)
class AcquiredAsset:
    body: bytes
    document: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AcquiredSourceReadyCandidate:
    carrier: str
    candidate: dict[str, Any]
    source_unit: dict[str, Any]
    body: bytes
    raw_evidence: bytes
    assets: tuple[AcquiredAsset, ...]
    source_selection_origin: str = "coverage_source"


def _sha256(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _stable_id(prefix: str, *values: object, size: int = 20) -> str:
    raw = "\n".join(str(value) for value in values).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:size]}"


def source_ready_sha256(body: bytes) -> str:
    return _sha256(body)


def source_ready_stable_id(prefix: str, *values: object, size: int = 20) -> str:
    return _stable_id(prefix, *values, size=size)


