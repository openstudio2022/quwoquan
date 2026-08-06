"""Validate one campaign lane's immutable canonical publish closure."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from content.execution.campaign_receipt import lane_receipt_path, load_lane_receipt
from content.execution.reviewed_closure_adoption_campaign_contract import (
    CAMPAIGN_ADOPTION_FIELD,
    adopted_object_refs,
    validate_adoption_task_binding,
    validate_campaign_adoption_binding,
)
from content.release.canonical.campaign_release_contract import (
    PUBLISH_BINDING_CONTRACT_REQUEST,
    PUBLISH_BINDING_FIELDS,
    CampaignReleaseRoots,
    file_digest,
    output_ref,
    read_regular,
    typed_error,
)
from core.io import read_json
from core.schema import assert_valid


def _safe_publish_ref(ref: object, *, label: str) -> str:
    text = str(ref or "").strip().strip("/")
    pure = PurePosixPath(text)
    if not text or pure.is_absolute() or ".." in pure.parts:
        raise typed_error("PUBLISH_REF_INVALID", f"{label} is unsafe: {ref}")
    return pure.as_posix()


def _canonical_refs(
    execution_id: str, *, roots: CampaignReleaseRoots
) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {"entities": [], "posts": []}
    for kind, selected_refs in refs.items():
        kind_root = roots.publish_root / kind
        if not kind_root.is_dir():
            continue
        for path in sorted(kind_root.rglob("manifest.json")):
            manifest = read_regular(path, label=f"canonical {kind} manifest")
            if manifest.get("executionId") != execution_id:
                continue
            source = manifest.get("sourceDigest")
            if not isinstance(source, Mapping):
                raise typed_error(
                    "PUBLISH_SOURCE_DRIFT",
                    f"{kind} manifest lacks sourceDigest",
                    evidence=path,
                )
            selected_refs.append(path.parent.relative_to(kind_root).as_posix())
    return refs


def _validate_adoption_lane_publish(
    *,
    root_id: str,
    carrier: str,
    execution_id: str,
    plan: Mapping[str, Any],
    submission: Mapping[str, Any],
    runtime: Mapping[str, Any],
    receipt: Mapping[str, Any],
    receipt_path: Path,
    roots: CampaignReleaseRoots,
) -> dict[str, Any]:
    adoption_document = plan.get(CAMPAIGN_ADOPTION_FIELD)
    try:
        binding = validate_campaign_adoption_binding(
            adoption_document,
            output_root=roots.output_root,
        )
        receipt_document = read_json(binding.receipt_path)
        expected_refs = adopted_object_refs(receipt_document)[carrier]
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise typed_error(
            "ADOPTION_BINDING_INVALID",
            str(exc),
            evidence=receipt_path,
        ) from exc
    expected = {
        "rootExecutionId": root_id,
        "executionId": execution_id,
        "carrier": carrier,
        "phase": "publish",
        "status": "finalized",
        "campaignRunId": runtime["runId"],
        "campaignGeneration": runtime["generation"],
        "campaignFencingToken": runtime["fencingToken"],
        CAMPAIGN_ADOPTION_FIELD: adoption_document,
        "adoptedObjectRefs": expected_refs,
    }
    expected_count = len(expected_refs)
    if (
        submission.get(CAMPAIGN_ADOPTION_FIELD) != adoption_document
        or any(receipt.get(key) != value for key, value in expected.items())
        or any(
            int(receipt.get(field) or 0) != expected_count
            for field in (
                "approvedQuota",
                "qualifiedCount",
                "finalizedCount",
                "selectedCount",
            )
        )
        or int(receipt.get("discardedCount") or 0) != 0
        or int(receipt.get("shortfallCount") or 0) != 0
        or receipt.get("discards") != []
        or "executionPublishRef" in receipt
        or "executionPublishSha256" in receipt
    ):
        raise typed_error(
            "ADOPTION_PUBLISH_DRIFT",
            f"{carrier} adoption publish receipt is not exact",
            evidence=receipt_path,
        )
    task_path = (
        roots.tasks_root / execution_id / "0.plan/reviewed_closure_adoption.json"
    )
    task = read_regular(task_path, label=f"{carrier} adoption task binding")
    try:
        validate_adoption_task_binding(task, output_root=roots.output_root)
    except (TypeError, ValueError) as exc:
        raise typed_error(
            "ADOPTION_TASK_INVALID",
            str(exc),
            evidence=task_path,
        ) from exc
    if (
        task.get("planDigest") != plan["planDigest"]
        or task.get("adoptedObjectRefs") != expected_refs
    ):
        raise typed_error(
            "ADOPTION_TASK_INVALID",
            f"{carrier} adoption task selection drifted",
            evidence=task_path,
        )
    return {
        "executionId": execution_id,
        "finalizedCount": expected_count,
        "publishReceiptRef": output_ref(
            receipt_path,
            roots=roots,
            label=f"{carrier} adoption receipt",
        ),
        "publishReceiptSha256": file_digest(receipt_path),
        "adoptedObjectRefs": expected_refs,
        "adoptionReceiptDigest": binding.adoption_receipt.receipt_digest,
    }


def validate_lane_publish(
    root_id: str,
    carrier: str,
    plan: Mapping[str, Any],
    submission: Mapping[str, Any],
    runtime: Mapping[str, Any],
    *,
    roots: CampaignReleaseRoots,
) -> dict[str, Any]:
    """Validate receipt, publish_ref, and canonical manifests for one lane."""

    execution_id = str(plan["executionIds"][carrier])
    receipt_path = lane_receipt_path(
        root_id, carrier, "publish", root=roots.campaigns_root
    )
    try:
        receipt = load_lane_receipt(
            root_id, carrier, "publish", root=roots.campaigns_root
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise typed_error(
            "PUBLISH_RECEIPT_INVALID", str(exc), evidence=receipt_path
        ) from exc
    raw_receipt = read_regular(receipt_path, label=f"{carrier} publish receipt")
    if receipt != raw_receipt:
        raise typed_error(
            "PUBLISH_RECEIPT_INVALID",
            f"{carrier} loader/raw receipt drift",
            evidence=receipt_path,
        )
    if plan.get(CAMPAIGN_ADOPTION_FIELD) is not None:
        return _validate_adoption_lane_publish(
            root_id=root_id,
            carrier=carrier,
            execution_id=execution_id,
            plan=plan,
            submission=submission,
            runtime=runtime,
            receipt=receipt,
            receipt_path=receipt_path,
            roots=roots,
        )
    missing = [field for field in PUBLISH_BINDING_FIELDS if field not in receipt]
    if missing:
        raise typed_error(
            "PUBLISH_BINDING_MISSING",
            f"{carrier} receipt lacks {', '.join(missing)}; "
            f"contract request: {PUBLISH_BINDING_CONTRACT_REQUEST}",
            evidence=receipt_path,
        )
    expected_receipt = {
        "rootExecutionId": root_id,
        "executionId": execution_id,
        "carrier": carrier,
        "phase": "publish",
        "campaignRunId": runtime["runId"],
        "campaignGeneration": runtime["generation"],
        "campaignFencingToken": runtime["fencingToken"],
    }
    finalized = int(receipt.get("finalizedCount") or 0)
    if (
        any(receipt.get(key) != value for key, value in expected_receipt.items())
        or receipt.get("status") not in {"finalized", "partial"}
        or finalized <= 0
        or finalized != int(receipt.get("qualifiedCount") or 0)
        or int(receipt.get("approvedQuota") or 0) != int(submission["quota"])
    ):
        raise typed_error(
            "PUBLISH_RECEIPT_DRIFT",
            f"{carrier} receipt is not a positive current-lane closure",
            evidence=receipt_path,
        )
    publish_path = roots.tasks_root / execution_id / "publish_ref.json"
    publish = read_regular(publish_path, label=f"{carrier} execution publish_ref")
    try:
        assert_valid(
            publish, "execution", "publish_ref", label=f"publish_ref:{execution_id}"
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise typed_error(
            "PUBLISH_REF_INVALID", str(exc), evidence=publish_path
        ) from exc
    expected_ref = output_ref(publish_path, roots=roots, label=f"{carrier} publish_ref")
    if (
        receipt.get("executionPublishRef") != expected_ref
        or receipt.get("executionPublishSha256") != file_digest(publish_path)
        or publish.get("executionId") != execution_id
    ):
        raise typed_error(
            "PUBLISH_BINDING_DRIFT",
            f"{carrier} receipt does not bind current canonical publish_ref",
            evidence=receipt_path,
        )
    raw_refs = publish.get("publishedRefs")
    if not isinstance(raw_refs, Mapping):
        raise typed_error(
            "PUBLISH_REF_INVALID",
            f"{carrier} publishedRefs is not an object",
            evidence=publish_path,
        )
    publish_refs = {
        kind: sorted(
            _safe_publish_ref(ref, label=f"{carrier}.{kind}")
            for ref in raw_refs.get(kind) or []
        )
        for kind in ("entities", "posts")
    }
    if any(len(values) != len(set(values)) for values in publish_refs.values()):
        raise typed_error(
            "PUBLISH_REF_INVALID",
            f"{carrier} publish_ref contains duplicates",
            evidence=publish_path,
        )
    selected = (
        publish_refs["entities"] if carrier == "homepage" else publish_refs["posts"]
    )
    forbidden = (
        publish_refs["posts"] if carrier == "homepage" else publish_refs["entities"]
    )
    if forbidden or len(selected) != finalized:
        raise typed_error(
            "PUBLISH_COUNT_DRIFT",
            f"{carrier} publish_ref differs from finalizedCount",
            evidence=publish_path,
        )
    canonical_refs = _canonical_refs(execution_id, roots=roots)
    if canonical_refs != publish_refs:
        raise typed_error(
            "CANONICAL_PUBLISH_DRIFT",
            f"{carrier} publish_ref differs from current canonical object closure",
            evidence=publish_path,
        )
    for kind, refs in canonical_refs.items():
        for ref in refs:
            manifest_path = roots.publish_root / kind / ref / "manifest.json"
            manifest = read_regular(
                manifest_path, label=f"{carrier} canonical manifest"
            )
            if manifest.get("sourceDigest") != submission["sourceDigest"]:
                raise typed_error(
                    "PUBLISH_SOURCE_DRIFT",
                    f"{carrier} canonical object sourceDigest drift",
                    evidence=manifest_path,
                )
            if kind == "posts" and manifest.get("contentType") != carrier:
                raise typed_error(
                    "PUBLISH_CARRIER_DRIFT",
                    f"{carrier} canonical post contentType drift",
                    evidence=manifest_path,
                )
    return {
        "executionId": execution_id,
        "finalizedCount": finalized,
        "publishReceiptRef": output_ref(
            receipt_path, roots=roots, label=f"{carrier} receipt"
        ),
        "publishReceiptSha256": file_digest(receipt_path),
        "executionPublishRef": expected_ref,
        "executionPublishSha256": file_digest(publish_path),
    }


__all__ = ["validate_lane_publish"]
