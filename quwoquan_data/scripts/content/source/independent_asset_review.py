"""Freeze one provenance-bound review for exact acquired bytes.

Acquisition cannot prove its own rights, safety, entity, or quality admission.
This module binds distinct author/reviewer runs without model or network I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import OUTPUT_ROOT
from core.schema import assert_valid

from content.source.independent_asset_review_contract import (
    IndependentAssetReviewError,
    assert_video_asset_snapshot_publishable,
    asset_snapshot,
    audited_path,
    canonical_digest,
    file_digest,
    load_document,
    resolve_ref,
    write_create_once,
)

_EXTRACTED_DEPENDENCIES = (load_document,)

_ACCEPTED_DECISIONS = {"research_allowed", "commercial_allowed"}
_POPULAR_BINDING_FIELDS = (
    "popularCandidateId",
    "popularCatalogRef",
    "popularCatalogDigest",
    "popularCatalogFileSha256",
)


def _asset_snapshot(
    asset: Mapping[str, Any],
    *,
    asset_kind: str,
) -> dict[str, Any]:
    snapshot = asset_snapshot(asset)
    if asset_kind != "video":
        return snapshot
    values = [str(asset.get(field) or "").strip() for field in _POPULAR_BINDING_FIELDS]
    if any(values) and not all(values):
        raise IndependentAssetReviewError(
            "video popular-catalog acquisition binding is incomplete"
        )
    if all(values):
        snapshot.update(zip(_POPULAR_BINDING_FIELDS, values, strict=True))
    return snapshot


def _author_evidence_issues(
    envelope: Mapping[str, Any],
    *,
    workspace_root: Path,
) -> list[str]:
    """Validate the author envelope without importing the execution package."""
    issues: list[str] = []
    agent = envelope.get("agent")
    if not isinstance(agent, Mapping) or any(
        not str(agent.get(field) or "").strip()
        for field in ("provider", "model", "runId", "promptSha256")
    ):
        issues.append("author agent identity is incomplete")
    for row in envelope.get("files") or []:
        if not isinstance(row, Mapping):
            issues.append("author file evidence is invalid")
            continue
        relative = Path(str(row.get("path") or ""))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            issues.append("author file evidence path is unsafe")
            continue
        path = workspace_root / relative
        if not path.is_file() or file_digest(path) != row.get("sha256"):
            issues.append(f"author file evidence drift: {relative.as_posix()}")
    for gate in envelope.get("gates") or []:
        if (
            not isinstance(gate, Mapping)
            or gate.get("final") is not True
            or gate.get("decision") not in {"passed", "approved"}
        ):
            issues.append("author gate is not final/passing")
    return issues


def _load_acquisition(
    path: Path,
    *,
    asset_kind: str,
    output_root: Path,
) -> tuple[dict[str, Any], str, str]:
    audited, ref = audited_path(
        path,
        output_root=output_root,
        label=f"{asset_kind} acquisition receipt",
    )
    if audited.parent.name != "receipts":
        raise IndependentAssetReviewError(
            f"{asset_kind} acquisition receipt path is not canonical: {audited}"
        )
    acquisition_root = audited.parent.parent
    receipt_ref = audited.relative_to(acquisition_root).as_posix()
    try:
        if asset_kind == "image":
            from content.source.professional_image_acquisition import (
                load_professional_image_acquisition_receipt,
            )

            receipt = load_professional_image_acquisition_receipt(
                receipt_ref,
                root=acquisition_root,
            )
        elif asset_kind == "video":
            from content.source.professional_video_receipt import (
                load_professional_video_acquisition_receipt,
            )

            receipt = load_professional_video_acquisition_receipt(
                receipt_ref,
                root=acquisition_root,
            )
        else:
            raise IndependentAssetReviewError(f"assetKind is unsupported: {asset_kind}")
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, IndependentAssetReviewError):
            raise
        raise IndependentAssetReviewError(str(exc)) from exc
    return receipt, ref, file_digest(audited)


def _one_asset(receipt: Mapping[str, Any], *, asset_id: str) -> dict[str, Any]:
    matches = [
        dict(row)
        for row in receipt.get("assets") or []
        if isinstance(row, Mapping) and str(row.get("assetId") or "") == asset_id
    ]
    if len(matches) != 1:
        raise IndependentAssetReviewError(
            f"acquisition asset binding is missing or ambiguous: {asset_id}"
        )
    asset = matches[0]
    if asset.get("acquisitionStatus") != "acquired":
        raise IndependentAssetReviewError(f"asset was not acquired: {asset_id}")
    return asset


def _review_decision(
    judgment: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
    acquisition_safety: Mapping[str, Any],
) -> str:
    if judgment.get("rightsStatus") != snapshot.get("rightsStatus"):
        raise IndependentAssetReviewError(
            "review rightsStatus cannot upgrade acquisition truth"
        )
    if judgment.get("authorizationRequired") is not snapshot.get(
        "authorizationRequired"
    ):
        raise IndependentAssetReviewError(
            "review authorizationRequired cannot drift from acquisition truth"
        )
    accepted = (
        snapshot.get("distributionDecision") in _ACCEPTED_DECISIONS
        and judgment.get("distributionDecision") == snapshot.get("distributionDecision")
        and judgment.get("rightsStatus") in {"verified", "unverified", "unknown"}
        and judgment.get("safetyStatus") == "passed"
        and judgment.get("entityMatch") == "matched"
        and judgment.get("qualityStatus") == "passed"
        and judgment.get("privacyRisk") == "none"
        and judgment.get("minorRisk") == "none"
        and judgment.get("maliciousMediaRisk") == "none"
        and judgment.get("watermarkStatus") == "absent"
        and acquisition_safety.get("status") == "passed"
        and acquisition_safety.get("entityMatch") == "matched"
        and acquisition_safety.get("privacyRisk") == "none"
        and acquisition_safety.get("minorRisk") == "none"
        and acquisition_safety.get("maliciousMediaRisk") == "none"
        and acquisition_safety.get("watermarkStatus") == "absent"
    )
    if accepted:
        return "accepted"
    if judgment.get("distributionDecision") != "blocked":
        raise IndependentAssetReviewError(
            "a non-passing independent judgment must remain distributionDecision=blocked"
        )
    findings = [
        str(item).strip()
        for item in judgment.get("findings") or []
        if str(item).strip()
    ]
    if not findings:
        raise IndependentAssetReviewError(
            "blocked independent judgment requires findings"
        )
    return "blocked"


def _prepare_stable(
    *,
    output_root: Path,
    acquisition_receipt_path: Path,
    asset_kind: str,
    asset_id: str,
    execution_manifest_path: Path,
    author_evidence_path: Path,
    reviewer_evidence_path: Path,
    object_ref: str,
    judgment: Mapping[str, Any],
) -> dict[str, Any]:
    from content.source.independent_asset_review_preparation import prepare_stable

    return prepare_stable(
        output_root=output_root,
        acquisition_receipt_path=acquisition_receipt_path,
        asset_kind=asset_kind,
        asset_id=asset_id,
        execution_manifest_path=execution_manifest_path,
        author_evidence_path=author_evidence_path,
        reviewer_evidence_path=reviewer_evidence_path,
        object_ref=object_ref,
        judgment=judgment,
    )


def write_independent_asset_review_receipt(
    *,
    acquisition_receipt_path: Path,
    asset_kind: str,
    asset_id: str,
    execution_manifest_path: Path,
    author_evidence_path: Path,
    reviewer_evidence_path: Path,
    object_ref: str,
    judgment: Mapping[str, Any],
    output_root: Path | None = None,
    review_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Validate immutable inputs and write one idempotent create-once receipt."""

    root = (output_root or OUTPUT_ROOT).resolve()
    stable = _prepare_stable(
        output_root=root,
        acquisition_receipt_path=acquisition_receipt_path,
        asset_kind=asset_kind,
        asset_id=asset_id,
        execution_manifest_path=execution_manifest_path,
        author_evidence_path=author_evidence_path,
        reviewer_evidence_path=reviewer_evidence_path,
        object_ref=object_ref,
        judgment=judgment,
    )
    destination_root = (
        review_root.resolve()
        if review_root is not None
        else execution_manifest_path.resolve().parent / "evidence/asset_reviews"
    )
    try:
        destination_root.relative_to(root)
    except ValueError as exc:
        raise IndependentAssetReviewError(
            "asset review root must be below QWQ_OUTPUT_ROOT"
        ) from exc
    destination = destination_root / "receipts" / f"{stable['reviewId']}.json"
    if destination.is_file():
        existing = load_independent_asset_review_receipt(
            destination.relative_to(root).as_posix(),
            output_root=root,
        )
        existing_stable = {
            key: value
            for key, value in existing.items()
            if key not in {"recordedAt", "receiptDigest"}
        }
        if existing_stable != stable:
            raise IndependentAssetReviewError(
                f"independent asset review create-once collision: {destination}"
            )
        return existing, destination
    document = {
        **stable,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    document["receiptDigest"] = canonical_digest(document, excluded="receiptDigest")
    try:
        assert_valid(
            document,
            "source",
            "independent_asset_review_receipt",
            label="independent asset review receipt",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise IndependentAssetReviewError(str(exc)) from exc
    write_create_once(destination, document)
    frozen = load_independent_asset_review_receipt(
        destination.relative_to(root).as_posix(),
        output_root=root,
    )
    return frozen, destination


def load_independent_asset_review_receipt(
    receipt_ref: str,
    *,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Re-derive every identity and evidence digest before trusting a receipt."""

    root = (output_root or OUTPUT_ROOT).resolve()
    path = resolve_ref(
        receipt_ref,
        output_root=root,
        label="independent asset review receipt",
    )
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise IndependentAssetReviewError(
            "independent asset review receipt must be an object"
        )
    try:
        assert_valid(
            payload,
            "source",
            "independent_asset_review_receipt",
            label="independent asset review receipt",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise IndependentAssetReviewError(str(exc)) from exc
    if payload.get("receiptDigest") != canonical_digest(
        payload, excluded="receiptDigest"
    ):
        raise IndependentAssetReviewError(
            "independent asset review receiptDigest drift"
        )
    expected_name = f"{payload.get('reviewId')}.json"
    if path.parent.name != "receipts" or path.name != expected_name:
        raise IndependentAssetReviewError(
            "independent asset review receipt path is not canonical"
        )

    stable = _prepare_stable(
        output_root=root,
        acquisition_receipt_path=resolve_ref(
            str(payload["acquisitionReceiptRef"]),
            output_root=root,
            label="bound acquisition receipt",
        ),
        asset_kind=str(payload["assetKind"]),
        asset_id=str(payload["assetSnapshot"]["assetId"]),
        execution_manifest_path=resolve_ref(
            str(payload["executionManifestRef"]),
            output_root=root,
            label="bound execution manifest",
        ),
        author_evidence_path=resolve_ref(
            str(payload["authorExecution"]["evidenceRef"]),
            output_root=root,
            label="bound author evidence",
        ),
        reviewer_evidence_path=resolve_ref(
            str(payload["reviewerExecution"]["evidenceRef"]),
            output_root=root,
            label="bound reviewer evidence",
        ),
        object_ref=str(payload["objectRef"]),
        judgment=dict(payload["judgment"]),
    )
    recorded_stable = {
        key: value
        for key, value in payload.items()
        if key not in {"recordedAt", "receiptDigest"}
    }
    if recorded_stable != stable:
        raise IndependentAssetReviewError("independent asset review provenance drift")
    return payload


def assert_asset_review_accepted(
    receipt: Mapping[str, Any],
    *,
    content_sha256: str,
    source_digest: str,
    asset_id: str,
) -> None:
    """Fail closed unless a frozen receipt admits the exact release asset."""

    try:
        assert_valid(
            dict(receipt),
            "source",
            "independent_asset_review_receipt",
            label="independent asset review admission",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise IndependentAssetReviewError(str(exc)) from exc
    if receipt.get("receiptDigest") != canonical_digest(
        receipt, excluded="receiptDigest"
    ):
        raise IndependentAssetReviewError(
            "independent asset review receiptDigest drift"
        )
    snapshot = receipt.get("assetSnapshot")
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    if (
        receipt.get("reviewDecision") != "accepted"
        or receipt.get("sourceDigest") != source_digest
        or snapshot.get("assetId") != asset_id
        or snapshot.get("contentSha256") != content_sha256
        or snapshot.get("distributionDecision") not in _ACCEPTED_DECISIONS
        or snapshot.get("rightsStatus") == "restricted"
    ):
        raise IndependentAssetReviewError(
            "asset is not covered by one accepted independent review receipt"
        )
    if receipt.get("assetKind") == "video":
        assert_video_asset_snapshot_publishable(snapshot)


__all__ = [
    "IndependentAssetReviewError",
    "assert_asset_review_accepted",
    "load_independent_asset_review_receipt",
    "write_independent_asset_review_receipt",
]
