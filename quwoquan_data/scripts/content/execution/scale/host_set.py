"""Create-once governed worker-host admission for distributed scale runs."""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

from content.execution.preflight.receipt import validate_semantic_preflight_receipt

HOST_SET_INVALID = "DATA.SCALE.HOST_SET_INVALID"
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


class GovernedHostSetError(RuntimeError):
    """Typed rejection of an unsafe or drifting worker host set."""

    def __init__(self, message: str) -> None:
        self.code = HOST_SET_INVALID
        super().__init__(f"{HOST_SET_INVALID}: {message}")


def _invalid(message: str) -> GovernedHostSetError:
    return GovernedHostSetError(message)


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _required_digest(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if not _DIGEST_RE.fullmatch(text):
        raise _invalid(f"{label} must be a canonical sha256 digest")
    return text


def _host_document(
    raw: Mapping[str, Any],
    *,
    observed_now: datetime,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
) -> dict[str, Any]:
    host_scope_id = str(raw.get("hostScopeId") or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", host_scope_id):
        raise _invalid("hostScopeId must be a stable kebab-case scope")
    receipt = raw.get("preflightReceipt")
    if not isinstance(receipt, Mapping):
        raise _invalid(f"{host_scope_id} preflightReceipt is required")
    try:
        validate_semantic_preflight_receipt(
            receipt,
            require_semantic_execution_ready=True,
            now=observed_now,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid(f"{host_scope_id} fresh preflight is invalid: {exc}") from exc
    evidence = receipt.get("evidence")
    capacity = evidence.get("capacitySoak") if isinstance(evidence, Mapping) else None
    effective = capacity.get("effectiveConcurrency") if isinstance(capacity, Mapping) else None
    if isinstance(effective, bool) or not isinstance(effective, int) or effective < 1:
        raise _invalid(f"{host_scope_id} effectiveConcurrency is invalid")
    capsule = raw.get("sourceCapsule")
    if not isinstance(capsule, Mapping):
        raise _invalid(f"{host_scope_id} sourceCapsule receipt is required")
    try:
        assert_valid(
            dict(capsule),
            "execution",
            "governed_host_source_capsule",
            label=f"{host_scope_id} governed host source capsule",
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid(f"{host_scope_id} sourceCapsule is invalid: {exc}") from exc
    capsule_stable = {
        key: value for key, value in capsule.items() if key != "capsuleDigest"
    }
    if capsule.get("capsuleDigest") != _digest(capsule_stable):
        raise _invalid(f"{host_scope_id} sourceCapsule digest drift")
    if (
        capsule.get("sourceRevision") != source_revision
        or (capsule.get("sourceDigest") or {}).get("digest") != source_digest
        or capsule.get("entityCatalogDigest") != entity_catalog_digest
    ):
        raise _invalid(f"{host_scope_id} sourceCapsule source identity drift")
    executor = capsule["executorBundle"]
    return {
        "hostScopeId": host_scope_id,
        "preflight": {
            "receiptId": _required_digest(
                receipt.get("receiptId"), label=f"{host_scope_id}.receiptId"
            ),
            "selectionDigest": _required_digest(
                receipt.get("selectionDigest"),
                label=f"{host_scope_id}.selectionDigest",
            ),
            "provider": receipt.get("provider"),
            "model": receipt.get("model"),
            "runtimeProfileDigest": _required_digest(
                receipt.get("runtimeProfileDigest"),
                label=f"{host_scope_id}.runtimeProfileDigest",
            ),
            "validUntil": receipt.get("validUntil"),
            "effectiveConcurrency": effective,
        },
        "executorBundleRef": executor["ref"],
        "executorBundleDigest": executor["digest"],
        "executorBundleFileSha256": executor["fileSha256"],
        "sourceCapsuleId": capsule["capsuleId"],
        "sourceCapsuleDigest": _required_digest(
            capsule.get("capsuleDigest"),
            label=f"{host_scope_id}.sourceCapsuleDigest",
        ),
        "mongoTransportDigest": _required_digest(
            raw.get("mongoTransportDigest"),
            label=f"{host_scope_id}.mongoTransportDigest",
        ),
        "redisTransportDigest": _required_digest(
            raw.get("redisTransportDigest"),
            label=f"{host_scope_id}.redisTransportDigest",
        ),
    }


def build_governed_host_set(
    *,
    host_set_id: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    hosts: Sequence[Mapping[str, Any]],
    generation: int = 1,
    fencing_token: str | None = None,
    previous_host_set: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Admit distinct hosts only when all immutable runtime inputs agree."""

    normalized_id = str(host_set_id or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,95}", normalized_id):
        raise _invalid("hostSetId must be a stable kebab-case identity")
    if not hosts:
        raise _invalid("at least one worker host is required")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise _invalid("generation must be a positive integer")
    previous_digest: str | None = None
    if generation == 1:
        if previous_host_set is not None:
            raise _invalid("generation 1 cannot bind a previous host set")
    else:
        if not isinstance(previous_host_set, Mapping):
            raise _invalid("replacement generation requires previous_host_set")
        assert_valid(
            dict(previous_host_set),
            "execution",
            "governed_worker_host_set",
            label="previous governed worker host set",
        )
        if (
            previous_host_set.get("hostSetId") != normalized_id
            or previous_host_set.get("generation") != generation - 1
        ):
            raise _invalid("previous host set identity/generation drift")
        previous_digest = _required_digest(
            previous_host_set.get("hostSetDigest"), label="previousHostSetDigest"
        )
    observed_now = now or datetime.now(timezone.utc)
    rows = sorted(
        (
            _host_document(
                row,
                observed_now=observed_now,
                source_revision=source_revision,
                source_digest=source_digest,
                entity_catalog_digest=entity_catalog_digest,
            )
            for row in hosts
        ),
        key=lambda row: row["hostScopeId"],
    )
    scope_ids = [str(row["hostScopeId"]) for row in rows]
    if len(set(scope_ids)) != len(scope_ids):
        raise _invalid("hostScopeId values must be distinct")
    receipt_ids = [str(row["preflight"]["receiptId"]) for row in rows]
    if len(set(receipt_ids)) != len(receipt_ids):
        raise _invalid("each host requires its own fresh preflight receipt")
    for field in (
        "executorBundleDigest",
        "executorBundleRef",
        "executorBundleFileSha256",
        "sourceCapsuleId",
        "sourceCapsuleDigest",
        "mongoTransportDigest",
        "redisTransportDigest",
    ):
        if len({row[field] for row in rows}) != 1:
            raise _invalid(f"all hosts must share one {field}")
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.governed_worker_host_set",
        "hostSetId": normalized_id,
        "generation": generation,
        "previousHostSetDigest": previous_digest,
        "fencingToken": _required_digest(
            fencing_token or ("sha256:" + hashlib.sha256(
                f"{normalized_id}:{generation}".encode("utf-8")
            ).hexdigest()),
            label="fencingToken",
        ),
        "sourceRevision": _required_digest(source_revision, label="sourceRevision"),
        "sourceDigest": _required_digest(source_digest, label="sourceDigest"),
        "entityCatalogDigest": _required_digest(
            entity_catalog_digest, label="entityCatalogDigest"
        ),
        "transportBinding": {
            "mongoTransportDigest": rows[0]["mongoTransportDigest"],
            "redisTransportDigest": rows[0]["redisTransportDigest"],
        },
        "hosts": rows,
        "availableSlots": sum(
            int(row["preflight"]["effectiveConcurrency"]) for row in rows
        ),
    }
    if previous_host_set is not None:
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
            if previous_host_set.get(field) != stable[field]:
                raise _invalid(f"replacement host set {field} drift")
        prior_hosts = previous_host_set.get("hosts") or []
        for field in (
            "executorBundleDigest",
            "executorBundleRef",
            "executorBundleFileSha256",
            "sourceCapsuleId",
            "sourceCapsuleDigest",
            "mongoTransportDigest",
            "redisTransportDigest",
        ):
            if not prior_hosts or prior_hosts[0].get(field) != rows[0][field]:
                raise _invalid(f"replacement host set {field} drift")
    document = {**stable, "hostSetDigest": _digest(stable)}
    assert_valid(
        document,
        "execution",
        "governed_worker_host_set",
        label=f"governed worker host set:{normalized_id}",
    )
    return document


def write_governed_host_set_create_once(
    path: Path, document: Mapping[str, Any]
) -> dict[str, Any]:
    """Atomically create one host set, accepting only byte-equivalent replay."""

    payload = dict(document)
    assert_valid(
        payload,
        "execution",
        "governed_worker_host_set",
        label="governed worker host set",
    )
    stable = {key: value for key, value in payload.items() if key != "hostSetDigest"}
    if payload.get("hostSetDigest") != _digest(stable):
        raise _invalid("hostSetDigest drift")
    body = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = read_json(path)
        if existing != payload:
            raise _invalid("create-once host set collision") from None
        return payload
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return payload


__all__ = [
    "HOST_SET_INVALID",
    "GovernedHostSetError",
    "build_governed_host_set",
    "write_governed_host_set_create_once",
]
