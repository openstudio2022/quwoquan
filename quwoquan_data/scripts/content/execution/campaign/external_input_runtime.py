"""Fenced execution envelopes for lane-scoped capsule external inputs."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign.external_inputs import (
    CampaignExternalInputError,
    external_inputs_digest,
    payload_digest,
    verify_external_input_refs,
)
from content.execution.campaign.submission import load_submissions
from content.execution.identity import validate_execution_id

if TYPE_CHECKING:
    from content.execution.campaign.workspace import (
        CampaignLaneWorkspace,
        CampaignRuntimePaths,
    )

EXECUTION_EXTERNAL_INPUT_ENVELOPE_REF = (
    "0.plan/campaign_external_input_envelope.json"
)
EXECUTION_EXTERNAL_INPUT_ENVELOPE_SCHEMA = (
    "quwoquan_data.execution_external_input_envelope"
)
_BOUND_CONTEXTS: dict[str, ExternalInputRuntimeContext] = {}
_BOUND_CONTEXTS_LOCK = threading.Lock()


def _typed(code: str, detail: str) -> CampaignExternalInputError:
    return CampaignExternalInputError(f"DATA.CAMPAIGN.EXTERNAL_INPUT_{code}", detail)


def execution_external_input_envelope_path(execution_root: Path) -> Path:
    return execution_root / EXECUTION_EXTERNAL_INPUT_ENVELOPE_REF


def _assert_envelope(payload: dict[str, Any], *, label: str) -> None:
    try:
        assert_valid(
            payload,
            "execution",
            "execution_external_input_envelope",
            label=label,
        )
    except ValueError as exc:
        raise _typed("ENVELOPE_INVALID", str(exc)) from exc
    stable = {key: value for key, value in payload.items() if key != "envelopeDigest"}
    if payload.get("envelopeDigest") != payload_digest(stable):
        raise _typed("DIGEST_DRIFT", f"{label} envelopeDigest drift")


def load_execution_external_input_envelope(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise _typed("ENVELOPE_INVALID", f"execution envelope is not an object: {path}")
    _assert_envelope(payload, label=f"execution external inputs:{path}")
    return payload


def freeze_execution_external_input_envelope(
    *,
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    plan: dict[str, Any],
    submission: dict[str, Any],
    workspace: CampaignLaneWorkspace,
) -> Path:
    carrier = workspace.carrier
    lane = dict(plan["laneExternalInputs"][carrier])
    capsule_lane = dict(workspace.capsule.lane_external_inputs[carrier])
    refs = list(submission.get("externalInputRefs") or [])
    digest = external_inputs_digest(refs)
    if (
        lane.get("externalInputRefs") != refs
        or lane.get("externalInputsDigest") != digest
        or capsule_lane.get("externalInputRefs") != refs
        or capsule_lane.get("externalInputsDigest") != digest
    ):
        raise _typed("DIGEST_DRIFT", f"{carrier} plan/capsule descriptor drift")
    stable = {
        "schema": EXECUTION_EXTERNAL_INPUT_ENVELOPE_SCHEMA,
        "rootExecutionId": root_execution_id,
        "executionId": str(submission["executionId"]),
        "carrier": carrier,
        "sourceRevision": str(plan["sourceRevision"]),
        "sourceDigest": str(plan["sourceDigest"]),
        "entityCatalogDigest": str(plan["entityCatalogDigest"]),
        "submissionDigest": str(submission["requestDigest"]),
        "planDigest": str(plan["planDigest"]),
        "capsuleRef": workspace.capsule.ref,
        "capsuleDigest": workspace.capsule.capsule_digest,
        "externalInputRootRef": str(capsule_lane["rootRef"]),
        "externalInputRefs": refs,
        "externalInputsDigest": digest,
    }
    payload = {**stable, "envelopeDigest": payload_digest(stable)}
    _assert_envelope(payload, label=f"execution external inputs:{carrier}")
    path = execution_external_input_envelope_path(workspace.execution_root)
    if path.is_file():
        existing = load_execution_external_input_envelope(path)
        if existing != payload:
            raise _typed(
                "IMMUTABLE",
                f"{submission['executionId']} external inputs changed; create a new "
                "execution sequence with retryOf",
            )
        return path
    write_json(path, payload)
    return path


def _plan(runtime: CampaignRuntimePaths, root_execution_id: str) -> dict[str, Any]:
    path = runtime.campaigns_root / root_execution_id / "campaign_plan.json"
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise _typed("ENVELOPE_INVALID", "campaign plan must be an object")
    try:
        assert_valid(
            payload,
            "execution",
            "content_campaign_plan",
            label=f"campaign plan:{root_execution_id}",
        )
    except ValueError as exc:
        raise _typed("ENVELOPE_INVALID", str(exc)) from exc
    stable = {key: value for key, value in payload.items() if key != "planDigest"}
    if payload.get("planDigest") != payload_digest(stable):
        raise _typed("DIGEST_DRIFT", "campaign planDigest drift")
    return payload


def _portable_path(ref: str, *, runtime: CampaignRuntimePaths) -> Path:
    raw = Path(str(ref or "").strip())
    path = raw if raw.is_absolute() else runtime.output_root / raw
    return path.resolve()


def _capsule_manifest(path: Path) -> dict[str, Any]:
    manifest_path = path / ".qwq_campaign_capsule.json"
    payload = read_json(manifest_path)
    if not isinstance(payload, dict):
        raise _typed("ENVELOPE_INVALID", "capsule manifest must be an object")
    try:
        assert_valid(
            payload,
            "execution",
            "content_source_capsule",
            label=f"campaign capsule:{path}",
        )
    except ValueError as exc:
        raise _typed("ENVELOPE_INVALID", str(exc)) from exc
    stable = {
        key: value
        for key, value in payload.items()
        if key not in {"capsuleDigest", "treeDigest"}
    }
    if payload.get("capsuleDigest") != payload_digest(stable):
        raise _typed("DIGEST_DRIFT", "capsuleDigest drift")
    return payload


def _runtime_paths() -> CampaignRuntimePaths:
    from content.execution.campaign.workspace import CampaignRuntimePaths

    return CampaignRuntimePaths.defaults()


@dataclass(frozen=True, slots=True)
class ExternalInputRuntimeContext:
    root: Path
    envelope: dict[str, Any]
    refs: tuple[dict[str, Any], ...]
    blob_refs_by_digest: dict[str, str]
    capsule_root: Path | None = None

    def has_kind(self, kind: str) -> bool:
        return any(row.get("kind") == kind for row in self.refs)

    def descriptors(self, kind: str) -> tuple[dict[str, Any], ...]:
        rows = tuple(row for row in self.refs if row.get("kind") == kind)
        if not rows:
            raise _typed("UNDECLARED", f"undeclared external input kind: {kind}")
        return rows

    def receipt_refs(self, kind: str) -> list[str]:
        return [str(row["receiptRef"]) for row in self.descriptors(kind)]

    def acquisition_root(self, kind: str) -> Path:
        roots = {
            str(row.get("acquisitionRootRef") or "")
            for row in self.descriptors(kind)
        }
        if len(roots) != 1:
            raise _typed(
                "ROOT_AMBIGUOUS",
                f"{kind} must bind exactly one acquisitionRootRef",
            )
        relative = Path(next(iter(roots)))
        resolved = (self.root / relative).resolve()
        if resolved != self.root.resolve() and self.root.resolve() not in resolved.parents:
            raise _typed("PATH_ESCAPE", f"{kind} acquisition root escapes capsule")
        if not resolved.is_dir():
            raise _typed("MISSING", f"{kind} acquisition root is missing")
        return resolved

    def require_receipt_refs(self, kind: str, receipt_refs: list[str]) -> list[str]:
        requested = [str(item).strip() for item in receipt_refs]
        if not requested or any(not item for item in requested):
            raise _typed("UNDECLARED", f"{kind} receipt refs must be non-empty")
        if len(set(requested)) != len(requested):
            raise _typed("DUPLICATE", f"{kind} receipt refs contain duplicates")
        declared = set(self.receipt_refs(kind))
        undeclared = set(requested) - declared
        if undeclared:
            raise _typed(
                "UNDECLARED",
                "undeclared receipt refs: " + ", ".join(sorted(undeclared)),
            )
        return requested

    def blob_path(self, content_sha256: str) -> Path:
        ref = self.blob_refs_by_digest.get(content_sha256)
        if ref is None:
            raise _typed("UNDECLARED", f"undeclared blob digest: {content_sha256}")
        path = (self.root / ref).resolve()
        if self.root.resolve() not in path.parents or not path.is_file():
            raise _typed("PATH_ESCAPE", f"runtime blob path is invalid: {ref}")
        return path


def bind_runtime_external_input_context(
    context: ExternalInputRuntimeContext,
) -> ExternalInputRuntimeContext:
    execution_id = str(context.envelope["executionId"])
    with _BOUND_CONTEXTS_LOCK:
        existing = _BOUND_CONTEXTS.get(execution_id)
        if existing is not None and existing.envelope != context.envelope:
            raise _typed("IMMUTABLE", f"{execution_id} runtime context changed")
        _BOUND_CONTEXTS[execution_id] = context
    return context


def bound_runtime_external_input_context(
    execution_id: str,
    carrier: str,
) -> ExternalInputRuntimeContext | None:
    normalized = validate_execution_id(execution_id)
    with _BOUND_CONTEXTS_LOCK:
        context = _BOUND_CONTEXTS.get(normalized)
    if context is None:
        return None
    if context.envelope.get("carrier") != carrier:
        raise _typed("IDENTITY_DRIFT", "bound runtime carrier drift")
    return context


def resolve_runtime_external_input_context(
    execution_id: str,
    carrier: str,
    *,
    requested_receipt_refs: list[str] | None = None,
    requested_kind: str | None = None,
    runtime_paths: CampaignRuntimePaths | None = None,
) -> ExternalInputRuntimeContext:
    """Resolve only canonical envelope/capsule refs; never scan or trust env."""
    normalized = validate_execution_id(execution_id)
    runtime = runtime_paths or _runtime_paths()
    canonical_envelope_path = execution_external_input_envelope_path(
        runtime.output_root / "data" / "tasks" / normalized
    ).resolve()
    envelope = load_execution_external_input_envelope(canonical_envelope_path)
    root_execution_id = str(envelope.get("rootExecutionId") or "").strip()
    if not root_execution_id:
        raise _typed("ENVELOPE_INVALID", "rootExecutionId is missing")
    if envelope.get("executionId") != normalized or envelope.get("carrier") != carrier:
        raise _typed("IDENTITY_DRIFT", "execution envelope lane identity drift")
    submissions = load_submissions(root_execution_id, root=runtime.campaigns_root)
    submission = submissions.get(carrier)
    if not submission or submission.get("executionId") != normalized:
        raise _typed("IDENTITY_DRIFT", f"{carrier} submission identity drift")
    plan = _plan(runtime, root_execution_id)
    capsule_root = _portable_path(str(envelope["capsuleRef"]), runtime=runtime)
    capsule = _capsule_manifest(capsule_root)
    capsule_lane = dict(capsule["laneExternalInputs"][carrier])
    plan_lane = dict(plan["laneExternalInputs"][carrier])
    refs = list(envelope["externalInputRefs"])
    digest = external_inputs_digest(refs)
    expected_identity = {
        "sourceRevision": str(plan["sourceRevision"]),
        "sourceDigest": str(plan["sourceDigest"]),
        "entityCatalogDigest": str(plan["entityCatalogDigest"]),
        "submissionDigest": str(submission["requestDigest"]),
        "planDigest": str(plan["planDigest"]),
        "capsuleDigest": str(capsule["capsuleDigest"]),
        "externalInputsDigest": digest,
    }
    drift = [
        key for key, value in expected_identity.items() if envelope.get(key) != value
    ]
    if drift:
        raise _typed("IDENTITY_DRIFT", "execution envelope drift: " + ", ".join(drift))
    if any(
        row.get("externalInputRefs") != refs
        or row.get("externalInputsDigest") != digest
        for row in (submission, plan_lane, capsule_lane)
    ):
        raise _typed("DIGEST_DRIFT", "submission/plan/capsule external input drift")
    expected_root = (capsule_root / str(envelope["externalInputRootRef"])).resolve()
    if capsule_root not in expected_root.parents:
        raise _typed("PATH_ESCAPE", "capsule external input root escapes capsule")
    verify_external_input_refs(
        carrier,
        refs,
        acquisition_root=expected_root,
        source_revision=str(plan["sourceRevision"]),
        source_digest=str(plan["sourceDigest"]),
        entity_catalog_digest=str(plan["entityCatalogDigest"]),
    )
    blobs: dict[str, str] = {}
    for row in refs:
        root_ref = str(row["acquisitionRootRef"])
        for blob in row["blobRefs"]:
            digest_key = str(blob["contentSha256"])
            blob_ref = (Path(root_ref) / str(blob["blobRef"])).as_posix()
            if digest_key in blobs and blobs[digest_key] != blob_ref:
                raise _typed("DIGEST_DRIFT", f"conflicting blob digest: {digest_key}")
            blobs[digest_key] = blob_ref
    context = ExternalInputRuntimeContext(
        root=expected_root,
        envelope=envelope,
        refs=tuple(dict(row) for row in refs),
        blob_refs_by_digest=blobs,
        capsule_root=capsule_root,
    )
    if requested_kind is not None:
        if requested_receipt_refs is None:
            context.descriptors(requested_kind)
        else:
            context.require_receipt_refs(requested_kind, requested_receipt_refs)
    elif requested_receipt_refs:
        declared_receipts = {str(row["receiptRef"]) for row in refs}
        undeclared = {
            str(item).strip() for item in requested_receipt_refs
        } - declared_receipts
        if undeclared:
            raise _typed(
                "UNDECLARED",
                "undeclared receipt refs: " + ", ".join(sorted(undeclared)),
            )
    return context


__all__ = [
    "EXECUTION_EXTERNAL_INPUT_ENVELOPE_REF",
    "ExternalInputRuntimeContext",
    "bind_runtime_external_input_context",
    "bound_runtime_external_input_context",
    "execution_external_input_envelope_path",
    "freeze_execution_external_input_envelope",
    "load_execution_external_input_envelope",
    "resolve_runtime_external_input_context",
]
