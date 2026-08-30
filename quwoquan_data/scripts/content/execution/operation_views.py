"""Deterministic, projection-only operation views for content production.

Every source fact is supplied explicitly by the caller.  The projectors do not
look up a latest record, touch a repository, persist a snapshot, or mutate any
input.  A malformed or drifting fact raises ``ProjectionContractError`` rather
than being completed with defaults.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from content.release.canonical.object_source_identity import (
    source_identity_digest as _source_identity_digest,
)
from core.schema import assert_valid as _assert_valid

TASK_VIEW_SCHEMA = "quwoquan_data.content_production_task_view"
ITEM_VIEW_SCHEMA = "quwoquan_data.content_item_version_view"
PROJECTOR_VERSION = "operation_views_v1"
_SPEC_REF = "specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-003"
_STAGE_ORDER = (
    "0.plan",
    "sources",
    "1.download",
    "2.quality",
    "3.compose",
    "4.draft",
    "5.review",
    "publish",
    "release",
    "ship",
)
_TASK_FACTS = {
    "productionReady": ("quwoquan_data.production_ready_fact", "5.review"),
    "published": ("quwoquan_data.content_publish_fact", "publish"),
    "released": ("quwoquan_data.content_release_fact", "release"),
    "shipped": ("quwoquan_data.content_ship_fact", "ship"),
}
_FACT_VERDICTS = frozenset({"passed", "failed", "not_observed"})


class ProjectionContractError(ValueError):
    """Canonical source facts cannot produce a trustworthy projection."""


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _object(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProjectionContractError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ProjectionContractError(
            f"{label} key set drift: missing={missing} unknown={unknown}"
        )


def _text(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProjectionContractError(f"{label} must be non-empty")
    return text


def _digest(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if (
        len(text) != 71
        or not text.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in text[7:])
    ):
        raise ProjectionContractError(f"{label} must be a sha256 digest")
    return text


def _fact_ref(
    value: object,
    *,
    label: str,
    expected_schema: str,
    fact_keys: set[str],
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    binding = _object(value, label=label)
    _exact_keys(binding, {"ref", "digest", "fact"}, label=label)
    ref = _text(binding["ref"], label=f"{label}.ref")
    declared_digest = _digest(binding["digest"], label=f"{label}.digest")
    fact = _object(binding["fact"], label=f"{label}.fact")
    _exact_keys(fact, fact_keys, label=f"{label}.fact")
    if fact.get("schema") != expected_schema:
        raise ProjectionContractError(f"{label}.fact schema mismatch")
    observed_digest = _canonical_digest(fact)
    if observed_digest != declared_digest:
        raise ProjectionContractError(
            f"{label}.digest mismatch: declared={declared_digest} observed={observed_digest}"
        )
    return {"ref": ref, "digest": declared_digest}, fact


def _validate_work_request(work_request: object) -> Mapping[str, Any]:
    document = _object(work_request, label="workRequest")
    try:
        _assert_valid(dict(document), "execution", "work_request", label="workRequest")
    except (TypeError, ValueError) as exc:
        raise ProjectionContractError(str(exc)) from exc
    dependencies = _object(document["dependencies"], label="workRequest.dependencies")
    if document["dependencySetDigest"] != _canonical_digest(dict(dependencies)):
        raise ProjectionContractError("workRequest dependencySetDigest mismatch")
    stable = {
        key: value
        for key, value in document.items()
        if key not in {"workRequestId", "workRequestDigest", "compiledAt"}
    }
    observed = _canonical_digest(stable)
    if document["workRequestDigest"] != observed:
        raise ProjectionContractError("workRequest workRequestDigest mismatch")
    if document["workRequestId"] != f"wr-{observed[7:31]}":
        raise ProjectionContractError("workRequest identity mismatch")
    return document


def _validate_execution_state(
    execution_state: object, *, execution_id: str
) -> Mapping[str, Any]:
    document = _object(execution_state, label="executionState")
    try:
        _assert_valid(
            dict(document), "execution", "execution_state", label="executionState"
        )
    except (TypeError, ValueError) as exc:
        raise ProjectionContractError(str(exc)) from exc
    if document["executionId"] != execution_id:
        raise ProjectionContractError("executionState executionId mismatch")
    return document


def _validate_receipts(
    stage_receipts: object, *, execution_id: str
) -> tuple[list[Mapping[str, Any]], set[str], str]:
    if isinstance(stage_receipts, (str, bytes)) or not isinstance(
        stage_receipts, Sequence
    ):
        raise ProjectionContractError("stageReceipts must be an array")
    receipts: list[Mapping[str, Any]] = []
    passed: set[str] = set()
    for index, raw in enumerate(stage_receipts):
        receipt = _object(raw, label=f"stageReceipts[{index}]")
        try:
            _assert_valid(
                dict(receipt), "execution", "stage_receipt", label="stageReceipt"
            )
        except (TypeError, ValueError) as exc:
            raise ProjectionContractError(str(exc)) from exc
        expected_stage = _STAGE_ORDER[index] if index < len(_STAGE_ORDER) else None
        if receipt["executionId"] != execution_id:
            raise ProjectionContractError("stageReceipt executionId mismatch")
        if receipt["sequence"] != index + 1 or receipt["stage"] != expected_stage:
            raise ProjectionContractError("stageReceipt order or sequence mismatch")
        if index < len(stage_receipts) - 1 and receipt["verdict"] != "pass":
            raise ProjectionContractError("a blocked stageReceipt cannot have a successor")
        if receipt["verdict"] == "pass":
            expected_next = (
                _STAGE_ORDER[index + 1]
                if index + 1 < len(_STAGE_ORDER)
                else "END"
            )
            if receipt["next"] != expected_next:
                raise ProjectionContractError("stageReceipt next stage mismatch")
            passed.add(str(receipt["stage"]))
        elif receipt["next"] == "END":
            raise ProjectionContractError("blocked stageReceipt cannot point to END")
        receipts.append(receipt)
    if not receipts:
        return receipts, passed, "0.plan"
    latest = receipts[-1]
    current_stage = (
        str(latest["next"])
        if latest["verdict"] == "pass"
        else str(latest["stage"])
    )
    return receipts, passed, current_stage


def project_content_production_task_view(
    *,
    work_request: Mapping[str, Any],
    execution_state: Mapping[str, Any],
    stage_receipts: Sequence[Mapping[str, Any]],
    owner_evidence_refs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Rebuild one task view exclusively from explicitly supplied owner facts."""

    request = _validate_work_request(work_request)
    execution_id = _text(request["rootExecutionId"], label="rootExecutionId")
    state = _validate_execution_state(execution_state, execution_id=execution_id)
    receipts, passed_stages, current_stage = _validate_receipts(
        stage_receipts, execution_id=execution_id
    )
    owner_refs = _object(owner_evidence_refs, label="ownerEvidenceRefs")
    _exact_keys(owner_refs, set(_TASK_FACTS), label="ownerEvidenceRefs")

    projected_refs: dict[str, dict[str, str]] = {}
    flags: dict[str, bool] = {}
    for name, (fact_schema, required_stage) in _TASK_FACTS.items():
        ref, fact = _fact_ref(
            owner_refs[name],
            label=f"ownerEvidenceRefs.{name}",
            expected_schema=fact_schema,
            fact_keys={"schema", "executionId", "verdict"},
        )
        if fact["executionId"] != execution_id:
            raise ProjectionContractError(f"ownerEvidenceRefs.{name} identity mismatch")
        verdict = str(fact["verdict"])
        if verdict not in _FACT_VERDICTS:
            raise ProjectionContractError(f"ownerEvidenceRefs.{name} verdict invalid")
        if verdict == "passed" and required_stage not in passed_stages:
            raise ProjectionContractError(
                f"ownerEvidenceRefs.{name} passes before {required_stage}"
            )
        projected_refs[name] = {**ref, "verdict": verdict}
        flags[name] = verdict == "passed" and required_stage in passed_stages

    ship_receipt_passed = bool(
        receipts
        and receipts[-1]["stage"] == "ship"
        and receipts[-1]["verdict"] == "pass"
        and receipts[-1]["next"] == "END"
    )
    state_succeeded = state["status"] == "succeeded"
    if ship_receipt_passed != state_succeeded:
        raise ProjectionContractError(
            "execution succeeded requires matching ship pass END receipt"
        )
    if state_succeeded != flags["shipped"]:
        raise ProjectionContractError(
            "execution succeeded requires matching shipped owner fact"
        )
    if flags["published"] and not flags["productionReady"]:
        raise ProjectionContractError("published fact requires productionReady fact")
    if flags["released"] and not flags["published"]:
        raise ProjectionContractError("released fact requires published fact")
    if flags["shipped"] and not flags["released"]:
        raise ProjectionContractError("shipped fact requires released fact")

    terminal = (
        "succeeded"
        if flags["shipped"]
        else "blocked"
        if receipts and receipts[-1]["verdict"] == "blocked"
        else "running"
    )
    result = {
        "schema": TASK_VIEW_SCHEMA,
        "projectorVersion": PROJECTOR_VERSION,
        "specRef": _SPEC_REF,
        "executionId": execution_id,
        "workRequestId": request["workRequestId"],
        "productionReady": flags["productionReady"],
        "published": flags["published"],
        "released": flags["released"],
        "shipped": flags["shipped"],
        "currentStage": current_stage,
        "terminal": terminal,
        "ownerEvidenceRefs": projected_refs,
    }
    try:
        _assert_valid(result, "execution", "content_production_task_view")
    except (TypeError, ValueError) as exc:
        raise ProjectionContractError(str(exc)) from exc
    return result


def _validate_pool_record(pool_record: object) -> Mapping[str, Any]:
    record = _object(pool_record, label="poolRecord")
    try:
        _assert_valid(dict(record), "release", "pool_object_record", label="poolRecord")
    except (TypeError, ValueError) as exc:
        raise ProjectionContractError(str(exc)) from exc
    if record["objectType"] != "content":
        raise ProjectionContractError("ContentItemVersionView requires objectType=content")
    identity = _object(record["sourceIdentity"], label="poolRecord.sourceIdentity")
    try:
        observed = _source_identity_digest(identity)
    except (RuntimeError, ValueError) as exc:
        raise ProjectionContractError(str(exc)) from exc
    if observed != identity["identityDigest"]:
        raise ProjectionContractError("poolRecord source identity digest mismatch")
    if record["canonicalObjectDigest"] != record["payloadDigest"]:
        raise ProjectionContractError("poolRecord canonical payload digest mismatch")
    return record


def _matching_item_identity(
    fact: Mapping[str, Any], record: Mapping[str, Any], *, label: str
) -> None:
    if (
        fact["objectId"] != record["objectId"]
        or fact["contentVersion"] != record["contentVersion"]
        or fact["payloadDigest"] != record["payloadDigest"]
    ):
        raise ProjectionContractError(f"{label} identity or digest mismatch")


def project_content_item_version_view(
    *,
    pool_record: Mapping[str, Any],
    content_library_ref: Mapping[str, Any],
    source_ref: Mapping[str, Any],
    publish_ref: Mapping[str, Any],
    release_refs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Rebuild one content version view without reading or retaining media bytes."""

    record = _validate_pool_record(pool_record)
    library_binding, library_fact = _fact_ref(
        content_library_ref,
        label="contentLibraryRef",
        expected_schema="quwoquan_data.content_library_version_fact",
        fact_keys={
            "schema",
            "objectId",
            "contentVersion",
            "payloadDigest",
            "holder",
            "mediaRefs",
        },
    )
    _matching_item_identity(library_fact, record, label="contentLibraryRef")
    if library_fact["holder"] != "content_library":
        raise ProjectionContractError("contentLibraryRef holder mismatch")
    raw_media = library_fact["mediaRefs"]
    if isinstance(raw_media, (str, bytes)) or not isinstance(raw_media, Sequence):
        raise ProjectionContractError("contentLibraryRef.fact.mediaRefs must be an array")
    media_refs: list[dict[str, str]] = []
    media_ids: set[str] = set()
    for index, raw in enumerate(raw_media):
        media = _object(raw, label=f"contentLibraryRef.fact.mediaRefs[{index}]")
        _exact_keys(media, {"assetId", "ref", "digest"}, label="mediaRef")
        asset_id = _text(media["assetId"], label="mediaRef.assetId")
        if asset_id in media_ids:
            raise ProjectionContractError("duplicate media asset identity")
        media_ids.add(asset_id)
        media_refs.append(
            {
                "assetId": asset_id,
                "ref": _text(media["ref"], label="mediaRef.ref"),
                "digest": _digest(media["digest"], label="mediaRef.digest"),
            }
        )
    media_refs.sort(key=lambda row: (row["assetId"], row["ref"], row["digest"]))

    source_binding, source_fact = _fact_ref(
        source_ref,
        label="sourceRef",
        expected_schema="quwoquan_data.content_source_fact",
        fact_keys={"schema", "executionId", "identityDigest"},
    )
    source_identity = _object(record["sourceIdentity"], label="poolRecord.sourceIdentity")
    if (
        source_fact["executionId"] != source_identity["executionId"]
        or source_fact["identityDigest"] != source_identity["identityDigest"]
    ):
        raise ProjectionContractError("sourceRef identity or digest mismatch")

    publish_binding, publish_fact = _fact_ref(
        publish_ref,
        label="publishRef",
        expected_schema="quwoquan_data.content_publish_fact",
        fact_keys={
            "schema",
            "objectId",
            "contentVersion",
            "payloadDigest",
            "verdict",
        },
    )
    _matching_item_identity(publish_fact, record, label="publishRef")
    publish_verdict = str(publish_fact["verdict"])
    if publish_verdict not in _FACT_VERDICTS:
        raise ProjectionContractError("publishRef verdict invalid")

    if isinstance(release_refs, (str, bytes)) or not isinstance(release_refs, Sequence):
        raise ProjectionContractError("releaseRefs must be an array")
    projected_releases: list[dict[str, str]] = []
    release_ids: set[str] = set()
    for index, raw in enumerate(release_refs):
        binding, fact = _fact_ref(
            raw,
            label=f"releaseRefs[{index}]",
            expected_schema="quwoquan_data.release_content_fact",
            fact_keys={
                "schema",
                "releaseId",
                "objectId",
                "contentVersion",
                "payloadDigest",
                "verdict",
            },
        )
        _matching_item_identity(fact, record, label=f"releaseRefs[{index}]")
        release_id = _text(fact["releaseId"], label="releaseId")
        if release_id in release_ids:
            raise ProjectionContractError("duplicate release identity")
        release_ids.add(release_id)
        verdict = str(fact["verdict"])
        if verdict not in {"included", "excluded"}:
            raise ProjectionContractError("releaseRef verdict invalid")
        if verdict == "included" and publish_verdict != "passed":
            raise ProjectionContractError("included release requires passed publish fact")
        projected_releases.append({"releaseId": release_id, **binding, "verdict": verdict})
    projected_releases.sort(key=lambda row: (row["releaseId"], row["ref"]))

    admitted = (
        record["status"] == "active"
        and record["processResult"] == "completed"
        and record["qualityResult"] == "passed"
        and record["eligibilityResult"] == "passed"
    )
    if publish_verdict == "passed" and not admitted:
        raise ProjectionContractError("passed publish fact requires admitted pool record")

    result = {
        "schema": ITEM_VIEW_SCHEMA,
        "projectorVersion": PROJECTOR_VERSION,
        "specRef": _SPEC_REF,
        "identity": {
            "contentId": record["objectId"],
            "objectRef": record["objectRef"],
            "sourceExecutionId": source_identity["executionId"],
            "sourceIdentityDigest": source_identity["identityDigest"],
        },
        "version": {
            "contentVersion": record["contentVersion"],
            "recordSequence": record["recordSequence"],
            "payloadDigest": record["payloadDigest"],
        },
        "quality": {
            "result": record["qualityResult"],
            "evidenceRef": record["evidenceRef"],
            "evidenceDigest": record["evidenceDigest"],
        },
        "eligibility": {
            "result": record["eligibilityResult"],
            "processResult": record["processResult"],
            "objectStatus": record["status"],
        },
        "delivery": {
            "contentLibrary": library_binding,
            "source": source_binding,
            "publish": {**publish_binding, "verdict": publish_verdict},
            "releases": projected_releases,
            "media": media_refs,
        },
        "usageScope": record["usageScope"],
        "holder": "content_library",
    }
    try:
        _assert_valid(result, "release", "content_item_version_view")
    except (TypeError, ValueError) as exc:
        raise ProjectionContractError(str(exc)) from exc
    return result


__all__ = [
    "ProjectionContractError",
    "project_content_item_version_view",
    "project_content_production_task_view",
]
