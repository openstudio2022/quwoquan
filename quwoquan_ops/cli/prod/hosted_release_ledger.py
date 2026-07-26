#!/usr/bin/env python3
"""Hosted service-plane authority for immutable production release receipts.

The script is intentionally stdlib-only so ``sync_prod_plane_stack.sh`` can
pipe this exact source to ``python3 -`` over the service-plane SSH boundary.
The hosted filesystem owns the CAS generation and immutable receipt; local
``.qwq_output`` files are readback copies only.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Mapping


AUTHORITY = "prod-hosted-service-plane"
REQUEST_SCHEMA = "prod-hosted-release-transition-request"
RECEIPT_SCHEMA = "prod-hosted-release-receipt"
READBACK_SCHEMA = "prod-hosted-release-readback"
RECEIPT_READBACK_SCHEMA = "prod-hosted-release-receipt-readback"
STATE_SCHEMA = "prod-release-ledger"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SERVICE_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{0,255}$")
STAGES = {"gray-initial", "carry-on", "full"}
DECISIONS = {"continue", "pause", "rolled_back", "rollback_failed"}
ROLLBACK_OUTCOMES = {"not_triggered", "rolled_back", "rollback_failed"}


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _receipt_id(receipt: Mapping[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receiptId", None)
    return hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def _require_safe_string(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if SAFE_VALUE_RE.fullmatch(text) is None:
        raise ValueError(f"{field} is missing or unsafe")
    return text


def _validate_request(value: object) -> dict[str, Any]:
    required = {
        "schema",
        "service",
        "fromImage",
        "toImage",
        "fromConfig",
        "toConfig",
        "step",
        "stage",
        "decision",
        "rollbackOutcome",
        "manifestDigest",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "expectedGeneration",
        "sloReadback",
        "postChecks",
        "lastGoodTarget",
        "verifiedAt",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("hosted release transition request has an invalid shape")
    if value.get("schema") != REQUEST_SCHEMA:
        raise ValueError("hosted release transition request schema is invalid")
    service = str(value.get("service") or "")
    if SERVICE_RE.fullmatch(service) is None:
        raise ValueError("service is invalid")
    for field in ("fromImage", "toImage", "fromConfig", "toConfig", "step"):
        _require_safe_string(value.get(field), field=field)
    if value.get("stage") not in STAGES:
        raise ValueError("stage is invalid")
    if value.get("decision") not in DECISIONS:
        raise ValueError("decision is invalid")
    if value.get("rollbackOutcome") not in ROLLBACK_OUTCOMES:
        raise ValueError("rollbackOutcome is invalid")
    for field in (
        "manifestDigest",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
    ):
        if not isinstance(value.get(field), str) or SHA256_RE.fullmatch(value[field]) is None:
            raise ValueError(f"{field} must be sha256")
    generation = value.get("expectedGeneration")
    if not isinstance(generation, int) or generation < 0:
        raise ValueError("expectedGeneration must be a non-negative integer")
    if not isinstance(value.get("sloReadback"), dict):
        raise ValueError("sloReadback must be an object")
    checks = value.get("postChecks")
    if not isinstance(checks, list) or not all(
        isinstance(item, dict)
        and set(item) == {"name", "status", "receiptDigest"}
        and _require_safe_string(item.get("name"), field="postChecks.name")
        and item.get("status") in {"passed", "failed"}
        and isinstance(item.get("receiptDigest"), str)
        and SHA256_RE.fullmatch(item["receiptDigest"]) is not None
        for item in checks
    ):
        raise ValueError("postChecks must contain passed digest-bound checks")
    last_good = value.get("lastGoodTarget")
    if not isinstance(last_good, dict) or set(last_good) != {"image", "config"}:
        raise ValueError("lastGoodTarget has an invalid shape")
    _require_safe_string(last_good.get("image"), field="lastGoodTarget.image")
    _require_safe_string(last_good.get("config"), field="lastGoodTarget.config")
    _require_safe_string(value.get("verifiedAt"), field="verifiedAt")
    return dict(value)


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
        payload[key] = value
    if payload.get("schema") != STATE_SCHEMA:
        raise RuntimeError("hosted release ledger state schema is invalid")
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
    if re.fullmatch(r"[0-9a-f]{64}", receipt_id) is None:
        raise RuntimeError("hosted release ledger receipt id is invalid")
    receipt_path = root / "receipts" / f"{receipt_id}.json"
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise RuntimeError("hosted release ledger receipt is missing")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("authority") != AUTHORITY
        or receipt.get("service") != service
        or receipt.get("receiptId") != receipt_id
        or _receipt_id(receipt) != receipt_id
        or str(receipt.get("committedGeneration")) != state.get("generation")
        or receipt.get("manifestDigest") != state.get("manifest_digest")
        or receipt.get("imageDigest") != state.get("image_digest")
        or receipt.get("configDigest") != state.get("config_digest")
        or receipt.get("contractGraphDigest") != state.get("contract_graph_digest")
        or receipt.get("adapterDigest") != state.get("adapter_digest")
        or receipt.get("rollbackOutcome") != state.get("rollback_outcome")
    ):
        raise RuntimeError("hosted release receipt digest or ledger binding is invalid")
    return {
        "schema": READBACK_SCHEMA,
        "authority": AUTHORITY,
        "state": state,
        "receipt": receipt,
        "receiptRef": f"receipt:hosted:{receipt_id}",
    }


def commit(root: Path, request: object) -> dict[str, Any]:
    payload = _validate_request(request)
    service = payload["service"]
    with _ledger_lock(root):
        state_path = root / f"{service}.state"
        current = _load_state(state_path)
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
            "fromImage": payload["fromImage"],
            "toImage": payload["toImage"],
            "fromConfig": payload["fromConfig"],
            "toConfig": payload["toConfig"],
            "step": payload["step"],
            "stage": payload["stage"],
            "decision": payload["decision"],
            "rollbackOutcome": payload["rollbackOutcome"],
            "manifestDigest": payload["manifestDigest"],
            "imageDigest": payload["imageDigest"],
            "configDigest": payload["configDigest"],
            "contractGraphDigest": payload["contractGraphDigest"],
            "adapterDigest": payload["adapterDigest"],
            "expectedGeneration": payload["expectedGeneration"],
            "committedGeneration": payload["expectedGeneration"] + 1,
            "sloReadback": payload["sloReadback"],
            "postChecks": payload["postChecks"],
            "lastGoodTarget": payload["lastGoodTarget"],
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
            if receipt_path.read_bytes() != receipt_bytes:
                raise RuntimeError("hosted release receipt collision")
        else:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            with receipt_path.open("xb") as handle:
                handle.write(receipt_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        state = {
            "schema": STATE_SCHEMA,
            "authority": AUTHORITY,
            "service": service,
            "from_image": payload["fromImage"],
            "to_image": payload["toImage"],
            "from_config": payload["fromConfig"],
            "to_config": payload["toConfig"],
            "step": payload["step"],
            "stage": payload["stage"],
            "decision": payload["decision"],
            "rollback_outcome": payload["rollbackOutcome"],
            "manifest_digest": payload["manifestDigest"],
            "image_digest": payload["imageDigest"],
            "config_digest": payload["configDigest"],
            "contract_graph_digest": payload["contractGraphDigest"],
            "adapter_digest": payload["adapterDigest"],
            "last_good_image": payload["lastGoodTarget"]["image"],
            "last_good_config": payload["lastGoodTarget"]["config"],
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
    if re.fullmatch(r"[0-9a-f]{64}", receipt_id) is None:
        raise ValueError("receipt id is invalid")
    with _ledger_lock(root):
        path = root / "receipts" / f"{receipt_id}.json"
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("hosted release receipt is missing")
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(receipt, dict)
            or receipt.get("schema") != RECEIPT_SCHEMA
            or receipt.get("authority") != AUTHORITY
            or receipt.get("service") != service
            or receipt.get("receiptId") != receipt_id
            or _receipt_id(receipt) != receipt_id
        ):
            raise RuntimeError("hosted release receipt digest or identity is invalid")
        return {
            "schema": RECEIPT_READBACK_SCHEMA,
            "authority": AUTHORITY,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt_id}",
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--action", choices=("fetch", "commit", "receipt"), required=True)
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
        else:
            raw = base64.b64decode(args.request_base64, validate=True)
            request = json.loads(raw.decode("utf-8"))
            result = commit(root, request)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
