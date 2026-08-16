"""Builder implementation for canonical semantic-wave dispatch."""

from __future__ import annotations

from content.release.canonical.semantic_wave_dispatch import (
    _CARRIERS,
    _FAMILIES,
    _SAFE_ID,
    _SAFE_SCOPE,
    DISPATCH_EMPTY,
    DISPATCH_INVALID,
    Any,
    Mapping,
    Path,
    RuntimeExecutionRequest,
    Sequence,
    __file__,
    _digest,
    _fail,
    _file_sha256,
    _output_path,
    _read_json,
    _selection,
    _selector,
    _slot_count,
    _source_binding,
    _target_names,
    _unfinished_retry_candidates,
    _wave_input,
    assert_valid,
    bind_semantic_preflight_receipt,
    build_execution_id,
    parse_execution_id,
    task_execute_argv,
    validate_semantic_wave_dispatch,
)


def build_semantic_wave_dispatch(
    *,
    dispatch_id: str,
    pool_inspection_ref: str,
    semantic_preflight_receipt_ref: str,
    run_date: str,
    scope: str,
    region_ref: str,
    sequence_start: int,
    predecessor_dispatch_ref: str | None = None,
    predecessor_execution_ids: Mapping[str, str] | None = None,
    predecessor_unfinished_refs: Mapping[str, Sequence[str]] | None = None,
    required_workers: int,
    partition_count: int,
    capacity_plan_digest: str,
    output_root: Path,
    publish_root: Path,
    require_fresh_preflight: bool = True,
) -> dict[str, Any]:
    """Validate one inspection and project only its candidate-backed slots."""

    if not _SAFE_ID.fullmatch(dispatch_id):
        raise _fail(DISPATCH_INVALID, "dispatchId is invalid")
    if not _SAFE_SCOPE.fullmatch(scope):
        raise _fail(DISPATCH_INVALID, "scope is invalid")
    if isinstance(sequence_start, bool) or sequence_start < 1:
        raise _fail(DISPATCH_INVALID, "sequenceStart must be positive")
    predecessor_ref = str(predecessor_dispatch_ref or "").strip() or None
    predecessor_ids = {
        str(slot_id).strip(): str(execution_id).strip()
        for slot_id, execution_id in (predecessor_execution_ids or {}).items()
    }
    predecessor_ref_scopes = {
        str(slot_id).strip(): tuple(str(ref).strip() for ref in refs)
        for slot_id, refs in (predecessor_unfinished_refs or {}).items()
    }
    if bool(predecessor_ref) != bool(predecessor_ids):
        raise _fail(
            DISPATCH_INVALID,
            "predecessorDispatchRef and retry predecessor mappings are required together",
        )
    if predecessor_ref_scopes and set(predecessor_ref_scopes) != set(predecessor_ids):
        raise _fail(
            DISPATCH_INVALID,
            "retry unfinished ref scopes must exactly cover predecessor mappings",
        )
    predecessor_manifest: dict[str, Any] | None = None
    predecessor_binding: dict[str, Any] | None = None
    predecessor_slots: dict[str, dict[str, Any]] = {}
    if predecessor_ref is not None:
        predecessor_path, predecessor_ref = _output_path(
            output_root,
            predecessor_ref,
            label="predecessorDispatchRef",
        )
        try:
            predecessor_manifest = validate_semantic_wave_dispatch(
                _read_json(predecessor_path)
            )
        except (OSError, TypeError, ValueError) as exc:
            raise _fail(DISPATCH_INVALID, exc) from exc
        predecessor_binding = {
            "manifestRef": predecessor_ref,
            "manifestFileSha256": _file_sha256(predecessor_path),
            "manifestDigest": str(predecessor_manifest["manifestDigest"]),
        }
        predecessor_slots = {
            str(slot["slotId"]): dict(slot) for slot in predecessor_manifest["slots"]
        }
    reference_root = (
        Path(__file__).resolve().parents[4] / "reference/travel/entities" / region_ref
    ).resolve()
    entities_root = (
        Path(__file__).resolve().parents[4] / "reference/travel/entities"
    ).resolve()
    if (
        reference_root == entities_root
        or entities_root not in reference_root.parents
        or not reference_root.is_dir()
    ):
        raise _fail(DISPATCH_INVALID, "regionRef must resolve to one entity subtree")
    inspection_path, inspection_ref = _output_path(
        output_root,
        pool_inspection_ref,
        label="poolInspectionRef",
    )
    inspection = _read_json(inspection_path)
    try:
        assert_valid(
            inspection,
            "release",
            "pool_inspection",
            label="semantic wave pool inspection",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _fail(DISPATCH_INVALID, exc) from exc
    wave = _wave_input(inspection)
    binding, evidence_ref, selected, scheduling = _source_binding(
        inspection=inspection,
        wave=wave,
        output_root=output_root,
    )
    if predecessor_manifest is not None and (
        predecessor_manifest.get("sourcePoolBinding") != binding
        or predecessor_manifest.get("sourcePoolEvidenceRootRef") != evidence_ref
        or predecessor_manifest.get("waveInputDigest") != wave.get("waveInputDigest")
    ):
        raise _fail(
            DISPATCH_INVALID,
            "retry wave must preserve predecessor source-pool and waveInput binding",
        )
    receipt_path, _ = _output_path(
        output_root,
        semantic_preflight_receipt_ref,
        label="semanticPreflightReceiptRef",
    )
    try:
        preflight = bind_semantic_preflight_receipt(
            receipt_path,
            semantic_selection_id="cursor_grok",
            output_root=output_root,
            require_fresh=require_fresh_preflight,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise _fail(DISPATCH_INVALID, exc) from exc
    ordered_by_carrier = {
        carrier: [
            selected[str(row["candidateId"])]
            for row in wave["candidates"]
            if row["carrier"] == carrier
        ]
        for carrier in _CARRIERS
    }
    slots: list[dict[str, Any]] = []
    sequence = sequence_start
    seen_candidates: set[str] = set()
    seen_objects: set[str] = set()
    predecessor_mappings: list[dict[str, Any]] = []
    for carrier in _CARRIERS:
        candidates = ordered_by_carrier[carrier]
        if not candidates:
            continue
        count = _slot_count(
            carrier=carrier,
            candidate_count=len(candidates),
            scheduling=scheduling,
        )
        chunks = [candidates[index::count] for index in range(count)]
        for carrier_slot, chunk in enumerate(chunks, start=1):
            if not chunk or len(chunk) > 12:
                raise _fail(DISPATCH_INVALID, "slot candidate cardinality is invalid")
            slot_id = f"{carrier}-{carrier_slot:02d}"
            # A retry dispatch is a failed-shard successor, not a replay of
            # every sibling slot in the predecessor wave.  Only explicitly
            # mapped slots are materialized; each selected slot still freezes
            # the exact predecessor candidate/object/selection lineage below.
            if predecessor_manifest is not None and slot_id not in predecessor_ids:
                continue
            candidate_ids = [str(row["candidateId"]) for row in chunk]
            object_refs = [str(row["objectRef"]).strip("/") for row in chunk]
            retry_unfinished_refs: tuple[str, ...] = ()
            selection = _selection(carrier, chunk)
            target_names = _target_names(chunk)
            execution_id = build_execution_id(
                run_date=run_date,
                vertical="travel",
                content_type=carrier,
                intent=str(inspection["milestone"]).lower(),
                scope=scope,
                phase="scale",
                sequence=sequence,
            )
            retry_of: str | None = None
            if predecessor_manifest is not None:
                retry_of = predecessor_ids.get(slot_id)
                predecessor_slot = predecessor_slots.get(slot_id)
                if retry_of is None or predecessor_slot is None:
                    raise _fail(
                        DISPATCH_INVALID,
                        f"retry predecessor mapping is incomplete for slot: {slot_id}",
                    )
                if retry_of != predecessor_slot.get("executionId"):
                    raise _fail(
                        DISPATCH_INVALID,
                        f"retry predecessor does not match predecessor dispatch slot: {slot_id}",
                    )
                current_identity = parse_execution_id(execution_id)
                predecessor_identity = parse_execution_id(retry_of)
                comparable = ("vertical", "content_type", "intent", "scope", "phase")
                if (
                    any(
                        getattr(current_identity, field)
                        != getattr(predecessor_identity, field)
                        for field in comparable
                    )
                    or predecessor_identity.sequence >= current_identity.sequence
                ):
                    raise _fail(
                        DISPATCH_INVALID,
                        f"retry predecessor must be an earlier sequence in the same scope: {slot_id}",
                    )
                predecessor_request = predecessor_slot.get("taskRequest")
                if not isinstance(predecessor_request, Mapping) or (
                    predecessor_slot.get("carrier") != carrier
                    or predecessor_slot.get("candidateIds") != candidate_ids
                    or predecessor_slot.get("candidateObjectRefs") != object_refs
                    or predecessor_request.get("scaleSourcePool") != binding
                    or predecessor_request.get("sourcePoolEvidenceRootRef")
                    != evidence_ref
                    or predecessor_request.get("sourcePoolSelection") != selection
                    or predecessor_request.get("targetNames") != list(target_names)
                ):
                    raise _fail(
                        DISPATCH_INVALID,
                        f"retry slot drifted from predecessor physical selection: {slot_id}",
                    )
                retry_unfinished_refs = predecessor_ref_scopes.get(slot_id, ())
                if retry_unfinished_refs:
                    chunk = _unfinished_retry_candidates(
                        output_root=output_root,
                        predecessor_execution_id=retry_of,
                        predecessor_candidates=chunk,
                        unfinished_refs=retry_unfinished_refs,
                    )
                    candidate_ids = [str(row["candidateId"]) for row in chunk]
                    object_refs = [str(row["objectRef"]).strip("/") for row in chunk]
                    selection = _selection(carrier, chunk)
                    target_names = _target_names(chunk)
                predecessor_mappings.append(
                    {
                        "slotId": slot_id,
                        "executionId": execution_id,
                        "retryOf": retry_of,
                        "predecessorSlotDigest": str(predecessor_slot["slotDigest"]),
                        "selectionDigest": str(selection["selectionDigest"]),
                        **(
                            {"unfinishedRefs": list(retry_unfinished_refs)}
                            if retry_unfinished_refs
                            else {}
                        ),
                    }
                )
            if seen_candidates.intersection(candidate_ids) or seen_objects.intersection(
                object_refs
            ):
                raise _fail(
                    DISPATCH_INVALID, "candidate repeated across semantic slots"
                )
            if any(
                (publish_root / ref / "manifest.json").is_file() for ref in object_refs
            ):
                raise _fail(
                    DISPATCH_INVALID, "wave contains an already published object"
                )
            seen_candidates.update(candidate_ids)
            seen_objects.update(object_refs)
            request = RuntimeExecutionRequest(
                family_ref=_FAMILIES[carrier],
                region_ref=region_ref,
                selector=_selector(carrier),
                count=len(chunk),
                quota=len(chunk),
                required_workers=required_workers,
                partition_count=partition_count,
                capacity_plan_digest=capacity_plan_digest,
                worker_host_set_binding=None,
                topic=f"{str(inspection['milestone']).lower()}-{carrier}-wave",
                source_providers=(),
                target_names=target_names,
                scale_source_pool=binding,
                source_pool_evidence_root_ref=evidence_ref,
                source_pool_selection=selection,
            )
            stable_slot: dict[str, Any] = {
                "slotIndex": len(slots) + 1,
                "slotId": slot_id,
                "carrier": carrier,
                "executionId": execution_id,
                "candidateIds": candidate_ids,
                "candidateObjectRefs": object_refs,
                "taskRequest": request.to_document(),
                "argv": task_execute_argv(
                    execution_id=execution_id,
                    carrier=carrier,
                    request=request,
                    semantic_receipt_ref=str(preflight["receiptRef"]),
                    retry_of=retry_of,
                    retry_unfinished_refs=retry_unfinished_refs,
                ),
                "queueBackend": "local_file",
                "poolDeliveryBackend": "reliabletask",
            }
            if retry_of is not None:
                stable_slot["retryOf"] = retry_of
            if retry_unfinished_refs:
                stable_slot["retryUnfinishedRefs"] = list(retry_unfinished_refs)
            slots.append({**stable_slot, "slotDigest": _digest(stable_slot)})
            sequence += 1
    if not slots:
        raise _fail(DISPATCH_EMPTY, "wave produced no candidate-backed slot")
    if predecessor_manifest is not None:
        expected_slot_ids = {str(slot["slotId"]) for slot in slots}
        if set(predecessor_ids) != expected_slot_ids:
            raise _fail(
                DISPATCH_INVALID,
                "retry predecessor mappings must exactly cover dispatch slots",
            )
    active = [
        carrier
        for carrier in _CARRIERS
        if any(slot["carrier"] == carrier for slot in slots)
    ]
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.semantic_wave_dispatch_manifest",
        "dispatchId": dispatch_id,
        "milestone": str(inspection["milestone"]),
        "poolInspectionRef": inspection_ref,
        "poolInspectionFileSha256": _file_sha256(inspection_path),
        "waveInputDigest": str(wave["waveInputDigest"]),
        "sourcePoolBinding": binding,
        "sourcePoolEvidenceRootRef": evidence_ref,
        "semanticSelectionId": "cursor_grok",
        "semanticPreflightReceipt": preflight,
        "queueBackend": "local_file",
        "poolDeliveryBackend": "reliabletask",
        "activeCarriers": active,
        "slots": slots,
    }
    if predecessor_binding is not None:
        stable["predecessorDispatch"] = predecessor_binding
        stable["predecessorMappings"] = predecessor_mappings
    manifest = {**stable, "manifestDigest": _digest(stable)}
    validate_semantic_wave_dispatch(manifest)
    return manifest
