"""Prepare the receipt and atomically activate one complete dependency bundle."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .dependency_bundle import (
    APP_DEPENDENCY_BUNDLE_ACTIVE_SCHEMA,
    APP_DEPENDENCY_BUNDLE_RECEIPT_SCHEMA,
    APP_DEPENDENCY_COMPONENTS,
)
from .pub_cache_capsule import _canonical_bytes, _digest_bytes

AtomicJsonWriter = Callable[[Path, dict[str, Any]], None]


def publish_dependency_bundle_activation(
    *,
    output_root: Path,
    active_root: Path,
    attempt_id: str,
    source_identity: Mapping[str, str],
    components: Mapping[str, Mapping[str, Any]],
    atomic_json: AtomicJsonWriter,
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    """Write PREPARED receipt first and active pointer last; never reverse them."""

    output = output_root.expanduser().absolute()
    active_base = active_root.expanduser().absolute()
    if not active_base.is_relative_to(output):
        raise ValueError("APP.DEPENDENCY.activation_root_unsafe")
    if not attempt_id or any(
        character not in "0123456789abcdef" for character in attempt_id
    ):
        raise ValueError("APP.DEPENDENCY.attempt_identity_invalid")
    if set(components) != set(APP_DEPENDENCY_COMPONENTS):
        raise ValueError("APP.DEPENDENCY.component_set_incomplete")
    required_source_fields = {
        "flutterVersion",
        "flutterCommandResolutionDigest",
        "productionPubResolutionInputDigest",
        "patrolPubResolutionInputDigest",
        "nativeResolutionInputDigest",
    }
    if set(source_identity) != required_source_fields or any(
        not str(source_identity.get(field) or "") for field in required_source_fields
    ):
        raise ValueError("APP.DEPENDENCY.source_identity_incomplete")
    component_payload = {
        name: dict(components[name]) for name in APP_DEPENDENCY_COMPONENTS
    }
    active_path = active_base / "active.json"
    receipt_path = (
        output
        / "env/repo/runs/app-dependency-sync"
        / attempt_id
        / "report.json"
    )
    receipt = {
        "schema": APP_DEPENDENCY_BUNDLE_RECEIPT_SCHEMA,
        "claim": "PREPARED_NOT_ACTIVE",
        "attemptId": attempt_id,
        "components": component_payload,
        "activationEvidence": {
            "requiredActiveRef": active_path.relative_to(output).as_posix(),
            "requiredAttemptId": attempt_id,
        },
    }
    active = {
        "schema": APP_DEPENDENCY_BUNDLE_ACTIVE_SCHEMA,
        "attemptId": attempt_id,
        **dict(source_identity),
        "components": component_payload,
        "receiptRef": receipt_path.relative_to(output).as_posix(),
        "receiptDigest": _digest_bytes(_canonical_bytes(receipt)),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=False)
    atomic_json(receipt_path, receipt)
    active_base.mkdir(parents=True, exist_ok=True)
    atomic_json(active_path, active)
    return receipt, active, receipt_path, active_path
