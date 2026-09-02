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

from content.source.independent_asset_review_inputs import (
    _ACCEPTED_DECISIONS,
    _asset_snapshot,
    _author_evidence_issues,
    _load_acquisition,
    _one_asset,
    _review_decision,
)
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
    receipt, receipt_ref, receipt_sha = _load_acquisition(
        acquisition_receipt_path,
        asset_kind=asset_kind,
        output_root=output_root,
    )
    manifest, manifest_ref, manifest_sha = load_document(
        execution_manifest_path,
        output_root=output_root,
        schema_group="execution",
        schema_name="content_execution_manifest",
        label="asset review execution manifest",
    )
    author, author_ref, author_sha = load_document(
        author_evidence_path,
        output_root=output_root,
        schema_group="content",
        schema_name="agent_result_envelope",
        label="asset review author evidence",
    )
    reviewer_path, reviewer_ref = audited_path(
        reviewer_evidence_path,
        output_root=output_root,
        label="asset independent reviewer evidence",
    )
    raw_reviewer = read_json(reviewer_path)
    if not isinstance(raw_reviewer, dict):
        raise IndependentAssetReviewError(
            "asset independent reviewer evidence must be an object"
        )
    supported_api_reviewer = (
        raw_reviewer.get("schema") == "quwoquan_data.host_source_review_result"
    )
    if supported_api_reviewer:
        if asset_kind != "image":
            raise IndependentAssetReviewError(
                "supported-API reviewer evidence is image-only"
            )
        from content.source.professional_image_supported_api_contract import (
            load_reviewer_results,
        )

        try:
            reviewer = load_reviewer_results(
                [reviewer_ref],
                root=output_root,
                catalog={},
                digest=canonical_digest,
            )[asset_id]
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
            raise IndependentAssetReviewError(str(exc)) from exc
    else:
        try:
            assert_valid(
                raw_reviewer,
                "content",
                "reviewer_result",
                label="asset independent reviewer evidence",
            )
        except (FileNotFoundError, TypeError, ValueError) as exc:
            raise IndependentAssetReviewError(str(exc)) from exc
        reviewer = raw_reviewer
    reviewer_sha = file_digest(reviewer_path)
    envelope_issues = _author_evidence_issues(
        author,
        workspace_root=author_evidence_path.resolve().parent,
    )
    if envelope_issues:
        raise IndependentAssetReviewError(
            "asset author evidence is not promotable: " + "; ".join(envelope_issues[:3])
        )

    source_digest = str(receipt.get("sourceDigest") or "").strip()
    manifest_source = manifest.get("sourceDigest")
    manifest_source = manifest_source if isinstance(manifest_source, Mapping) else {}
    execution_id = str(manifest.get("executionId") or "").strip()
    author_agent = author.get("agent")
    author_agent = author_agent if isinstance(author_agent, Mapping) else {}
    author_object_ref = str(author.get("ref") or "").strip()
    normalized_supported_ref = (
        supported_api_reviewer
        and object_ref == f"posts/image/{asset_id}"
        and author_object_ref == f"/professional-image/{asset_id}"
    )
    if (
        manifest_source.get("digest") != source_digest
        or author.get("executionId") != execution_id
        or (author_object_ref != object_ref and not normalized_supported_ref)
        or author.get("stage") != "author"
        or not str(author_agent.get("provider") or "").strip()
        or not str(author_agent.get("model") or "").strip()
    ):
        raise IndependentAssetReviewError("asset review source/author identity drift")

    if supported_api_reviewer:
        reviewer_actor = reviewer.get("actor")
        reviewer_actor = reviewer_actor if isinstance(reviewer_actor, Mapping) else {}
        reviewer_session_id = str(reviewer_actor.get("sessionId") or "").strip()
        reviewer_execution_id = (
            f"host-review:{reviewer_session_id}" if reviewer_session_id else ""
        )
        reviewer_model_family = str(reviewer_actor.get("modelFamily") or "").strip()
        reviewer_provider = "host:" + str(reviewer_actor.get("host") or "").strip()
        reviewer_model = reviewer_model_family
        if (
            reviewer.get("candidateId") != asset_id
            or reviewer.get("contentSha256")
            != _one_asset(receipt, asset_id=asset_id).get("contentSha256")
            or not reviewer_execution_id
            or not reviewer_model_family
        ):
            raise IndependentAssetReviewError(
                "supported-API reviewer identity differs from frozen asset/journal"
            )
    else:
        reviewer_execution_id = str(reviewer.get("executionId") or "").strip()
        reviewer_model_family = str(reviewer.get("modelFamily") or "").strip()
        reviewer_provider = str(reviewer.get("provider") or "")
        reviewer_model = str(reviewer.get("model") or "")
        if (
            reviewer_execution_id != execution_id
            or reviewer.get("objectRef") != object_ref
            or not reviewer_provider.strip()
            or not reviewer_model.strip()
            or not reviewer_model_family
        ):
            raise IndependentAssetReviewError(
                "asset review source/author/reviewer identity drift"
            )

    author_run_id = str(author_agent.get("runId") or "").strip()
    reviewer_run_id = str(reviewer.get("runId") or "").strip()
    acquisition_run_id = f"acquisition:{receipt.get('manifestId')}"
    if (
        not author_run_id
        or not reviewer_run_id
        or len({acquisition_run_id, author_run_id, reviewer_run_id}) != 3
    ):
        raise IndependentAssetReviewError(
            "asset acquisition, author, and reviewer must use independent runId values"
        )

    normalized_judgment = dict(judgment)
    try:
        # Validate the judgment with the receipt schema before using it to derive
        # a decision.  A temporary complete document avoids a second schema.
        assert_valid(
            {
                "schema": "quwoquan_data.independent_asset_review_receipt",
                "reviewId": "asset-review-" + "0" * 64,
                "assetKind": asset_kind,
                "objectRef": object_ref,
                "sourceRevision": str(receipt.get("sourceRevision") or ""),
                "sourceDigest": source_digest,
                "entityCatalogDigest": str(receipt.get("entityCatalogDigest") or ""),
                "acquisitionReceiptRef": receipt_ref,
                "acquisitionReceiptDigest": str(receipt.get("receiptDigest") or ""),
                "acquisitionReceiptSha256": receipt_sha,
                "executionManifestRef": manifest_ref,
                "executionManifestSha256": manifest_sha,
                "assetSnapshot": _asset_snapshot(
                    _one_asset(receipt, asset_id=asset_id),
                    asset_kind=asset_kind,
                ),
                "acquisitionExecution": {
                    "executionId": acquisition_run_id,
                    "objectRef": f"assets/{asset_kind}/{asset_id}",
                    "provider": "data_cli",
                    "model": f"professional_{asset_kind}_acquisition",
                    "runId": acquisition_run_id,
                    "evidenceRef": receipt_ref,
                    "evidenceSha256": receipt_sha,
                },
                "authorExecution": {
                    "executionId": execution_id,
                    "objectRef": author_object_ref,
                    "provider": str(author_agent.get("provider") or ""),
                    "model": str(author_agent.get("model") or ""),
                    "runId": author_run_id,
                    "evidenceRef": author_ref,
                    "evidenceSha256": author_sha,
                },
                "reviewerExecution": {
                    "executionId": reviewer_execution_id,
                    "objectRef": object_ref,
                    "provider": reviewer_provider,
                    "model": reviewer_model,
                    "modelFamily": reviewer_model_family,
                    "runId": reviewer_run_id,
                    "resultHash": (
                        str(reviewer.get("resultDigest") or "")
                        if supported_api_reviewer
                        else str(reviewer.get("resultHash") or "")
                    ),
                    "evidenceRef": reviewer_ref,
                    "evidenceSha256": reviewer_sha,
                },
                "judgment": normalized_judgment,
                "reviewDecision": "accepted",
                "recordedAt": "2026-01-01T00:00:00+00:00",
                "receiptDigest": "sha256:" + "0" * 64,
            },
            "source",
            "independent_asset_review_receipt",
            label="independent asset review input",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise IndependentAssetReviewError(str(exc)) from exc

    expected_result_hash = (
        str(reviewer.get("resultDigest") or "")
        if supported_api_reviewer
        else canonical_digest(normalized_judgment)
    )
    supported_judgment = reviewer.get("judgment")
    supported_judgment = (
        supported_judgment if isinstance(supported_judgment, Mapping) else {}
    )
    reviewer_findings = [
        str(item).strip()
        for item in (
            supported_judgment.get("findings")
            if supported_api_reviewer
            else reviewer.get("findings")
        ) or []
        if str(item).strip()
    ]
    judgment_findings = [
        str(item).strip()
        for item in normalized_judgment.get("findings") or []
        if str(item).strip()
    ]
    supported_judgment_matches = (
        not supported_api_reviewer
        or (
            supported_judgment.get("status")
            == ("passed" if normalized_judgment.get("safetyStatus") == "passed" else "blocked")
            and supported_judgment.get("entityMatch") == normalized_judgment.get("entityMatch")
            and supported_judgment.get("qualityStatus") == normalized_judgment.get("qualityStatus")
            and supported_judgment.get("privacyRisk") == normalized_judgment.get("privacyRisk")
            and supported_judgment.get("minorRisk") == normalized_judgment.get("minorRisk")
            and supported_judgment.get("maliciousMediaRisk")
            == normalized_judgment.get("maliciousMediaRisk")
            and supported_judgment.get("watermarkStatus")
            == normalized_judgment.get("watermarkStatus")
        )
    )
    if (
        (not supported_api_reviewer and reviewer.get("resultHash") != expected_result_hash)
        or not supported_judgment_matches
        or reviewer_findings != judgment_findings
    ):
        raise IndependentAssetReviewError(
            "independent reviewer resultHash/findings do not bind the asset judgment"
        )

    asset = _one_asset(receipt, asset_id=asset_id)
    snapshot = _asset_snapshot(asset, asset_kind=asset_kind)
    safety = asset.get("safetyReview")
    safety = safety if isinstance(safety, Mapping) else {}
    review_decision = _review_decision(
        normalized_judgment,
        snapshot=snapshot,
        acquisition_safety=safety,
    )
    reviewer_issues = [
        str(item).strip() for item in reviewer.get("issues") or [] if str(item).strip()
    ]
    expected_verdict = "passed" if review_decision == "accepted" else "failed"
    expected_issues = [] if review_decision == "accepted" else judgment_findings
    if (
        not supported_api_reviewer
        and (reviewer.get("verdict") != expected_verdict or reviewer_issues != expected_issues)
    ):
        raise IndependentAssetReviewError(
            "independent reviewer verdict/issues do not bind the asset decision"
        )

    stable: dict[str, Any] = {
        "schema": "quwoquan_data.independent_asset_review_receipt",
        "assetKind": asset_kind,
        "objectRef": object_ref,
        "sourceRevision": str(receipt.get("sourceRevision") or ""),
        "sourceDigest": source_digest,
        "entityCatalogDigest": str(receipt.get("entityCatalogDigest") or ""),
        "acquisitionReceiptRef": receipt_ref,
        "acquisitionReceiptDigest": str(receipt.get("receiptDigest") or ""),
        "acquisitionReceiptSha256": receipt_sha,
        "executionManifestRef": manifest_ref,
        "executionManifestSha256": manifest_sha,
        "assetSnapshot": snapshot,
        "acquisitionExecution": {
            "executionId": acquisition_run_id,
            "objectRef": f"assets/{asset_kind}/{asset_id}",
            "provider": "data_cli",
            "model": f"professional_{asset_kind}_acquisition",
            "runId": acquisition_run_id,
            "evidenceRef": receipt_ref,
            "evidenceSha256": receipt_sha,
        },
        "authorExecution": {
            "executionId": execution_id,
            "objectRef": author_object_ref,
            "provider": str(author_agent.get("provider") or ""),
            "model": str(author_agent.get("model") or ""),
            "runId": author_run_id,
            "evidenceRef": author_ref,
            "evidenceSha256": author_sha,
        },
        "reviewerExecution": {
            "executionId": reviewer_execution_id,
            "objectRef": object_ref,
            "provider": reviewer_provider,
            "model": reviewer_model,
            "modelFamily": reviewer_model_family,
            "runId": reviewer_run_id,
            "resultHash": expected_result_hash,
            "evidenceRef": reviewer_ref,
            "evidenceSha256": reviewer_sha,
        },
        "judgment": normalized_judgment,
        "reviewDecision": review_decision,
    }
    stable["reviewId"] = "asset-review-" + canonical_digest(stable).removeprefix("sha256:")
    return stable


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
        raise IndependentAssetReviewError("asset review root must be below QWQ_OUTPUT_ROOT") from exc
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
        raise IndependentAssetReviewError("independent asset review receipt must be an object")
    try:
        assert_valid(
            payload,
            "source",
            "independent_asset_review_receipt",
            label="independent asset review receipt",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise IndependentAssetReviewError(str(exc)) from exc
    if payload.get("receiptDigest") != canonical_digest(payload, excluded="receiptDigest"):
        raise IndependentAssetReviewError("independent asset review receiptDigest drift")
    expected_name = f"{payload.get('reviewId')}.json"
    if path.parent.name != "receipts" or path.name != expected_name:
        raise IndependentAssetReviewError("independent asset review receipt path is not canonical")

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
    if receipt.get("receiptDigest") != canonical_digest(receipt, excluded="receiptDigest"):
        raise IndependentAssetReviewError("independent asset review receiptDigest drift")
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
    "assert_asset_review_accepted", "load_independent_asset_review_receipt",
    "write_independent_asset_review_receipt",
]
