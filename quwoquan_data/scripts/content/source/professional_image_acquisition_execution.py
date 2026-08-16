"""Execution implementation for governed professional-image acquisition."""

from __future__ import annotations

from content.source.professional_image_acquisition import (
    _MAX_IMAGE_BYTES,
    _MIN_IMAGE_BYTES,
    ACQUISITION_ROOT,
    AcquisitionStatus,
    Any,
    DistributionDecision,
    Mapping,
    Path,
    RightsStatus,
    _content_digest,
    _digest,
    _frozen_supported_api_payload,
    _manual_payload,
    _portable_ref,
    _provider_counts,
    _put_cas,
    _validate_item,
    _write_create_once_receipt,
    bound_image_source_attribution,
    build_image_plan_spec,
    image_distribution_decision,
    load_discovery_candidates,
    pixel_size_issue,
    pre_acquisition_block,
    probe_image_bytes,
    read_json,
    validate_discovery_binding,
    validate_image_receipt_inventory,
)


def acquire_professional_images(
    manifest_path: Path,
    *,
    handoff_ref: Path,
    repo_root: Path | None = None,
    manual_root: Path | None = None,
    output_root: Path = ACQUISITION_ROOT,
    schema_validator: Any,
    network_payload: Any,
    source_identity_guard: Any,
    safety_evidence_loader: Any,
    safety_payload_validator: Any,
) -> tuple[dict[str, Any], Path]:
    """Acquire every manifest item and write a create-once auditable receipt."""
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise TypeError("professional image acquisition manifest must be an object")
    schema_validator(
        manifest,
        "source",
        "professional_image_acquisition_manifest",
        label="professional image acquisition manifest",
    )
    source_identity_guard(
        manifest,
        handoff_ref=handoff_ref,
        repo_root=repo_root,
    )
    asset_ids = [str(item["assetId"]) for item in manifest["items"]]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("professional image acquisition assetId values must be unique")
    discovery_candidates = load_discovery_candidates(
        manifest,
        output_root=output_root,
    )
    manifest_digest = _digest(manifest)
    rows: list[dict[str, Any]] = []
    seen_content: dict[str, str] = {}
    for raw in manifest["items"]:
        item = dict(raw)
        validate_discovery_binding(item, candidates=discovery_candidates)
        rights_status, provider = _validate_item(item)
        safety_evidence = safety_evidence_loader(
            item,
            evidence_root=output_root,
            kind="image",
        )
        path_allowed = bool(provider["pathAllowed"])
        payload: dict[str, Any] | None = None
        failure_code = ""
        failure = ""
        if not path_allowed:
            acquisition_status = AcquisitionStatus.BLOCKED
            failure_code = "DATA.SOURCE.ACQUISITION_PATH_BLOCKED"
            failure = failure_code
        else:
            failure_code, failure_detail = pre_acquisition_block(item)
            if failure_code:
                acquisition_status = AcquisitionStatus.BLOCKED
                failure = f"{failure_code}:{failure_detail}"
            else:
                if item["acquisitionPath"] == "manual_file":
                    if manual_root is None:
                        raise ValueError(
                            "manual_root is required by manual_file acquisition"
                        )
                    payload = _manual_payload(
                        str(item["manualFile"]),
                        manual_root=manual_root,
                    )
                elif (
                    item["acquisitionPath"] == "supported_api"
                    and not str(item.get("apiEvidence") or "").startswith("https://")
                    and (output_root / str(item.get("apiEvidence") or "")).is_file()
                ):
                    payload = _frozen_supported_api_payload(
                        item, output_root=output_root
                    )
                else:
                    payload = network_payload(
                        str(item["assetUrl"]),
                        supported_api=item["acquisitionPath"] == "supported_api",
                    )
                acquisition_status = (
                    AcquisitionStatus.ACQUIRED
                    if payload is not None
                    else AcquisitionStatus.FAILED
                )
                if payload is None:
                    failure_code = "DATA.SOURCE.ACQUISITION_FAILED"
                    failure = failure_code
        authorization_proof = str(item.get("authorizationProof") or "").strip()
        decision = image_distribution_decision(
            acquisition_status=acquisition_status,
            rights_status=rights_status,
            authorization_proof=authorization_proof,
            usage_scope=str(item["usageScope"]),
            model_release_status=str(item["modelReleaseStatus"]),
        )
        source_attribution = None
        if isinstance(item.get("sourceAttribution"), Mapping):
            source_attribution = bound_image_source_attribution(
                item,
                platform=str(provider["platform"]),
                distribution_decision=decision.value,
            )
        elif decision in {
            DistributionDecision.RESEARCH_ALLOWED,
            DistributionDecision.COMMERCIAL_ALLOWED,
        }:
            raise ValueError(
                f"{item['assetId']}: admitted image requires sourceAttribution"
            )
        content_sha256 = ""
        asset_ref = ""
        width = 0
        height = 0
        plan_spec: dict[str, Any] | None = None
        if payload is not None:
            body = bytes(payload["bytes"])
            probe = probe_image_bytes(body)
            if not probe.succeeded:
                acquisition_status = AcquisitionStatus.FAILED
                decision = DistributionDecision.BLOCKED
                failure_code = "DATA.SOURCE.IMAGE_DECODE_FAILED"
                failure = f"{failure_code}:{probe.failure.value}"
            else:
                safety_payload_validator(
                    safety_evidence,
                    item,
                    body=body,
                    width=probe.width,
                    height=probe.height,
                )
                content_sha256 = _content_digest(body)
                duplicate_of = seen_content.get(content_sha256)
                cas_path = _put_cas(body, str(payload["ext"]), output_root=output_root)
                asset_ref = _portable_ref(cas_path, output_root)
                width, height = probe.width, probe.height
                if duplicate_of:
                    decision = DistributionDecision.BLOCKED
                    failure_code = "DATA.SOURCE.DUPLICATE_ASSET"
                    failure = f"{failure_code}:{duplicate_of}"
                else:
                    seen_content[content_sha256] = str(item["assetId"])
                    quality_issue = pixel_size_issue(
                        width,
                        height,
                        asset_id=str(item["assetId"]),
                    )
                    if quality_issue:
                        decision = DistributionDecision.BLOCKED
                        failure_code = "DATA.SOURCE.IMAGE_QUALITY_BLOCKED"
                        failure = f"{failure_code}:{quality_issue}"
                if decision in {
                    DistributionDecision.RESEARCH_ALLOWED,
                    DistributionDecision.COMMERCIAL_ALLOWED,
                }:
                    plan_spec = build_image_plan_spec(
                        item,
                        platform=str(provider["platform"]),
                        source_id=str(provider["sourceId"]),
                        cas_uri=cas_path.resolve().as_uri(),
                        content_sha256=content_sha256,
                        acquisition_status=acquisition_status.value,
                        rights_status=rights_status.value,
                        authorization_required=(
                            rights_status is not RightsStatus.VERIFIED
                            or not authorization_proof
                        ),
                        distribution_decision=decision.value,
                        width=width,
                        height=height,
                    )
        rows.append(
            {
                "assetId": str(item["assetId"]),
                "entityId": str(item["entityId"]),
                "observedEntityId": str(item["observedEntityId"]),
                "entityAliases": list(item["entityAliases"]),
                "displayName": str(item["displayName"]),
                "discoveryCandidateId": str(item["discoveryCandidateId"]),
                "discoveryUrl": str(item["discoveryUrl"]),
                "provider": str(provider["sourceId"]),
                "platform": str(provider["platform"]),
                "acquisitionPath": str(item["acquisitionPath"]),
                "assetUrl": str(item.get("assetUrl") or ""),
                "manualFile": str(item.get("manualFile") or ""),
                "apiEvidence": str(item.get("apiEvidence") or ""),
                "accessEvidence": dict(item["accessEvidence"]),
                "acquisitionStatus": acquisition_status.value,
                "rightsStatus": rights_status.value,
                "authorizationRequired": (
                    rights_status is not RightsStatus.VERIFIED
                    or not authorization_proof
                ),
                "distributionDecision": decision.value,
                "sourceUrl": str(item["sourceUrl"]),
                "creator": str(item["creator"]),
                "capturedAt": str(item["capturedAt"]),
                "contentSha256": content_sha256,
                "assetRef": asset_ref,
                "bytes": len(payload["bytes"]) if payload is not None else 0,
                "width": width,
                "height": height,
                "license": str(item["license"]),
                "licenseSnapshot": str(item["licenseSnapshot"]),
                "usageScope": str(item["usageScope"]),
                "modelReleaseStatus": str(item["modelReleaseStatus"]),
                "termsUrl": str(item["termsUrl"]),
                "authorizationProof": authorization_proof,
                "rightsIssues": list(item["rightsIssues"]),
                "caption": str(item["caption"]),
                "relevance": str(item["relevance"]),
                "safetyReview": dict(item["safetyReview"]),
                "sourceAttribution": source_attribution,
                "withdrawalRequired": rights_status is not RightsStatus.VERIFIED,
                "failureCode": failure_code,
                "failure": failure,
                "planImageSpec": plan_spec,
            }
        )
    provider_counts = _provider_counts(rows)
    downloaded = sum(row["acquisitionStatus"] == "acquired" for row in rows)
    accepted = sum(
        row["distributionDecision"] in {"research_allowed", "commercial_allowed"}
        for row in rows
    )
    stable = {
        "schema": "quwoquan_data.professional_image_acquisition_receipt",
        "manifestId": str(manifest["manifestId"]),
        "manifestDigest": manifest_digest,
        "sourceRevision": str(manifest["sourceRevision"]),
        "sourceDigest": str(manifest["sourceDigest"]),
        "entityCatalogDigest": str(manifest["entityCatalogDigest"]),
        "discoveryPlanRef": str(manifest["discoveryPlanRef"]),
        "discoveryPlanDigest": str(manifest["discoveryPlanDigest"]),
        "plannedAssetCount": len(rows),
        "discoveredAssetCount": len(rows),
        "downloadedAssetCount": downloaded,
        "acceptedAssetCount": accepted,
        "rejectedAssetCount": len(rows) - accepted,
        "providerAssetCounts": provider_counts,
        "assets": rows,
    }
    receipt = {**stable, "receiptDigest": _digest(stable)}
    schema_validator(
        receipt,
        "source",
        "professional_image_acquisition_receipt",
        label="professional image acquisition receipt",
    )
    validate_image_receipt_inventory(
        receipt,
        resolved_root=output_root.resolve(),
        min_image_bytes=_MIN_IMAGE_BYTES,
        max_image_bytes=_MAX_IMAGE_BYTES,
        validate_item=_validate_item,
        pre_acquisition_block=pre_acquisition_block,
        provider_counts=_provider_counts,
    )
    receipt_path = (
        output_root / "receipts" / f"{manifest_digest.removeprefix('sha256:')}.json"
    )
    _write_create_once_receipt(receipt_path, receipt)
    return receipt, receipt_path
