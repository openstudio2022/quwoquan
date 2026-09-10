"""新包仅 exact replay；不升级、补写或双读历史包。"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import ObjectTransactionError, _read_json
from core.schema import assert_valid


def reuse_existing_post_package(*, package_root: Path, transaction_id: str, execution_id: str,
                                input_payload_digest: str, canonical_ref: str,
                                creator_binding: Mapping[str, Any], output_root: Path) -> dict[str, Any]:
    existing = _read_json(package_root / "object_transaction_package.json")
    assert_valid(existing, "release", "object_transaction_package")
    manifest = _read_json(package_root / "object/manifest.json")
    if (existing.get("transactionId") != transaction_id or existing.get("executionId") != execution_id
            or existing.get("inputPayloadDigest") != input_payload_digest
            or existing["target"]["objectRef"] != canonical_ref
            or any(manifest.get(key) != value for key, value in creator_binding.items())):
        raise ObjectTransactionError("DATA.POOL.IDEMPOTENCY_CONFLICT: frozen package input drift")
    return existing
