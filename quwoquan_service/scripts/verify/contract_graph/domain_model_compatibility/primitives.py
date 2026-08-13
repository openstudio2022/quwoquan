"""共享常量、schema 标识、输入原语与不可信输入防御。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


REPORT_SCHEMA = "domain-model-compatibility-report"
WINDOW_SCHEMA = "client-contract-compatibility-window"
MIGRATION_SCHEMA = "quiesced-storage-migration-plan"
HOSTED_READBACK_SCHEMA = "prod-hosted-release-receipt-readback"
HOSTED_RECEIPT_SCHEMA = "prod-hosted-release-receipt"
HOSTED_AUTHORITY = "prod-hosted-service-plane"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RECEIPT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
MODEL_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
COMPATIBILITY_LEVELS = {"none": 0, "compatible": 1, "incompatible": 2}
NULLABLE_CONSTRAINTS = {"NULLABLE"}
REQUIRED_CONSTRAINTS = {"NOT_NULL", "NOT_BLANK", "REQUIRED"}


class InputError(ValueError):
    """Raised when a release input cannot be trusted."""


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise InputError(f"cannot read {path}: {error}") from error
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise InputError(f"invalid JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise InputError(f"{path} must contain one JSON object")
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _file_digest(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise InputError(f"cannot hash {path}: {error}") from error


def _digest_value(value: object, field_name: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise InputError(f"{field_name} must be canonical sha256:<hex>")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field_name} must be a non-empty string")
    return value.strip()


def _list(value: object, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise InputError(f"{field_name} must be an array")
    return value


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{field_name} must be an object")
    return value


def _receipt_id(receipt: Mapping[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receiptId", None)
    return hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
