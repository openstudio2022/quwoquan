"""Failure-isolated provider candidate batches for professional videos."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.paths import SOURCE_ACQUISITION_ROOT

from content.source.professional_commons_video_input_evidence import (
    CommonsVideoInputError,
    digest,
)
from content.source.professional_video_acquisition import (
    ProfessionalVideoAcquisitionBlocked,
)
from content.source.professional_video_store import ProfessionalVideoCasCollision
from content.source.research.text_match import _normalized_title

COMMONS_INPUT_ROOT = SOURCE_ACQUISITION_ROOT / "video"


@dataclass(frozen=True, slots=True)
class VideoSourceProfile:
    """Registered provider identity consumed by the shared acquisition chain."""

    provider: str
    platform: str
    display_name: str
    source_kind: str
    acquisition_path: str
    candidate_directory: str
    asset_prefix: str
    credential_assertion: str
    time_bucket: str


COMMONS_VIDEO_PROFILE = VideoSourceProfile(
    provider="wikimedia_commons_video",
    platform="Wikimedia Commons",
    display_name="Wikimedia Commons 公开旅行视频",
    source_kind="tourism_video_site",
    acquisition_path="public_direct",
    candidate_directory="commons-direct",
    asset_prefix="commons-video",
    credential_assertion="no_cookie_no_api_key_no_account_session",
    time_bucket="commons-unranked",
)
STOCK_VIDEO_PROFILES = {
    "pexels_videos": VideoSourceProfile(
        provider="pexels_videos",
        platform="Pexels Videos",
        display_name="Pexels 免费视频素材",
        source_kind="tourism_video_site",
        acquisition_path="supported_api",
        candidate_directory="pexels-direct",
        asset_prefix="pexels-video",
        credential_assertion="api_key_discovery_anonymous_asset_download",
        time_bucket="pexels-unranked",
    ),
    "pixabay_videos": VideoSourceProfile(
        provider="pixabay_videos",
        platform="Pixabay Videos",
        display_name="Pixabay 免费视频素材",
        source_kind="tourism_video_site",
        acquisition_path="supported_api",
        candidate_directory="pixabay-direct",
        asset_prefix="pixabay-video",
        credential_assertion="api_key_discovery_anonymous_asset_download",
        time_bucket="pixabay-unranked",
    ),
}


def candidate_token(
    candidate: Mapping[str, Any],
    *,
    entity_id: str,
    aliases: Sequence[str],
    source_identity: Mapping[str, str],
) -> str:
    return digest(
        {
            "entityId": entity_id,
            "entityAliases": list(aliases),
            "assetUrl": str(candidate["assetUrl"]),
            "sourcePostUrl": str(candidate["sourcePostUrl"]),
            "title": str(candidate["title"]),
            "creator": str(candidate["originalCreatorName"]),
            "license": str(candidate["rightsBasis"]),
            "termsUrl": str(candidate["termsUrl"]),
            "sourceRevision": source_identity["sourceRevision"],
            "sourceDigest": source_identity["sourceDigest"],
            "entityCatalogDigest": source_identity["entityCatalogDigest"],
        }
    ).removeprefix("sha256:")[:24]


class CommonsVideoBatchBlocked(CommonsVideoInputError):
    """All discovered candidates were independently excluded."""

    def __init__(self, outcomes: Sequence[Mapping[str, Any]]) -> None:
        self.outcomes = [dict(row) for row in outcomes]
        codes = ",".join(
            sorted({str(row.get("failureCode") or "") for row in self.outcomes})
        )
        pending = [
            row for row in self.outcomes
            if row.get("failureCode") == "DATA.SOURCE.HOST_REVIEW_PENDING"
        ]
        next_step = (
            "; nextAction=record_host_source_review_result pending="
            + json.dumps(
                [
                    {
                        "assetId": row.get("assetId"),
                        "requestRef": row.get("requestRef"),
                        "reentryRef": row.get("reentryRef"),
                    }
                    for row in pending
                ],
                ensure_ascii=False,
                sort_keys=True,
            )
            if pending
            else ""
        )
        super().__init__(
            "DATA.SOURCE.VIDEO_BATCH_NO_SUCCESS",
            f"no discovered video candidate was admitted; exclusions={codes}{next_step}",
        )


@dataclass(frozen=True, slots=True)
class ProviderVideoBatchDependencies:
    load_handoff: Callable[[Path], Mapping[str, Any]]
    file_sha256: Callable[[Path], str]
    candidate_token: Callable[..., str]
    prepare_candidate: Callable[..., tuple[Path, dict[str, Any]]]
    acquire_videos: Callable[..., tuple[dict[str, Any], Path]]
    safe_ref: Callable[[Path, Path], str]


def _normal_aliases(entity_id: str, aliases: Sequence[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in (entity_id, *aliases):
        normalized = _normalized_title(str(value))
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(str(value).strip())
    if not unique:
        raise CommonsVideoInputError(
            "DATA.SOURCE.ENTITY_MISMATCH", "entity aliases are empty"
        )
    return unique


def _candidate_asset_id(
    candidate: Mapping[str, Any],
    *,
    index: int,
    entity_id: str,
    aliases: Sequence[str],
    source_identity: Mapping[str, str],
    profile: VideoSourceProfile,
    dependencies: ProviderVideoBatchDependencies,
) -> str:
    try:
        token = dependencies.candidate_token(
            candidate,
            entity_id=entity_id,
            aliases=aliases,
            source_identity=source_identity,
        )
    except Exception:  # noqa: BLE001 - diagnostic identity for malformed candidate.
        token = digest(
            {
                "index": index,
                "candidate": dict(candidate),
                "sourceIdentity": dict(source_identity),
            }
        ).removeprefix("sha256:")[:24]
    return f"{profile.asset_prefix}-{token}"


def _candidate_exclusion(
    candidate: Mapping[str, Any],
    *,
    index: int,
    entity_id: str,
    aliases: Sequence[str],
    source_identity: Mapping[str, str],
    profile: VideoSourceProfile,
    root: Path,
    error: BaseException,
    prepared_outcome: Mapping[str, Any],
    dependencies: ProviderVideoBatchDependencies,
) -> dict[str, Any]:
    if isinstance(error, ProfessionalVideoAcquisitionBlocked):
        row = error.receipt["assets"][0]
        return {
            **dict(prepared_outcome),
            "assetId": str(row["assetId"]),
            "status": "excluded",
            "receiptRef": dependencies.safe_ref(error.receipt_path, root),
            "receiptDigest": str(error.receipt["receiptDigest"]),
            "contentSha256": str(row["contentSha256"]),
            "acquisitionStatus": str(row["acquisitionStatus"]),
            "distributionDecision": str(row["distributionDecision"]),
            "failureCode": str(row["failureCode"]),
            "failure": str(row["failure"]),
        }
    code = getattr(error, "code", "")
    if not isinstance(code, str) or not code:
        code = "DATA.SOURCE.CANDIDATE_EXCLUDED"
    detail = str(error).strip() or f"{type(error).__name__} excluded candidate"
    pending_fields = (
        {
            "requestRef": str(getattr(error, "request_ref", "")),
            "nextAction": str(getattr(error, "next_action", "")),
            "reentryRef": str(getattr(error, "reentry_ref", "")),
        }
        if getattr(error, "code", "") == "DATA.SOURCE.HOST_REVIEW_PENDING"
        else {}
    )
    return {
        **dict(prepared_outcome),
        **pending_fields,
        "assetId": _candidate_asset_id(
            candidate,
            index=index,
            entity_id=entity_id,
            aliases=aliases,
            source_identity=source_identity,
            profile=profile,
            dependencies=dependencies,
        ),
        "status": "excluded",
        "receiptRef": "",
        "receiptDigest": "",
        "contentSha256": "",
        "acquisitionStatus": "blocked",
        "distributionDecision": "blocked",
        "failureCode": code,
        "failure": detail,
    }


def _is_global_candidate_failure(error: BaseException) -> bool:
    if isinstance(error, ProfessionalVideoCasCollision):
        return True
    if (
        isinstance(error, CommonsVideoInputError)
        and error.code == "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT"
    ):
        return True
    return "professional video acquisition receipt collision:" in str(error)


def acquire_provider_sourced_videos(
    *,
    entity_id: str,
    entity_aliases: Sequence[str],
    handoff_ref: Path,
    output_root: Path | None,
    candidate_limit: int,
    discovery: Callable[..., list[dict[str, Any]]],
    profile: VideoSourceProfile,
    dependencies: ProviderVideoBatchDependencies,
) -> list[dict[str, Any]]:
    if candidate_limit < 1:
        raise CommonsVideoInputError(
            "DATA.SOURCE.POOL_SHORTFALL", "candidateLimit must be at least one"
        )
    root = (output_root or COMMONS_INPUT_ROOT).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    handoff_path = handoff_ref.expanduser().resolve()
    handoff = dependencies.load_handoff(handoff_path)
    source_identity = {
        "sourceRevision": str(handoff["sourceRevision"]),
        "sourceDigest": str(handoff["sourceDigest"]["digest"]),
        "entityCatalogDigest": str(handoff["entityCatalogDigest"]),
    }
    source_review_identity = {
        **source_identity,
        "executionBundleDigest": str(handoff["executionBundle"]["digest"]),
        "handoffDigest": dependencies.file_sha256(handoff_path),
    }
    aliases = _normal_aliases(entity_id, entity_aliases)
    candidates = discovery(
        entity_id,
        entity_aliases=aliases,
        limit=50,
        selected_limit=candidate_limit,
        diagnostics=[],
    )
    if not candidates:
        raise CommonsVideoInputError(
            "DATA.SOURCE.POOL_SHORTFALL",
            f"{profile.platform} returned no admissible public video "
            f"for entity={entity_id}",
        )
    outcomes: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        prepared_outcome: dict[str, Any] = {}
        try:
            manifest_path, prepared_outcome = dependencies.prepare_candidate(
                candidate=candidate,
                entity_id=entity_id,
                aliases=aliases,
                root=root,
                source_identity=source_identity,
                source_review_identity=source_review_identity,
                profile=profile,
            )
            receipt, receipt_path = dependencies.acquire_videos(
                manifest_path,
                handoff_ref=handoff_path,
                output_root=root,
            )
            row = receipt["assets"][0]
            outcomes.append(
                {
                    **prepared_outcome,
                    "status": "accepted",
                    "receiptRef": dependencies.safe_ref(receipt_path, root),
                    "receiptDigest": receipt["receiptDigest"],
                    "contentSha256": row["contentSha256"],
                    "acquisitionStatus": row["acquisitionStatus"],
                    "distributionDecision": row["distributionDecision"],
                    "failureCode": row["failureCode"],
                    "failure": row["failure"],
                }
            )
        except Exception as exc:  # noqa: BLE001 - one candidate is isolated.
            if _is_global_candidate_failure(exc):
                raise
            outcomes.append(
                _candidate_exclusion(
                    candidate,
                    index=index,
                    entity_id=entity_id,
                    aliases=aliases,
                    source_identity=source_identity,
                    profile=profile,
                    root=root,
                    error=exc,
                    prepared_outcome=prepared_outcome,
                    dependencies=dependencies,
                )
            )
    if not any(row["status"] == "accepted" for row in outcomes):
        raise CommonsVideoBatchBlocked(outcomes)
    return outcomes


__all__ = [
    "COMMONS_INPUT_ROOT",
    "COMMONS_VIDEO_PROFILE",
    "STOCK_VIDEO_PROFILES",
    "CommonsVideoBatchBlocked",
    "ProviderVideoBatchDependencies",
    "VideoSourceProfile",
    "acquire_provider_sourced_videos",
    "candidate_token",
]
