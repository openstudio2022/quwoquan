"""Freeze image bytes and exact host-review requests before admission."""
from __future__ import annotations
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from core.image_decode import probe_image_bytes
from core.image_deduplication import perceptual_hash, perceptual_hash_distance
from core.image_safety import (
    NEAR_DUP_HAMMING,
    STATUS_UNSAFE,
    assess_image,
    watermark_prone_source_reason,
)
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT
from core.schema import assert_valid
from content.source.pre_acquisition_handoff import (
    guard_acquisition_source_identity,
)
from content.release.canonical.canonical_inventory import (
    assert_canonical_image_unique,
)
from content.source.professional_image_supported_api_input_support import (
    PREPARATION_INVALID,
    PREPARATION_ROOT,
    SOURCE_POOL_SHORTFALL,
    ProfessionalImageSupportedApiInputError,
    _MAX_IMAGE_BYTES,
    _MIN_IMAGE_BYTES,
    _assert_rebindable_provenance,
    _bytes_digest,
    _digest,
    _external_inputs_digest,
    _manifest_item,
    _prior_physical_identities,
    _prior_rebindable_physical_inputs,
    _review_bindings,
    _safe_ref,
    _safe_token,
    _validated_transport,
    _write_json,
    _write_once,
)
from content.source.professional_image_supported_api_contract import (
    commons_request_url,
    load_document,
    load_reviewer_results,
    review_accepted,
    source_attribution,
    supported_api_detail,
    verify_fresh_metadata,
    verify_metadata_catalog,
    verify_plan,
)
from content.source.professional_image_openverse_contract import openverse_detail_url
from content.source.professional_image_transport import (
    fetch_public_image,
    fetch_public_json,
)
from content.source.professional_safety_evidence import file_sha256
from content.source.host_source_review import prepare_host_source_review_request
def prepare_supported_api_inputs(
    *,
    handoff_ref: Path,
    discovery_plan_path: Path,
    metadata_catalog_path: Path,
    accepted_target: int,
    output_root: Path = PREPARATION_ROOT,
    reviewer_root: Path = OUTPUT_ROOT,
    reviewer_result_refs: Sequence[str] = (),
    publish_root: Path = PUBLISH_ROOT,
    api_fetcher: Callable[..., dict[str, Any]] = fetch_public_json,
    image_fetcher: Callable[..., dict[str, Any] | None] = fetch_public_image,
    identity_guard: Callable[..., Mapping[str, Any]] = guard_acquisition_source_identity,
    inventory_check: Callable[..., None] = assert_canonical_image_unique,
) -> tuple[dict[str, Any], Path]:
    """Create or resume one deterministic supported-API preparation checkpoint."""
    if isinstance(accepted_target, bool) or accepted_target < 1:
        raise ProfessionalImageSupportedApiInputError(
            PREPARATION_INVALID, "acceptedTarget must be >= 1"
        )
    try:
        plan = load_document(
            discovery_plan_path, group="source", name="professional_image_discovery_plan"
        )
        catalog = load_document(
            metadata_catalog_path,
            group="source", name="professional_image_supported_api_metadata_catalog",
        )
        verify_metadata_catalog(catalog, digest=_digest)
        planned = verify_plan(plan, catalog, digest=_digest)
        handoff = identity_guard(
            catalog, handoff_ref=handoff_ref, frozen_external_input=True
        )
        if not isinstance(handoff, Mapping) or not handoff.get("sourceDigest"):
            handoff = {
                "sourceRevision": catalog["sourceRevision"],
                "sourceDigest": {
                    "algorithm": "sha256", "digest": catalog["sourceDigest"],
                    "inputs": ["focused-test-injected-identity"],
                },
                "executionBundle": {
                    "algorithm": "sha256", "digest": "sha256:" + "0" * 64,
                    "inputs": ["focused-test-injected-identity"],
                },
                "entityCatalogDigest": catalog["entityCatalogDigest"],
            }
        execution_identity = {
            "sourceRevision": str(handoff["sourceRevision"]),
            "sourceDigest": str(handoff["sourceDigest"]["digest"]),
            "entityCatalogDigest": str(handoff["entityCatalogDigest"]),
        }
        resolved_handoff_ref = handoff_ref.expanduser().resolve()
        source_review_identity = (
            {
                **execution_identity,
                "executionBundleDigest": str(handoff["executionBundle"]["digest"]),
                "handoffDigest": file_sha256(resolved_handoff_ref),
            }
            if resolved_handoff_ref.is_file()
            else None
        )
        reviewers = load_reviewer_results(
            reviewer_result_refs, root=reviewer_root.resolve(), catalog=catalog,
            digest=_digest, execution_source_identity=execution_identity,
            source_review_identity=source_review_identity,
        )
    except ProfessionalImageSupportedApiInputError:
        raise
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise ProfessionalImageSupportedApiInputError(
            PREPARATION_INVALID, str(exc)
        ) from exc
    preparation_digest = _digest(
        {
            "planDigest": plan["planDigest"],
            "catalogDigest": catalog["catalogDigest"],
            "acceptedTarget": accepted_target,
        }
    )
    preparation_id = "professional-image-supported-api-" + preparation_digest[7:23]
    root = output_root.resolve() / preparation_id
    _write_json(root / "inputs/discovery-plan.json", plan)
    _write_json(root / "inputs/metadata-catalog.json", catalog)
    items: list[dict[str, Any]] = []
    manifest_items: list[dict[str, Any]] = []
    seen = _prior_physical_identities(output_root=output_root, current_root=root)
    prior_provider_asset_ids = {row[3] for row in seen}
    prior_rebinds = _prior_rebindable_physical_inputs(
        output_root=output_root, current_root=root
    )
    for candidate in catalog["candidates"]:
        candidate_id = str(candidate["candidateId"])
        token = _safe_token(candidate_id)
        provenance_block = watermark_prone_source_reason(
            [candidate_id, candidate["fileTitle"], candidate["caption"], candidate["relevance"]]
        )
        if provenance_block:
            block = {
                "schema": "quwoquan_data.professional_image_supported_api_block",
                "candidateId": candidate_id, "status": "blocked",
                "failureCode": "DATA.SOURCE.WATERMARK_BLOCKED", "reason": provenance_block,
            }
            assert_valid(
                block, "source", "professional_image_supported_api_block",
                label=f"supported API block:{candidate_id}",
            )
            block_path = _write_json(root / f"candidates/{token}/block.json", block)
            items.append({
                "candidateId": candidate_id, "status": "blocked",
                "evidenceRef": _safe_ref(block_path, root),
                "evidenceSha256": file_sha256(block_path),
                "failureCode": "DATA.SOURCE.WATERMARK_BLOCKED",
            })
            continue
        try:
            request_url = (
                openverse_detail_url(str(candidate["providerAssetId"]))
                if candidate["provider"] == "openverse"
                else commons_request_url(str(candidate["fileTitle"]))
            )
            api_path = root / f"candidates/{token}/api-response.json"
            api_transport_path = root / f"candidates/{token}/api-https-transport.json"
            if api_path.is_file():
                api_bytes = api_path.read_bytes()
                api_payload = json.loads(api_bytes.decode("utf-8"))
                api_transport = load_document(
                    api_transport_path,
                    group="source",
                    name="professional_image_https_transport_evidence",
                )
                if api_transport["responseSha256"] != _bytes_digest(api_bytes):
                    raise ProfessionalImageSupportedApiInputError(
                        PREPARATION_INVALID, "cached API HTTPS transport bytes drift"
                    )
            else:
                fetched_api = api_fetcher(request_url)
                api_bytes = bytes(fetched_api["bytes"])
                api_payload = fetched_api["payload"]
                api_transport = _validated_transport(fetched_api, body=api_bytes)
                _write_once(api_path, api_bytes)
                _write_json(api_transport_path, api_transport)
            meta = supported_api_detail(candidate, api_payload)
            verify_fresh_metadata(candidate, meta)
            second_block = watermark_prone_source_reason(
                [*meta.values(), candidate["fileTitle"]]
            )
            if second_block:
                raise ProfessionalImageSupportedApiInputError(
                    "DATA.SOURCE.WATERMARK_BLOCKED", second_block
                )
            asset_path_root = root / f"candidates/{token}/original"
            existing = next(asset_path_root.glob("asset.*"), None) if asset_path_root.is_dir() else None
            rebound_physical_input = prior_rebinds.get(
                str(candidate["providerAssetId"])
            )
            if (
                rebound_physical_input is None
                and str(candidate["providerAssetId"]) in prior_provider_asset_ids
            ):
                raise ProfessionalImageSupportedApiInputError(
                    "DATA.SOURCE.REBIND_ASSET_SHA_DRIFT",
                    "prior physical evidence for providerAssetId is not integrity-valid",
                )
            if existing is None:
                if rebound_physical_input is not None:
                    prior_asset, prior_evidence, prior_request = rebound_physical_input
                    _assert_rebindable_provenance(
                        candidate=candidate,
                        meta=meta,
                        evidence=prior_evidence,
                        request=prior_request,
                    )
                    asset_path = _write_once(
                        asset_path_root / f"asset{prior_asset.suffix}",
                        prior_asset.read_bytes(),
                    )
                    prior_transport = prior_evidence["originalTransportEvidenceRef"]
                    prior_root = prior_asset.parents[3]
                    original_transport = load_document(
                        prior_root / str(prior_transport),
                        group="source",
                        name="professional_image_https_transport_evidence",
                    )
                    original_transport_path = _write_json(
                        root / f"candidates/{token}/original-https-transport.json",
                        original_transport,
                    )
                else:
                    fetched = image_fetcher(
                        str(meta["originalAssetUrl"]), supported_api=True,
                        min_bytes=_MIN_IMAGE_BYTES, max_bytes=_MAX_IMAGE_BYTES,
                    )
                    if fetched is None:
                        raise ProfessionalImageSupportedApiInputError(
                            PREPARATION_INVALID, "original image fetch returned no image"
                        )
                    asset_path = _write_once(
                        asset_path_root / f"asset{fetched['ext']}", bytes(fetched["bytes"])
                    )
                    original_transport = _validated_transport(
                        fetched, body=bytes(fetched["bytes"])
                    )
                    original_transport_path = _write_json(
                        root / f"candidates/{token}/original-https-transport.json",
                        original_transport,
                    )
            else:
                asset_path = existing
                original_transport_path = (
                    root / f"candidates/{token}/original-https-transport.json"
                )
                original_transport = load_document(
                    original_transport_path,
                    group="source",
                    name="professional_image_https_transport_evidence",
                )
            body = asset_path.read_bytes()
            if original_transport["responseSha256"] != _bytes_digest(body):
                raise ProfessionalImageSupportedApiInputError(
                    PREPARATION_INVALID, "cached original HTTPS transport bytes drift"
                )
            probe = probe_image_bytes(body)
            if not probe.succeeded:
                raise ProfessionalImageSupportedApiInputError(
                    PREPARATION_INVALID, f"image decode failed: {probe.failure.value}"
                )
            content_sha = _bytes_digest(body)
            phash = perceptual_hash(asset_path)
            if any(
                content_sha == sha
                or perceptual_hash_distance(phash, peer) <= NEAR_DUP_HAMMING
                for sha, peer, _, _ in seen
            ) and rebound_physical_input is None:
                raise ProfessionalImageSupportedApiInputError(
                    "DATA.SOURCE.DUPLICATE_ASSET",
                    "global exact/pHash duplicate across supported-API preparations",
                )
            inventory_check(
                publish_root=publish_root,
                manifest={"contentType": "image", "assets": [{
                    "assetId": candidate_id, "sha256": content_sha,
                    "perceptualHash": phash,
                }]},
                excluded_manifest_path=f"__supported_api_preparation__/{token}",
            )
            seen.append(
                (
                    content_sha,
                    phash,
                    candidate_id,
                    str(candidate["providerAssetId"]),
                )
            )
            machine = {
                "schema": "quwoquan_data.professional_image_machine_assessment",
                "candidateId": candidate_id, "contentSha256": content_sha,
                "bytes": len(body), "dimensions": {"width": probe.width, "height": probe.height},
                "perceptualHash": phash, "verdict": assess_image(asset_path).to_dict(),
            }
            assert_valid(
                machine, "source", "professional_image_machine_assessment",
                label=f"professional image machine assessment:{candidate_id}",
            )
            machine_path = _write_json(root / f"candidates/{token}/machine-assessment.json", machine)
            request_path = root / f"candidates/{token}/review-request.json"
            acquisition_evidence = {
                "schema": "quwoquan_data.host_review_image_acquisition_evidence",
                "assetId": candidate_id,
                "entityId": str(candidate["entityId"]),
                "observedEntityId": str(candidate["observedEntityId"]),
                "contentSha256": content_sha,
                "assetRef": _safe_ref(asset_path, root),
                "apiResponseRef": _safe_ref(api_path, root),
                "apiResponseSha256": file_sha256(api_path),
            }
            acquisition_path = _write_json(
                root / f"candidates/{token}/acquisition-evidence.json", acquisition_evidence
            )
            probe_evidence = {
                "schema": "quwoquan_data.host_review_image_probe_evidence",
                "assetId": candidate_id,
                "entityId": str(candidate["entityId"]),
                "contentSha256": content_sha,
                "dimensions": {"width": probe.width, "height": probe.height},
                "machineAssessmentRef": _safe_ref(machine_path, root),
                "machineAssessmentSha256": file_sha256(machine_path),
            }
            probe_path = _write_json(
                root / f"candidates/{token}/media-probe-evidence.json", probe_evidence
            )
            safety_scan = {
                "schema": "quwoquan_data.host_review_safety_scan_evidence",
                "assetId": candidate_id,
                "entityId": str(candidate["entityId"]),
                "contentSha256": content_sha,
                "machineVerdict": machine["verdict"],
            }
            safety_scan_path = _write_json(
                root / f"candidates/{token}/safety-scan-evidence.json", safety_scan
            )
            rights = source_attribution(
                meta,
                observed_at=str(catalog["observedAt"]),
                platform=("Openverse" if candidate["provider"] == "openverse" else "Wikimedia Commons"),
            )
            rights_evidence = {
                "schema": "quwoquan_data.host_review_rights_evidence",
                "assetId": candidate_id,
                "entityId": str(candidate["entityId"]),
                "contentSha256": content_sha,
                "sourceAttribution": rights,
            }
            rights_path = _write_json(
                root / f"candidates/{token}/rights-evidence.json", rights_evidence
            )
            review_identity = source_review_identity or {**execution_identity,
                "executionBundleDigest": str(handoff["executionBundle"]["digest"]),
                "handoffDigest": str(catalog["handoffDigest"])}
            request, request_ref = prepare_host_source_review_request(
                evidence_root=root, source_identity=review_identity,
                asset_kind="image",
                asset_id=candidate_id,
                asset_ref=_safe_ref(asset_path, root),
                content_sha256=content_sha,
                entity_id=str(candidate["entityId"]),
                observed_entity_id=str(candidate["observedEntityId"]),
                content_ref=str(meta["sourcePageUrl"]),
                evidence_refs={
                    "acquisition": _safe_ref(acquisition_path, root),
                    "media_probe": _safe_ref(probe_path, root),
                    "safety_scan": _safe_ref(safety_scan_path, root),
                    "rights_attribution": _safe_ref(rights_path, root),
                },
            )
            request_path = root / request_ref
            reviewer = reviewers.get(candidate_id)
            judgment = reviewer.get("judgment") if reviewer else None
            machine_unsafe = machine["verdict"]["status"] == STATUS_UNSAFE
            accepted = (
                isinstance(judgment, Mapping)
                and reviewer.get("contentSha256") == content_sha
                and reviewer.get("requestDigest") == request["requestDigest"]
                and not machine_unsafe
                and review_accepted(judgment)
            )
            status = "accepted" if accepted else ("blocked" if reviewer else "review_pending")
            failure_code = "" if accepted else ("DATA.SOURCE.SAFETY_REVIEW_BLOCKED"
                if reviewer else "DATA.SOURCE.HOST_REVIEW_PENDING")
            reviewer_ref = str(reviewer.get("evidenceRef") or "") if reviewer else ""
            reviewer_sha = file_sha256(reviewer["evidencePath"]) if reviewer else ""
            safety_ref = safety_sha = ""
            attribution = None
            if accepted:
                safety = {
                    "schema": "quwoquan_data.professional_image_safety_review_evidence",
                    "assetId": candidate_id, "entityId": candidate["entityId"],
                    "observedEntityId": candidate["observedEntityId"],
                    "sourceUrl": meta["sourcePageUrl"], "contentSha256": content_sha,
                    "bytes": len(body), "dimensions": {"width": probe.width, "height": probe.height},
                    "status": "passed", "entityMatch": "matched", "privacyRisk": "none",
                    "minorRisk": "none", "maliciousMediaRisk": "none",
                    "watermarkStatus": "absent", "reviewedAt": reviewer["reviewedAt"],
                    "reviewer": f"host:{reviewer['runId']}",
                }
                safety_path = _write_json(root / f"safety-evidence/images/{token}.json", safety)
                safety_ref, safety_sha = _safe_ref(safety_path, root), file_sha256(safety_path)
                attribution = source_attribution(
                    meta,
                    observed_at=str(catalog["observedAt"]),
                    platform=(
                        "Openverse"
                        if candidate["provider"] == "openverse"
                        else "Wikimedia Commons"
                    ),
                )
            evidence = {
                "schema": "quwoquan_data.professional_image_supported_api_evidence",
                "candidateId": candidate_id,
                "discoveryCandidateId": candidate["discoveryCandidateId"],
                "provider": candidate["provider"],
                "providerAssetId": candidate["providerAssetId"],
                "upstreamProvider": candidate["upstreamProvider"],
                "status": status,
                "requestUrl": request_url, "observedAt": catalog["observedAt"],
                "sourcePageUrl": meta["sourcePageUrl"],
                "originalAssetUrl": meta["originalAssetUrl"], "creator": meta["creator"],
                "license": meta["license"],
                "licenseVersion": meta["licenseVersion"],
                "attributionText": meta["attributionText"],
                "termsUrl": meta["termsUrl"],
                "apiResponseRef": _safe_ref(api_path, root),
                "apiResponseSha256": file_sha256(api_path),
                "apiResponseDigest": _digest(api_payload),
                "apiTransportEvidenceRef": _safe_ref(api_transport_path, root),
                "apiTransportEvidenceSha256": file_sha256(api_transport_path),
                "originalAssetRef": _safe_ref(asset_path, root),
                "originalTransportEvidenceRef": _safe_ref(
                    original_transport_path, root
                ),
                "originalTransportEvidenceSha256": file_sha256(
                    original_transport_path
                ),
                "contentSha256": content_sha, "bytes": len(body),
                "dimensions": {"width": probe.width, "height": probe.height},
                "perceptualHash": phash,
                "machineAssessmentRef": _safe_ref(machine_path, root),
                "machineAssessmentSha256": file_sha256(machine_path),
                "reviewRequestRef": _safe_ref(request_path, root),
                "reviewRequestSha256": file_sha256(request_path),
                "reviewerEvidenceRef": reviewer_ref,
                "reviewerEvidenceSha256": reviewer_sha,
                "safetyEvidenceRef": safety_ref, "safetyEvidenceSha256": safety_sha,
                "sourceAttribution": attribution, "failureCode": failure_code,
            }
            assert_valid(
                evidence, "source", "professional_image_supported_api_evidence",
                label=f"supported API evidence:{candidate_id}",
            )
            evidence_digest = _digest(evidence)
            evidence_path = _write_json(
                root / f"candidates/{token}/evidence/{evidence_digest[7:]}.json", evidence
            )
            items.append({
                "candidateId": candidate_id, "status": status,
                "evidenceRef": _safe_ref(evidence_path, root),
                "evidenceSha256": file_sha256(evidence_path), "failureCode": failure_code,
            })
            if accepted:
                evidence_ref = _safe_ref(evidence_path, root)
                acquisition_evidence_ref = (
                    (root.relative_to(output_root.resolve()) / evidence_ref).as_posix()
                    if output_root.resolve() in root.parents
                    else evidence_ref
                )
                manifest_items.append(_manifest_item(
                    candidate, planned[str(candidate["discoveryCandidateId"])], meta,
                    safety_ref, safety_sha, acquisition_evidence_ref,
                    {
                        **judgment, "reviewerRunId": reviewer["runId"],
                        "reviewerReviewedAt": reviewer["reviewedAt"],
                    },
                    str(catalog["observedAt"]),
                ))
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            code = exc.code if isinstance(exc, ProfessionalImageSupportedApiInputError) else PREPARATION_INVALID
            block = {
                "schema": "quwoquan_data.professional_image_supported_api_block",
                "candidateId": candidate_id, "status": "blocked", "failureCode": code,
                "reason": str(exc),
            }
            assert_valid(
                block, "source", "professional_image_supported_api_block",
                label=f"supported API block:{candidate_id}",
            )
            block_path = _write_json(root / f"candidates/{token}/block.json", block)
            items.append({
                "candidateId": candidate_id, "status": "blocked",
                "evidenceRef": _safe_ref(block_path, root),
                "evidenceSha256": file_sha256(block_path), "failureCode": code,
            })
    manifest_ref = manifest_sha = ""
    external_inputs_digest = _external_inputs_digest(
        plan=plan, catalog=catalog, root=root
    )
    frozen_physical_input = {
        "sourceRevision": catalog["sourceRevision"],
        "sourceDigest": catalog["sourceDigest"],
        "entityCatalogDigest": catalog["entityCatalogDigest"],
        "metadataCatalogDigest": catalog["catalogDigest"],
        "externalInputsDigest": external_inputs_digest,
    }
    review_execution_bindings, review_source_bindings = _review_bindings(reviewers)
    if manifest_items:
        manifest = {
            "schema": "quwoquan_data.professional_image_acquisition_manifest",
            "manifestId": preparation_id,
            **execution_identity,
            "executionBundle": handoff["executionBundle"],
            "frozenPhysicalInput": frozen_physical_input,
            "reviewExecutionBindings": review_execution_bindings,
            "reviewSourceBindings": review_source_bindings,
            "discoveryPlanRef": "inputs/discovery-plan.json",
            "discoveryPlanDigest": plan["planDigest"], "items": manifest_items,
        }
        assert_valid(
            manifest, "source", "professional_image_acquisition_manifest",
            label="prepared professional image acquisition manifest",
        )
        manifest_body = (
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        )
        manifest_path = root / "manifests/acquisition.json"
        if manifest_path.is_file() and manifest_path.read_bytes() != manifest_body:
            manifest_path = (
                root / f"manifests/acquisition-{_digest(manifest)[7:23]}.json"
            )
        manifest_path = _write_json(manifest_path, manifest)
        manifest_ref, manifest_sha = _safe_ref(manifest_path, root), file_sha256(manifest_path)
    accepted = sum(row["status"] == "accepted" for row in items)
    pending = sum(row["status"] == "review_pending" for row in items)
    blocked = len(items) - accepted - pending
    shortfall = max(0, accepted_target - accepted)
    stable = {
        "schema": "quwoquan_data.professional_image_supported_api_preparation_receipt",
        "preparationId": preparation_id,
        **execution_identity,
        "executionBundle": handoff["executionBundle"],
        "frozenPhysicalInput": frozen_physical_input,
        "reviewExecutionBindings": review_execution_bindings,
        "discoveryPlanRef": "inputs/discovery-plan.json", "discoveryPlanDigest": plan["planDigest"],
        "metadataCatalogRef": "inputs/metadata-catalog.json",
        "metadataCatalogDigest": catalog["catalogDigest"],
        "acceptedTarget": accepted_target, "candidateCount": len(items),
        "acceptedCount": accepted, "pendingCount": pending, "blockedCount": blocked,
        "shortfall": shortfall,
        "status": "ready" if shortfall == 0 else ("partial" if accepted or pending else "blocked"),
        "acquisitionManifestRef": manifest_ref,
        "acquisitionManifestSha256": manifest_sha, "items": items,
    }
    receipt = {**stable, "receiptDigest": _digest(stable)}
    assert_valid(
        receipt, "source", "professional_image_supported_api_preparation_receipt",
        label="professional image supported API preparation receipt",
    )
    receipt_path = _write_json(
        root / f"receipts/{receipt['receiptDigest'][7:]}.json", receipt
    )
    if shortfall:
        raise ProfessionalImageSupportedApiInputError(
            SOURCE_POOL_SHORTFALL,
            f"acceptedTarget={accepted_target} accepted={accepted} pending={pending} "
            f"blocked={blocked} nextAction=record_host_source_review_result",
            receipt_ref=_safe_ref(receipt_path, output_root.resolve()),
        )
    return receipt, receipt_path
__all__ = [
    "PREPARATION_INVALID", "PREPARATION_ROOT", "SOURCE_POOL_SHORTFALL",
    "ProfessionalImageSupportedApiInputError", "prepare_supported_api_inputs",
]
