"""Atomic WorkRequest package projection on the campaign envelope store."""

from __future__ import annotations

import fcntl
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from content.execution.campaign.carrier_execution_policy import (
    POLICY_PATH as CARRIER_POLICY_PATH,
)
from content.execution.campaign.request_envelope import (
    envelopes_root,
    normalize_execution_scope,
    scale_root,
)
from content.execution.identity import parse_execution_id
from content.execution.planning.work_request_contract import (
    _MAX_DOCUMENT_BYTES,
    _RESULT_SCHEMA,
    _digest,
    _document_size,
    _validated_result,
)
from core import paths
from core.io import read_json
from core.schema import assert_valid


def artifact_base(output_root: Path | None) -> Path:
    return (output_root or paths.OUTPUT_ROOT).resolve()


def artifact_ref(path: Path, output_root: Path | None) -> str:
    return path.resolve().relative_to(artifact_base(output_root)).as_posix()


def _assert_work_request_identity(work_request: Mapping[str, Any]) -> str:
    assert_valid(dict(work_request), "execution", "work_request")
    dependencies = work_request["dependencies"]
    if not isinstance(dependencies, Mapping):
        raise TypeError("WorkRequest dependencies must be an object")
    for binding in dependencies.values():
        if not isinstance(binding, Mapping):
            raise TypeError("WorkRequest dependency binding must be an object")
        ref = Path(str(binding.get("ref") or ""))
        if ref.is_absolute() or ".." in ref.parts:
            raise ValueError("WorkRequest dependency ref is not portable")
    if work_request.get("dependencySetDigest") != _digest(dict(dependencies)):
        raise ValueError("WorkRequest dependency set digest drift")
    stable = {
        key: value
        for key, value in work_request.items()
        if key not in {"workRequestId", "workRequestDigest", "compiledAt"}
    }
    observed_digest = _digest(stable)
    if work_request.get("workRequestDigest") != observed_digest:
        raise ValueError("WorkRequest canonical payload digest drift")
    if work_request.get("workRequestId") != (
        f"wr-{observed_digest.removeprefix('sha256:')[:24]}"
    ):
        raise ValueError("WorkRequest identity drift")
    return observed_digest


def _find_work_request_by(
    field: str, digest: str, *, output_root: Path | None
) -> Path | None:
    root = envelopes_root(root=output_root)
    if not root.is_dir():
        return None
    matches = []
    for path in root.rglob("work-request.json"):
        try:
            document = read_json(path)
        except (OSError, ValueError) as exc:
            raise ValueError(f"WorkRequest package is unreadable: {path}") from exc
        if not isinstance(document, Mapping):
            raise TypeError(f"WorkRequest package is not an object: {path}")
        _assert_work_request_identity(document)
        if document.get(field) == digest:
            matches.append(path)
    if len(matches) > 1:
        raise ValueError(f"WorkRequest {field} resolves multiple compile packages")
    return matches[0] if matches else None


def find_work_request(
    work_request_digest: str, *, output_root: Path | None
) -> Path | None:
    return _find_work_request_by(
        "workRequestDigest", work_request_digest, output_root=output_root
    )


def find_work_request_by_request_digest(
    request_digest: str, *, output_root: Path | None
) -> Path | None:
    return _find_work_request_by(
        "requestDigest", request_digest, output_root=output_root
    )


@contextmanager
def compile_lock(output_root: Path | None) -> Iterator[None]:
    root = envelopes_root(root=output_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".work-request-compile.lock"
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def next_sequence(
    normalized: Mapping[str, Any], *, output_root: Path | None
) -> tuple[str, int]:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    predecessors = normalized["predecessorExecutionIdsByCarrier"]
    if predecessors:
        identities = [parse_execution_id(str(value)) for value in predecessors.values()]
        sequence = max(identity.sequence for identity in identities) + 1
        day = identities[0].run_date
        if any(identity.run_date != day for identity in identities):
            raise ValueError("retry predecessors disagree on run date")
        return day, sequence
    scope = normalize_execution_scope(
        str(normalized["regionRef"]), normalized.get("topic")
    )
    parent = scale_root(
        str(normalized["scale"]),
        scope=scope,
        vertical=str(normalized["vertical"]),
        root=output_root,
        sequence=1,
    ).parent
    occupied = {
        int(path.name.removeprefix("sequence-"))
        for path in parent.glob("sequence-[0-9][0-9][0-9]")
        if path.is_dir()
    }
    sequence = 1
    while sequence in occupied:
        sequence += 1
    return day, sequence


def envelope_refs(
    payloads: Mapping[str, Mapping[str, Any]],
    envelope_paths: Mapping[str, Path],
    *,
    output_root: Path | None,
) -> list[dict[str, Any]]:
    return [
        {
            "carrier": carrier,
            "executionId": str(payloads[carrier]["executionId"]),
            "envelopeRef": artifact_ref(envelope_paths[carrier], output_root),
            "requestDigest": str(payloads[carrier]["requestDigest"]),
        }
        for carrier in payloads
    ]


def confirmed_projection(
    work_request_path: Path, *, output_root: Path | None, replayed: bool
) -> dict[str, Any]:
    work_request = read_json(work_request_path)
    receipt_path = work_request_path.parent / "compile-receipt.json"
    receipt = read_json(receipt_path)
    if not isinstance(work_request, dict) or not isinstance(receipt, dict):
        raise TypeError("WorkRequest compile package documents must be objects")
    observed_digest = _assert_work_request_identity(work_request)
    assert_valid(receipt, "execution", "work_request_compile_receipt")
    receipt_stable = {
        key: value for key, value in receipt.items() if key != "receiptDigest"
    }
    if receipt.get("receiptDigest") != _digest(receipt_stable):
        raise ValueError("WorkRequest compile receipt digest drift")
    expected_receipt = {
        "workRequestId": work_request["workRequestId"],
        "workRequestRef": artifact_ref(work_request_path, output_root),
        "workRequestDigest": observed_digest,
        "requestDigest": work_request["requestDigest"],
        "correlationId": observed_digest,
        "carrierPolicyRef": work_request["carrierPolicyRef"],
        "carrierPolicyDigest": work_request["carrierPolicyDigest"],
        "rootExecutionId": work_request["rootExecutionId"],
        "sourceRevision": work_request["sourceRevision"],
        "sourceDigest": work_request["sourceDigest"],
        "entityCatalogDigest": work_request["entityCatalogDigest"],
        "dependencySetDigest": work_request["dependencySetDigest"],
        "sourcePoolPlanRef": work_request["sourcePool"]["planRef"],
        "sourcePoolPlanDigest": work_request["sourcePool"]["planDigest"],
        "carrierEnvelopes": work_request["carrierEnvelopes"],
        "activeCarrierCount": len(work_request["activeCarriers"]),
        "artifactCount": len(work_request["carrierEnvelopes"]) + 2,
        "compiledAt": work_request["compiledAt"],
    }
    drift = [
        key for key, value in expected_receipt.items() if receipt.get(key) != value
    ]
    if drift:
        raise ValueError(
            "WorkRequest compile receipt binding drift: " + ", ".join(drift)
        )
    envelope_refs = list(work_request["carrierEnvelopes"])
    if [row["carrier"] for row in envelope_refs] != list(
        work_request["activeCarriers"]
    ):
        raise ValueError("WorkRequest carrier envelope order drift")
    base = artifact_base(output_root)
    for row in envelope_refs:
        envelope_path = (base / str(row["envelopeRef"])).resolve()
        try:
            envelope_path.relative_to(base)
        except ValueError as exc:
            raise ValueError("WorkRequest envelope ref escapes output root") from exc
        envelope = read_json(envelope_path)
        if not isinstance(envelope, dict):
            raise TypeError("WorkRequest carrier envelope must be an object")
        assert_valid(envelope, "execution", "content_campaign_request_envelope")
        envelope_stable = {
            key: value
            for key, value in envelope.items()
            if key != "requestDigest"
        }
        if (
            envelope.get("carrier") != row["carrier"]
            or envelope.get("executionId") != row["executionId"]
            or envelope.get("requestDigest") != row["requestDigest"]
            or envelope.get("requestDigest") != _digest(envelope_stable)
            or envelope.get("frozenAt") != work_request["compiledAt"]
        ):
            raise ValueError("WorkRequest carrier envelope binding drift")
    return _validated_result(
        {
            "schema": _RESULT_SCHEMA,
            "outcome": "confirmed",
            "requestDigest": str(work_request["requestDigest"]),
            "workRequestRef": artifact_ref(work_request_path, output_root),
            "workRequestDigest": str(work_request["workRequestDigest"]),
            "carrierPolicyDigest": str(work_request["carrierPolicyDigest"]),
            "entityCatalogDigest": str(work_request["entityCatalogDigest"]),
            "dependencySetDigest": str(work_request["dependencySetDigest"]),
            "compileReceiptRef": artifact_ref(receipt_path, output_root),
            "compileReceiptDigest": str(receipt["receiptDigest"]),
            "carrierEnvelopes": list(work_request["carrierEnvelopes"]),
            "replayed": replayed,
        }
    )


def batch_documents_factory(
    *,
    normalized: Mapping[str, Any],
    preview_digest: str,
    output_root: Path | None,
    started: float,
) -> Callable[
    [Mapping[str, Mapping[str, Any]], Mapping[str, Path]],
    Mapping[str, Mapping[str, Any]],
]:
    def build(
        payloads: Mapping[str, Mapping[str, Any]],
        envelope_paths: Mapping[str, Path],
    ) -> Mapping[str, Mapping[str, Any]]:
        first = next(iter(payloads.values()))
        refs = envelope_refs(payloads, envelope_paths, output_root=output_root)
        compiled_at = str(first["frozenAt"])
        policy_ref = CARRIER_POLICY_PATH.relative_to(paths.REPO_ROOT).as_posix()
        pool = first["scaleSourcePool"]
        work_request_stable: dict[str, Any] = {
            "schema": "quwoquan_data.work_request",
            "requestDigest": preview_digest,
            "status": "compiled",
            "intent": {
                "vertical": normalized["vertical"],
                "regionRef": normalized["regionRef"],
                "topic": normalized["topic"],
            },
            "lifecycle": normalized["lifecycle"],
            "executionMode": normalized["executionMode"],
            "scale": normalized["scale"],
            "workloadMode": normalized["workloadMode"],
            "activeCarriers": normalized["activeCarriers"],
            "workloads": normalized["workloads"],
            "carrierPolicyRef": policy_ref,
            "carrierPolicyDigest": normalized["carrierPolicyDigest"],
            "rootExecutionId": first["rootExecutionId"],
            "sourceRevision": first["sourceRevision"],
            "sourceDigest": first["sourceDigest"]["digest"],
            "entityCatalogDigest": first["entityCatalogDigest"],
            "dependencies": normalized["dependencies"],
            "dependencySetDigest": normalized["dependencySetDigest"],
            "sourcePool": {
                "poolId": pool["poolId"],
                "targetScale": pool["targetScale"],
                "planRef": pool["planRef"],
                "planDigest": pool["planDigest"],
                "evidenceRootRef": first["sourcePoolEvidenceRootRef"],
            },
            "carrierEnvelopes": refs,
            "retention": {
                "archiveAfterDays": 180,
                "deleteAfterDays": 365,
                "tombstoneRequired": True,
            },
        }
        work_request_digest = _digest(work_request_stable)
        work_request: dict[str, Any] = {
            **work_request_stable,
            "workRequestId": (
                f"wr-{work_request_digest.removeprefix('sha256:')[:24]}"
            ),
            "workRequestDigest": work_request_digest,
            "compiledAt": compiled_at,
        }
        assert_valid(work_request, "execution", "work_request")
        if _document_size(work_request) > _MAX_DOCUMENT_BYTES:
            raise ValueError("WorkRequest exceeds 256 KiB")
        target_root = next(iter(envelope_paths.values())).parent
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        total_bytes = _document_size(work_request) + sum(
            _document_size(payload) for payload in payloads.values()
        )
        receipt_stable: dict[str, Any] = {
            "schema": "quwoquan_data.work_request_compile_receipt",
            "workRequestId": work_request["workRequestId"],
            "workRequestRef": artifact_ref(
                target_root / "work-request.json", output_root
            ),
            "workRequestDigest": work_request_digest,
            "requestDigest": preview_digest,
            "correlationId": work_request_digest,
            "outcome": "confirmed",
            "carrierPolicyRef": policy_ref,
            "carrierPolicyDigest": normalized["carrierPolicyDigest"],
            "rootExecutionId": first["rootExecutionId"],
            "sourceRevision": first["sourceRevision"],
            "sourceDigest": first["sourceDigest"]["digest"],
            "entityCatalogDigest": first["entityCatalogDigest"],
            "dependencySetDigest": normalized["dependencySetDigest"],
            "sourcePoolPlanRef": pool["planRef"],
            "sourcePoolPlanDigest": pool["planDigest"],
            "carrierEnvelopes": refs,
            "activeCarrierCount": len(payloads),
            "artifactCount": len(payloads) + 2,
            "totalBytes": total_bytes,
            "durationMs": duration_ms,
            "compiledAt": compiled_at,
        }
        receipt = {**receipt_stable, "receiptDigest": _digest(receipt_stable)}
        assert_valid(receipt, "execution", "work_request_compile_receipt")
        if _document_size(receipt) > _MAX_DOCUMENT_BYTES:
            raise ValueError("WorkRequest compile receipt exceeds 256 KiB")
        return {"work-request.json": work_request, "compile-receipt.json": receipt}

    return build


__all__ = [
    "batch_documents_factory",
    "compile_lock",
    "confirmed_projection",
    "find_work_request",
    "find_work_request_by_request_digest",
    "next_sequence",
]
