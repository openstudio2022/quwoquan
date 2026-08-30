"""Derive strict pool migration rows from canonical object bytes."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import (
    POOL_RECORD_SCHEMA,
    _commercial_proof_closed,
    is_pool_record_admitted,
    iter_pool_records,
    pool_payload_digest,
)
from content.release.canonical.canonical_identity_state import (
    CanonicalIdentityStateQuery,
)
from content.release.canonical.object_source_identity import (
    validate_object_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
    _read_json,
)
from content.release.canonical.pool_source_attribution import (
    source_attribution_complete,
)
from content.source.professional_video_probe import probe_professional_video
from core.content_library import MediaHoldingError, resolve_media_holding

_ATTRIBUTION_FIELDS = (
    "isOriginal",
    "originalCreatorName",
    "platform",
    "sourcePostUrl",
    "originalAssetUrl",
    "attributionText",
    "rightsBasis",
    "commercialAuthorizationStatus",
    "publicationAdmission",
    "watermarkStatus",
    "audioRightsStatus",
    "modelReleaseStatus",
    "propertyReleaseStatus",
    "collectedAt",
    "takedownPolicy",
)


def build_pool_record(
    *,
    object_type: str,
    object_id: str,
    object_ref: str,
    record_sequence: int,
    content_version: int,
    process_result: str,
    quality_result: str,
    eligibility_result: str,
    usage_scope: str | None,
    evidence_ref: str,
    evidence_digest: str,
    payload_digest: str,
    source_identity: Mapping[str, Any] | None = None,
    source_attribution: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "schema": POOL_RECORD_SCHEMA,
        "objectType": object_type,
        "objectId": object_id,
        "objectRef": object_ref,
        "recordSequence": record_sequence,
        "contentVersion": content_version,
        "status": "active",
        "processResult": process_result,
        "qualityResult": quality_result,
        "eligibilityResult": eligibility_result,
        "usageScope": usage_scope,
        "evidenceRef": evidence_ref,
        "evidenceDigest": evidence_digest,
        "payloadDigest": payload_digest,
    }
    if object_type in {"homepage", "content"}:
        record.update(
            canonicalObjectDigest=payload_digest,
            sourceIdentity=dict(source_identity or {}),
            sourceAttribution=dict(source_attribution or {}),
        )
    return record


def object_evidence(root: Path) -> tuple[bool, Path | None]:
    attestation = root / "attestation.json"
    if not attestation.is_file():
        return False, None
    document = _read_json(attestation)
    passed = document.get("decision") == "approved" and all(
        isinstance(document.get(key), Mapping)
        and document[key].get("status") == "passed"
        for key in ("deterministicGate", "independentReviewer", "mediaRefReview")
    )
    return passed, attestation


def rights_rows(root: Path) -> list[dict[str, Any]]:
    rights_path = root / "rights.json"
    if not rights_path.is_file():
        return []
    raw = _read_json(rights_path).get("assets")
    return [dict(item) for item in raw or [] if isinstance(item, Mapping)]


def usage_scope(
    manifest: Mapping[str, Any], rows: list[dict[str, Any]]
) -> tuple[str, str | None, str | None]:
    if any(
        row.get("rightsAuditStatus") != "verified"
        or not str(row.get("authorizationProof") or "").strip()
        for row in rows
    ):
        return "pending", None, "DATA.POOL.ELIGIBILITY_EVIDENCE_PENDING"
    if _commercial_proof_closed(manifest, rows):
        return "passed", "commercial", None
    return "passed", "research", None


def _evidence_sources(object_root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name in ("manifest.json", "rights.json", "source_catalog.json", "attestation.json"):
        path = object_root / name
        if path.is_file() and not path.is_symlink():
            rows.append({"ref": name, "sha256": _digest_file(path)})
    return rows


def attribution_repair_requirement(
    *,
    object_type: str,
    object_ref: str,
    object_root: Path,
    attribution: object,
) -> dict[str, Any]:
    source = dict(attribution) if isinstance(attribution, Mapping) else {}
    missing = [
        field
        for field in _ATTRIBUTION_FIELDS
        if (
            not isinstance(source.get(field), bool)
            if field == "isOriginal"
            else not str(source.get(field) or "").strip()
        )
    ]
    return {
        "schema": "quwoquan_data.pool_attribution_repair_requirement",
        "objectType": object_type,
        "objectRef": object_ref,
        "canonicalObjectDigest": pool_payload_digest(object_root),
        "evidenceSources": _evidence_sources(object_root),
        "requiredSourceAttributionFields": missing,
        "repairEvidencePolicy": (
            "canonical_bytes_plus_fresh_source_evidence"
        ),
        "oldTaskReceiptReuseAllowed": False,
    }


def _video_digests(root: Path) -> Counter[str]:
    digests: Counter[str] = Counter()
    if not root.is_dir():
        return digests
    for path in sorted(root.rglob("manifest.json")):
        manifest = _read_json(path)
        for asset in manifest.get("assets") or []:
            if isinstance(asset, Mapping) and asset.get("kind") == "video":
                digest = str(asset.get("sha256") or "").strip()
                if digest:
                    digests[digest] += 1
    return digests


def _video_research_issue(
    object_root: Path,
    manifest: Mapping[str, Any],
    *,
    digest_counts: Counter[str],
) -> str | None:
    if manifest.get("contentType") != "video":
        return None
    assets = [
        dict(row)
        for row in manifest.get("assets") or []
        if isinstance(row, Mapping) and row.get("kind") == "video"
    ]
    if len(assets) != 1:
        return "DATA.POOL.VIDEO_MEDIA_MISSING"
    asset = assets[0]
    digest = str(asset.get("sha256") or "")
    poster_digest = str(asset.get("posterSha256") or "")
    # The object records its track and poster by digest; the content library owns
    # the bodies. Resolving them here is what makes "the media is present" a claim
    # about the bytes rather than about a copy sitting next to the manifest.
    try:
        video_path = resolve_media_holding(digest)
        poster_path = resolve_media_holding(poster_digest)
    except (MediaHoldingError, ValueError):
        return "DATA.POOL.VIDEO_MEDIA_MISSING"
    if _digest_file(video_path) != digest:
        return "DATA.POOL.VIDEO_DIGEST_DRIFT"
    if _digest_file(poster_path) != poster_digest:
        return "DATA.POOL.VIDEO_POSTER_INVALID"
    if digest_counts[digest] != 1:
        return "DATA.POOL.VIDEO_DUPLICATE"
    provenance_path = object_root / "provenance.json"
    if not provenance_path.is_file() or provenance_path.is_symlink():
        return "DATA.POOL.VIDEO_PROVENANCE_INCOMPLETE"
    provenance = _read_json(provenance_path)
    sources = provenance.get("sources")
    if not isinstance(sources, list) or not sources or any(
        not isinstance(row, Mapping)
        or row.get("drmDetected") is not False
        or row.get("accessControlBypassed") is not False
        for row in sources
    ):
        return "DATA.POOL.VIDEO_ACCESS_SAFETY_INVALID"
    try:
        probe = probe_professional_video(video_path)
    except (OSError, RuntimeError, TypeError, ValueError):
        return "DATA.POOL.VIDEO_UNPLAYABLE"
    if probe.get("playable") is not True:
        return "DATA.POOL.VIDEO_UNPLAYABLE"
    if (
        probe.get("motionVideo") is not True
        or probe.get("staticImageSequence") is not False
    ):
        return "DATA.POOL.VIDEO_STATIC_IMAGE_SEQUENCE"
    return None


def canonical_plan_items(
    publish_root: Path, kind: str
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, str]],
    list[dict[str, Any]],
    list[dict[str, str]],
    list[dict[str, Any]],
]:
    object_type = "homepage" if kind == "entities" else "content"
    items: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    repair_requirements: list[dict[str, Any]] = []
    already_admitted: list[dict[str, str]] = []
    identity_states: list[dict[str, Any]] = []
    root = publish_root / kind
    identity_query = CanonicalIdentityStateQuery(publish_root=publish_root)
    video_digests = _video_digests(root) if kind == "posts" else Counter()
    for manifest_path in sorted(root.rglob("manifest.json")) if root.is_dir() else []:
        object_root = manifest_path.parent
        object_ref = object_root.relative_to(root).as_posix()
        manifest = _read_json(manifest_path)
        identity_state = identity_query.get(
            object_type=object_type,
            object_ref=f"{kind}/{object_ref}",
        )
        identity_states.append(identity_state)
        if identity_state["state"].startswith("invalid_"):
            exclusions.append(
                {
                    "objectType": object_type,
                    "objectRef": object_ref,
                    "reason": str(identity_state["deepestError"]),
                }
            )
            repair_requirements.append(identity_state)
            continue
        if identity_state["state"] == "terminated":
            exclusions.append(
                {
                    "objectType": object_type,
                    "objectRef": object_ref,
                    "reason": "DATA.POOL.IDENTITY_TERMINATED",
                }
            )
            continue
        passed, evidence_path = object_evidence(object_root)
        process_result = "completed" if passed else "failed"
        quality_result = "passed" if passed else "failed"
        rows = rights_rows(object_root)
        if passed:
            eligibility_result, selected_scope, reason = usage_scope(manifest, rows)
        else:
            eligibility_result, selected_scope, reason = (
                "failed",
                None,
                "DATA.POOL.QUALITY_EVIDENCE_FAILED",
            )
        old_records = iter_pool_records(object_root, object_type=object_type)
        latest_old = old_records[-1] if old_records else None
        identity_key = "contentId" if object_type == "content" else "entityId"
        object_id = str(
            manifest.get(identity_key) or (latest_old or {}).get("objectId") or ""
        ).strip()
        content_version = manifest.get("version") or (latest_old or {}).get(
            "contentVersion"
        )
        if (
            not object_id
            or not isinstance(content_version, int)
            or isinstance(content_version, bool)
            or content_version < 1
        ):
            exclusions.append(
                {
                    "objectType": object_type,
                    "objectRef": object_ref,
                    "reason": "DATA.POOL.IDENTITY_INVALID",
                }
            )
            continue
        attribution = manifest.get("sourceAttribution")
        if not isinstance(attribution, Mapping) or not source_attribution_complete(
            {"sourceAttribution": attribution}
        ):
            exclusions.append(
                {
                    "objectType": object_type,
                    "objectRef": object_ref,
                    "reason": "DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE",
                }
            )
            repair_requirements.append(
                attribution_repair_requirement(
                    object_type=object_type,
                    object_ref=object_ref,
                    object_root=object_root,
                    attribution=attribution,
                )
            )
            continue
        video_issue = (
            _video_research_issue(
                object_root,
                manifest,
                digest_counts=video_digests,
            )
            if eligibility_result == "passed"
            else None
        )
        if video_issue is not None:
            exclusions.append(
                {
                    "objectType": object_type,
                    "objectRef": object_ref,
                    "reason": video_issue,
                }
            )
            continue
        evidence_ref = (
            evidence_path.relative_to(object_root).as_posix()
            if evidence_path is not None
            else "attestation.json"
        )
        evidence_digest = (
            _digest_file(evidence_path)
            if evidence_path is not None
            else "sha256:" + "0" * 64
        )
        payload_digest = pool_payload_digest(object_root)
        try:
            source_identity = validate_object_source_identity(manifest)
        except ObjectTransactionError:
            exclusions.append(
                {
                    "objectType": object_type,
                    "objectRef": object_ref,
                    "reason": "DATA.POOL.SOURCE_IDENTITY_INVALID",
                }
            )
            continue
        record_sequence = int(latest_old["recordSequence"]) + 1 if latest_old else 1
        record = build_pool_record(
            object_type=object_type,
            object_id=object_id,
            object_ref=object_ref,
            record_sequence=record_sequence,
            content_version=content_version,
            process_result=process_result,
            quality_result=quality_result,
            eligibility_result=eligibility_result,
            usage_scope=selected_scope,
            evidence_ref=evidence_ref,
            evidence_digest=evidence_digest,
            payload_digest=payload_digest,
            source_identity=source_identity,
            source_attribution=attribution,
        )
        if latest_old is not None and is_pool_record_admitted(latest_old):
            replay_record = dict(record)
            replay_record["recordSequence"] = latest_old["recordSequence"]
            if latest_old == replay_record:
                already_admitted.append(
                    {"objectType": object_type, "objectRef": object_ref}
                )
                continue
            if latest_old.get("contentVersion") == content_version:
                exclusions.append(
                    {
                        "objectType": object_type,
                        "objectRef": object_ref,
                        "reason": "DATA.POOL.CANONICAL_RECORD_DRIFT",
                    }
                )
                continue
        item: dict[str, Any] = {
            "itemId": (
                f"{object_type}:{object_id}:{content_version}:"
                f"record-{record_sequence}"
            ),
            "sourceRef": f"{kind}/{object_ref}",
            "record": record,
        }
        if reason:
            item["reason"] = reason
        items.append(item)
    return (
        items,
        exclusions,
        repair_requirements,
        already_admitted,
        identity_states,
    )


__all__ = [
    "attribution_repair_requirement",
    "build_pool_record",
    "canonical_plan_items",
    "object_evidence",
    "rights_rows",
    "usage_scope",
]
