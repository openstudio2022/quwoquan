"""通过统一视频 acquisition 链路接入 governed 公开视频 provider。

Wikimedia Commons 是默认 provider；registry 已登记的 stock provider
（pexels_videos/pixabay_videos）复用完全相同的下载、probe、水印、语义安全
审查与 create-once receipt 链路，只替换 provider profile 与 discovery。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import SOURCE_ACQUISITION_ROOT
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid

from content.execution.agent.capacity_broker import SemanticCapacityBroker
from content.execution.agent.outcome import AgentRunOutcome
from content.execution.controller.execute.pre_acquisition_handoff import (
    load_pre_acquisition_handoff,
)
from content.source.professional_commons_video_input_evidence import (
    CommonsVideoInputError,
    digest,
    parse_judgment,
    review_evidence,
    safe_file,
    safe_ref,
    source_runner,
    validate_review_evidence,
    write_once,
)
from content.source.professional_safety_evidence import file_sha256
from content.source.professional_video_acquisition import acquire_professional_videos
from content.source.professional_video_manual_input_media import render_contact_sheet
from content.source.professional_video_probe import probe_professional_video
from content.source.professional_video_transport import fetch_public_video
from content.source.research.auto_plan_video import discover_commons_sourced_videos
from content.source.research.text_match import _normalized_title
from content.source.source_review_journal import run_source_review
from content.source.sourced_video_admission import scan_sourced_video_watermark

_EXTRACTED_DEPENDENCIES = (
    active_runtime_policy,
    assert_valid,
    parse_judgment,
    review_evidence,
    safe_file,
    validate_review_evidence,
    write_once,
)

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


def _candidate_token(
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


def _stable_candidate_view(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Project a candidate without volatile observation timestamps."""
    view = {
        key: value for key, value in candidate.items() if key != "popularitySignals"
    }
    signals = dict(candidate.get("popularitySignals") or {})
    signals.pop("observedAt", None)
    view["popularitySignals"] = signals
    return view


def _stabilized_candidate(
    candidate_root: Path, candidate: Mapping[str, Any]
) -> dict[str, Any]:
    """Adopt the frozen candidate observation on resume.

    Discovery stamps a fresh ``popularitySignals.observedAt`` on every run, so
    a resume after a mid-candidate crash used to collide on the create-once
    ``metadata.json``.  The volatile timestamp is not part of the candidate
    identity: when frozen metadata exists and every stable field matches, the
    stored candidate (including its original observedAt) is the truth source.
    """
    metadata_path = candidate_root / "metadata.json"
    if not metadata_path.is_file() or metadata_path.is_symlink():
        return dict(candidate)
    stored = read_json(metadata_path)
    if not isinstance(stored, Mapping) or not isinstance(stored.get("source"), Mapping):
        raise CommonsVideoInputError(
            "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT",
            f"stored Commons candidate metadata is invalid: {metadata_path}",
        )
    stored_source = dict(stored["source"])
    if _stable_candidate_view(stored_source) != _stable_candidate_view(candidate):
        raise CommonsVideoInputError(
            "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT",
            f"stored Commons candidate drifted on stable fields: {metadata_path}",
        )
    return stored_source


def _download_candidate(
    candidate_root: Path, candidate: Mapping[str, Any]
) -> tuple[Path, str]:
    existing = sorted(candidate_root.glob("original.*"))
    if len(existing) == 1 and existing[0].is_file() and not existing[0].is_symlink():
        return existing[0], existing[0].suffix
    if len(existing) > 1:
        raise CommonsVideoInputError(
            "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT",
            f"ambiguous frozen Commons bytes: {candidate_root}",
        )
    candidate_root.mkdir(parents=True, exist_ok=True)
    temporary = candidate_root / ".anonymous-download"
    temporary.unlink(missing_ok=True)
    try:
        suffix = fetch_public_video(
            str(candidate["assetUrl"]), temporary, supported_api=False
        )
        destination = candidate_root / f"original{suffix}"
        if destination.exists():
            if (
                destination.is_symlink()
                or destination.read_bytes() != temporary.read_bytes()
            ):
                raise CommonsVideoInputError(
                    "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT",
                    f"Commons byte collision: {destination}",
                )
            temporary.unlink(missing_ok=True)
        else:
            os.replace(temporary, destination)
    except CommonsVideoInputError:
        temporary.unlink(missing_ok=True)
        raise
    except (OSError, TimeoutError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise CommonsVideoInputError(
            "DATA.SOURCE.ACQUISITION_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc
    return destination, suffix


def _pre_review_result(
    *,
    source: Path,
    candidate_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    try:
        probe = probe_professional_video(source)
        watermark = scan_sourced_video_watermark(source)
        contact_sheet = candidate_root / "contact-sheet.jpg"
        if not contact_sheet.is_file():
            render_contact_sheet(
                source,
                contact_sheet,
                frame_count=int(probe["frameCount"]),
                fail=lambda detail: (_ for _ in ()).throw(
                    CommonsVideoInputError(
                        "DATA.SOURCE.MEDIA_PROBE_FAILED", str(detail)
                    )
                ),
            )
    except CommonsVideoInputError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise CommonsVideoInputError(
            "DATA.SOURCE.MEDIA_PROBE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc
    return probe, watermark, contact_sheet


def _blocked_safety(
    *,
    asset_id: str,
    entity_id: str,
    source_page_url: str,
    source: Path,
    contact_sheet: Path,
    probe: Mapping[str, Any],
    watermark: Mapping[str, Any],
    failure_code: str,
) -> dict[str, Any]:
    watermark_status = (
        "present"
        if watermark.get("watermarkDetected") is True
        else "unknown"
        if watermark.get("decision") != "passed"
        else "absent"
    )
    return {
        "schema": "quwoquan_data.manual_asset_safety_evidence",
        "assetId": asset_id,
        "entityId": entity_id,
        "observedEntityId": entity_id,
        "sourcePageUrl": source_page_url,
        "fileRef": "",
        "fileSha256": file_sha256(source),
        "bytes": source.stat().st_size,
        "contactSheetRef": "",
        "contactSheetSha256": "",
        "mediaProbe": dict(probe),
        "status": "blocked",
        "entityMatch": "unknown",
        "privacyRisk": "unknown",
        "minorRisk": "unknown",
        "maliciousMediaRisk": "unknown",
        "watermarkStatus": watermark_status,
        "reviewedAt": "",
        "reviewer": f"automatic:{failure_code}",
    }


def _manifest_item(
    *,
    asset_id: str,
    entity_id: str,
    aliases: Sequence[str],
    candidate: Mapping[str, Any],
    safety: Mapping[str, Any],
    profile: VideoSourceProfile,
) -> dict[str, Any]:
    return {
        "assetId": asset_id,
        "entityId": entity_id,
        "observedEntityId": entity_id,
        "entityAliases": list(aliases),
        "provider": profile.provider,
        "platform": profile.platform,
        "displayName": profile.display_name,
        "sourceKind": profile.source_kind,
        "acquisitionPath": profile.acquisition_path,
        "sourceUrl": str(candidate["sourcePostUrl"]),
        "assetUrl": str(candidate["assetUrl"]),
        "manualFile": "",
        "apiEvidence": (
            str(candidate.get("apiEvidenceUrl") or "")
            if profile.acquisition_path == "supported_api"
            else ""
        ),
        "accessEvidence": {
            "anonymousAssetAccess": True,
            "loginRequired": False,
            "captchaRequired": False,
            "paywallRequired": False,
            "drmProtected": False,
            "accessControlBypass": False,
        },
        "title": str(candidate["title"]),
        "relevance": str(candidate["relevance"]),
        "creator": str(candidate["originalCreatorName"]),
        "capturedAt": str(candidate["popularitySignals"]["observedAt"]),
        "rightsStatus": "verified",
        "license": str(candidate["rightsBasis"]),
        "termsUrl": str(candidate["termsUrl"]),
        "authorizationProof": str(candidate["authorizationProofUrl"]),
        "rightsIssues": [],
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "safetyReview": {
            "status": safety["status"],
            "entityMatch": safety["entityMatch"],
            "privacyRisk": safety["privacyRisk"],
            "minorRisk": safety["minorRisk"],
            "maliciousMediaRisk": safety["maliciousMediaRisk"],
            "watermarkStatus": safety["watermarkStatus"],
            "reviewedAt": safety["reviewedAt"],
            "reviewer": safety["reviewer"],
            "evidenceRef": safety["evidenceRef"],
            "safetyEvidenceFileSha256": safety["safetyEvidenceFileSha256"],
        },
        "popularitySignals": {
            "playCount": None,
            "likeCount": None,
            "commentCount": None,
            "shareCount": None,
            "favoriteCount": None,
            "observedAt": str(candidate["popularitySignals"]["observedAt"]),
            "provider": profile.provider,
            "topic": entity_id,
            "timeBucket": profile.time_bucket,
        },
    }


def _prepared_candidate(
    *,
    candidate: Mapping[str, Any],
    entity_id: str,
    aliases: Sequence[str],
    root: Path,
    source_identity: Mapping[str, str],
    source_review_identity: Mapping[str, str],
    runner: Callable[[str], AgentRunOutcome],
    broker: SemanticCapacityBroker,
    profile: VideoSourceProfile = COMMONS_VIDEO_PROFILE,
) -> tuple[Path, dict[str, Any]]:
    from content.source.professional_commons_video_preparation import prepare_candidate

    return prepare_candidate(
        candidate=candidate,
        entity_id=entity_id,
        aliases=aliases,
        root=root,
        source_identity=source_identity,
        source_review_identity=source_review_identity,
        runner=runner,
        broker=broker,
        profile=profile,
        run_source_review_fn=run_source_review,
    )


def _acquire_provider_sourced_videos(
    *,
    entity_id: str,
    entity_aliases: Sequence[str],
    handoff_ref: Path,
    output_root: Path | None,
    candidate_limit: int,
    runner: Callable[[str], AgentRunOutcome] | None,
    broker: SemanticCapacityBroker | None,
    discovery: Callable[..., list[dict[str, Any]]],
    profile: VideoSourceProfile,
) -> list[dict[str, Any]]:
    if candidate_limit < 1:
        raise CommonsVideoInputError(
            "DATA.SOURCE.POOL_SHORTFALL", "candidateLimit must be at least one"
        )
    root = (output_root or COMMONS_INPUT_ROOT).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    handoff_path = handoff_ref.expanduser().resolve()
    handoff = load_pre_acquisition_handoff(handoff_path)
    source_identity = {
        "sourceRevision": str(handoff["sourceRevision"]),
        "sourceDigest": str(handoff["sourceDigest"]["digest"]),
        "entityCatalogDigest": str(handoff["entityCatalogDigest"]),
    }
    source_review_identity = {
        **source_identity,
        "executionBundleDigest": str(handoff["executionBundle"]["digest"]),
        "handoffDigest": file_sha256(handoff_path),
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
    reviewer = runner or source_runner
    shared_broker = broker or SemanticCapacityBroker()
    outcomes: list[dict[str, Any]] = []
    for candidate in candidates:
        manifest_path, outcome = _prepared_candidate(
            candidate=candidate,
            entity_id=entity_id,
            aliases=aliases,
            root=root,
            source_identity=source_identity,
            source_review_identity=source_review_identity,
            runner=reviewer,
            broker=shared_broker,
            profile=profile,
        )
        receipt, receipt_path = acquire_professional_videos(
            manifest_path,
            handoff_ref=handoff_path,
            output_root=root,
        )
        row = receipt["assets"][0]
        outcomes.append(
            {
                **outcome,
                "receiptRef": safe_ref(receipt_path, root),
                "receiptDigest": receipt["receiptDigest"],
                "contentSha256": row["contentSha256"],
                "acquisitionStatus": row["acquisitionStatus"],
                "distributionDecision": row["distributionDecision"],
                "failureCode": row["failureCode"],
            }
        )
    return outcomes


def acquire_commons_sourced_videos(
    *,
    entity_id: str,
    entity_aliases: Sequence[str],
    handoff_ref: Path,
    output_root: Path | None = None,
    candidate_limit: int = 1,
    runner: Callable[[str], AgentRunOutcome] | None = None,
    broker: SemanticCapacityBroker | None = None,
    discovery: Callable[..., list[dict[str, Any]]] = discover_commons_sourced_videos,
) -> list[dict[str, Any]]:
    """发现、下载、审核并冻结 Commons 视频到既有 video acquisition receipt。"""
    return _acquire_provider_sourced_videos(
        entity_id=entity_id,
        entity_aliases=entity_aliases,
        handoff_ref=handoff_ref,
        output_root=output_root,
        candidate_limit=candidate_limit,
        runner=runner,
        broker=broker,
        discovery=discovery,
        profile=COMMONS_VIDEO_PROFILE,
    )


def acquire_stock_sourced_videos(
    *,
    provider: str,
    entity_id: str,
    entity_aliases: Sequence[str],
    handoff_ref: Path,
    output_root: Path | None = None,
    candidate_limit: int = 1,
    runner: Callable[[str], AgentRunOutcome] | None = None,
    broker: SemanticCapacityBroker | None = None,
    discovery: Callable[..., list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """经登记的 stock provider 官方 API 走同一条 acquisition/审查/receipt 链。"""
    profile = STOCK_VIDEO_PROFILES.get(provider)
    if profile is None:
        raise CommonsVideoInputError(
            "DATA.SOURCE.PROVIDER_NOT_REGISTERED",
            f"stock video provider is not governed: {provider}",
        )
    if discovery is None:
        from content.source.research.auto_plan_video_stock import (
            STOCK_VIDEO_DISCOVERIES,
        )

        discovery = STOCK_VIDEO_DISCOVERIES[provider]
    return _acquire_provider_sourced_videos(
        entity_id=entity_id,
        entity_aliases=entity_aliases,
        handoff_ref=handoff_ref,
        output_root=output_root,
        candidate_limit=candidate_limit,
        runner=runner,
        broker=broker,
        discovery=discovery,
        profile=profile,
    )


__all__ = [
    "COMMONS_INPUT_ROOT",
    "COMMONS_VIDEO_PROFILE",
    "STOCK_VIDEO_PROFILES",
    "CommonsVideoInputError",
    "VideoSourceProfile",
    "acquire_commons_sourced_videos",
    "acquire_stock_sourced_videos",
]
