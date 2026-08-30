"""Build release-bound inputs consumed by App content UAT.

ReleaseUatSamplePlan is owned by Data and frozen in immutable release bytes.
Ops validates the exact header binding and projects ordered samples/case cells;
it never reads a readiness-owned UAT envelope or re-samples release objects.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

VIDEO_PAGE_SIZE = 20
_CARRIERS = ("homepage", "article", "image", "video")
_ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_RETIRED_READINESS_FIELDS = frozenset({"appUatEnvelope", "appUatEnvelopeDigest"})


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _required_text(value: object, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"App content UAT {label} is missing")
    return normalized


def _required_digest(value: object, *, label: str) -> str:
    digest = _required_text(value, label=label)
    if not _DIGEST_PATTERN.fullmatch(digest):
        raise ValueError(f"App content UAT {label} is not a canonical sha256 digest")
    return digest


def _required_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"App content UAT {label} is missing or invalid")
    return value


def _validate_readiness_surface(readiness: Mapping[str, Any]) -> None:
    retired = sorted(_RETIRED_READINESS_FIELDS.intersection(readiness))
    if retired:
        raise ValueError(
            "App content UAT readiness contains retired fields: " + ", ".join(retired)
        )


def _release_entity_refs(readiness: Mapping[str, Any]) -> set[str]:
    raw = readiness.get("entityRefs")
    if not isinstance(raw, list):
        raise ValueError("App content UAT release entityRefs are missing")
    values = [_required_text(item, label="entityRef") for item in raw]
    if len(values) != len(set(values)):
        raise ValueError("App content UAT release entityRefs are duplicated")
    return set(values)


def _normalized_entity_identity(value: object) -> str:
    normalized = _required_text(value, label="homepage identity").strip("/")
    for prefix in ("entities/", "entity/"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized


def _count_map(value: object, *, label: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(_CARRIERS):
        raise ValueError(f"App content UAT {label} carrier fields are invalid")
    result: dict[str, int] = {}
    for carrier in _CARRIERS:
        count = value.get(carrier)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"App content UAT {label}.{carrier} is invalid")
        result[carrier] = count
    return result


def _sample_rows(
    release_uat_sample_plan: Mapping[str, Any],
    *,
    release_header: Mapping[str, Any],
    release_entity_refs: set[str],
) -> list[dict[str, str]]:
    raw_samples = release_uat_sample_plan.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("App content UAT ReleaseUatSamplePlan samples are missing")
    normalized: list[dict[str, str]] = []
    sample_ids: list[str] = []
    object_ids: list[str] = []
    object_refs: list[str] = []
    normalized_entity_refs = {
        _normalized_entity_identity(value) for value in release_entity_refs
    }
    raw_contents = release_header.get("contents")
    if not isinstance(raw_contents, list):
        raise ValueError("App content UAT release header contents are missing")
    content_bindings: dict[str, tuple[str, str]] = {}
    for index, raw_content in enumerate(raw_contents):
        if not isinstance(raw_content, Mapping):
            raise ValueError(f"App content UAT release content {index} is invalid")
        content_id = _required_text(
            raw_content.get("contentId"), label=f"release content {index}.contentId"
        )
        post_ref = _required_text(
            raw_content.get("postRef"), label=f"release content {index}.postRef"
        )
        carrier = post_ref.partition("/")[0]
        if (
            carrier not in {"article", "image", "video"}
            or content_id in content_bindings
        ):
            raise ValueError(f"App content UAT release content {index} identity is invalid")
        content_bindings[content_id] = (carrier, post_ref)
    for index, raw_sample in enumerate(raw_samples):
        if not isinstance(raw_sample, Mapping) or set(raw_sample) != {
            "sampleId",
            "carrier",
            "objectId",
            "objectRef",
            "objectDigest",
        }:
            raise ValueError(f"App content UAT release sample {index} fields are invalid")
        sample_id = _required_text(
            raw_sample.get("sampleId"), label=f"sample {index}.sampleId"
        )
        carrier = _required_text(
            raw_sample.get("carrier"), label=f"sample {index}.carrier"
        )
        object_id = _required_text(
            raw_sample.get("objectId"), label=f"sample {index}.objectId"
        )
        object_ref = _required_text(
            raw_sample.get("objectRef"), label=f"sample {index}.objectRef"
        )
        _required_digest(
            raw_sample.get("objectDigest"), label=f"sample {index}.objectDigest"
        )
        if carrier not in _CARRIERS:
            raise ValueError(f"App content UAT release sample {index} carrier is invalid")
        if carrier == "homepage":
            expected_ref = (
                "objects/entities/" + _normalized_entity_identity(object_id)
            )
            if (
                _normalized_entity_identity(object_id) not in normalized_entity_refs
                or object_ref != expected_ref
            ):
                raise ValueError(
                    f"App content UAT release sample {sample_id} is not release-bound"
                )
        else:
            binding = content_bindings.get(object_id)
            if binding is None or binding[0] != carrier:
                raise ValueError(
                    f"App content UAT release sample {sample_id} is not release-bound"
                )
            expected_ref = "objects/posts/" + binding[1]
            if object_ref != expected_ref:
                raise ValueError(
                    f"App content UAT release sample {sample_id} is not release-bound"
                )
        normalized.append(dict(raw_sample))
        sample_ids.append(sample_id)
        object_ids.append(object_id)
        object_refs.append(object_ref)
    if (
        len(sample_ids) != len(set(sample_ids))
        or len(object_ids) != len(set(object_ids))
        or len(object_refs) != len(set(object_refs))
    ):
        raise ValueError("App content UAT sample identities are not unique")
    return normalized


def _case_cells(release_uat_sample_plan: Mapping[str, Any]) -> list[dict[str, str]]:
    raw_cells = release_uat_sample_plan.get("entryCarrierCells")
    if not isinstance(raw_cells, list) or len(raw_cells) != 16:
        raise ValueError("App content UAT ReleaseUatSamplePlan entryCarrierCells are invalid")
    expected_pairs = [(entry, carrier) for entry in _ENTRIES for carrier in _CARRIERS]
    cells: list[dict[str, str]] = []
    observed_pairs: list[tuple[str, str]] = []
    for index, raw_cell in enumerate(raw_cells):
        if not isinstance(raw_cell, Mapping):
            raise ValueError(f"App content UAT case cell {index} is invalid")
        entry = _required_text(raw_cell.get("entry"), label=f"case cell {index}.entry")
        carrier = _required_text(
            raw_cell.get("carrier"), label=f"case cell {index}.carrier"
        )
        applicability = _required_text(
            raw_cell.get("applicability"), label=f"case cell {index}.applicability"
        )
        if (entry, carrier) not in expected_pairs:
            raise ValueError(f"App content UAT case cell {index} identity is invalid")
        if applicability == "required":
            spec_ref = _required_text(
                raw_cell.get("specRef"), label=f"case cell {index}.specRef"
            )
            runner = _required_text(
                raw_cell.get("runnerClass"), label=f"case cell {index}.runnerClass"
            )
            if "reasonCode" in raw_cell:
                raise ValueError(f"App content UAT case cell {index} reasonCode is invalid")
            cells.append(
                {
                    "entry": entry,
                    "carrier": carrier,
                    "applicability": applicability,
                    "specRef": spec_ref,
                    "runnerClass": runner,
                }
            )
        elif applicability == "not_applicable":
            reason = _required_text(
                raw_cell.get("reasonCode"), label=f"case cell {index}.reasonCode"
            )
            if "specRef" in raw_cell or "runnerClass" in raw_cell:
                raise ValueError(f"App content UAT case cell {index} runner fields are invalid")
            cells.append(
                {
                    "entry": entry,
                    "carrier": carrier,
                    "applicability": applicability,
                    "reasonCode": reason,
                }
            )
        else:
            raise ValueError(f"App content UAT case cell {index} applicability is invalid")
        observed_pairs.append((entry, carrier))
    if observed_pairs != expected_pairs:
        raise ValueError("App content UAT ReleaseUatSamplePlan entry/carrier order drifted")
    return cells


def _release_identity(
    *,
    readiness: Mapping[str, Any],
    release_header: Mapping[str, Any],
    release_uat_sample_plan: Mapping[str, Any],
    release_payload_sha256: str,
) -> dict[str, Any]:
    release_id = _required_text(readiness.get("releaseId"), label="readiness releaseId")
    manifest_digest = _required_digest(
        readiness.get("manifestDigest"), label="readiness manifestDigest"
    )
    payload_sha256 = _required_digest(
        release_payload_sha256, label="explicit release payloadSha256"
    )
    if payload_sha256 != manifest_digest:
        raise ValueError("App content UAT release payloadSha256 drifted")
    expected_header_identity = {
        "schema": "quwoquan_data.release",
        "sourceOwner": "qwq_data",
        "releaseKind": "content",
    }
    if any(
        release_header.get(field) != value
        for field, value in expected_header_identity.items()
    ):
        raise ValueError("App content UAT release header identity is invalid")
    if release_header.get("releaseId") != release_id:
        raise ValueError("App content UAT release header releaseId mismatch")
    if release_uat_sample_plan.get("releaseId") != release_id:
        raise ValueError("App content UAT ReleaseUatSamplePlan releaseId mismatch")
    for field in ("releaseClass", "productLifecycleState"):
        expected = _required_text(readiness.get(field), label=f"readiness {field}")
        if release_header.get(field) != expected:
            raise ValueError(f"App content UAT release header {field} mismatch")
    header_source_set = release_header.get("sourceIdentities")
    readiness_source_set = readiness.get("sourceIdentities")
    if header_source_set is not None or readiness_source_set is not None:
        if (
            not isinstance(header_source_set, list)
            or not header_source_set
            or readiness_source_set != header_source_set
            or release_header.get("sourceIdentitySetDigest")
            != readiness.get("sourceIdentitySetDigest")
        ):
            raise ValueError("App content UAT release source identity set drifted")
        source_identity: dict[str, Any] = {
            "sourceIdentities": copy.deepcopy(header_source_set),
            "sourceIdentitySetDigest": _required_digest(
                release_header.get("sourceIdentitySetDigest"),
                label="release header sourceIdentitySetDigest",
            ),
        }
    else:
        source_identity = {}
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
            value = _required_digest(
                release_header.get(field), label=f"release header {field}"
            )
            if readiness.get(field) != value:
                raise ValueError(f"App content UAT release {field} drifted")
            source_identity[field] = value
    selection_evidence = _required_mapping(
        release_uat_sample_plan.get("selectionEvidence"),
        label="ReleaseUatSamplePlan selectionEvidence",
    )
    expected_selection_fields = {
        "poolDigest",
        "sourceIdentitySetDigest",
        "canonicalMerkle",
        "releaseContentsDigest",
        "releaseEntityCohortDigest",
    }
    if set(selection_evidence) != expected_selection_fields:
        raise ValueError(
            "App content UAT ReleaseUatSamplePlan selection evidence fields drifted"
        )
    for field in expected_selection_fields:
        _required_digest(
            selection_evidence.get(field),
            label=f"ReleaseUatSamplePlan selectionEvidence.{field}",
        )
    if selection_evidence.get("poolDigest") != release_header.get("poolDigest"):
        raise ValueError("App content UAT ReleaseUatSamplePlan pool digest drifted")
    if (
        selection_evidence.get("sourceIdentitySetDigest")
        != release_header.get("sourceIdentitySetDigest")
        or selection_evidence.get("sourceIdentitySetDigest")
        != readiness.get("sourceIdentitySetDigest")
    ):
        raise ValueError(
            "App content UAT ReleaseUatSamplePlan source identity set drifted"
        )
    if selection_evidence.get("canonicalMerkle") != release_header.get("canonicalMerkle"):
        raise ValueError("App content UAT ReleaseUatSamplePlan canonicalMerkle drifted")
    expected_release_digest = _canonical_digest(
        {
            "schema": "quwoquan_data.release_uat_sample_plan_identity",
            "releaseId": release_id,
            "canonicalMerkle": selection_evidence.get("canonicalMerkle"),
            "selectionEvidence": dict(selection_evidence),
        }
    )
    if release_uat_sample_plan.get("releaseDigest") != expected_release_digest:
        raise ValueError("App content UAT ReleaseUatSamplePlan releaseDigest drifted")
    release_contents_digest = _required_digest(
        selection_evidence.get("releaseContentsDigest"),
        label="ReleaseUatSamplePlan selectionEvidence.releaseContentsDigest",
    )
    release_entity_cohort_digest = _required_digest(
        selection_evidence.get("releaseEntityCohortDigest"),
        label="ReleaseUatSamplePlan selectionEvidence.releaseEntityCohortDigest",
    )
    return {
        "releaseId": release_id,
        "payloadSha256": payload_sha256,
        "releaseClass": str(release_header["releaseClass"]),
        "productLifecycleState": str(release_header["productLifecycleState"]),
        "selectionScope": _required_text(
            release_header.get("selectionScope"), label="release header selectionScope"
        ),
        "milestone": release_uat_sample_plan.get("milestone"),
        "poolDigest": _required_digest(
            release_header.get("poolDigest"), label="release header poolDigest"
        ),
        "canonicalMerkle": _required_digest(
            release_header.get("canonicalMerkle"), label="release header canonicalMerkle"
        ),
        "releaseDigest": _required_digest(
            release_uat_sample_plan.get("releaseDigest"),
            label="ReleaseUatSamplePlan releaseDigest",
        ),
        "releaseContentsDigest": release_contents_digest,
        "releaseEntityCohortDigest": release_entity_cohort_digest,
        **source_identity,
    }


def _validate_release_uat_sample_plan(
    release_uat_sample_plan: Mapping[str, Any],
    *,
    release_header: Mapping[str, Any],
    readiness: Mapping[str, Any],
    release_payload_sha256: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    expected_plan_fields = {
        "schema",
        "releaseId",
        "releaseDigest",
        "milestone",
        "selectionEvidence",
        "eligiblePopulationCounts",
        "exactCohortCounts",
        "entryCarrierCells",
        "sampleStrategy",
        "sampleCount",
        "samples",
    }
    if (
        set(release_uat_sample_plan) != expected_plan_fields
        or release_uat_sample_plan.get("schema")
        != "quwoquan_data.release_uat_sample_plan"
    ):
        raise ValueError("App content UAT ReleaseUatSamplePlan fields are invalid")
    release_identity = _release_identity(
        readiness=readiness,
        release_header=release_header,
        release_uat_sample_plan=release_uat_sample_plan,
        release_payload_sha256=release_payload_sha256,
    )
    milestone = release_uat_sample_plan.get("milestone")
    if milestone is not None:
        milestone = _required_text(milestone, label="ReleaseUatSamplePlan milestone")
    header_milestone = release_header.get("milestone")
    if release_header.get("selectionScope") not in {
        "target_environment",
        "all_publishable",
        "milestone",
    }:
        raise ValueError("App content UAT release header selectionScope is invalid")
    if milestone != header_milestone:
        raise ValueError("App content UAT ReleaseUatSamplePlan milestone mismatch")
    exact_counts = _count_map(
        release_uat_sample_plan.get("exactCohortCounts"),
        label="ReleaseUatSamplePlan exactCohortCounts",
    )
    eligible_counts = _count_map(
        release_uat_sample_plan.get("eligiblePopulationCounts"),
        label="ReleaseUatSamplePlan eligiblePopulationCounts",
    )
    if any(eligible_counts[key] < exact_counts[key] for key in _CARRIERS):
        raise ValueError("App content UAT ReleaseUatSamplePlan eligible population has a shortfall")
    header_targets = release_header.get("milestoneTargets")
    if milestone is not None and _count_map(
        header_targets, label="release header milestoneTargets"
    ) != exact_counts:
        raise ValueError("App content UAT ReleaseUatSamplePlan exact cohort drifted")
    samples = _sample_rows(
        release_uat_sample_plan,
        release_header=release_header,
        release_entity_refs=_release_entity_refs(readiness),
    )
    if release_uat_sample_plan.get("sampleCount") != len(samples):
        raise ValueError("App content UAT ReleaseUatSamplePlan sampleCount drifted")
    policy = _required_mapping(
        release_uat_sample_plan.get("sampleStrategy"),
        label="ReleaseUatSamplePlan sampleStrategy",
    )
    distribution = _count_map(
        policy.get("sampleDistribution"),
        label="ReleaseUatSamplePlan sampleStrategy.sampleDistribution",
    )
    if dict(Counter(row["carrier"] for row in samples)) != distribution:
        raise ValueError("App content UAT ReleaseUatSamplePlan distribution drifted")
    expected_strategy = (
        "stratified_exact" if milestone is not None else "baseline_per_required_carrier"
    )
    expected_seed = _canonical_digest(
        {
            "releaseDigest": release_uat_sample_plan.get("releaseDigest"),
            "sampleDistribution": distribution,
        }
    )
    if (
        (milestone is None and distribution != {carrier: 1 for carrier in _CARRIERS})
        or policy.get("name") != expected_strategy
        or policy.get("version") != 1
        or policy.get("carrierOrder") != list(_CARRIERS)
        or policy.get("sortKey") != "identity"
        or policy.get("direction") != "ascending"
        or policy.get("objectDigestAlgorithm") != "sha256-path-blob-merkle"
        or policy.get("seedDigest") != expected_seed
    ):
        raise ValueError("App content UAT ReleaseUatSamplePlan strategy drifted")
    return samples, _case_cells(release_uat_sample_plan), release_identity


def _release_uat_sample_plan_binding(
    release_header: Mapping[str, Any],
) -> tuple[str, str]:
    return (
        _required_text(
            release_header.get("samplePlanRef"),
            label="release header ReleaseUatSamplePlan ref",
        ),
        _required_digest(
            release_header.get("samplePlanDigest"),
            label="release header ReleaseUatSamplePlan digest",
        ),
    )


def load_release_uat_sample_plan(
    *,
    release_root: Path,
    release_header: Mapping[str, Any],
) -> tuple[dict[str, Any], str, str]:
    """Load the header-bound exact bytes from one immutable release payload root."""

    ref, expected_digest = _release_uat_sample_plan_binding(release_header)
    root = release_root.expanduser().resolve(strict=True)
    if ref != "uat/sample_plan.json":
        raise ValueError("App content UAT ReleaseUatSamplePlan ref is not canonical")
    path = root / ref
    if path.is_symlink():
        raise ValueError("App content UAT ReleaseUatSamplePlan must not be a symlink")
    resolved = path.resolve(strict=True)
    try:
        observed_ref = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("App content UAT ReleaseUatSamplePlan escapes release root") from exc
    if observed_ref != ref:
        raise ValueError("App content UAT ReleaseUatSamplePlan ref drifted")
    try:
        raw = resolved.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("App content UAT ReleaseUatSamplePlan is not readable JSON") from exc
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if digest != expected_digest:
        raise ValueError("App content UAT ReleaseUatSamplePlan digest drifted")
    if not isinstance(value, dict):
        raise ValueError("App content UAT ReleaseUatSamplePlan must be an object")
    return value, ref, digest


def _first_sample_identities(samples: list[dict[str, str]]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for sample in samples:
        selected.setdefault(sample["carrier"], sample["objectId"])
    if set(selected) != set(_CARRIERS):
        raise ValueError("App content UAT ReleaseUatSamplePlan lacks a required carrier")
    return selected


def build_app_content_uat_plan(
    readiness: Mapping[str, Any],
    *,
    release_header: Mapping[str, Any] | None = None,
    release_uat_sample_plan: Mapping[str, Any] | None = None,
    release_uat_sample_plan_digest: str = "",
    release_payload_sha256: str = "",
) -> dict[str, Any]:
    """Project exact release samples and environment readback into Ops UAT inputs."""

    _validate_readiness_surface(readiness)
    if release_header is None or not isinstance(release_header, Mapping):
        raise ValueError("App content UAT explicit release header is missing")
    if release_uat_sample_plan is None or not isinstance(
        release_uat_sample_plan, Mapping
    ):
        raise ValueError("App content UAT ReleaseUatSamplePlan is missing")
    ref, header_digest = _release_uat_sample_plan_binding(release_header)
    observed_digest = _required_digest(
        release_uat_sample_plan_digest,
        label="loaded ReleaseUatSamplePlan digest",
    )
    if observed_digest != header_digest:
        raise ValueError("App content UAT ReleaseUatSamplePlan digest binding drifted")
    samples, case_cells, release_identity = _validate_release_uat_sample_plan(
        release_uat_sample_plan,
        release_header=release_header,
        readiness=readiness,
        release_payload_sha256=release_payload_sha256,
    )
    selected = _first_sample_identities(samples)
    video_ids = [
        sample["objectId"] for sample in samples if sample["carrier"] == "video"
    ]
    search_canaries = [
        {
            "kind": carrier,
            "query": selected[carrier],
            "expectedObjectType": (
                "entity.homepage" if carrier == "homepage" else "content.post"
            ),
            "expectedObjectId": selected[carrier],
        }
        for carrier in _CARRIERS
    ]
    return {
        "releaseIdentity": release_identity,
        "releaseUatSamplePlanRef": ref,
        "releaseUatSamplePlanDigest": header_digest,
        "orderedSamples": copy.deepcopy(samples),
        "requiredCasePlan": copy.deepcopy(case_cells),
        "carrierIdentities": selected,
        "searchCanaries": search_canaries,
        "videoPagination": {
            "pageSize": VIDEO_PAGE_SIZE,
            "expectedWorkIds": video_ids[:VIDEO_PAGE_SIZE],
        },
        "mediaChecks": {
            "automatic": True,
            "imageWorkId": selected["image"],
            "videoWorkIds": video_ids,
        },
    }


__all__ = ["build_app_content_uat_plan", "load_release_uat_sample_plan"]
