"""Fail-closed semantic evidence for research scale promotion.

Primary authoring and independent review use the governed Terra binding. Sol is
not the primary reviewer: it independently calibrates a deterministic sample of
accepted objects. The immutable campaign evidence records both run classes and
rebinds every projection to an audited file below ``QWQ_OUTPUT_ROOT``.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.execution.production_contracts import validate_agent_result_envelope
from core.data_issue import DataIssueCode
from core.io import read_json
from core.runtime_policy import DEFAULT_RUNTIME_PROFILE_ID, runtime_profile_digest
from core.schema import assert_valid


SCALE_SEMANTIC_PROMOTION_ISSUE_CODE = (
    DataIssueCode.AGENT_SCALE_CALIBRATION_REQUIRED.value
)
SCALE_PROMOTION_PROVIDER = "codex_sdk"
SCALE_PROMOTION_AUTHOR_MODEL = "gpt-5.6-terra"
SCALE_PROMOTION_REVIEWER_MODEL = "gpt-5.6-terra"
SCALE_PROMOTION_MODEL_FAMILY = "gpt"
SCALE_CALIBRATION_PROVIDER = "codex_sdk"
SCALE_CALIBRATION_MODEL = "gpt-5.6-sol"
SCALE_CALIBRATION_MODEL_FAMILY = "gpt"
SCALE_CALIBRATION_SAMPLE_RATE = 0.1
SCALE_CALIBRATION_MINIMUM_SAMPLE_COUNT = 10
SCALE_CALIBRATION_SMALL_BATCH_POLICY = "all"


class ScaleSemanticPromotionError(RuntimeError):
    """A scale candidate lacks exact independent semantic evidence."""

    code = SCALE_SEMANTIC_PROMOTION_ISSUE_CODE

    def __init__(self, message: str) -> None:
        super().__init__(f"[{self.code}] {message}")


def require_scale_promotion_model_binding(
    binding: Mapping[str, Any] | object,
    *,
    label: str,
) -> dict[str, str]:
    """Require Codex Terra for both primary author and independent reviewer."""

    if not isinstance(binding, Mapping):
        raise ScaleSemanticPromotionError(f"{label} modelBinding is missing")
    expected = {
        "provider": SCALE_PROMOTION_PROVIDER,
        "authorModel": SCALE_PROMOTION_AUTHOR_MODEL,
        "authorModelFamily": SCALE_PROMOTION_MODEL_FAMILY,
        "reviewerModel": SCALE_PROMOTION_REVIEWER_MODEL,
        "reviewerModelFamily": SCALE_PROMOTION_MODEL_FAMILY,
    }
    mismatches = [
        field
        for field, value in expected.items()
        if str(binding.get(field) or "").strip() != value
    ]
    if mismatches:
        raise ScaleSemanticPromotionError(
            f"{label} requires Codex Terra author and independent Terra reviewer; "
            f"mismatches={','.join(mismatches)}"
        )
    return dict(expected)


def scale_calibration_sample_count(accepted_count: int) -> int:
    """Return all small batches, otherwise max(10, ceil(accepted * 10%))."""

    if (
        isinstance(accepted_count, bool)
        or not isinstance(accepted_count, int)
        or accepted_count < 0
    ):
        raise ScaleSemanticPromotionError(
            "semantic calibration acceptedObjectCount must be a non-negative integer"
        )
    if accepted_count == 0:
        return 0
    return min(
        accepted_count,
        max(
            SCALE_CALIBRATION_MINIMUM_SAMPLE_COUNT,
            math.ceil(accepted_count * SCALE_CALIBRATION_SAMPLE_RATE),
        ),
    )


def select_scale_calibration_refs(
    *,
    carrier: str,
    object_refs: Sequence[str],
    accepted_count: int,
) -> tuple[str, ...]:
    """Select the reproducible calibration sample without trusting list order."""

    normalized = tuple(str(ref or "").strip() for ref in object_refs)
    if any(not ref for ref in normalized) or len(set(normalized)) != len(normalized):
        raise ScaleSemanticPromotionError(
            f"{carrier} calibration candidates must be non-empty and unique"
        )
    if accepted_count > len(normalized):
        raise ScaleSemanticPromotionError(
            f"{carrier} acceptedObjectCount exceeds published object closure"
        )
    required = scale_calibration_sample_count(accepted_count)
    ranked = sorted(
        normalized,
        key=lambda ref: (
            hashlib.sha256(f"{carrier}\0{ref}".encode("utf-8")).hexdigest(),
            ref,
        ),
    )
    return tuple(ranked[:required])


def semantic_calibration_evidence_path(
    execution_root: Path,
    *,
    object_ref: str,
) -> Path:
    token = hashlib.sha256(object_ref.encode("utf-8")).hexdigest()[:20]
    return execution_root / "evidence/semantic_calibration" / f"{token}.reviewer_result.json"


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _audited_ref(path: Path, *, output_root: Path, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise ScaleSemanticPromotionError(
            f"{label} must be one regular audited file: {path}"
        )
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise ScaleSemanticPromotionError(
            f"{label} must be below QWQ_OUTPUT_ROOT: {path}"
        ) from exc


def _resolve_audited_ref(ref: object, *, output_root: Path, label: str) -> Path:
    raw = Path(str(ref or "").strip())
    if raw.is_absolute() or not raw.parts or ".." in raw.parts:
        raise ScaleSemanticPromotionError(f"{label} is unsafe: {ref}")
    path = output_root / raw
    _audited_ref(path, output_root=output_root, label=label)
    return path


def _load_validated(path: Path, *schema: str, label: str) -> dict[str, Any]:
    try:
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise TypeError(f"{label} must be an object")
        assert_valid(payload, *schema, label=label)
    except (OSError, TypeError, ValueError) as exc:
        raise ScaleSemanticPromotionError(str(exc)) from exc
    return payload


def _validate_primary_runs(
    *,
    execution_id: str,
    binding: Mapping[str, str],
    author_path: Path,
    reviewer_path: Path,
) -> tuple[str, str, str]:
    author = _load_validated(
        author_path,
        "content",
        "agent_result_envelope",
        label="scale primary author evidence",
    )
    reviewer = _load_validated(
        reviewer_path,
        "content",
        "reviewer_result",
        label="scale primary reviewer evidence",
    )
    envelope_issues = validate_agent_result_envelope(
        author,
        workspace_root=author_path.parent,
        require_passing_gates=True,
    )
    author_agent = author.get("agent")
    author_agent = author_agent if isinstance(author_agent, Mapping) else {}
    author_ref = str(author.get("ref") or "").strip()
    reviewer_ref = str(reviewer.get("objectRef") or "").strip()
    author_run_id = str(author_agent.get("runId") or "").strip()
    reviewer_run_id = str(reviewer.get("runId") or "").strip()
    if (
        envelope_issues
        or author.get("executionId") != execution_id
        or author.get("stage") != "author"
        or not author_ref
        or author_ref != reviewer_ref
        or author_agent.get("provider") != binding["provider"]
        or author_agent.get("model") != binding["authorModel"]
        or reviewer.get("executionId") != execution_id
        or reviewer.get("provider") != binding["provider"]
        or reviewer.get("model") != binding["reviewerModel"]
        or reviewer.get("modelFamily") != binding["reviewerModelFamily"]
        or reviewer.get("verdict") != "passed"
        or reviewer.get("issues")
        or not author_run_id
        or not reviewer_run_id
        or author_run_id == reviewer_run_id
    ):
        detail = "; ".join(envelope_issues[:3]) or "binding/run independence drift"
        raise ScaleSemanticPromotionError(
            f"primary semantic author/reviewer evidence is not promotable: {detail}"
        )
    return author_ref, author_run_id, reviewer_run_id


def _validate_calibration_run(
    *,
    execution_id: str,
    object_ref: str,
    evidence_path: Path,
    disallowed_run_ids: set[str],
) -> str:
    calibration = _load_validated(
        evidence_path,
        "content",
        "reviewer_result",
        label=f"Sol calibration evidence:{object_ref}",
    )
    run_id = str(calibration.get("runId") or "").strip()
    if (
        calibration.get("executionId") != execution_id
        or calibration.get("objectRef") != object_ref
        or calibration.get("provider") != SCALE_CALIBRATION_PROVIDER
        or calibration.get("model") != SCALE_CALIBRATION_MODEL
        or calibration.get("modelFamily") != SCALE_CALIBRATION_MODEL_FAMILY
        or calibration.get("verdict") != "passed"
        or calibration.get("issues")
        or not run_id
        or run_id in disallowed_run_ids
    ):
        raise ScaleSemanticPromotionError(
            f"{object_ref} Sol calibration evidence is not independent/promotable"
        )
    return run_id


def _run_projection(
    *,
    object_ref: str,
    run_id: str,
    evidence_path: Path,
    output_root: Path,
    label: str,
) -> dict[str, str]:
    return {
        "objectRef": object_ref,
        "runId": run_id,
        "evidenceRef": _audited_ref(
            evidence_path,
            output_root=output_root,
            label=label,
        ),
        "evidenceSha256": _file_sha256(evidence_path),
    }


def _selection_policy(
    *,
    carrier: str,
    accepted_count: int,
    selected_refs: Sequence[str],
) -> dict[str, Any]:
    stable: dict[str, Any] = {
        "sampleRate": SCALE_CALIBRATION_SAMPLE_RATE,
        "minimumSampleCount": SCALE_CALIBRATION_MINIMUM_SAMPLE_COUNT,
        "smallBatchPolicy": SCALE_CALIBRATION_SMALL_BATCH_POLICY,
        "acceptedObjectCount": accepted_count,
        "requiredSampleCount": len(selected_refs),
        "selectedObjectRefs": list(selected_refs),
    }
    digest_payload = {
        "schema": "quwoquan_data.semantic_calibration_selection",
        "carrier": carrier,
        **stable,
    }
    return {**stable, "selectionDigest": _payload_sha256(digest_payload)}


def build_scale_semantic_calibration(
    *,
    execution_id: str,
    carrier: str,
    execution_manifest_path: Path,
    object_root: Path,
    published_refs: Sequence[str],
    accepted_object_count: int,
    output_root: Path,
) -> dict[str, Any]:
    """Bind primary Terra runs and all required Sol calibration samples."""

    manifest = _load_validated(
        execution_manifest_path,
        "execution",
        "content_execution_manifest",
        label=f"scale execution manifest:{execution_id}",
    )
    if manifest.get("executionId") != execution_id:
        raise ScaleSemanticPromotionError(
            f"{carrier} scale execution manifest identity drift"
        )
    if (
        manifest.get("runtimeProfileId") != DEFAULT_RUNTIME_PROFILE_ID
        or manifest.get("runtimeProfileDigest")
        != runtime_profile_digest(DEFAULT_RUNTIME_PROFILE_ID)
    ):
        raise ScaleSemanticPromotionError(
            f"{carrier} scale runtime profile identity drift"
        )
    binding = require_scale_promotion_model_binding(
        manifest.get("modelBinding"),
        label=f"{carrier} M100 promotion",
    )
    author_path = object_root / "4.draft/agent_result_envelope.json"
    reviewer_path = object_root / "5.review/reviewer_result.json"
    primary_ref, author_run_id, reviewer_run_id = _validate_primary_runs(
        execution_id=execution_id,
        binding=binding,
        author_path=author_path,
        reviewer_path=reviewer_path,
    )
    selected_refs = select_scale_calibration_refs(
        carrier=carrier,
        object_refs=published_refs,
        accepted_count=accepted_object_count,
    )
    if not selected_refs:
        raise ScaleSemanticPromotionError(
            f"{carrier} M100 calibration has no accepted objects"
        )
    execution_root = execution_manifest_path.parent
    used_run_ids = {author_run_id, reviewer_run_id}
    calibration_runs: list[dict[str, str]] = []
    for selected_ref in selected_refs:
        evidence_path = semantic_calibration_evidence_path(
            execution_root,
            object_ref=selected_ref,
        )
        run_id = _validate_calibration_run(
            execution_id=execution_id,
            object_ref=selected_ref,
            evidence_path=evidence_path,
            disallowed_run_ids=used_run_ids,
        )
        used_run_ids.add(run_id)
        calibration_runs.append(
            _run_projection(
                object_ref=selected_ref,
                run_id=run_id,
                evidence_path=evidence_path,
                output_root=output_root,
                label=f"{carrier} Sol calibration evidence",
            )
        )
    return {
        "carrier": carrier,
        **binding,
        "calibrationProvider": SCALE_CALIBRATION_PROVIDER,
        "calibrationModel": SCALE_CALIBRATION_MODEL,
        "calibrationModelFamily": SCALE_CALIBRATION_MODEL_FAMILY,
        "executionManifestRef": _audited_ref(
            execution_manifest_path,
            output_root=output_root,
            label=f"{carrier} execution manifest",
        ),
        "executionManifestSha256": _file_sha256(execution_manifest_path),
        "authorRun": _run_projection(
            object_ref=primary_ref,
            run_id=author_run_id,
            evidence_path=author_path,
            output_root=output_root,
            label=f"{carrier} primary author evidence",
        ),
        "reviewerRun": _run_projection(
            object_ref=primary_ref,
            run_id=reviewer_run_id,
            evidence_path=reviewer_path,
            output_root=output_root,
            label=f"{carrier} primary reviewer evidence",
        ),
        "selectionPolicy": _selection_policy(
            carrier=carrier,
            accepted_count=accepted_object_count,
            selected_refs=selected_refs,
        ),
        "calibrationRuns": calibration_runs,
    }


def validate_scale_semantic_calibration(
    payload: Mapping[str, Any] | object,
    *,
    execution_id: str,
    carrier: str,
    published_refs: Sequence[str],
    accepted_object_count: int,
    output_root: Path,
) -> None:
    """Rebind frozen primary and calibration projections to exact files."""

    if not isinstance(payload, Mapping):
        raise ScaleSemanticPromotionError(
            f"{carrier} semantic calibration evidence is missing"
        )
    binding = require_scale_promotion_model_binding(
        payload,
        label=f"{carrier} M100 promotion evidence",
    )
    if (
        payload.get("carrier") != carrier
        or payload.get("calibrationProvider") != SCALE_CALIBRATION_PROVIDER
        or payload.get("calibrationModel") != SCALE_CALIBRATION_MODEL
        or payload.get("calibrationModelFamily") != SCALE_CALIBRATION_MODEL_FAMILY
    ):
        raise ScaleSemanticPromotionError(
            f"{carrier} semantic calibration provider/model drift"
        )
    manifest_path = _resolve_audited_ref(
        payload.get("executionManifestRef"),
        output_root=output_root,
        label=f"{carrier} execution manifest ref",
    )
    if (
        manifest_path.name != "execution_manifest.json"
        or manifest_path.parent.name != execution_id
        or _file_sha256(manifest_path) != payload.get("executionManifestSha256")
    ):
        raise ScaleSemanticPromotionError(
            f"{carrier} semantic calibration manifest path/digest drift"
        )
    manifest = _load_validated(
        manifest_path,
        "execution",
        "content_execution_manifest",
        label=f"scale execution manifest:{execution_id}",
    )
    if (
        manifest.get("executionId") != execution_id
        or manifest.get("runtimeProfileId") != DEFAULT_RUNTIME_PROFILE_ID
        or manifest.get("runtimeProfileDigest")
        != runtime_profile_digest(DEFAULT_RUNTIME_PROFILE_ID)
        or require_scale_promotion_model_binding(
            manifest.get("modelBinding"),
            label=f"{carrier} frozen M100 manifest",
        )
        != binding
    ):
        raise ScaleSemanticPromotionError(
            f"{carrier} semantic calibration manifest binding drift"
        )
    author_projection = payload.get("authorRun")
    reviewer_projection = payload.get("reviewerRun")
    if not isinstance(author_projection, Mapping) or not isinstance(
        reviewer_projection,
        Mapping,
    ):
        raise ScaleSemanticPromotionError(f"{carrier} primary run projection is missing")
    author_path = _resolve_audited_ref(
        author_projection.get("evidenceRef"),
        output_root=output_root,
        label=f"{carrier} primary author evidence ref",
    )
    reviewer_path = _resolve_audited_ref(
        reviewer_projection.get("evidenceRef"),
        output_root=output_root,
        label=f"{carrier} primary reviewer evidence ref",
    )
    if (
        author_path.name != "agent_result_envelope.json"
        or author_path.parent.name != "4.draft"
        or reviewer_path.name != "reviewer_result.json"
        or reviewer_path.parent.name != "5.review"
        or author_path.parent.parent != reviewer_path.parent.parent
        or _file_sha256(author_path) != author_projection.get("evidenceSha256")
        or _file_sha256(reviewer_path) != reviewer_projection.get("evidenceSha256")
    ):
        raise ScaleSemanticPromotionError(
            f"{carrier} primary semantic evidence path/digest drift"
        )
    primary_ref, author_run_id, reviewer_run_id = _validate_primary_runs(
        execution_id=execution_id,
        binding=binding,
        author_path=author_path,
        reviewer_path=reviewer_path,
    )
    if (
        author_projection.get("objectRef") != primary_ref
        or reviewer_projection.get("objectRef") != primary_ref
        or author_projection.get("runId") != author_run_id
        or reviewer_projection.get("runId") != reviewer_run_id
    ):
        raise ScaleSemanticPromotionError(
            f"{carrier} primary semantic run projection drift"
        )
    selected_refs = select_scale_calibration_refs(
        carrier=carrier,
        object_refs=published_refs,
        accepted_count=accepted_object_count,
    )
    expected_policy = _selection_policy(
        carrier=carrier,
        accepted_count=accepted_object_count,
        selected_refs=selected_refs,
    )
    if payload.get("selectionPolicy") != expected_policy:
        raise ScaleSemanticPromotionError(
            f"{carrier} semantic calibration selection policy drift"
        )
    runs = payload.get("calibrationRuns")
    if not isinstance(runs, list) or len(runs) != len(selected_refs):
        raise ScaleSemanticPromotionError(
            f"{carrier} semantic calibration sample count drift"
        )
    used_run_ids = {author_run_id, reviewer_run_id}
    execution_root = manifest_path.parent
    for selected_ref, projection in zip(selected_refs, runs, strict=True):
        if not isinstance(projection, Mapping) or projection.get("objectRef") != selected_ref:
            raise ScaleSemanticPromotionError(
                f"{carrier} semantic calibration object selection drift"
            )
        evidence_path = _resolve_audited_ref(
            projection.get("evidenceRef"),
            output_root=output_root,
            label=f"{carrier} Sol calibration evidence ref",
        )
        expected_path = semantic_calibration_evidence_path(
            execution_root,
            object_ref=selected_ref,
        )
        if (
            evidence_path.resolve() != expected_path.resolve()
            or _file_sha256(evidence_path) != projection.get("evidenceSha256")
        ):
            raise ScaleSemanticPromotionError(
                f"{carrier} Sol calibration evidence path/digest drift"
            )
        run_id = _validate_calibration_run(
            execution_id=execution_id,
            object_ref=selected_ref,
            evidence_path=evidence_path,
            disallowed_run_ids=used_run_ids,
        )
        if projection.get("runId") != run_id:
            raise ScaleSemanticPromotionError(
                f"{carrier} Sol calibration runId drift"
            )
        used_run_ids.add(run_id)


__all__ = [
    "SCALE_SEMANTIC_PROMOTION_ISSUE_CODE",
    "ScaleSemanticPromotionError",
    "build_scale_semantic_calibration",
    "require_scale_promotion_model_binding",
    "scale_calibration_sample_count",
    "select_scale_calibration_refs",
    "semantic_calibration_evidence_path",
    "validate_scale_semantic_calibration",
]
