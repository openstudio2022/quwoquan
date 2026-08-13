"""state/receipt 的安全读写、锁与 readback 一致性校验（stdlib-only）。"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .contract import (
    AUTHORITY,
    POSITIVE_INTEGER_RE,
    READBACK_SCHEMA,
    RECEIPT_FIELDS,
    RECEIPT_ID_RE,
    RECEIPT_SCHEMA,
    REQUEST_FIELDS,
    REQUEST_SCHEMA,
    SOAK_RECEIPT_FIELDS,
    SOAK_RECEIPT_SCHEMA,
    SOAK_REQUEST_FIELDS,
    SOAK_REQUEST_SCHEMA,
    STAGE_RECEIPT_ID_FIELDS,
    STATE_FIELDS,
    STATE_SCHEMA,
    _receipt_id,
    _require_timestamp,
)
from .request_validation import _validate_request, _validate_soak_request


def _load_hosted_soak_receipt(
    root: Path,
    *,
    service: str,
    receipt_id: str,
) -> dict[str, Any]:
    if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise RuntimeError("hosted prod soak receipt id is invalid")
    receipt_path = root / "soak-receipts" / f"{receipt_id}.json"
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise RuntimeError("hosted prod soak receipt is missing")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("hosted prod soak receipt is not canonical JSON") from error
    if (
        not isinstance(receipt, dict)
        or set(receipt) != SOAK_RECEIPT_FIELDS
        or receipt.get("schema") != SOAK_RECEIPT_SCHEMA
        or receipt.get("authority") != AUTHORITY
        or receipt.get("service") != service
        or receipt.get("receiptId") != receipt_id
        or _receipt_id(receipt) != receipt_id
    ):
        raise RuntimeError("hosted prod soak receipt digest or ledger binding is invalid")
    request = {
        field: receipt[field] for field in SOAK_REQUEST_FIELDS if field != "schema"
    }
    request["schema"] = SOAK_REQUEST_SCHEMA
    try:
        _validate_soak_request(request)
    except ValueError as error:
        raise RuntimeError("hosted prod soak receipt payload is not canonical") from error
    started_at = _require_timestamp(receipt.get("soakStartedAt"), field="soakStartedAt")
    ended_at = _require_timestamp(receipt.get("soakEndedAt"), field="soakEndedAt")
    verified_at = _require_timestamp(receipt.get("verifiedAt"), field="verifiedAt")
    duration = receipt.get("soakDurationSeconds")
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration != int((ended_at - started_at).total_seconds())
        or duration < receipt["requiredSoakSeconds"]
        or ended_at > verified_at
    ):
        raise RuntimeError("hosted prod soak receipt duration is invalid")
    return receipt


def _load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("hosted release ledger state is not a regular file")
    payload: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw:
            raise RuntimeError("hosted release ledger state is malformed")
        key, value = raw.split("=", 1)
        if key in payload:
            raise RuntimeError("hosted release ledger state has duplicate fields")
        payload[key] = value
    if set(payload) != STATE_FIELDS or payload.get("schema") != STATE_SCHEMA:
        raise RuntimeError("hosted release ledger state shape is not canonical")
    return payload


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


@contextlib.contextmanager
def _ledger_lock(root: Path) -> Any:
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise RuntimeError("hosted release ledger root must not be a symlink")
    lock_path = root / ".ledger.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_hosted_receipt(
    root: Path,
    *,
    service: str,
    receipt_id: str,
) -> dict[str, Any]:
    if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise RuntimeError("hosted release receipt id is invalid")
    receipt_path = root / "receipts" / f"{receipt_id}.json"
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise RuntimeError("hosted release receipt is missing")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("hosted release receipt is not canonical JSON") from error
    if (
        not isinstance(receipt, dict)
        or set(receipt) != RECEIPT_FIELDS
        or receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("authority") != AUTHORITY
        or receipt.get("service") != service
        or receipt.get("receiptId") != receipt_id
        or _receipt_id(receipt) != receipt_id
    ):
        raise RuntimeError("hosted release receipt digest or ledger binding is invalid")
    request = {
        field: receipt[field]
        for field in REQUEST_FIELDS
        if field != "schema"
    }
    request["schema"] = REQUEST_SCHEMA
    try:
        _validate_request(request)
    except ValueError as error:
        raise RuntimeError("hosted release receipt payload is not canonical") from error
    expected_generation = receipt.get("expectedGeneration")
    committed_generation = receipt.get("committedGeneration")
    if (
        not isinstance(committed_generation, int)
        or isinstance(committed_generation, bool)
        or committed_generation != expected_generation + 1
    ):
        raise RuntimeError("hosted release receipt generation is invalid")
    return receipt


def _history_receipt_matches_transaction(
    state: Mapping[str, str],
    receipt: Mapping[str, Any],
) -> bool:
    state_pair = (
        state.get("from_candidate_digest"),
        state.get("to_candidate_digest"),
    )
    receipt_pair = (
        receipt.get("fromCandidateDigest"),
        receipt.get("toCandidateDigest"),
    )
    if receipt_pair == state_pair:
        return True
    return (
        state.get("decision") in {"rolled_back", "rollback_failed"}
        and receipt_pair == tuple(reversed(state_pair))
    )


def _validate_stage_receipt_history(
    root: Path,
    *,
    service: str,
    state: Mapping[str, str],
) -> None:
    generation = state.get("generation", "")
    if POSITIVE_INTEGER_RE.fullmatch(generation) is None:
        raise RuntimeError("hosted release ledger generation is invalid")
    current_generation = int(generation)

    for stage, field in STAGE_RECEIPT_ID_FIELDS.items():
        receipt_id = state.get(field, "")
        if not receipt_id:
            continue
        receipt = _load_hosted_receipt(
            root,
            service=service,
            receipt_id=receipt_id,
        )
        committed_generation = receipt.get("committedGeneration")
        if (
            receipt.get("triggerStage") != stage
            or not isinstance(committed_generation, int)
            or isinstance(committed_generation, bool)
            or committed_generation <= 0
            or committed_generation > current_generation
            or not _history_receipt_matches_transaction(state, receipt)
            or receipt.get("artifactDigest") != state.get("artifact_digest")
            or receipt.get("imageDigest") != state.get("image_digest")
            or receipt.get("configDigest") != state.get("config_digest")
            or receipt.get("contractGraphDigest")
            != state.get("contract_graph_digest")
            or receipt.get("adapterDigest") != state.get("adapter_digest")
        ):
            raise RuntimeError(
                f"hosted release {stage} receipt is not candidate-transaction bound"
            )

    trigger_stage = state.get("trigger_stage", "")
    active_field = STAGE_RECEIPT_ID_FIELDS.get(trigger_stage)
    if active_field is None or state.get(active_field) != state.get("receipt_id"):
        raise RuntimeError(
            "hosted release ledger current receipt is not bound to trigger stage"
        )


def _next_stage_receipt_history(
    current: Mapping[str, str],
    payload: Mapping[str, Any],
    *,
    receipt_id: str,
) -> dict[str, str]:
    history = {field: "" for field in STAGE_RECEIPT_ID_FIELDS.values()}
    if current:
        current_pair = (
            current.get("from_candidate_digest"),
            current.get("to_candidate_digest"),
        )
        next_pair = (
            payload.get("fromCandidateDigest"),
            payload.get("toCandidateDigest"),
        )
        same_transaction = current_pair == next_pair
        rollback_transaction = (
            payload.get("decision") in {"rolled_back", "rollback_failed"}
            and current_pair == tuple(reversed(next_pair))
        )
        if same_transaction or rollback_transaction:
            for state_field, request_field in (
                ("artifact_digest", "artifactDigest"),
                ("image_digest", "imageDigest"),
                ("config_digest", "configDigest"),
                ("contract_graph_digest", "contractGraphDigest"),
                ("adapter_digest", "adapterDigest"),
            ):
                if current.get(state_field) != payload.get(request_field):
                    raise RuntimeError(
                        "hosted release candidate transaction evidence drifted"
                    )
            transport_bindings = (
                (
                    "from_release_evidence_ref",
                    "fromReleaseEvidenceRef",
                    "to_release_evidence_ref",
                    "toReleaseEvidenceRef",
                ),
                (
                    "from_image_transport_tag",
                    "fromImageTransportTag",
                    "to_image_transport_tag",
                    "toImageTransportTag",
                ),
            )
            for (
                current_from_field,
                request_from_field,
                current_to_field,
                request_to_field,
            ) in transport_bindings:
                if same_transaction:
                    transport_matches = (
                        current.get(current_from_field)
                        == payload.get(request_from_field)
                        and current.get(current_to_field)
                        == payload.get(request_to_field)
                    )
                else:
                    transport_matches = (
                        current.get(current_from_field)
                        == payload.get(request_to_field)
                        and current.get(current_to_field)
                        == payload.get(request_from_field)
                    )
                if not transport_matches:
                    raise RuntimeError(
                        "hosted release candidate transaction transport drifted"
                    )
            history = {
                field: current.get(field, "")
                for field in STAGE_RECEIPT_ID_FIELDS.values()
            }
    history[STAGE_RECEIPT_ID_FIELDS[payload["triggerStage"]]] = receipt_id
    return history


def _validated_readback(root: Path, service: str) -> dict[str, Any]:
    state = _load_state(root / f"{service}.state")
    if not state:
        return {
            "schema": READBACK_SCHEMA,
            "authority": AUTHORITY,
            "state": {},
            "receipt": {},
            "receiptRef": "",
        }
    receipt_id = state.get("receipt_id", "")
    receipt = _load_hosted_receipt(
        root,
        service=service,
        receipt_id=receipt_id,
    )
    if (
        state.get("authority") != AUTHORITY
        or state.get("service") != service
        or str(receipt.get("committedGeneration")) != state.get("generation")
        or receipt.get("artifactDigest") != state.get("artifact_digest")
        or receipt.get("fromCandidateDigest")
        != state.get("from_candidate_digest")
        or receipt.get("toCandidateDigest") != state.get("to_candidate_digest")
        or receipt.get("step") != state.get("step")
        or receipt.get("stage") != state.get("stage")
        or receipt.get("decision") != state.get("decision")
        or receipt.get("imageDigest") != state.get("image_digest")
        or receipt.get("configDigest") != state.get("config_digest")
        or receipt.get("contractGraphDigest") != state.get("contract_graph_digest")
        or receipt.get("adapterDigest") != state.get("adapter_digest")
        or receipt.get("rollbackOutcome") != state.get("rollback_outcome")
        or receipt.get("triggerStage") != state.get("trigger_stage")
        or receipt.get("fromReleaseEvidenceRef")
        != state.get("from_release_evidence_ref")
        or receipt.get("toReleaseEvidenceRef")
        != state.get("to_release_evidence_ref")
        or receipt.get("fromImageTransportTag")
        != state.get("from_image_transport_tag")
        or receipt.get("toImageTransportTag")
        != state.get("to_image_transport_tag")
        or receipt.get("lastGoodCandidateDigest")
        != state.get("last_good_candidate_digest")
        or receipt.get("verifiedAt") != state.get("updated_at")
    ):
        raise RuntimeError("hosted release receipt digest or ledger binding is invalid")
    _validate_stage_receipt_history(
        root,
        service=service,
        state=state,
    )
    return {
        "schema": READBACK_SCHEMA,
        "authority": AUTHORITY,
        "state": state,
        "receipt": receipt,
        "receiptRef": f"receipt:hosted:{receipt_id}",
    }
