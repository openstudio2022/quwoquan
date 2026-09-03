"""Predecessor-chain validation for environment acceptance facts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import (
    _PREDECESSOR_KEYS,
    PREDECESSOR,
)


def validate_predecessor_acceptance(
    *,
    environment: str,
    predecessor_acceptance: Mapping[str, Any] | None,
    evidence_root: Path,
    release_id: str,
    release_digest: str,
    digest: Callable[..., str],
    relative_ref: Callable[..., str],
    secure_read: Callable[..., bytes],
    exact_byte_digest: Callable[[bytes | Path], str],
    decode_json: Callable[..., dict[str, Any]],
    validate_fact: Callable[..., dict[str, Any]],
    block: Callable[[str, str], None],
    error_type: type[ValueError],
    invalid_code: str,
    predecessor_blocked_code: str,
) -> dict[str, str] | None:
    expected = PREDECESSOR.get(environment)
    if expected is None:
        if environment != "alpha":
            block(invalid_code, "environment is unknown")
        if predecessor_acceptance is not None:
            block(
                predecessor_blocked_code, "alpha must not provide predecessor acceptance"
            )
        return None
    if (
        not isinstance(predecessor_acceptance, Mapping)
        or set(predecessor_acceptance) != _PREDECESSOR_KEYS
    ):
        block(
            predecessor_blocked_code, f"{environment} requires exact {expected} predecessor"
        )
    if predecessor_acceptance.get("environment") != expected:
        block(
            predecessor_blocked_code,
            f"{environment} predecessor must be exactly {expected}",
        )
    normalized = {
        "environment": expected,
        "factId": digest(
            predecessor_acceptance.get("factId"), field="predecessorAcceptance.factId"
        ),
        "ref": relative_ref(
            predecessor_acceptance.get("ref"), field="predecessorAcceptance.ref"
        ),
        "digest": digest(
            predecessor_acceptance.get("digest"), field="predecessorAcceptance.digest"
        ),
    }
    raw = secure_read(evidence_root, normalized["ref"], label="predecessorAcceptance")
    if exact_byte_digest(raw) != normalized["digest"]:
        block(predecessor_blocked_code, "predecessor acceptance exact bytes drifted")
    previous = decode_json(raw, label="predecessorAcceptance")
    previous_profiles = [
        {"platform": item.get("platform"), "deviceProfile": item.get("deviceProfile")}
        for item in previous.get("targetBindingRefs", [])
        if isinstance(item, Mapping)
    ]
    try:
        validate_fact(
            previous,
            evidence_root=evidence_root,
            required_target_profiles=previous_profiles,
            verify_references=True,
        )
    except error_type as exc:
        raise error_type(
            predecessor_blocked_code, f"predecessor acceptance is invalid: {exc}"
        ) from exc
    if (
        previous.get("acceptanceProfile") != "environment_promotion"
        or previous.get("environment") != expected
        or previous.get("releaseId") != release_id
        or previous.get("releaseDigest") != release_digest
        or previous.get("factId") != normalized["factId"]
    ):
        block(predecessor_blocked_code, "predecessor acceptance identity drifted")
    return normalized


__all__ = ["validate_predecessor_acceptance"]
