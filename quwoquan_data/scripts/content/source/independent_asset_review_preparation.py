"""Stable review preparation implementation for independent assets."""

from __future__ import annotations

from content.source.independent_asset_review import (
    Any,
    IndependentAssetReviewError,
    Mapping,
    Path,
    _asset_snapshot,
    _author_evidence_issues,
    _load_acquisition,
    _one_asset,
    _review_decision,
    assert_valid,
    audited_path,
    canonical_digest,
    file_digest,
    load_document,
    read_json,
    resolve_ref,
)


def prepare_stable(
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
        raw_reviewer.get("schema")
        == "quwoquan_data.professional_image_supported_api_reviewer_result"
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
            )[str(raw_reviewer.get("candidateId") or "")]
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
    binding = manifest.get("modelBinding")
    binding = binding if isinstance(binding, Mapping) else {}
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
        or author_agent.get("provider") != binding.get("provider")
        or author_agent.get("model") != binding.get("authorModel")
    ):
        raise IndependentAssetReviewError("asset review source/author identity drift")

    reviewer_execution_id = str(reviewer.get("executionId") or "").strip()
    reviewer_model_family = str(reviewer.get("modelFamily") or "").strip()
    if supported_api_reviewer:
        reviewer_manifest = read_json(
            resolve_ref(
                str(reviewer["executionManifestRef"]),
                output_root=output_root,
                label="supported-API reviewer execution manifest",
            )
        )
        reviewer_binding = (
            reviewer_manifest.get("modelBinding")
            if isinstance(reviewer_manifest, Mapping)
            else {}
        )
        reviewer_binding = (
            reviewer_binding if isinstance(reviewer_binding, Mapping) else {}
        )
        reviewer_model_family = str(reviewer_binding.get("reviewerModelFamily") or "")
        if (
            reviewer.get("candidateId") != asset_id
            or reviewer.get("contentSha256")
            != _one_asset(receipt, asset_id=asset_id).get("contentSha256")
            or reviewer.get("provider") != reviewer_binding.get("provider")
            or reviewer.get("model") != reviewer_binding.get("reviewerModel")
            or not reviewer_execution_id
        ):
            raise IndependentAssetReviewError(
                "supported-API reviewer identity differs from frozen asset/journal"
            )
    elif (
        reviewer_execution_id != execution_id
        or reviewer.get("objectRef") != object_ref
        or reviewer.get("provider") != binding.get("provider")
        or reviewer.get("model") != binding.get("reviewerModel")
        or reviewer_model_family != binding.get("reviewerModelFamily")
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
                    "provider": str(reviewer.get("provider") or ""),
                    "model": str(reviewer.get("model") or ""),
                    "modelFamily": reviewer_model_family,
                    "runId": reviewer_run_id,
                    "resultHash": (
                        str(reviewer.get("judgmentDigest") or "")
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
        str(reviewer.get("judgmentDigest") or "")
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
        )
        or []
        if str(item).strip()
    ]
    judgment_findings = [
        str(item).strip()
        for item in normalized_judgment.get("findings") or []
        if str(item).strip()
    ]
    supported_judgment_matches = not supported_api_reviewer or (
        supported_judgment.get("status")
        == (
            "passed"
            if normalized_judgment.get("safetyStatus") == "passed"
            else "blocked"
        )
        and supported_judgment.get("entityMatch")
        == normalized_judgment.get("entityMatch")
        and supported_judgment.get("qualityStatus")
        == normalized_judgment.get("qualityStatus")
        and supported_judgment.get("privacyRisk")
        == normalized_judgment.get("privacyRisk")
        and supported_judgment.get("minorRisk") == normalized_judgment.get("minorRisk")
        and supported_judgment.get("maliciousMediaRisk")
        == normalized_judgment.get("maliciousMediaRisk")
        and supported_judgment.get("watermarkStatus")
        == normalized_judgment.get("watermarkStatus")
    )
    if (
        (
            not supported_api_reviewer
            and reviewer.get("resultHash") != expected_result_hash
        )
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
    if not supported_api_reviewer and (
        reviewer.get("verdict") != expected_verdict
        or reviewer_issues != expected_issues
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
            "provider": str(reviewer.get("provider") or ""),
            "model": str(reviewer.get("model") or ""),
            "modelFamily": reviewer_model_family,
            "runId": reviewer_run_id,
            "resultHash": expected_result_hash,
            "evidenceRef": reviewer_ref,
            "evidenceSha256": reviewer_sha,
        },
        "judgment": normalized_judgment,
        "reviewDecision": review_decision,
    }
    stable["reviewId"] = "asset-review-" + canonical_digest(stable).removeprefix(
        "sha256:"
    )
    return stable
