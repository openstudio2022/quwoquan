from __future__ import annotations

from content.source.professional_image_supported_api_input import (
    OUTPUT_ROOT,
    PREPARATION_INVALID,
    PREPARATION_ROOT,
    PUBLISH_ROOT,
    SOURCE_POOL_SHORTFALL,
    Any,
    Callable,
    Mapping,
    Path,
    ProfessionalImageSupportedApiInputError,
    Sequence,
    _digest,
    _external_inputs_digest,
    _safe_ref,
    _write_json,
    assert_canonical_image_unique,
    assert_valid,
    fetch_public_image,
    fetch_public_json,
    file_sha256,
    guard_acquisition_source_identity,
    json,
    load_document,
    load_reviewer_results,
    verify_metadata_catalog,
    verify_plan,
)


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
    identity_guard: Callable[
        ..., Mapping[str, Any]
    ] = guard_acquisition_source_identity,
    inventory_check: Callable[..., None] = assert_canonical_image_unique,
) -> tuple[dict[str, Any], Path]:
    """Create or resume one deterministic supported-API preparation checkpoint."""
    if isinstance(accepted_target, bool) or accepted_target < 1:
        raise ProfessionalImageSupportedApiInputError(
            PREPARATION_INVALID, "acceptedTarget must be >= 1"
        )
    try:
        plan = load_document(
            discovery_plan_path,
            group="source",
            name="professional_image_discovery_plan",
        )
        catalog = load_document(
            metadata_catalog_path,
            group="source",
            name="professional_image_supported_api_metadata_catalog",
        )
        verify_metadata_catalog(catalog, digest=_digest)
        planned = verify_plan(plan, catalog, digest=_digest)
        handoff = identity_guard(
            catalog, handoff_ref=handoff_ref, frozen_external_input=True
        )
        if not isinstance(handoff, Mapping) or not handoff.get("sourceDigest"):
            # Injectable focused-test seams predate the dual-identity contract.
            handoff = {
                "sourceRevision": catalog["sourceRevision"],
                "sourceDigest": {
                    "algorithm": "sha256",
                    "digest": catalog["sourceDigest"],
                    "inputs": ["focused-test-injected-identity"],
                },
                "executionBundle": {
                    "algorithm": "sha256",
                    "digest": "sha256:" + "0" * 64,
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
            reviewer_result_refs,
            root=reviewer_root.resolve(),
            catalog=catalog,
            digest=_digest,
            execution_source_identity=execution_identity,
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
    from content.source.professional_image_supported_api_candidates import (
        prepare_candidate_rows,
    )

    items, manifest_items = prepare_candidate_rows(
        catalog=catalog,
        output_root=output_root,
        root=root,
        planned=planned,
        reviewers=reviewers,
        api_fetcher=api_fetcher,
        image_fetcher=image_fetcher,
        inventory_check=inventory_check,
        publish_root=publish_root,
    )
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
    review_execution_bindings = []
    for binding in sorted(
        {
            (
                str(row["executionId"]),
                str(row["executionManifestRef"]),
                str(row["executionManifestSha256"]),
                json.dumps(row["executionBundle"], sort_keys=True),
            )
            for row in reviewers.values()
            if row.get("executionId")
        }
    ):
        execution_id, manifest_ref_value, manifest_sha_value, bundle_json = binding
        review_execution_bindings.append(
            {
                "executionId": execution_id,
                "executionBundle": json.loads(bundle_json),
                "executionManifestRef": manifest_ref_value,
                "executionManifestSha256": manifest_sha_value,
            }
        )
    review_source_bindings = [
        {
            "sourceReview": dict(row["sourceIdentity"]),
            "reviewerResultRef": str(row["evidenceRef"]),
            "reviewerResultSha256": file_sha256(row["evidencePath"]),
        }
        for row in reviewers.values()
        if row.get("sourceIdentity") and not row.get("executionId")
    ]
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
            "discoveryPlanDigest": plan["planDigest"],
            "items": manifest_items,
        }
        assert_valid(
            manifest,
            "source",
            "professional_image_acquisition_manifest",
            label="prepared professional image acquisition manifest",
        )
        # The manifest grows as blocked/pending candidates become accepted on
        # later resumes.  The first record owns the canonical fixed path; any
        # different manifest content is frozen as a content-addressed
        # create-once record so historical receipts keep validating.
        manifest_body = (
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        )
        manifest_path = root / "manifests/acquisition.json"
        if manifest_path.is_file() and manifest_path.read_bytes() != manifest_body:
            manifest_path = (
                root / f"manifests/acquisition-{_digest(manifest)[7:23]}.json"
            )
        manifest_path = _write_json(manifest_path, manifest)
        manifest_ref, manifest_sha = (
            _safe_ref(manifest_path, root),
            file_sha256(manifest_path),
        )
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
        "discoveryPlanRef": "inputs/discovery-plan.json",
        "discoveryPlanDigest": plan["planDigest"],
        "metadataCatalogRef": "inputs/metadata-catalog.json",
        "metadataCatalogDigest": catalog["catalogDigest"],
        "acceptedTarget": accepted_target,
        "candidateCount": len(items),
        "acceptedCount": accepted,
        "pendingCount": pending,
        "blockedCount": blocked,
        "shortfall": shortfall,
        "status": "ready"
        if shortfall == 0
        else ("partial" if accepted or pending else "blocked"),
        "acquisitionManifestRef": manifest_ref,
        "acquisitionManifestSha256": manifest_sha,
        "items": items,
    }
    receipt = {**stable, "receiptDigest": _digest(stable)}
    assert_valid(
        receipt,
        "source",
        "professional_image_supported_api_preparation_receipt",
        label="professional image supported API preparation receipt",
    )
    receipt_path = _write_json(
        root / f"receipts/{receipt['receiptDigest'][7:]}.json", receipt
    )
    if shortfall:
        raise ProfessionalImageSupportedApiInputError(
            SOURCE_POOL_SHORTFALL,
            f"acceptedTarget={accepted_target} accepted={accepted} pending={pending} blocked={blocked}",
            receipt_ref=_safe_ref(receipt_path, output_root.resolve()),
        )
    return receipt, receipt_path
