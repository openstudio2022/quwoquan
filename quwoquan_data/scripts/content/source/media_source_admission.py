"""Create-once source admission for physical image and video evidence."""
from __future__ import annotations
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from core.io import read_json
from core.schema import assert_valid
from content.source.host_source_review import read_host_source_review_result
from content.source.media_source_admission_contract import (
    MEDIA_SOURCE_ADMISSION_BLOCKED,
    MEDIA_SOURCE_ADMISSION_INVALID,
    MEDIA_SOURCE_MEDIA_PROBE_BLOCKED,
    MEDIA_SOURCE_SAFETY_REVIEW_BLOCKED,
    MediaSourceAdmissionError,
    canonical_digest,
)
from content.source.research.scale_source_pool_evidence_path import (
    ScaleSourcePoolEvidencePathError,
    compute_evidence_file_sha256,
    resolve_evidence_file,
    resolve_evidence_root,
)

_SHA256_PREFIX = "sha256:"
_ASSET_KINDS = frozenset({"image", "video"})
_ACCEPTED_DISTRIBUTION = frozenset({"research_allowed", "commercial_allowed"})
_EVIDENCE_ROLES = (
    "catalog",
    "acquisition",
    "media_probe",
    "rights_attribution",
    "source_semantic_review",
)
_GENERATED_VIDEO_MARKERS = ("generated", "synthetic", "text_to_video", "ai_video")

def _invalid(issue: object) -> MediaSourceAdmissionError:
    return MediaSourceAdmissionError(MEDIA_SOURCE_ADMISSION_INVALID, issue)

def _document_binding(root: Path, ref: object, *, role: str) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        path = resolve_evidence_file(root, ref, label=f"{role}Ref")
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise TypeError(f"{role} evidence must be one JSON object")
        relative = path.relative_to(root).as_posix()
        return payload, {
            "role": role,
            "ref": relative,
            "documentDigest": canonical_digest(payload),
            "fileSha256": compute_evidence_file_sha256(path),
        }
    except (KeyError, OSError, TypeError, ValueError, ScaleSourcePoolEvidencePathError) as exc:
        if isinstance(exc, MediaSourceAdmissionError):
            raise
        raise _invalid(exc) from exc

def _matching_rows(document: Mapping[str, Any], *, asset_id: str) -> list[Mapping[str, Any]]:
    for key in ("assets", "candidates"):
        rows = document.get(key)
        if not isinstance(rows, list):
            continue
        direct = [
            row
            for row in rows
            if isinstance(row, Mapping)
            and str(row.get("assetId") or row.get("candidateId") or "") == asset_id
        ]
        if direct:
            return direct
    if str(document.get("assetId") or "") == asset_id:
        return [document]
    return []

def _one_evidence_row(
    document: Mapping[str, Any],
    *,
    asset_id: str,
    role: str,
) -> Mapping[str, Any]:
    rows = _matching_rows(document, asset_id=asset_id)
    if len(rows) != 1:
        raise _invalid(f"{role} must bind exactly one asset: {asset_id}")
    return rows[0]

def _identity_issues(
    documents: Mapping[str, Mapping[str, Any]],
    *,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
) -> list[str]:
    expected = {
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    issues: list[str] = []
    for role, document in documents.items():
        for field, value in expected.items():
            observed = document.get(field)
            if observed is not None and observed != value:
                issues.append(f"{role}.{field} drift")
    return issues

def _cross_evidence_issues(
    rows: Mapping[str, Mapping[str, Any]],
    *,
    asset_id: str,
    content_sha256: str,
    entity_id: str,
) -> list[str]:
    issues: list[str] = []
    for role, row in rows.items():
        observed_asset = row.get("assetId")
        if observed_asset is not None and observed_asset != asset_id:
            issues.append(f"{role}.assetId drift")
        observed_content = row.get("contentSha256")
        if observed_content is not None and observed_content != content_sha256:
            issues.append(f"{role}.contentSha256 drift")
        observed_entity = row.get("entityId")
        if observed_entity is not None and observed_entity != entity_id:
            issues.append(f"{role}.entityId drift")
    return issues

def _normalized_review(
    document: Mapping[str, Any], *, root: Path, asset_id: str, result_ref: str
) -> dict[str, Any]:
    if document.get("schema") != "quwoquan_data.host_source_review_result":
        raise _invalid("source semantic review must be one validated host source review result")
    try:
        result = read_host_source_review_result(
            evidence_root=root,
            request_ref=str(document.get("requestRef") or ""),
            result_ref=result_ref,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise _invalid(exc) from exc
    asset = result.get("assetBinding")
    if not isinstance(asset, Mapping) or asset.get("assetId") != asset_id:
        raise _invalid("host source review asset identity drift")
    verdict = result["verdict"]
    return {
        "resultRef": result_ref,
        "requestDigest": str(result["requestDigest"]),
        "resultDigest": str(result["resultDigest"]),
        "actor": dict(result["actor"]),
        **dict(verdict),
    }

def _source_attribution(
    asset: Mapping[str, Any], rights: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    for source in (rights, asset):
        value = source.get("sourceAttribution")
        if isinstance(value, Mapping):
            return value
        plan = source.get("planImageSpec")
        if isinstance(plan, Mapping) and isinstance(plan.get("sourceAttribution"), Mapping):
            return plan["sourceAttribution"]
    return None


def _asset_snapshot(
    *,
    asset_kind: str,
    acquisition: Mapping[str, Any],
    probe: Mapping[str, Any],
    rights: Mapping[str, Any],
) -> dict[str, Any]:
    required = (
        "assetId",
        "entityId",
        "observedEntityId",
        "contentSha256",
        "assetRef",
        "provider",
        "platform",
        "sourceUrl",
        "creator",
        "capturedAt",
        "acquisitionStatus",
    )
    missing = [field for field in required if not str(acquisition.get(field) or "").strip()]
    if missing:
        raise _invalid("acquisition asset is incomplete: " + ", ".join(missing))
    rights_status = str(rights.get("rightsStatus") or acquisition.get("rightsStatus") or "")
    distribution = str(
        rights.get("distributionDecision")
        or acquisition.get("distributionDecision")
        or ""
    )
    authorization = rights.get("authorizationRequired")
    if not isinstance(authorization, bool):
        authorization = acquisition.get("authorizationRequired")
    if not isinstance(authorization, bool):
        raise _invalid("rights attribution authorizationRequired is absent")
    snapshot: dict[str, Any] = {
        **{field: acquisition[field] for field in required},
        "rightsStatus": rights_status,
        "authorizationRequired": authorization,
        "distributionDecision": distribution,
    }
    attribution = _source_attribution(acquisition, rights)
    if attribution is not None:
        snapshot["sourceAttribution"] = dict(attribution)
    if asset_kind == "image":
        if attribution is None:
            raise _invalid("image rights attribution lacks canonical sourceAttribution")
        width = probe.get("width", acquisition.get("width"))
        height = probe.get("height", acquisition.get("height"))
        if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
            raise _invalid("image media probe width is invalid")
        if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
            raise _invalid("image media probe height is invalid")
        snapshot.update(width=width, height=height)
    else:
        media_probe = probe.get("mediaProbe")
        if not isinstance(media_probe, Mapping):
            media_probe = acquisition.get("mediaProbe")
        popularity = probe.get("popularitySignals")
        if not isinstance(popularity, Mapping):
            popularity = acquisition.get("popularitySignals")
        if not isinstance(media_probe, Mapping) or not isinstance(popularity, Mapping):
            raise _invalid("video media probe/popularity evidence is absent")
        snapshot.update(
            sourceKind=str(acquisition.get("sourceKind") or "unknown_source"),
            mediaProbe=dict(media_probe),
            popularitySignals=dict(popularity),
        )
    return snapshot


def _blockers(
    *,
    asset_kind: str,
    snapshot: Mapping[str, Any],
    review: Mapping[str, Any],
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if (
        snapshot.get("acquisitionStatus") != "acquired"
        or snapshot.get("rightsStatus") not in {"verified", "unverified", "unknown"}
        or snapshot.get("distributionDecision") not in _ACCEPTED_DISTRIBUTION
    ):
        blockers.append(
            {
                "code": MEDIA_SOURCE_ADMISSION_BLOCKED,
                "message": "acquisition or rights attribution is not source-admissible",
            }
        )
    review_passed = all(
        (
            review.get("status") == "passed",
            review.get("entityMatch") == "matched",
            review.get("qualityStatus") == "passed",
            review.get("privacyRisk") == "none",
            review.get("minorRisk") == "none",
            review.get("maliciousMediaRisk") == "none",
            review.get("watermarkStatus") == "absent",
        )
    )
    if not review_passed:
        code = (
            MEDIA_SOURCE_SAFETY_REVIEW_BLOCKED
            if asset_kind == "video" and review.get("entityMatch") == "mismatch"
            else MEDIA_SOURCE_ADMISSION_BLOCKED
        )
        blockers.append(
            {
                "code": code,
                "message": "source-scoped semantic review is not accepted",
            }
        )
    if asset_kind == "video":
        probe = snapshot.get("mediaProbe")
        probe = probe if isinstance(probe, Mapping) else {}
        source_kind = str(snapshot.get("sourceKind") or "").casefold()
        if any(marker in source_kind for marker in _GENERATED_VIDEO_MARKERS) or not all(
            (
                probe.get("playable") is True,
                probe.get("motionVideo") is True,
                probe.get("staticImageSequence") is False,
            )
        ):
            blockers.append(
                {
                    "code": MEDIA_SOURCE_MEDIA_PROBE_BLOCKED,
                    "message": "video is not acquired playable motion media",
                }
            )
    deduplicated: list[dict[str, str]] = []
    for blocker in blockers:
        if blocker not in deduplicated:
            deduplicated.append(blocker)
    return deduplicated


def _prepare_receipt(
    *,
    root: Path,
    asset_kind: str,
    asset_id: str,
    object_ref: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    evidence_refs: Mapping[str, object],
    recorded_at: str,
) -> dict[str, Any]:
    if asset_kind not in _ASSET_KINDS:
        raise _invalid(f"assetKind is unsupported: {asset_kind}")
    if set(evidence_refs) != set(_EVIDENCE_ROLES):
        raise _invalid("evidence refs must contain exactly: " + ", ".join(_EVIDENCE_ROLES))
    documents: dict[str, dict[str, Any]] = {}
    bindings: list[dict[str, str]] = []
    for role in _EVIDENCE_ROLES:
        document, binding = _document_binding(root, evidence_refs[role], role=role)
        documents[role] = document
        bindings.append(binding)
    identity_issues = _identity_issues(
        documents,
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )
    if identity_issues:
        raise _invalid(identity_issues)
    rows = {
        role: _one_evidence_row(document, asset_id=asset_id, role=role)
        for role, document in documents.items()
        if role != "source_semantic_review"
    }
    review_document = documents["source_semantic_review"]
    review_asset = review_document.get("assetBinding")
    if not isinstance(review_asset, Mapping) or review_asset.get("assetId") != asset_id:
        raise _invalid("source_semantic_review must bind the exact asset")
    rows["source_semantic_review"] = review_asset
    acquisition = rows["acquisition"]
    content_sha256 = str(acquisition.get("contentSha256") or "")
    entity_id = str(acquisition.get("entityId") or "")
    issues = _cross_evidence_issues(
        rows,
        asset_id=asset_id,
        content_sha256=content_sha256,
        entity_id=entity_id,
    )
    if issues:
        raise _invalid(issues)
    snapshot = _asset_snapshot(
        asset_kind=asset_kind,
        acquisition=acquisition,
        probe=rows["media_probe"],
        rights=rows["rights_attribution"],
    )
    try:
        asset_path = resolve_evidence_file(root, snapshot["assetRef"], label="assetBytesRef")
        asset_sha = compute_evidence_file_sha256(asset_path)
    except (KeyError, OSError, ValueError, ScaleSourcePoolEvidencePathError) as exc:
        raise _invalid(exc) from exc
    if asset_sha != snapshot["contentSha256"]:
        raise _invalid("asset bytes contentSha256 drift")
    review = _normalized_review(
        documents["source_semantic_review"],
        root=root,
        asset_id=asset_id,
        result_ref=str(evidence_refs["source_semantic_review"]),
    )
    blockers = _blockers(asset_kind=asset_kind, snapshot=snapshot, review=review)
    evidence_root_digest = canonical_digest(
        {
            "evidenceBindings": bindings,
            "assetBytes": {
                "ref": str(snapshot["assetRef"]),
                "fileSha256": asset_sha,
            },
        }
    )
    identity = {
        "assetKind": asset_kind,
        "objectRef": str(object_ref),
        "assetId": asset_id,
        "contentSha256": snapshot["contentSha256"],
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    stable = {
        "schema": "quwoquan_data.media_source_admission_receipt",
        "admissionId": "media-source-admission-" + canonical_digest(identity).removeprefix(
            _SHA256_PREFIX
        ),
        "assetKind": asset_kind,
        "objectRef": str(object_ref),
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "evidenceRootDigest": evidence_root_digest,
        "evidenceBindings": bindings,
        "assetSnapshot": snapshot,
        "sourceReview": review,
        "admissionDecision": "blocked" if blockers else "accepted",
        "blockers": blockers,
        "recordedAt": str(recorded_at),
    }
    document = {**stable, "receiptDigest": canonical_digest(stable)}
    try:
        assert_valid(
            document,
            "source",
            "media_source_admission_receipt",
            label="media source admission receipt",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _invalid(exc) from exc
    return document


def _write_create_once(path: Path, document: Mapping[str, Any]) -> None:
    body = json.dumps(
        dict(document),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


class MediaSourceAdmissionCommandWriter:
    """Validate one portable evidence root and freeze a source admission fact."""

    def __init__(self, evidence_root: Path) -> None:
        try:
            self._root = resolve_evidence_root(evidence_root)
        except ScaleSourcePoolEvidencePathError as exc:
            raise _invalid(exc) from exc

    def write(
        self,
        *,
        asset_kind: str,
        asset_id: str,
        object_ref: str,
        source_revision: str,
        source_digest: str,
        entity_catalog_digest: str,
        evidence_refs: Mapping[str, object],
        recorded_at: str,
    ) -> tuple[dict[str, Any], str]:
        document = _prepare_receipt(
            root=self._root,
            asset_kind=asset_kind,
            asset_id=str(asset_id),
            object_ref=str(object_ref),
            source_revision=str(source_revision),
            source_digest=str(source_digest),
            entity_catalog_digest=str(entity_catalog_digest),
            evidence_refs=evidence_refs,
            recorded_at=str(recorded_at),
        )
        receipt_ref = (
            Path("receipts")
            / "media-source-admission"
            / f"{document['admissionId']}.json"
        ).as_posix()
        destination = self._root / receipt_ref
        if destination.exists():
            existing = MediaSourceAdmissionQuery(self._root).read(receipt_ref)["receipt"]
            comparable = lambda value: {
                key: item
                for key, item in value.items()
                if key not in {"recordedAt", "receiptDigest"}
            }
            if comparable(existing) != comparable(document):
                raise _invalid(f"media source admission create-once collision: {receipt_ref}")
            return dict(existing), receipt_ref
        _write_create_once(destination, document)
        return MediaSourceAdmissionQuery(self._root).read(receipt_ref)["receipt"], receipt_ref


class MediaSourceAdmissionQuery:
    """Revalidate source evidence and expose accepted/blocked typed results."""

    def __init__(self, evidence_root: Path) -> None:
        try:
            self._root = resolve_evidence_root(evidence_root)
        except ScaleSourcePoolEvidencePathError as exc:
            raise _invalid(exc) from exc

    def read(self, receipt_ref: str) -> dict[str, Any]:
        try:
            path = resolve_evidence_file(
                self._root,
                receipt_ref,
                label="mediaSourceAdmissionRef",
            )
            payload = read_json(path)
        except (OSError, TypeError, ValueError, ScaleSourcePoolEvidencePathError) as exc:
            raise _invalid(exc) from exc
        if not isinstance(payload, dict):
            raise _invalid("media source admission receipt must be one object")
        try:
            assert_valid(
                payload, "source", "media_source_admission_receipt",
                label="media source admission receipt",
            )
        except (FileNotFoundError, TypeError, ValueError) as exc:
            raise _invalid(exc) from exc
        stable = {key: value for key, value in payload.items() if key != "receiptDigest"}
        if payload.get("receiptDigest") != canonical_digest(stable):
            raise _invalid("media source admission receiptDigest drift")
        canonical_ref = (
            Path("receipts")
            / "media-source-admission"
            / f"{payload['admissionId']}.json"
        ).as_posix()
        if path.relative_to(self._root).as_posix() != canonical_ref:
            raise _invalid("media source admission receipt path is not canonical")
        bindings = payload.get("evidenceBindings")
        if not isinstance(bindings, list):
            raise _invalid("media source admission evidence bindings are absent")
        evidence_refs = {
            str(binding.get("role") or ""): str(binding.get("ref") or "")
            for binding in bindings if isinstance(binding, Mapping)
        }
        rebuilt = _prepare_receipt(
            root=self._root,
            asset_kind=str(payload["assetKind"]),
            asset_id=str(payload["assetSnapshot"]["assetId"]),
            object_ref=str(payload["objectRef"]),
            source_revision=str(payload["sourceRevision"]),
            source_digest=str(payload["sourceDigest"]),
            entity_catalog_digest=str(payload["entityCatalogDigest"]),
            evidence_refs=evidence_refs,
            recorded_at=str(payload["recordedAt"]),
        )
        if rebuilt != payload:
            raise _invalid("media source admission provenance/root digest drift")
        return {
            "status": str(payload["admissionDecision"]),
            "receiptRef": canonical_ref,
            "receiptDigest": str(payload["receiptDigest"]),
            "receipt": payload,
        }

    def require_accepted(self, receipt_ref: str) -> dict[str, Any]:
        result = self.read(receipt_ref)
        if result["status"] != "accepted":
            receipt = result["receipt"]
            blockers = receipt.get("blockers") if isinstance(receipt, Mapping) else None
            blocker = blockers[0] if isinstance(blockers, list) and blockers else {}
            code = str(blocker.get("code") or MEDIA_SOURCE_ADMISSION_BLOCKED)
            issue = str(blocker.get("message") or "media source admission is blocked")
            raise MediaSourceAdmissionError(code, issue)
        return result


__all__ = [
    "MEDIA_SOURCE_ADMISSION_BLOCKED",
    "MEDIA_SOURCE_ADMISSION_INVALID",
    "MEDIA_SOURCE_MEDIA_PROBE_BLOCKED",
    "MEDIA_SOURCE_SAFETY_REVIEW_BLOCKED",
    "MediaSourceAdmissionCommandWriter",
    "MediaSourceAdmissionError",
    "MediaSourceAdmissionQuery",
    "canonical_digest",
]
