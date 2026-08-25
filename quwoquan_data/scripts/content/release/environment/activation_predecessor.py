"""Validate the previous environment's independent milestone activation receipt."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.environment.activation_envelope import (
    EnvironmentActivationEnvelopeError,
    document_digest,
    file_digest,
)
from core.schema import assert_valid
from verify.release_publishability import evaluate_release_readiness_receipt

_PREVIOUS_ENVIRONMENT = {
    "alpha": None,
    "beta": "alpha",
    "gamma": "beta",
    "prod": "gamma",
}


def _checksum(value: Mapping[str, Any]) -> str:
    stable = {key: item for key, item in value.items() if key != "verificationChecksum"}
    encoded = json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EnvironmentActivationEnvelopeError(
            f"previous environment readiness is unreadable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise EnvironmentActivationEnvelopeError(
            "previous environment readiness must be an object"
        )
    return value


def load_previous_environment_activation(
    *,
    environment: str,
    readiness_path: Path | None,
    release_id: str,
    manifest_digest: str,
    source_identity_set_digest: str,
    output_root: Path,
) -> dict[str, str] | None:
    """Freeze the exact preceding Research readiness receipt for one milestone."""

    if environment not in _PREVIOUS_ENVIRONMENT:
        raise EnvironmentActivationEnvelopeError(
            f"unsupported activation environment: {environment!r}"
        )
    previous = _PREVIOUS_ENVIRONMENT[environment]
    if previous is None:
        if readiness_path is not None:
            raise EnvironmentActivationEnvelopeError(
                "alpha milestone activation must not bind a predecessor"
            )
        return None
    if readiness_path is None:
        raise EnvironmentActivationEnvelopeError(
            f"{environment} milestone activation requires {previous} readiness"
        )
    expected_parts = (
        "env",
        previous,
        "runs",
        "data-release",
        release_id,
    )
    try:
        relative = readiness_path.relative_to(output_root)
        readiness_path.resolve().relative_to(output_root.resolve())
    except ValueError as exc:
        raise EnvironmentActivationEnvelopeError(
            "previous environment readiness must be below QWQ_OUTPUT_ROOT"
        ) from exc
    if (
        relative.parts[:5] != expected_parts
        or len(relative.parts) != 7
        or relative.name != "release-readiness.json"
        or any(
            output_root.joinpath(*relative.parts[:index]).is_symlink()
            for index in range(1, len(relative.parts) + 1)
        )
    ):
        raise EnvironmentActivationEnvelopeError(
            "previous environment readiness path is not canonical"
        )
    receipt = _read_json(readiness_path)
    try:
        assert_valid(
            receipt,
            "release",
            "environment_release_readiness",
            label="previous environment readiness",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise EnvironmentActivationEnvelopeError(str(exc)) from exc
    activation = receipt.get("activationEnvelope")
    if not isinstance(activation, Mapping):
        raise EnvironmentActivationEnvelopeError(
            "previous environment activation envelope is missing"
        )
    verdict = evaluate_release_readiness_receipt(receipt)
    if not verdict.publishable or verdict.phase != "research":
        raise EnvironmentActivationEnvelopeError(
            "previous environment readiness is not a publishable research receipt"
        )
    if (
        receipt.get("verificationChecksum") != _checksum(receipt)
        or receipt.get("activationEnvelopeDigest") != document_digest(activation)
        or receipt.get("environment") != previous
        or receipt.get("releaseId") != release_id
        or receipt.get("manifestDigest") != manifest_digest
        or receipt.get("sourceIdentitySetDigest") != source_identity_set_digest
        or activation.get("environment") != previous
        or activation.get("releaseId") != release_id
        or activation.get("manifestDigest") != manifest_digest
        or activation.get("sourceIdentitySetDigest")
        != source_identity_set_digest
    ):
        raise EnvironmentActivationEnvelopeError(
            "previous environment activation identity drift"
        )
    return {
        "environment": previous,
        "readinessRef": relative.as_posix(),
        "readinessDigest": file_digest(readiness_path),
        "verifyRunId": str(receipt.get("verifyRunId") or ""),
        "activationEnvelopeDigest": str(
            receipt.get("activationEnvelopeDigest") or ""
        ),
        "appUatEnvelopeDigest": str(receipt.get("appUatEnvelopeDigest") or ""),
    }


def previous_environment_activation_for_release(
    *,
    header: Mapping[str, Any],
    environment: str,
    readiness_path: Path | None,
    release_id: str,
    manifest_digest: str,
    output_root: Path,
) -> dict[str, str] | None:
    """Apply milestone-only predecessor semantics to one release header."""

    if header.get("milestone") is None:
        if readiness_path is not None:
            raise EnvironmentActivationEnvelopeError(
                "non-milestone readiness cannot bind an environment predecessor"
            )
        return None
    return load_previous_environment_activation(
        environment=environment,
        readiness_path=readiness_path,
        release_id=release_id,
        manifest_digest=manifest_digest,
        source_identity_set_digest=str(
            header.get("sourceIdentitySetDigest") or ""
        ),
        output_root=output_root,
    )


__all__ = [
    "load_previous_environment_activation",
    "previous_environment_activation_for_release",
]
