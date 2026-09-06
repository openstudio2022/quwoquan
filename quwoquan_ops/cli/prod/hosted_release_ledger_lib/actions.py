"""commit/fetch 五个动作与 CLI main（stdlib-only）。"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from .contract import (
    AUTHORITY,
    RECEIPT_ID_RE,
    RECEIPT_READBACK_SCHEMA,
    RECEIPT_SCHEMA,
    SERVICE_RE,
    SOAK_RECEIPT_READBACK_SCHEMA,
    SOAK_RECEIPT_SCHEMA,
    SOAK_REQUEST_FIELDS,
    STATE_SCHEMA,
    _receipt_id,
    _require_timestamp,
)
from .ledger_store import (
    _atomic_write,
    _ledger_lock,
    _load_hosted_receipt,
    _load_hosted_soak_receipt,
    _next_stage_receipt_history,
    _validated_readback,
)
from .request_validation import _validate_request, _validate_soak_request


def commit(root: Path, request: object) -> dict[str, Any]:
    payload = _validate_request(request)
    service = payload["service"]
    with _ledger_lock(root):
        state_path = root / f"{service}.state"
        current = _validated_readback(root, service)["state"]
        current_generation = int(current.get("generation") or 0)
        if current_generation != payload["expectedGeneration"]:
            raise RuntimeError(
                "hosted release ledger CAS conflict: "
                f"expected {payload['expectedGeneration']}, found {current_generation}"
            )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "authority": AUTHORITY,
            "service": service,
            "fromCandidateDigest": payload["fromCandidateDigest"],
            "toCandidateDigest": payload["toCandidateDigest"],
            "step": payload["step"],
            "stage": payload["stage"],
            "triggerStage": payload["triggerStage"],
            "fromServiceFactoryOciDigest": payload["fromServiceFactoryOciDigest"],
            "toServiceFactoryOciDigest": payload["toServiceFactoryOciDigest"],
            "fromAppFactoryOciDigest": payload["fromAppFactoryOciDigest"],
            "toAppFactoryOciDigest": payload["toAppFactoryOciDigest"],
            "decision": payload["decision"],
            "rollbackOutcome": payload["rollbackOutcome"],
            "rollbackEvidence": payload["rollbackEvidence"],
            "candidateMaterialId": payload["candidateMaterialId"],
            "prodActivationAdmissionRef": payload["prodActivationAdmissionRef"],
            "prodActivationAdmissionOciDigest": payload["prodActivationAdmissionOciDigest"],
            "prodActivationAdmissionPayloadDigest": payload["prodActivationAdmissionPayloadDigest"],
            "prodActivationAdmissionId": payload["prodActivationAdmissionId"],
            "candidateMaterialManifestRef": payload["candidateMaterialManifestRef"],
            "candidateMaterialManifestOciDigest": payload["candidateMaterialManifestOciDigest"],
            "candidateMaterialManifestPayloadDigest": payload["candidateMaterialManifestPayloadDigest"],
            "previousReleasedRef": payload["previousReleasedRef"],
            "previousReleasedOciDigest": payload["previousReleasedOciDigest"],
            "previousReleasedPayloadDigest": payload["previousReleasedPayloadDigest"],
            "previousReleasedId": payload["previousReleasedId"],
            "imageDigest": payload["imageDigest"],
            "configDigest": payload["configDigest"],
            "contractGraphDigest": payload["contractGraphDigest"],
            "adapterDigest": payload["adapterDigest"],
            "expectedGeneration": payload["expectedGeneration"],
            "committedGeneration": payload["expectedGeneration"] + 1,
            "sloReadback": payload["sloReadback"],
            "postChecks": payload["postChecks"],
            "lastGoodCandidateDigest": payload["lastGoodCandidateDigest"],
            "verifiedAt": payload["verifiedAt"],
        }
        receipt_id = _receipt_id(receipt)
        receipt["receiptId"] = receipt_id
        receipt_path = root / "receipts" / f"{receipt_id}.json"
        receipt_bytes = json.dumps(
            receipt,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8") + b"\n"
        if receipt_path.exists():
            if not receipt_path.is_file() or receipt_path.is_symlink():
                raise RuntimeError("hosted release receipt path is not a regular file")
            if receipt_path.read_bytes() != receipt_bytes:
                raise RuntimeError("hosted release receipt collision")
        else:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            with receipt_path.open("xb") as handle:
                handle.write(receipt_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        stage_receipt_history = _next_stage_receipt_history(
            current,
            payload,
            receipt_id=receipt_id,
        )
        state = {
            "schema": STATE_SCHEMA,
            "authority": AUTHORITY,
            "service": service,
            "from_candidate_digest": payload["fromCandidateDigest"],
            "to_candidate_digest": payload["toCandidateDigest"],
            "step": payload["step"],
            "stage": payload["stage"],
            "trigger_stage": payload["triggerStage"],
            "from_service_factory_oci_digest": payload["fromServiceFactoryOciDigest"],
            "to_service_factory_oci_digest": payload["toServiceFactoryOciDigest"],
            "from_app_factory_oci_digest": payload["fromAppFactoryOciDigest"],
            "to_app_factory_oci_digest": payload["toAppFactoryOciDigest"],
            "decision": payload["decision"],
            "rollback_outcome": payload["rollbackOutcome"],
            "candidate_material_id": payload["candidateMaterialId"],
            "prod_activation_admission_ref": payload["prodActivationAdmissionRef"],
            "prod_activation_admission_oci_digest": payload["prodActivationAdmissionOciDigest"],
            "prod_activation_admission_payload_digest": payload["prodActivationAdmissionPayloadDigest"],
            "prod_activation_admission_id": payload["prodActivationAdmissionId"],
            "candidate_material_manifest_ref": payload["candidateMaterialManifestRef"],
            "candidate_material_manifest_oci_digest": payload["candidateMaterialManifestOciDigest"],
            "candidate_material_manifest_payload_digest": payload["candidateMaterialManifestPayloadDigest"],
            "previous_released_ref": payload["previousReleasedRef"],
            "previous_released_oci_digest": payload["previousReleasedOciDigest"],
            "previous_released_payload_digest": payload["previousReleasedPayloadDigest"],
            "previous_released_id": payload["previousReleasedId"],
            "image_digest": payload["imageDigest"],
            "config_digest": payload["configDigest"],
            "contract_graph_digest": payload["contractGraphDigest"],
            "adapter_digest": payload["adapterDigest"],
            "last_good_candidate_digest": payload["lastGoodCandidateDigest"],
            **stage_receipt_history,
            "generation": str(payload["expectedGeneration"] + 1),
            "receipt_id": receipt_id,
            "updated_at": payload["verifiedAt"],
        }
        state_bytes = (
            "\n".join(f"{key}={value}" for key, value in state.items()) + "\n"
        ).encode("utf-8")
        _atomic_write(state_path, state_bytes)
        return _validated_readback(root, service)


def fetch(root: Path, service: str) -> dict[str, Any]:
    if SERVICE_RE.fullmatch(service) is None:
        raise ValueError("service is invalid")
    with _ledger_lock(root):
        return _validated_readback(root, service)


def fetch_receipt(root: Path, service: str, receipt_id: str) -> dict[str, Any]:
    if SERVICE_RE.fullmatch(service) is None:
        raise ValueError("service is invalid")
    if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise ValueError("receipt id is invalid")
    with _ledger_lock(root):
        receipt = _load_hosted_receipt(
            root,
            service=service,
            receipt_id=receipt_id,
        )
        return {
            "schema": RECEIPT_READBACK_SCHEMA,
            "authority": AUTHORITY,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt_id}",
        }


def commit_soak(root: Path, request: object) -> dict[str, Any]:
    payload = _validate_soak_request(request)
    service = payload["service"]
    now = dt.datetime.now(dt.timezone.utc)
    with _ledger_lock(root):
        readback = _validated_readback(root, service)
        state = readback["state"]
        if (
            state.get("trigger_stage") != "100"
            or state.get("stage") != "100"
            or state.get("decision") != "continue"
            or state.get("rollback_outcome") != "not_triggered"
        ):
            raise RuntimeError(
                "GATE_BLOCK: prod soak requires current successful full rollout state"
            )
        full_receipt_id = state.get("percent_100_receipt_id", "")
        if full_receipt_id != payload["fullRolloutReceiptId"]:
            raise RuntimeError("GATE_BLOCK: prod soak full rollout receipt drift")
        full_receipt = _load_hosted_receipt(
            root,
            service=service,
            receipt_id=full_receipt_id,
        )
        expected_bindings = {
            "candidateId": full_receipt["toCandidateDigest"],
            "candidateMaterialId": full_receipt["candidateMaterialId"],
            "prodActivationAdmissionRef": full_receipt["prodActivationAdmissionRef"],
            "prodActivationAdmissionOciDigest": full_receipt["prodActivationAdmissionOciDigest"],
            "prodActivationAdmissionPayloadDigest": full_receipt["prodActivationAdmissionPayloadDigest"],
            "prodActivationAdmissionId": full_receipt["prodActivationAdmissionId"],
            "candidateMaterialManifestRef": full_receipt["candidateMaterialManifestRef"],
            "candidateMaterialManifestOciDigest": full_receipt["candidateMaterialManifestOciDigest"],
            "candidateMaterialManifestPayloadDigest": full_receipt["candidateMaterialManifestPayloadDigest"],
            "serviceFactoryOciDigest": full_receipt["toServiceFactoryOciDigest"],
            "appFactoryOciDigest": full_receipt["toAppFactoryOciDigest"],
            "rolloutConfigDigest": full_receipt["configDigest"],
            "contractGraphDigest": full_receipt["contractGraphDigest"],
        }
        for field, expected in expected_bindings.items():
            if payload[field] != expected:
                raise RuntimeError(f"GATE_BLOCK: prod soak {field} drift")

        started_at = _require_timestamp(
            full_receipt["verifiedAt"], field="fullRolloutReceipt.verifiedAt"
        )
        duration = int((now - started_at).total_seconds())
        if duration < payload["requiredSoakSeconds"]:
            raise RuntimeError(
                "GATE_BLOCK: authoritative prod soak window is incomplete"
            )
        for name in ("slo", "alerts", "health"):
            observed_at = _require_timestamp(
                payload[name]["observedAt"], field=f"{name}.observedAt"
            )
            if observed_at < started_at or observed_at > now:
                raise RuntimeError(
                    f"GATE_BLOCK: {name} observation is outside authoritative soak window"
                )
        for index, credential in enumerate(payload["credentials"]):
            verified_at = _require_timestamp(
                credential["verifiedAt"], field=f"credentials[{index}].verifiedAt"
            )
            expires_at = _require_timestamp(
                credential["expiresAt"], field=f"credentials[{index}].expiresAt"
            )
            if verified_at < started_at or verified_at > now:
                raise RuntimeError(
                    "GATE_BLOCK: credential verification is outside soak window"
                )
            if expires_at <= now:
                raise RuntimeError("GATE_BLOCK: prod credential is expired")
        approval_at = _require_timestamp(
            payload["approval"]["verifiedAt"], field="approval.verifiedAt"
        )
        if approval_at > now:
            raise RuntimeError("GATE_BLOCK: prod approval verification is future-dated")

        timestamp = now.isoformat().replace("+00:00", "Z")
        receipt = {
            "schema": SOAK_RECEIPT_SCHEMA,
            "authority": AUTHORITY,
            **{field: payload[field] for field in SOAK_REQUEST_FIELDS if field != "schema"},
            "soakStartedAt": started_at.astimezone(dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "soakEndedAt": timestamp,
            "soakDurationSeconds": duration,
            "verifiedAt": timestamp,
        }
        receipt_id = _receipt_id(receipt)
        receipt["receiptId"] = receipt_id
        receipt_path = root / "soak-receipts" / f"{receipt_id}.json"
        receipt_bytes = json.dumps(
            receipt,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8") + b"\n"
        if receipt_path.exists():
            if (
                not receipt_path.is_file()
                or receipt_path.is_symlink()
                or receipt_path.read_bytes() != receipt_bytes
            ):
                raise RuntimeError("hosted prod soak receipt collision")
        else:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            with receipt_path.open("xb") as handle:
                handle.write(receipt_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        verified = _load_hosted_soak_receipt(
            root,
            service=service,
            receipt_id=receipt_id,
        )
        return {
            "schema": SOAK_RECEIPT_READBACK_SCHEMA,
            "authority": AUTHORITY,
            "receipt": verified,
            "receiptRef": f"receipt:hosted-soak:{receipt_id}",
        }


def fetch_soak_receipt(
    root: Path,
    service: str,
    receipt_id: str,
) -> dict[str, Any]:
    if SERVICE_RE.fullmatch(service) is None:
        raise ValueError("service is invalid")
    if RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise ValueError("soak receipt id is invalid")
    with _ledger_lock(root):
        receipt = _load_hosted_soak_receipt(
            root,
            service=service,
            receipt_id=receipt_id,
        )
        return {
            "schema": SOAK_RECEIPT_READBACK_SCHEMA,
            "authority": AUTHORITY,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted-soak:{receipt_id}",
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument(
        "--action",
        choices=("fetch", "commit", "receipt", "soak-commit", "soak-receipt"),
        required=True,
    )
    parser.add_argument("--service", default="")
    parser.add_argument("--receipt-id", default="")
    parser.add_argument("--request-base64", default="")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        root = Path(args.root).expanduser()
        if not root.is_absolute():
            raise ValueError("hosted release ledger root must be absolute")
        if args.action == "fetch":
            result = fetch(root, args.service)
        elif args.action == "receipt":
            result = fetch_receipt(root, args.service, args.receipt_id)
        elif args.action == "soak-receipt":
            result = fetch_soak_receipt(root, args.service, args.receipt_id)
        else:
            raw = base64.b64decode(args.request_base64, validate=True)
            request = json.loads(raw.decode("utf-8"))
            result = (
                commit_soak(root, request)
                if args.action == "soak-commit"
                else commit(root, request)
            )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0
