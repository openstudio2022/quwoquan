"""Supported-API metadata discovery execution."""

from __future__ import annotations

from content.source.professional_image_supported_api_metadata import (
    METADATA_DISCOVERY_ROOT,
    METADATA_INVALID,
    RATE_LIMITED,
    SOURCE_ACQUISITION_ROOT,
    SOURCE_POOL_SHORTFALL,
    Any,
    Callable,
    Mapping,
    Path,
    ProfessionalImageSupportedApiMetadataError,
    Sequence,
    _digest,
    _failure,
    _load_plan,
    _load_response,
    _now,
    _project_response,
    _response_bytes,
    _safe_ref,
    _supported_queries,
    _write_catalog,
    _write_json,
    _write_once,
    _write_receipt,
    fetch_public_json,
    file_sha256,
    guard_acquisition_source_identity,
    hashlib,
    load_entity_bindings,
    load_pre_acquisition_handoff,
    read_json,
    urllib,
)


def discover_supported_api_metadata(
    *,
    handoff_ref: Path,
    discovery_plan_path: Path,
    entity_catalog_path: Path,
    candidate_target: int,
    results_per_query: int = 50,
    providers: Sequence[str] = ("wikimedia_commons", "openverse"),
    output_root: Path = METADATA_DISCOVERY_ROOT,
    physical_evidence_root: Path = SOURCE_ACQUISITION_ROOT,
    api_fetcher: Callable[[str], Mapping[str, Any]] = fetch_public_json,
    handoff_loader: Callable[[Path], Mapping[str, Any]] = load_pre_acquisition_handoff,
    identity_guard: Callable[
        ..., Mapping[str, Any]
    ] = guard_acquisition_source_identity,
    entity_loader: Callable[
        [Path], tuple[str, str, dict[str, dict[str, Any]]]
    ] = load_entity_bindings,
    clock: Callable[[], str] = _now,
) -> tuple[dict[str, Any], Path, Path | None]:
    """Create or resume a source-bound metadata catalog and checkpoint receipt."""
    del physical_evidence_root  # raw identity is admitted by governed preparation.
    if (
        isinstance(candidate_target, bool)
        or candidate_target < 1
        or isinstance(results_per_query, bool)
        or not 1 <= results_per_query <= 50
    ):
        raise ProfessionalImageSupportedApiMetadataError(
            METADATA_INVALID, "candidateTarget must be >=1 and resultsPerQuery 1..50"
        )
    requested_providers = tuple(
        sorted(
            {str(provider).strip() for provider in providers if str(provider).strip()}
        )
    )
    if not requested_providers or any(
        provider not in {"wikimedia_commons", "openverse"}
        for provider in requested_providers
    ):
        raise ProfessionalImageSupportedApiMetadataError(
            METADATA_INVALID,
            "providers must select wikimedia_commons and/or openverse",
        )
    try:
        plan = _load_plan(discovery_plan_path.expanduser().resolve())
        handoff = dict(handoff_loader(handoff_ref.expanduser().resolve()))
        entity_ref, entity_digest, entity_index = entity_loader(
            entity_catalog_path.expanduser().resolve()
        )
        source_document = handoff.get("sourceDigest")
        source_digest = (
            str(source_document.get("digest") or "")
            if isinstance(source_document, Mapping)
            else str(source_document or "")
        )
        identity = {
            "sourceRevision": str(handoff.get("sourceRevision") or ""),
            "sourceDigest": source_digest,
            "entityCatalogDigest": entity_digest,
        }
        if str(handoff.get("entityCatalogDigest") or "") != entity_digest:
            raise ValueError("entity catalog digest differs from current handoff")
        identity_guard(identity, handoff_ref=handoff_ref.expanduser().resolve())
        queries = _supported_queries(
            plan,
            entity_index,
            limit=results_per_query,
            providers=requested_providers,
        )
    except ProfessionalImageSupportedApiMetadataError:
        raise
    except (FileNotFoundError, OSError, KeyError, TypeError, ValueError) as exc:
        raise ProfessionalImageSupportedApiMetadataError(
            METADATA_INVALID, str(exc)
        ) from exc

    run_stable = {
        **identity,
        "discoveryPlanId": plan["planId"],
        "discoveryPlanDigest": plan["planDigest"],
        "handoffId": str(handoff.get("handoffId") or ""),
        "handoffRevision": int(handoff.get("handoffRevision") or 0),
        "handoffDigest": str(handoff.get("handoffDigest") or ""),
        "entityCatalogRef": entity_ref,
        "requestedProviders": list(requested_providers),
        "targetCandidateCount": candidate_target,
        "resultsPerQuery": results_per_query,
    }
    discovery_id = (
        "professional-image-supported-api-metadata-discovery-"
        + _digest(run_stable)[7:23]
    )
    output_root = output_root.expanduser().resolve()
    root = output_root / discovery_id
    identity_path = root / "identity.json"
    if identity_path.is_file():
        run_identity = read_json(identity_path)
        if not isinstance(run_identity, dict) or any(
            run_identity.get(key) != value for key, value in run_stable.items()
        ):
            raise ProfessionalImageSupportedApiMetadataError(
                METADATA_INVALID,
                f"metadata discovery identity collision: {identity_path}",
            )
    else:
        run_identity = {**run_stable, "observedAt": clock()}
        _write_json(identity_path, run_identity)

    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    seen_sources: set[tuple[str, str]] = set()
    for query in queries:
        if len(candidates) >= candidate_target:
            break
        query_dir = root / "queries" / str(query["queryId"])
        _write_json(query_dir / "request.json", query)
        response_path = query_dir / "response.json"
        transport_path = query_dir / "https-transport-evidence.json"
        try:
            if response_path.is_file():
                body, payload, transport = _load_response(response_path, transport_path)
            else:
                body, payload, transport = _response_bytes(
                    api_fetcher(str(query["requestUrl"]))
                )
                _write_once(response_path, body)
                _write_json(transport_path, transport)
            response_sha = "sha256:" + hashlib.sha256(body).hexdigest()
            projected, query_exclusions = _project_response(
                payload, query=query, response_sha=response_sha
            )
            accepted_before = len(candidates)
            for row in projected:
                source_identity = (
                    str(row["sourcePageUrl"]),
                    str(row["originalAssetUrl"]),
                )
                if source_identity in seen_sources:
                    query_exclusions.append(
                        {
                            "queryId": query["queryId"],
                            "fileTitle": row["fileTitle"],
                            "failureCode": "DATA.SOURCE.DUPLICATE",
                            "detail": "duplicate Commons page/original identity",
                        }
                    )
                    continue
                seen_sources.add(source_identity)
                candidates.append(row)
            exclusions.extend(query_exclusions)
            items.append(
                {
                    "queryId": query["queryId"],
                    "discoveryCandidateId": query["discoveryCandidateId"],
                    "entityId": query["entityId"],
                    "status": "completed",
                    "evidenceRef": _safe_ref(response_path, root),
                    "evidenceSha256": file_sha256(response_path),
                    "transportEvidenceRef": _safe_ref(transport_path, root),
                    "transportEvidenceSha256": file_sha256(transport_path),
                    "candidateCount": len(candidates) - accepted_before,
                    "excludedCount": len(query_exclusions),
                }
            )
        except (
            OSError,
            TimeoutError,
            TypeError,
            ValueError,
            urllib.error.HTTPError,
        ) as exc:
            failure = _failure(str(query["queryId"]), exc)
            failures.append(failure)
            items.append(
                {
                    "queryId": query["queryId"],
                    "discoveryCandidateId": query["discoveryCandidateId"],
                    "entityId": query["entityId"],
                    "status": "failed",
                    "evidenceRef": "",
                    "evidenceSha256": "",
                    "transportEvidenceRef": "",
                    "transportEvidenceSha256": "",
                    "candidateCount": 0,
                    "excludedCount": 0,
                }
            )
            if failure["failureCode"] == RATE_LIMITED:
                break

    selected = candidates[:candidate_target]
    status = "completed" if len(selected) >= candidate_target else "partial"
    catalog: dict[str, Any] | None = None
    catalog_path: Path | None = None
    if status == "completed":
        catalog, catalog_path = _write_catalog(
            root,
            stable={
                **identity,
                "discoveryPlanId": plan["planId"],
                "discoveryPlanDigest": plan["planDigest"],
                "handoffId": run_stable["handoffId"],
                "handoffRevision": run_stable["handoffRevision"],
                "handoffDigest": run_stable["handoffDigest"],
                "entityCatalogRef": entity_ref,
                "requestedProviders": list(requested_providers),
                "observedAt": run_identity["observedAt"],
                "targetCandidateCount": candidate_target,
                "queryCount": len(queries),
                "completedQueryCount": sum(
                    row["status"] == "completed" for row in items
                ),
                "excludedCount": len(exclusions),
                "candidateCount": len(selected),
                "candidates": selected,
            },
        )
    receipt, receipt_path = _write_receipt(
        root,
        output_root=output_root,
        stable={
            "status": status,
            **identity,
            "discoveryPlanId": plan["planId"],
            "discoveryPlanDigest": plan["planDigest"],
            "handoffId": run_stable["handoffId"],
            "handoffRevision": run_stable["handoffRevision"],
            "handoffDigest": run_stable["handoffDigest"],
            "entityCatalogRef": entity_ref,
            "requestedProviders": list(requested_providers),
            "observedAt": run_identity["observedAt"],
            "targetCandidateCount": candidate_target,
            "queryCount": len(queries),
            "completedQueryCount": sum(row["status"] == "completed" for row in items),
            "candidateCount": len(selected),
            "excludedCount": len(exclusions),
            "shortfallCount": max(0, candidate_target - len(selected)),
            "items": items,
            "exclusions": exclusions,
            "failures": failures,
            "catalogRef": _safe_ref(catalog_path, output_root) if catalog_path else "",
            "catalogDigest": str(catalog["catalogDigest"]) if catalog else "",
        },
    )
    if status != "completed":
        raise ProfessionalImageSupportedApiMetadataError(
            SOURCE_POOL_SHORTFALL,
            f"supported API metadata shortfall={receipt['shortfallCount']}",
            receipt_ref=_safe_ref(receipt_path, output_root),
        )
    return receipt, receipt_path, catalog_path
